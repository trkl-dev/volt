const std = @import("std");
const http = @import("http.zig");
const middleware = @import("middleware.zig");
const builtin = @import("builtin");

const Router = @import("router.zig").Router;
const Route = @import("router.zig").Route;
const expect = std.testing.expect;

const log = std.log.scoped(.zig);
const test_log = std.log.scoped(.zig_test);

var py_collect_garbage: http.GCFn = undefined;

pub export fn run_server(server_addr: [*:0]const u8, server_port: u16, routes_to_register: [*]http.Route, num_routes: u16, garbage_collection_func: http.GCFn) void {
    log.debug("run_server called", .{});
    var gpa = std.heap.DebugAllocator(.{}).init;
    const allocator = gpa.allocator();

    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();

    const arena_allocator = arena.allocator();

    const routes = registerRoutes(arena_allocator, routes_to_register, num_routes) catch |err| {
        log.err("error registering routes: {any}", .{err});
        return;
    };

    py_collect_garbage = garbage_collection_func;

    runServer(allocator, server_addr, server_port, routes, 0, &should_exit) catch |err| {
        log.err("error running server: {any}", .{err});
        return;
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
    exit: *bool,
) !void {
    std.debug.assert(routes.len > 0);

    const server_addr_slice = std.mem.span(server_addr);
    const addr = try std.net.Address.resolveIp(server_addr_slice, server_port);

    // reuse_address = true -> prevents TIME_WAIT on the socket
    // which would otherwise result in `AddressInUse` error on restart for ~30s
    // force_nonblocking = true -> server.accept() below is no longer a blocking call and
    // will return errors when there are no connections and would otherwise block
    var server: std.net.Server = undefined;

    while (true) {
        server = addr.listen(std.net.Address.ListenOptions{
            // Non-default fields
            .reuse_address = true, // TODO: CHANGE THIS BACK TO false!
            .force_nonblocking = true,

            // Default fields
            .kernel_backlog = 128,
        }) catch |err| switch (err) {
            error.AddressInUse => {
                log.warn("address in use. waiting...", .{});
                std.Thread.sleep(3 * std.time.ns_per_s);
                continue;
            },
            else => return err,
        };
        break;
    }

    defer {
        log.debug("deinitialising server...", .{});
        server.deinit();
        log.debug("complete.", .{});
    }

    log.info("Running server on {f}", .{server.listen_address});

    var num_iters: u16 = 0;
    // Continue checking for new connections. New connections are given a separate thread to be handled in.
    // This thread will continue waiting for requests on the same connection until the connection is closed.
    while (!exit.*) {
        if (stop_iter > 0 and num_iters >= stop_iter) {
            break;
        }
        if (stop_iter > 0) {
            num_iters += 1;
        }
        const connection = server.accept() catch |err| {
            if (err == error.WouldBlock) {
                std.Thread.sleep(10 * std.time.ns_per_ms);
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

/// Function to wrap runServer for use in threads, since error returning functions can't be used
/// as thread functions. Panics on err, which is fine, since this is used for testing only
fn runServerWithErrorHandler(
    allocator: std.mem.Allocator,
    server_addr: [*:0]const u8,
    server_port: u16,
    routes: []Route,
    stop_iter: u16,
    exit: *bool,
) void {
    runServer(
        allocator,
        server_addr,
        server_port,
        routes,
        stop_iter,
        exit,
    ) catch |err| {
        log.err("error running server: {any}", .{err});
        @panic("error running server in runServerWithErrorHandler");
    };
}

pub fn thandler(request: *http.Request, response: *http.Response) callconv(.c) void {
    response.status = 200;
    const body = request.body[0..request.content_length];
    std.testing.expectEqualStrings("this is some POST content", body) catch |err| {
        log.err("error comparing strings: {any}", .{err});
        @panic("err");
    };
    response.body = "a response body";
}

test runServer {
    const allocator = std.testing.allocator;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const arena_allocator = arena.allocator();

    const r = [_]http.Route{
        .{
            .name = "/blog",
            .method = "GET",
            .handler = testHandlerSuccessful,
        },
        .{
            .name = "/home",
            .method = "GET",
            .handler = testHandlerForbidden,
        },
        .{
            .name = "/content",
            .method = "POST",
            .handler = thandler,
        },
    };
    const routes_to_register: [*]const http.Route = &r;

    const routes = try registerRoutes(arena_allocator, routes_to_register, r.len);

    const thread = try std.Thread.spawn(
        std.Thread.SpawnConfig{
            .stack_size = std.Thread.SpawnConfig.default_stack_size,
            .allocator = null,
        },
        runServerWithErrorHandler, // Can't have an error returning function used as a thread function
        .{ allocator, "127.0.0.1", 1235, routes, 0, &should_exit }, // different port to regular
    );
    defer {
        shutdown_server();
        thread.join();
    }

    var client = std.http.Client{ .allocator = allocator };
    defer client.deinit();

    const homeResponse = try client.fetch(
        .{
            .location = .{ .url = "http://127.0.0.1:1235/home" },
            .keep_alive = true,
        },
    );
    std.testing.expectEqual(std.http.Status.forbidden, homeResponse.status) catch |err| {
        std.debug.print("url: http://127.0.0.1:1235/home\n", .{});
        return err;
    };

    const blogResponse = try client.fetch(
        .{
            .location = .{ .url = "http://127.0.0.1:1235/blog" },
            .keep_alive = true,
        },
    );
    std.testing.expectEqual(std.http.Status.ok, blogResponse.status) catch |err| {
        std.debug.print("url: http://127.0.0.1:1235/blog\n", .{});
        return err;
    };

    var postResponseBody: [1000]u8 = undefined;
    var responseBodyWriter = std.io.Writer.fixed(&postResponseBody);
    const postResponse = try client.fetch(
        .{
            .response_writer = &responseBodyWriter,
            .method = .POST,
            .payload = "this is some POST content",

            .location = .{ .url = "http://127.0.0.1:1235/content" },
            .keep_alive = true,
        },
    );
    std.testing.expectEqual(std.http.Status.ok, postResponse.status) catch |err| {
        std.debug.print("url: http://127.0.0.1:1235/content\n", .{});
        return err;
    };
    try std.testing.expectEqualStrings("a response body", postResponseBody[0..responseBodyWriter.end]);
}

fn testHandlerSuccessful(request: *http.Request, response: *http.Response) callconv(.c) void {
    test_log.debug("handler: {}, {}", .{ request, response });
    test_log.debug("header name: {s}", .{request.headers[1].name});

    response.status = 200;
    response.body = "hi there";
    response.content_length = 8;
}

fn testHandlerForbidden(request: *http.Request, response: *http.Response) callconv(.c) void {
    test_log.debug("handler: {}, {}", .{ request, response });
    test_log.debug("header name: {s}", .{request.headers[1].name});

    response.status = 403;
}

fn handleConnection(allocator: std.mem.Allocator, connection: std.net.Server.Connection, routes: []Route) void {
    var recv_header: [4000]u8 = undefined;
    var send_header: [4000]u8 = undefined;
    var conn_reader = connection.stream.reader(&recv_header);
    var conn_writer = connection.stream.writer(&send_header);
    var http_server = std.http.Server.init(conn_reader.interface(), &conn_writer.interface);

    // Continue trying to receive requests on the same connection
    while (true) {
        var request = http_server.receiveHead() catch |err| switch (err) {
            error.HttpConnectionClosing => {
                log.debug("Connection closing.", .{});
                return;
            },
            // ReadFailed is returned for numerous errors, with the actual error on conn_reader.file_reader.err
            error.ReadFailed => {
                switch (conn_reader.file_reader.err.?) {
                    // error.WouldBlock is returned on MacOS, according to stdlib docs -> #std.posix.readv
                    // since Non Blocking mode seems to be the default. This is returned and we continue to
                    // receiveHead() on the connection while this is returned, or exit out if the connection is closed.
                    // TODO: Look into Non Blocking mode and whether that should be enabled, and how this differs per OS.
                    error.WouldBlock => {
                        continue;
                    },
                    else => {
                        log.err("Unexpected error when ReadFailed: {any}, {any}", .{ err, conn_reader.file_reader.err });
                        if (@errorReturnTrace()) |trace| {
                            std.debug.dumpStackTrace(trace.*);
                        }
                        // TODO: Look into whether this should be a return or a continue
                        continue;
                    },
                }
            },
            else => {
                log.err("Request error in handle connection: {any}", .{err});
                if (@errorReturnTrace()) |trace| {
                    std.debug.dumpStackTrace(trace.*);
                }
                return;
            },
        };
        log.debug("Request received on connection.", .{});

        // Capture the head, as the memory will become invalidated as part of handling the request
        const head = request.head;

        const logging_middleware = middleware.Logging.init();
        const status = handleRequest(allocator, routes, &request) catch |err| {
            log.err("Error calling handleRequest in handleConnection(): {}", .{err});
            if (@errorReturnTrace()) |trace| {
                std.debug.dumpStackTrace(trace.*);
            }
            // Using the state of .received_head to check whether the request has already been responded to
            if (request.server.reader.state != .received_head) {
                log.debug("not in .received_head state, no need to create response", .{});
                return;
            }
            log.err("request not already responded to, responding with 500", .{});
            request.respond("", .{ .status = .internal_server_error }) catch |res_err| {
                log.err("Error trying to respond to request with internal_server_error. Server state: {any}, err: {any}", .{ request.server.reader.state, res_err });
                return;
            };
            return;
        };

        logging_middleware.after(head.target, status, head.method);
    }
}

/// Requires an arena allocator so route paths and routes themselves can be freed together.
/// Caller owns the memory
fn registerRoutes(arena: std.mem.Allocator, routes_to_register: [*]const http.Route, num_routes: u16) ![]Route {
    const routes = try arena.alloc(Route, num_routes);

    var i: usize = 0;
    while (i < num_routes) : (i += 1) {
        const method = std.meta.stringToEnum(std.http.Method, std.mem.span(routes_to_register[i].method));
        if (method == null) {
            if (!builtin.is_test) {
                log.err("Could not parse method: {s}", .{std.mem.span(routes_to_register[i].method)});
            }
            return error.BadMethod;
        }
        routes[i].method = method.?;
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
            .method = "GET",
            .handler = testHandlerSuccessful,
        },
        .{
            .name = "/home",
            .method = "GET",
            .handler = testHandlerSuccessful,
        },
    };
    const routes_to_register: [*]const http.Route = &r;

    const routes = try registerRoutes(arena_allocator, routes_to_register, 2);

    try std.testing.expectEqual(2, routes.len);
    try std.testing.expectEqualSlices(u8, "/blog", routes[0].path);
    try std.testing.expectEqualSlices(u8, "/home", routes[1].path);
}

test "registerRoutes with Error" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const arena_allocator = arena.allocator();

    const r = [_]http.Route{
        .{
            .name = "/blog",
            .method = "GET",
            .handler = testHandlerSuccessful,
        },
        .{
            .name = "/home",
            .method = "NOTAREALMETHOD",
            .handler = testHandlerSuccessful,
        },
    };
    const routes_to_register: [*]const http.Route = &r;

    try std.testing.expectError(error.BadMethod, registerRoutes(arena_allocator, routes_to_register, 2));
}

const mime_type_map = std.StaticStringMap([]const u8).initComptime(.{
    .{ ".html", "text/html" },
    .{ ".css", "text/css" },
    .{ ".js", "text/javascript" },
    .{ ".png", "image/png" },
    .{ ".jpg", "image/jpeg" },
    .{ ".jpeg", "image/jpeg" },
    .{ ".gif", "image/gif" },
    .{ ".ico", "image/x-icon" },
    .{ ".svg", "image/svg+xml" },
    .{ ".woff", "font/woff" },
    .{ ".woff2", "font/woff2" },
    .{ ".ttf", "font/ttf" },
    .{ ".otf", "font/otf" },
});
fn getMimeType(file_path: []const u8) ?[]const u8 {
    if (std.mem.lastIndexOfScalar(u8, file_path, '.')) |dot_index| {
        const extension = file_path[dot_index..];
        return mime_type_map.get(extension);
    }

    return null;
}

test getMimeType {
    try std.testing.expectEqual("image/jpeg", getMimeType("file.jpeg"));
    try std.testing.expectEqual("image/jpeg", getMimeType("jpg.file.jpg"));
    try std.testing.expectEqual("font/woff2", getMimeType("something....font.woff2"));
    try std.testing.expectEqual("text/javascript", getMimeType("scripts with a space.js"));

    try std.testing.expectEqual(null, getMimeType("not_a_mime_type.txt"));
    try std.testing.expectEqual(null, getMimeType("no extension"));
}

fn isPathSafe(path: []const u8) bool {
    return std.mem.indexOf(u8, path, "..") == null;
}

test isPathSafe {
    try std.testing.expect(isPathSafe("..") == false);
    try std.testing.expect(isPathSafe("../somepath.js") == false);
    try std.testing.expect(isPathSafe("file/../something/here.js") == false);
    try std.testing.expect(isPathSafe("file/static/something/..") == false);

    try std.testing.expect(isPathSafe("file/static/something/here.js") == true);
}

fn handleStaticRoute(allocator: std.mem.Allocator, request: *std.http.Server.Request) !std.http.Status {
    log.debug("running handleStaticRoute", .{});

    // Build full file path
    const file_path = request.head.target;

    if (!isPathSafe(file_path)) {
        try request.respond("", .{ .status = std.http.Status.forbidden });
        return .forbidden;
    }

    // Strip leading '/' and open file
    const file = std.fs.cwd().openFile(file_path[1..], .{}) catch |err| switch (err) {
        error.FileNotFound => {
            log.warn("Static file not found: {s}", .{file_path});
            try request.respond("", .{ .status = .not_found });
            return .not_found;
        },
        else => return err,
    };
    defer file.close();

    const file_size = try file.getEndPos();
    const content_length = try std.fmt.allocPrint(allocator, "{d}", .{file_size});

    const mime_type = getMimeType(file_path);
    const status: std.http.Status = .ok;
    var send_buffer: [1024]u8 = undefined;
    var respond_options: std.http.Server.Request.RespondOptions = undefined;
    if (mime_type == null) {
        respond_options = .{
            .status = status,
            .extra_headers = &.{
                .{ .name = "content-length", .value = content_length },
            },
        };
    } else {
        respond_options = .{
            .status = status,
            .extra_headers = &.{
                .{ .name = "content-length", .value = content_length },
                .{ .name = "content-type", .value = mime_type.? },
            },
        };
    }

    var response = try request.respondStreaming(
        &send_buffer,
        .{
            .content_length = file_size,
            .respond_options = respond_options,
        },
    );
    defer response.end() catch |err| {
        log.err("Error while responding with static content: {any}.", .{err});
    };

    var body_buffer: [8192]u8 = undefined;

    var file_reader = file.reader(&body_buffer);

    while (true) {
        const bytes_read = file_reader.read(&body_buffer) catch |err| switch (err) {
            error.EndOfStream => break,
            else => {
                return err;
            },
        };
        if (bytes_read == 0) break;

        try response.writer.writeAll(body_buffer[0..bytes_read]);
        try response.flush();
    }
    return status;
}

fn handleRequest(allocator: std.mem.Allocator, routes: []Route, request: *std.http.Server.Request) !std.http.Status {
    log.debug("Handling request for {s}", .{request.head.target});

    // CORS middleware will respond to request if allowed is false
    if (!try middleware.CORS.allowed(request)) {
        try request.respond("", .{ .status = .forbidden });
        return .forbidden;
    }

    // Static file serving
    if (std.mem.startsWith(u8, request.head.target, "/static/")) {
        const status = try handleStaticRoute(allocator, request);
        return status;
    }

    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();
    const arena_allocator = arena.allocator();

    var router = Router.init(arena_allocator, routes);
    var matched_route = try router.match(request.head.method, request.head.target);
    // const route = routing.getRoute(routes, request.head.target);
    if (matched_route == null) {
        try request.respond("", .{ .status = .not_found });
        return .not_found;
    }

    log.debug("matched route: {s}", .{matched_route.?.route.path});
    const head = request.head;

    const content_length = head.content_length orelse 0;
    std.log.debug("content_length: {d}", .{content_length});

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

    const path_nt = try allocator.dupeZ(u8, head.target);
    defer allocator.free(path_nt);

    const method = std.enums.tagName(std.http.Method, head.method);
    if (method == null) {
        // Unfortunately the original method string is lost, unless we re-parse the original request
        log.warn("bad method", .{});
        try request.respond("", .{ .status = .method_not_allowed });
        return .method_not_allowed;
    }

    const method_nt = try allocator.dupeZ(u8, method.?);
    defer allocator.free(method_nt);

    // Do this last as it invalidates `request.head`
    var buffer: [8000]u8 = undefined;
    const request_reader = request.readerExpectNone(&buffer);

    var request_body: []u8 = undefined;
    if (content_length > 0) {
        request_body = try request_reader.readAlloc(arena_allocator, content_length);
    } else {
        request_body = &[_]u8{};
    }
    var req = http.Request{
        .path = path_nt,
        .method = method_nt,
        .body = request_body.ptr,
        .content_length = content_length,
        .headers = headers.ptr,
        .num_headers = num_headers,
        .query_params = &matched_route.?.query_params,
        .route_params = &matched_route.?.route_params,
    };

    const handler = matched_route.?.route.handler;

    var context = http.Context{
        .allocator = arena_allocator,
    };

    const res = handler(&req, &context);
    if (res == null) {
        return error.NullResponse;
    }
    const response = res.?;

    // Run python garbage collection to ensure that any memory worked with is stable
    // TODO: This should really only occur in debug mode, or something like that
    py_collect_garbage();

    log.debug("route handling complete", .{});

    try request.respond(response.body, std.http.Server.Request.RespondOptions{
        .status = response.status,
        .extra_headers = response.headers,
    });
    return response.status;
}

// const Route = struct {
//     path: []const u8,
//     handler: http.HandlerFn,
//
//     pub fn format(
//         self: Route,
//         comptime fmt: []const u8,
//         options: std.fmt.FormatOptions,
//         writer: anytype,
//     ) !void {
//         _ = fmt;
//         _ = options;
//
//         try writer.print("{s} ({})", .{
//             self.path, self.handler,
//         });
//     }
// };

var should_exit = false;

export fn shutdown_server() void {
    log.info("shutting down server...", .{});
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
