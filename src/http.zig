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

pub const Response = extern struct {
    body: [*:0]const u8,
    content_length: usize,
    content_type: ?[*:0]const u8,
    status: c_int,
    headers: [*]Header,
    num_headers: usize,
};

pub const Header = extern struct {
    name: [*:0]const u8,
    value: [*:0]const u8,
};

pub const Route = extern struct {
    name: [*:0]const u8,
    method: [*:0]const u8,
    handler: HandlerFn,
};

pub const HandlerFn = *const fn (*Request, *Response) callconv(.C) void;
