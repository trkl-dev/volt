const std = @import("std");
const http = @import("http.zig");
const middleware = @import("middleware.zig");

const expect = std.testing.expect;

const log = std.log.scoped(.zig);
const test_log = std.log.scoped(.zig_test);

var num_active_threads: u8 = 0;

pub export fn run_server(server_addr: [*:0]const u8, server_port: u16, routes_to_register: [*]http.Route, num_routes: u16) void {
    log.debug("run_server called", .{});
    var gpa = std.heap.DebugAllocator(.{}).init;
    const allocator = gpa.allocator();

    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();

    const arena_allocator = arena.allocator();

    const routes = registerRoutes(arena_allocator, routes_to_register, num_routes) catch |err| {
        log.err("error registering routes: {any}", .{err});
        @panic("_run_server");
    };
    defer arena_allocator.free(routes);

    runServer(allocator, server_addr, server_port, routes, 0) catch |err| {
        log.err("error running server: {any}", .{err});
        @panic("_run_server");
    };
}

/// stop_iter will stop the server after stop_iter iterations, unless stop_iter is 0. This is for testing,
/// so as to prevent blocking
fn runServer(
    allocator: std.mem.Allocator,
    server_addr: [*:0]const u8,
    server_port: u16,
    routes: []Route,
    stop_iter: u16,
) !void {
    std.debug.assert(routes.len > 0);

    const server_addr_slice = std.mem.span(server_addr);
    const addr = try std.net.Address.resolveIp(server_addr_slice, server_port);

    // reuse_address = true -> prevents TIME_WAIT on the socket
    // which would otherwise result in `AddressInUse` error on restart for ~30s
    // force_nonblocking = true -> server.accept() below is no longer a blocking call and
    // will return errors when there are no connections and would otherwise block
    var server = try addr.listen(std.net.Address.ListenOptions{
        // Non-default fields
        .reuse_address = true,
        .force_nonblocking = true,

        // Default fields
        .kernel_backlog = 128,
        .reuse_port = false,
    });
    defer server.deinit();

    log.info("Running server on {any}", .{server.listen_address});

    var num_iters: u16 = 0;
    // Continue checking for new connections. New connections are given a separate thread to be handled in.
    // This thread will continue waiting for requests on the same connection until the connection is closed.
    while (!should_exit) {
        if (stop_iter > 0 and num_iters >= stop_iter) {
            break;
        }
        if (stop_iter > 0) {
            num_iters += 1;
        }
        const connection = server.accept() catch |err| {
            if (err == error.WouldBlock) {
                std.time.sleep(10 * std.time.ns_per_ms);
                continue;
            } else {
                log.err("Connection error: {}", .{err});
                continue;
            }
        };

        log.debug("Handling new connection", .{});

        // Give each new connection a new thread.
        // TODO: This should probably be a threadpool
        const thread_result = std.Thread.spawn(
            .{},
            handleConnection,
            .{ allocator, connection, routes },
        );
        log.debug("Thread spawned", .{});
        if (thread_result) |thread| {
            thread.detach();
        } else |err| {
            log.err("Failed to spawn thread: {any}", .{err});
            continue;
        }
    }

    log.info("Shutting down...", .{});
}

test runServer {
    const allocator = std.testing.allocator;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const arena_allocator = arena.allocator();

    const r = [_]http.Route{
        .{
            .name = "/blog",
            .handler = testHandlerSuccessful,
        },
        .{
            .name = "/home",
            .handler = testHandlerForbidden,
        },
    };
    const routes_to_register: [*]const http.Route = &r;

    const routes = try registerRoutes(arena_allocator, routes_to_register, 2);
    defer arena_allocator.free(routes);

    const thread = try std.Thread.spawn(
        std.Thread.SpawnConfig{
            .stack_size = std.Thread.SpawnConfig.default_stack_size,
            .allocator = null,
        },
        runServer,
        .{ allocator, "127.0.0.1", 1234, routes, 0 },
    );
    _ = thread;

    var client = std.http.Client{ .allocator = allocator };
    defer client.deinit();

    var header_buffer: [16 * 1024]u8 = undefined;
    const homeResponse = try client.fetch(.{ .location = .{ .url = "http://127.0.0.1:1234/home" }, .keep_alive = true, .server_header_buffer = &header_buffer });
    try std.testing.expectEqual(std.http.Status.forbidden, homeResponse.status);

    const blogResponse = try client.fetch(.{ .location = .{ .url = "http://127.0.0.1:1234/blog" }, .keep_alive = true, .server_header_buffer = &header_buffer });
    try std.testing.expectEqual(std.http.Status.ok, blogResponse.status);

    shutdown_server();
}

fn testHandlerSuccessful(request: *http.Request, response: *http.Response) callconv(.C) void {
    test_log.debug("handler: {}, {}", .{ request, response });
    test_log.debug("header name: {s}", .{request.headers[1].name});

    response.status = 200;
    response.body = "hi there";
}

fn testHandlerForbidden(request: *http.Request, response: *http.Response) callconv(.C) void {
    test_log.debug("handler: {}, {}", .{ request, response });
    test_log.debug("header name: {s}", .{request.headers[1].name});

    response.status = 403;
}

fn handleConnection(allocator: std.mem.Allocator, connection: std.net.Server.Connection, routes: []Route) void {
    num_active_threads += 1;
    defer num_active_threads -= 1;

    var read_buffer: [1024]u8 = undefined;
    var http_server = std.http.Server.init(connection, &read_buffer);

    // Continue trying to receive requests on the same connection
    while (true) {
        var request = http_server.receiveHead() catch |err| switch (err) {
            error.HttpConnectionClosing => return,
            // error.HttpHeadersOversize => handleResponseWith431(),
            else => {
                log.err("Request error in handle connection: {any}", .{err});
                return;
            },
        };
        handleRequest(allocator, routes, &request) catch |err| {
            log.err("Error handling request in handleConnection(): {any}", .{err});
            return;
        };
    }
}

/// Requires an arena allocator so route paths and routes themselves can be freed together.
/// Caller owns the memory
fn registerRoutes(arena: std.mem.Allocator, routes_to_register: [*]const http.Route, num_routes: u16) ![]Route {
    const routes = try arena.alloc(Route, num_routes);

    var i: usize = 0;
    while (i < num_routes) : (i += 1) {
        routes[i].path = try arena.dupeZ(u8, std.mem.span(routes_to_register[i].name));
        routes[i].handler = routes_to_register[i].handler;

        log.debug("zig: Route registered: {s} -> {any}", .{ routes[i].path, routes[i].handler });
    }

    return routes;
}

test registerRoutes {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const arena_allocator = arena.allocator();

    const r = [_]http.Route{
        .{
            .name = "/blog",
            .handler = testHandlerSuccessful,
        },
        .{
            .name = "/home",
            .handler = testHandlerSuccessful,
        },
    };
    const routes_to_register: [*]const http.Route = &r;

    const routes = try registerRoutes(arena_allocator, routes_to_register, 2);
    defer arena_allocator.free(routes);

    try std.testing.expectEqual(2, routes.len);
    try std.testing.expectEqualSlices(u8, "/blog", routes[0].path);
    try std.testing.expectEqualSlices(u8, "/home", routes[1].path);
}

fn handleRequest(allocator: std.mem.Allocator, routes: []Route, request: *std.http.Server.Request) !void {
    log.debug("Handling request for {s}", .{request.head.target});

    var res = http.Response{ .body = undefined, .content_length = 0, .content_type = null, .status = 0, .headers = &.{}, .num_headers = 0 };

    const logging_middleware = middleware.Logging.init();

    // CORS middleware will respond to request if allowed is false
    if (!try middleware.CORS.allowed(request)) {
        return;
    }

    var route: ?Route = null;
    for (routes) |r| {
        if (!std.mem.eql(u8, r.path, request.head.target)) {
            continue;
        }
        route = r;
    }

    if (route == null) {
        log.warn("##### Not found #####", .{});
        try request.respond("404 Not Found", .{ .status = std.http.Status.not_found });
        return;
    }

    log.debug("matched route: {s}", .{route.?.path});
    var read_body: bool = true;
    const request_reader: ?std.io.AnyReader = request.reader() catch |err| {
        log.err("error requesting reader: {any}", .{err});
        read_body = false;
        return;
    };

    const content_length = request.head.content_length orelse 0;
    var request_body: []u8 = undefined;
    if (read_body) {
        request_body = try request_reader.?.readAllAlloc(allocator, content_length);
    }

    // Get the number of headers
    var header_iterator_counter = request.iterateHeaders();
    var num_headers: usize = 0;
    while (header_iterator_counter.next()) |header| {
        log.debug("request header: name: {s}, value: {s}", .{ header.name, header.value });
        num_headers += 1;
    }

    const headers = try allocator.alloc(http.Header, num_headers);
    defer allocator.free(headers);

    var header_iterator = request.iterateHeaders();
    var index: usize = 0;
    while (header_iterator.next()) |header| {
        const header_name = try allocator.dupeZ(u8, header.name);
        const header_value = try allocator.dupeZ(u8, header.value);
        headers[index] = http.Header{ .name = header_name, .value = header_value };
        index += 1;
    }

    defer {
        for (headers) |header| {
            // .free wants a slice, so we convert the null terminated strings to slices for freeing
            allocator.free(std.mem.span(header.name));
            allocator.free(std.mem.span(header.value));
        }
    }

    const null_terminated_path = try allocator.dupeZ(u8, request.head.target);
    defer allocator.free(null_terminated_path);
    var req = http.Request{
        .path = null_terminated_path,
        .method = @tagName(request.head.method),
        .body = request_body.ptr,
        .content_length = content_length,
        .headers = headers.ptr,
        .num_headers = num_headers,
    };

    const handler = route.?.handler;

    handler(&req, &res);

    log.debug("route handling complete", .{});

    const status: std.http.Status = @enumFromInt(res.status);
    var response_body: []const u8 = "";
    response_body = std.mem.span(res.body);
    log.debug("response body: {s}", .{response_body});

    const header_list = try allocator.alloc(std.http.Header, res.num_headers);
    defer allocator.free(header_list);

    for (header_list, 0..) |*header, ii| {
        const c_header = res.headers[ii];
        header.name = std.mem.span(c_header.name);
        header.value = std.mem.span(c_header.value);
    }

    for (header_list) |header| {
        log.debug("response header name: {s}, value: {s}", .{ header.name, header.value });
    }

    try request.respond(response_body, std.http.Server.Request.RespondOptions{
        .status = status,
        .extra_headers = header_list,
    });
    logging_middleware.post(request.head.target, status, request.head.method);
}

const Route = struct {
    path: []const u8,
    handler: http.HandlerFn,

    pub fn format(
        self: Route,
        comptime fmt: []const u8,
        options: std.fmt.FormatOptions,
        writer: anytype,
    ) !void {
        _ = fmt;
        _ = options;

        try writer.print("{s} ({})", .{
            self.path, self.handler,
        });
    }
};

var should_exit = false;

export fn shutdown_server() void {
    std.debug.assert(!should_exit);
    should_exit = true;
}

test shutdown_server {
    // Ensure should_exit is set back to false after testing
    should_exit = false;
    defer should_exit = false;

    // Ensure shutdown_server sets should_exit from false -> true
    try std.testing.expect(!should_exit);
    shutdown_server();
    try std.testing.expect(should_exit);
}
