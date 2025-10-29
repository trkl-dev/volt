const std = @import("std");
const http = @import("http.zig");
const middleware = @import("middleware.zig");
const builtin = @import("builtin");

const Router = @import("router.zig").Router;
const Route = @import("router.zig").Route;
const expect = std.testing.expect;

const log = std.log.default;
const test_log = std.log.scoped(.zig_test);

var py_collect_garbage: ?http.GCFn = null;
var py_log_callback: ?http.LogFn = null;

pub const std_options: std.Options = .{
    .log_level = .debug,
    .logFn = pyLogger,
};

var no_logs = false;
var server_is_running = false;
/// For python to confirm that the server has completed startup, and is ready
/// to accept connections
pub export fn server_running() usize {
    if (server_is_running) {
        return 1;
    }
    return 0;
}

pub export fn run_server(
    server_addr: [*:0]const u8,
    server_port: u16,
    routes_to_register: [*]http.Route,
    num_routes: u16,
    garbage_collection_func: http.GCFn,
    log_callback_func: http.LogFn,
) void {
    // Must be set first so logging can proceed
    py_log_callback = log_callback_func;
    py_collect_garbage = garbage_collection_func;

    defer {
        should_exit = false;
        server_is_running = false;
    }

    const allocator = std.heap.smp_allocator;

    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();

    const arena_allocator = arena.allocator();

    if (std.posix.getenv("NO_LOGS") != null) {
        no_logs = true;
    }

    const routes = registerRoutes(arena_allocator, routes_to_register, num_routes) catch |err| {
        log.err("error registering routes: {any}", .{err});
        return;
    };

    var router = Router.init(arena_allocator, routes);

    runServer(allocator, server_addr, server_port, &router, &should_exit) catch |err| {
        log.err("error running server: {any}", .{err});
        return;
    };
}

fn runServer(
    allocator: std.mem.Allocator,
    server_addr: [*:0]const u8,
    server_port: u16,
    router: *Router,
    exit: *bool,
) !void {
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

    server_is_running = true;

    // Continue checking for new connections. New connections are given a separate thread to be handled in.
    // This thread will continue waiting for requests on the same connection until the connection is closed.
    while (!exit.*) {
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
        // TODO: This should probably be a threadpool, and the closure of threads handled properly
        const thread = std.Thread.spawn(
            .{
                .allocator = allocator,
            },
            handleConnection,
            .{ allocator, &connection, router },
        ) catch |err| {
            log.err("failed to spawn thread: {any}", .{err});
            continue;
        };
        thread.detach();
        log.debug("Thread spawned", .{});
    }

    log.info("Shutting down...", .{});
}

fn handleConnection(allocator: std.mem.Allocator, connection: *const std.net.Server.Connection, router: *Router) void {
    var recv_header: [4000]u8 = undefined;
    var send_header: [4000]u8 = undefined;
    var conn_reader = connection.stream.reader(&recv_header);
    var conn_writer = connection.stream.writer(&send_header);
    var http_server = std.http.Server.init(conn_reader.interface(), &conn_writer.interface);

    // Continue trying to receive requests on the same connection
    while (true) {
        var request = http_server.receiveHead() catch |err| switch (err) {
            error.HttpConnectionClosing => {
                log.debug("connection closing...", .{});
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
        const status = handleRequest(allocator, router, &request) catch |err| {
            log.err("Error calling handleRequest in handleConnection(): {}", .{err});
            if (@errorReturnTrace()) |trace| {
                std.debug.dumpStackTrace(trace.*);
            }
            // Using the state of .received_head to check whether the request has already been responded to
            if (request.server.reader.state != .received_head) {
                log.debug("not in .received_head state (state: {any}), no need to create response", .{request.server.reader.state});
                return;
            }
            log.err("request not already responded to, responding with 500", .{});
            request.respond("", .{ .status = .internal_server_error, .keep_alive = false }) catch |res_err| {
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
        routes[i].path = std.mem.span(routes_to_register[i].name);
        routes[i].handler = routes_to_register[i].handler;

        log.debug("zig: Route registered: {s} -> {any}", .{ routes[i].path, routes[i].handler });
    }

    return routes;
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

fn handleStaticRoute(request: *std.http.Server.Request) !std.http.Status {
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

    const mime_type = getMimeType(file_path);
    const status: std.http.Status = .ok;
    var send_buffer: [1024]u8 = undefined;
    var respond_options: std.http.Server.Request.RespondOptions = undefined;
    if (mime_type == null) {
        respond_options = .{
            .status = status,
        };
    } else {
        respond_options = .{
            .status = status,
            .extra_headers = &.{
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

fn handleRequest(allocator: std.mem.Allocator, router: *Router, request: *std.http.Server.Request) !std.http.Status {
    log.debug("Handling request for {s}", .{request.head.target});

    // CORS middleware will respond to request if allowed is false
    if (!try middleware.CORS.allowed(request)) {
        try request.respond("", .{ .status = .forbidden });
        return .forbidden;
    }

    // Static file serving
    if (std.mem.startsWith(u8, request.head.target, "/static/")) {
        const status = try handleStaticRoute(request);
        return status;
    }

    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();
    const arena_allocator = arena.allocator();

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

    const headers = try arena_allocator.alloc(http.Header, num_headers);

    var header_iterator = request.iterateHeaders();
    var index: usize = 0;
    while (header_iterator.next()) |header| {
        const header_name = try arena_allocator.dupeZ(u8, header.name);
        const header_value = try arena_allocator.dupeZ(u8, header.value);
        headers[index] = http.Header{ .name = header_name, .value = header_value };
        index += 1;
    }

    const path_nt = try arena_allocator.dupeZ(u8, head.target);

    const method = std.enums.tagName(std.http.Method, head.method);
    if (method == null) {
        // Unfortunately the original method string is lost, unless we re-parse the original request
        log.warn("bad method", .{});
        try request.respond("", .{ .status = .method_not_allowed });
        return .method_not_allowed;
    }

    const method_nt = try arena_allocator.dupeZ(u8, method.?);

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

    var response: *http.Response = undefined;
    const success = handler(&req, &response, &context);
    defer arena_allocator.free(response.headers);
    defer arena_allocator.destroy(response);
    log.debug("handler complete", .{});
    if (success == 0) {
        log.err("handler was unsuccessful", .{});
        return error.HandlerFailure;
    }

    // Run python garbage collection to ensure that any memory worked with is stable
    // TODO: This should really only occur in debug mode, or something like that
    if (py_collect_garbage != null) {
        py_collect_garbage.?();
    }

    log.debug("route handling complete", .{});

    std.debug.assert(response.headers.len > 0);
    try request.respond(response.body, std.http.Server.Request.RespondOptions{
        .status = response.status,
        .extra_headers = response.headers,
    });
    return response.status;
}

var should_exit = false;

export fn shutdown_server() void {
    log.info("shutting down server...", .{});
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

pub fn pyLogger(
    comptime level: std.log.Level,
    comptime scope: @Type(.enum_literal),
    comptime format: []const u8,
    args: anytype,
) void {
    // _ = scope;
    std.debug.assert(py_log_callback != null);

    var buffer: [200]u8 = undefined;
    var py_logger = PyLogger.init(level, &buffer);

    // Currently disabling logging when running in pytest. Seems to be race conditions allowing some logs to
    // get through during test runs when they shouldn't. This github issue seems related:
    // https://github.com/pytest-dev/pytest/issues/13693

    if (no_logs) {
        return;
    }

    switch (scope) {
        .default => {
            // omit the scope for the defau
            py_logger.writer.print(format, args) catch {
                std.debug.print("Write failed error, log message too long\n", .{});
            };
        },
        else => {
            py_logger.writer.print("(" ++ @tagName(scope) ++ ") " ++ format, args) catch {
                std.debug.print("Write failed error, log message too long\n", .{});
            };
        },
    }

    py_logger.writer.flush() catch {
        std.debug.print("Write failed error, log message too long\n", .{});
    };
}

const PyLogger = struct {
    log_level: std.log.Level,
    writer: std.io.Writer,

    pub fn init(log_level: std.log.Level, buffer: []u8) PyLogger {
        return .{
            .log_level = log_level,
            .writer = std.io.Writer{
                .buffer = buffer,
                .vtable = &vtable,
            },
        };
    }

    const vtable: std.io.Writer.VTable = .{
        .drain = PyLogger.drain,
    };

    fn pass_to_py_callback(self: *PyLogger, data: []const u8) void {
        std.debug.assert(py_log_callback != null);
        const level_int: i8 = switch (self.log_level) {
            .debug => 0,
            .info => 1,
            .warn => 2,
            .err => 3,
        };
        py_log_callback.?(data.ptr, data.len, level_int);
    }

    // Write the given slice to the buffer. If the buffer is too small for the slice, write to the buffer,
    // send on to callback, and reset buffer repeatedly until all data has been passed through the buffer.
    pub fn writeSliceToBuffer(self: *PyLogger, w: *std.io.Writer, slice: []const u8) std.io.Writer.Error!usize {
        var remaining = slice;
        var written: usize = 0;

        while (remaining.len > 0) {
            const available_space = w.buffer.len - w.end;
            const to_copy = @min(remaining.len, available_space);
            @memcpy(w.buffer[w.end .. w.end + to_copy], remaining[0..to_copy]);
            w.end += to_copy;
            written += to_copy;
            remaining = remaining[to_copy..];

            if (w.end == self.writer.buffer.len) {
                self.pass_to_py_callback(w.buffer[0..self.writer.end]);
                w.end = 0;
            }
        }

        return written;
    }

    // drain performs three main functions:
    // - empty the buffer of contents, passing on to callback
    // - move data from given slices into the buffer, passing on to the callback if the data is too large
    // - splat the last array in the data, 'splat' times, into the buffer
    pub fn drain(w: *std.io.Writer, data: []const []const u8, splat: usize) std.io.Writer.Error!usize {
        const self: *PyLogger = @fieldParentPtr("writer", w);

        std.debug.assert(data.len != 0);

        // Handle buffer
        if (w.end > 0) {
            // empty the buffer and reset end to 0, to signify buffer can be re-used.
            self.pass_to_py_callback(w.buffered());
            w.end = 0;
        }

        var total_written: usize = 0;

        // Handle data
        if (data.len >= 2) {
            for (data[0 .. data.len - 1]) |slice| {
                total_written += try self.writeSliceToBuffer(w, slice);
            }
        }

        // Handle splats
        if (data[data.len - 1].len > 0) {
            for (0..splat) |_| {
                const splat_slice = data[data.len - 1];
                total_written += try self.writeSliceToBuffer(w, splat_slice);
            }
        }
        return total_written;
    }
};
