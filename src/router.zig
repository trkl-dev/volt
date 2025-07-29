const std = @import("std");
const http = @import("http.zig");

var should_exit = false;

// pub const HandlerFn = *const fn () callconv(.C) [*:0]const u8;

const Route = struct {
    path: []const u8,
    handler: http.HandlerFn,
};

var routes: [10]Route = undefined;
var route_count: usize = 0;

/// Register a route
/// ctypes.c_char_p from python are ALLEGEDLY null terminated, so we can [*:0].
export fn register_route(path: [*:0]const u8, handler: http.HandlerFn) void {
    if (route_count >= 10) return;

    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    const allocator = gpa.allocator();

    const path_slice = std.mem.span(path);
    const copied_path = allocator.alloc(u8, path_slice.len) catch {
        std.log.err("Failed to allocate for path", .{});
        return;
    };
    std.mem.copyForwards(u8, copied_path, path_slice);

    routes[route_count] = Route{
        .path = copied_path,
        .handler = handler,
    };

    std.debug.print("route registered: {s}\n", .{routes[route_count].path});

    route_count += 1;
}

/// Match a route and return handler_id, or -1
fn match_route(path: []const u8) i32 {
    var i: usize = 0;
    while (i < route_count) : (i += 1) {
        if (std.mem.eql(u8, routes[i].path, path)) {
            return routes[i].handler_id;
        }
    }

    return -1;
}

export fn shutdown_server() void {
    should_exit = true;
}

pub export fn run_server(server_addr: [*:0]const u8, server_port: u16) void {
    const server_addr_slice = std.mem.span(server_addr);
    const addr = std.net.Address.resolveIp(server_addr_slice, server_port) catch |err| {
        std.debug.print("An error occurred while resolving the IP address: {}\n", .{err});
        return;
    };

    // reuse_address = true -> prevents TIME_WAIT on the socket
    // which would otherwise result in `AddressInUse` error on restart for ~30s
    // force_nonblocking = true -> server.accept() below is no longer a blocking call and
    // will return errors when there are no connections and would otherwise block
    var server = addr.listen(.{ .reuse_address = true, .force_nonblocking = true }) catch |err| {
        std.debug.print("An error occurred while listening on address: {}\n", .{err});
        return;
    };
    defer server.deinit();

    _run_server(&server) catch |err| {
        std.debug.print("error running server: {any}\n", .{err});
        @panic("_run_server");
    };
}

fn _run_server(server: *std.net.Server) !void {
    std.debug.print("Running server on {any}\n", .{server.listen_address});

    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    const allocator = gpa.allocator();

    while (!should_exit) {
        const connection = server.accept() catch |err| {
            if (err == error.WouldBlock) {
                std.time.sleep(10 * std.time.ns_per_ms);
                continue;
            } else {
                std.debug.print("Connection error: {}\n", .{err});
                continue;
            }
        };

        if (should_exit) {
            break;
        }
        defer connection.stream.close();

        var read_buffer: [1024]u8 = undefined;
        var http_server = std.http.Server.init(connection, &read_buffer);

        var request = http_server.receiveHead() catch |err| {
            std.debug.print("Could not read head: {}\n", .{err});
            continue;
        };

        handle_request(allocator, &request) catch |err| {
            std.debug.print("Could not handle request: {}", .{err});
            continue;
        };
    }

    std.debug.print("Shutting down...\n", .{});
}

fn handle_request(allocator: std.mem.Allocator, request: *std.http.Server.Request) !void {
    std.debug.print("Handling request for {s}\n", .{request.head.target});

    var res = http.Response{
        .body = null,
        .content_type = null,
        .status = 0,
    };

    var i: usize = 0;
    while (i < route_count) : (i += 1) {
        if (std.mem.eql(u8, routes[i].path, request.head.target)) {
            const request_reader = try request.reader();

            const content_length = request.head.content_length orelse 0;
            const body = try request_reader.readAllAlloc(allocator, content_length);

            // Get the number of headers
            var header_iterator_counter = request.iterateHeaders();
            var num_headers: usize = 0;
            while (header_iterator_counter.next()) |_| {
                num_headers += 1;
            }

            const headers = try allocator.alloc(http.Header, num_headers);

            var header_iterator = request.iterateHeaders();
            var index: usize = 0;
            while (header_iterator.next()) |header| {
                headers[index] = http.Header{ .key = try allocator.dupeZ(u8, header.name), .value = try allocator.dupeZ(u8, header.value) };
                index += 1;
            }

            const null_terminated_path = try allocator.dupeZ(u8, request.head.target);
            var req = http.Request{
                .path = null_terminated_path,
                .method = @tagName(request.head.method),
                .body = body.ptr,
                .body_len = content_length,
                .headers = headers.ptr,
                .num_headers = num_headers,
            };
            const handler = routes[i].handler;
            handler(&req, &res);
            std.debug.print("Response: {}", .{res.status});
        }
    }

    if (res.status == 0) {
        try request.respond("404 Not Found\n", .{ .status = std.http.Status.not_found });
    }

    const status: std.http.Status = @enumFromInt(res.status);
    var body: []const u8 = "";
    if (res.body != null) {
        body = std.mem.span(res.body.?);
    }

    try request.respond(body, std.http.Server.Request.RespondOptions{ .status = status });
}
