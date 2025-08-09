const std = @import("std");
const http = @import("http.zig");

const expect = std.testing.expect;

var num_active_threads: u8 = 0;

pub export fn run_server(server_addr: [*:0]const u8, server_port: u16, routes_to_register: [*]http.Route, num_routes: u16) void {
    std.debug.print("run_server called\n", .{});
    var gpa = std.heap.DebugAllocator(.{}).init;
    const allocator = gpa.allocator();

    var arena = std.heap.ArenaAllocator.init(allocator);
    defer {
        std.debug.print("running areana.deinit()\n", .{});
        arena.deinit();
    }

    const arena_allocator = arena.allocator();

    const routes = registerRoutes(arena_allocator, routes_to_register, num_routes) catch |err| {
        std.debug.print("error registering routes: {any}\n", .{err});
        @panic("_run_server");
    };
    defer {
        std.debug.print("running arena_allocator.free()\n", .{});
        arena_allocator.free(routes);
    }

    runServer(allocator, server_addr, server_port, routes, 0) catch |err| {
        std.debug.print("error running server: {any}\n", .{err});
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

    std.debug.print("Running server on {any}\n", .{server.listen_address});

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
                // std.debug.print("waiting...\n", .{});
                std.time.sleep(10 * std.time.ns_per_ms);
                continue;
            } else {
                std.debug.print("Connection error: {}\n", .{err});
                continue;
            }
        };

        std.debug.print("Handling new connection\n", .{});

        // Give each new connection a new thread.
        // TODO: This should probably be a threadpool
        const thread_result = std.Thread.spawn(
            .{},
            handleConnection,
            .{ allocator, connection, routes },
        );
        std.debug.print("Thread spawned\n", .{});
        if (thread_result) |thread| {
            std.debug.print("Thread detached\n", .{});
            thread.detach();
        } else |err| {
            std.debug.print("Failed to spawn thread: {any}\n", .{err});
        }

        std.debug.print("thread count: {d}\n", .{num_active_threads});
    }

    std.debug.print("Shutting down...\n", .{});
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
    std.debug.print("handler: {}, {}\n", .{ request, response });
    std.debug.print("header name: {s}\n", .{request.headers[1].name});

    response.status = 200;
    response.body = "hi there";
}

fn testHandlerForbidden(request: *http.Request, response: *http.Response) callconv(.C) void {
    std.debug.print("handler: {}, {}\n", .{ request, response });
    std.debug.print("header name: {s}\n", .{request.headers[1].name});

    response.status = 403;
}

fn handleConnection(allocator: std.mem.Allocator, connection: std.net.Server.Connection, routes: []Route) void {
    num_active_threads += 1;
    defer num_active_threads -= 1;
    std.debug.print("starting handleConnection()\n", .{});
    var read_buffer: [1024]u8 = undefined;
    var http_server = std.http.Server.init(connection, &read_buffer);

    // Continue trying to receive requests on the same connection
    while (true) {
        var request = http_server.receiveHead() catch |err| switch (err) {
            error.HttpConnectionClosing => return,
            // error.HttpHeadersOversize => handleResponseWith431(),
            else => {
                std.debug.print("Request error in handle connection: {any}\n", .{err});
                return;
            },
        };
        handleRequest(allocator, routes, &request) catch |err| {
            std.debug.print("Error handling request in handleConnection(): {any}\n", .{err});
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

        std.debug.print("zig: Route registered: {s} -> {any}\n", .{ routes[i].path, routes[i].handler });
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
    std.debug.print("Handling request for {s}\n", .{request.head.target});

    var res = http.Response{ .body = undefined, .content_length = 0, .content_type = null, .status = 0, .headers = &.{}, .num_headers = 0 };

    std.debug.print("server state: {s}\n", .{@tagName(request.server.state)});

    for (routes) |route| {
        std.debug.print("checking route: {s}\n", .{route.path});
        if (std.mem.eql(u8, route.path, request.head.target)) {
            std.debug.print("matched route: {s}\n", .{route.path});
            var read_body: bool = true;
            std.debug.print("server state: {s}\n", .{@tagName(request.server.state)});
            const request_reader: ?std.io.AnyReader = request.reader() catch |err| {
                std.debug.print("error requesting reader: {any}\n", .{err});
                read_body = false;
                return;
            };

            const content_length = request.head.content_length orelse 0;
            var body: []u8 = undefined;
            if (read_body) {
                body = try request_reader.?.readAllAlloc(allocator, content_length);
            }

            // Get the number of headers
            var header_iterator_counter = request.iterateHeaders();
            var num_headers: usize = 0;
            while (header_iterator_counter.next()) |header| {
                std.debug.print("request header: name: {s}, value: {s}\n", .{ header.name, header.value });
                num_headers += 1;
            }
            std.debug.print("server state post header iterate 1: {s}\n", .{@tagName(request.server.state)});

            const headers = try allocator.alloc(http.Header, num_headers);
            defer allocator.free(headers);
            std.debug.print("server state post headers: {s}\n", .{@tagName(request.server.state)});

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

            std.debug.print("server state post header iterate 2: {s}\n", .{@tagName(request.server.state)});

            const null_terminated_path = try allocator.dupeZ(u8, request.head.target);
            defer allocator.free(null_terminated_path);
            var req = http.Request{
                .path = null_terminated_path,
                .method = @tagName(request.head.method),
                .body = body.ptr,
                .content_length = content_length,
                .headers = headers.ptr,
                .num_headers = num_headers,
            };
            std.debug.print("ntp: {*}, {*}\n", .{ body.ptr, headers.ptr });

            std.debug.print("header name: {s}\n", .{headers[1].name});
            std.debug.print("server state pre handler: {s}\n", .{@tagName(request.server.state)});
            const handler = route.handler;

            handler(&req, &res);
            std.debug.print("route handling complete\n", .{});
            std.debug.print("server state post handler: {s}\n", .{@tagName(request.server.state)});

            break;
        }
        std.debug.print("server state outer loop: {s}\n", .{@tagName(request.server.state)});
    }

    if (res.status == 0) {
        std.debug.print("##### Not found#####\n", .{});
        try request.respond("404 Not Found\n", .{ .status = std.http.Status.not_found });
    }

    std.debug.print("server state: {s}\n", .{@tagName(request.server.state)});
    const status: std.http.Status = @enumFromInt(res.status);
    var body: []const u8 = "";
    body = std.mem.span(res.body);
    std.debug.print("response body: {s}\n", .{res.body});

    const header_list = try allocator.alloc(std.http.Header, res.num_headers);
    defer allocator.free(header_list);

    for (header_list, 0..) |*header, ii| {
        const c_header = res.headers[ii];
        header.name = std.mem.span(c_header.name);
        header.value = std.mem.span(c_header.value);
    }

    for (header_list) |header| {
        std.debug.print("response header name: {s}, value: {s}\n", .{ header.name, header.value });
    }

    std.debug.print("body: {s}\n", .{body});
    try request.respond(body, std.http.Server.Request.RespondOptions{
        .status = status,
        .extra_headers = header_list,
    });

    std.debug.print("Handled\n", .{});
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
