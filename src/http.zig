const std = @import("std");

const log = std.log.scoped(.zig);

// Don't love these being in this file
pub const ParamType = enum {
    int,
    str,
};

pub const RouteParam = struct {
    name: []const u8,
    value: RouteParamValue,
};

pub const RouteParamValue = union(ParamType) {
    int: i32,
    str: []const u8,
};

pub const Request = extern struct {
    method: [*:0]const u8,
    path: [*:0]const u8,
    body: [*]const u8, // Why isn't this null terminated?
    content_length: usize,
    headers: [*]Header,
    num_headers: usize,
    query_params: *std.StringHashMap([]const u8),
    route_params: *std.StringHashMap(RouteParamValue),
};

export fn route_params_size(request: *Request) usize {
    const size = request.route_params.count();
    return size;
}

// Get value by key, returning the length of the value if found, else 0
export fn route_params_get_value(request: *Request, key: [*:0]const u8, value_out: *RouteParamValue, tag_out: *c_int) usize {
    const key_slice = std.mem.span(key);

    if (request.route_params.get(key_slice)) |value| {
        value_out.* = value;
        return switch (value) {
            .int => {
                tag_out.* = 0;
                return 0;
            },
            .str => |s| {
                tag_out.* = 1;
                return s.len;
            },
        };
    }

    return 0; // Not found
}

export fn route_params_get_keys(request: *Request, keys_array: [*][*:0]const u8, key_lengths: [*]usize, max_keys: usize) usize {
    var count: usize = 0;
    var iterator = request.route_params.iterator();

    while (iterator.next()) |entry| {
        if (count >= max_keys) break;
        // log.debug("key: {s}", .{entry.value_ptr.*});
        keys_array[count] = @ptrCast(entry.key_ptr.ptr);
        key_lengths[count] = entry.key_ptr.len;
        count += 1;
    }

    return count;
}

export fn query_params_size(request: *Request) usize {
    const size = request.query_params.count();
    return size;
}

// Get value by key, returning the length of the value if found, else 0
export fn query_params_get_value(request: *Request, key: [*:0]const u8, value_out: *[*]const u8) usize {
    const key_slice = std.mem.span(key);

    if (request.query_params.get(key_slice)) |value| {
        value_out.* = value.ptr;
        return value.len; // Found
    }

    return 0; // Not found
}

export fn query_params_get_keys(request: *Request, keys_array: [*][*:0]const u8, key_lengths: [*]usize, max_keys: usize) usize {
    var count: usize = 0;
    var iterator = request.query_params.iterator();

    while (iterator.next()) |entry| {
        if (count >= max_keys) break;
        keys_array[count] = @ptrCast(entry.key_ptr.ptr);
        key_lengths[count] = entry.key_ptr.len;
        count += 1;
    }

    return count;
}

pub const Header = extern struct {
    name: [*:0]const u8,
    value: [*:0]const u8,
};

pub const Route = extern struct {
    name: [*:0]const u8,
    method: [*:0]const u8,
    handler: HandlerFn,
};

pub const Response = struct {
    body: []const u8,
    content_length: usize,
    content_type: []const u8,
    status: std.http.Status,
    headers: []std.http.Header,
    num_headers: usize,
};

pub const HandlerFn = *const fn (*Request, *Context) callconv(.c) ?*Response;

/// Callback function for forcing python to collect garbage.
pub const GCFn = *const fn () callconv(.c) void;

pub const Context = struct {
    allocator: std.mem.Allocator,
};

export fn save_response(
    ctx_ptr: *anyopaque,
    body: [*:0]const u8,
    content_length: usize,
    status: c_int,
    headers: [*]Header,
    num_headers: usize,
    response_ptr: **anyopaque,
) usize {
    log.debug("saving response...", .{});
    const ctx = @as(*Context, @ptrCast(@alignCast(ctx_ptr)));
    var response = ctx.allocator.create(Response) catch |err| {
        log.err("error allocating response: {any}", .{err});
        return 0;
    };
    response.body = std.mem.span(body);
    response.content_length = content_length;
    response.status = @enumFromInt(status);

    const header_list = ctx.allocator.alloc(std.http.Header, num_headers) catch |err| {
        log.err("error allocating {d} headers: {any}", .{ num_headers, err });
        return 0;
    };

    for (header_list, 0..) |*header, i| {
        header.name = std.mem.span(headers[i].name);
        header.value = std.mem.span(headers[i].value);
    }
    response.headers = header_list;

    response_ptr.* = response;
    log.debug("response saved", .{});
    return 1;
}
