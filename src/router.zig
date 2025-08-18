const http = @import("http.zig");
const std = @import("std");

const log = std.log.scoped(.zig);

pub const Router = struct {
    routes: []Route,
    arena_allocator: std.mem.Allocator,

    pub fn init(arena_allocator: std.mem.Allocator, routes: []Route) Router {
        return Router{
            .arena_allocator = arena_allocator,
            .routes = routes,
        };
    }

    pub fn match(self: *Router, method: std.http.Method, path: []const u8) !?MatchedRoute {
        for (self.routes) |route| {
            if (method != route.method) {
                continue;
            }

            const params = self.matchPath(route.path, path) catch |err| {
                log.err("Error matching route: {s}", .{route});
                return err;
            } orelse continue;

            return MatchedRoute{
                .route = route,
                .allocator = self.arena_allocator,
                .query_params = params.query_params,
                .route_params = params.route_params,
            };
        }
        return null;
    }

    fn matchPath(self: *Router, template: []const u8, actual: []const u8) !?Params {
        log.debug("matching path", .{});
        var route_params = std.StringHashMap(http.RouteParamValue).init(self.arena_allocator);
        errdefer route_params.deinit();

        var template_parts = std.mem.splitScalar(u8, template, '/');
        var actual_query_parts = std.mem.splitScalar(u8, actual, '?');
        var actual_parts = std.mem.splitScalar(u8, actual_query_parts.first(), '/');

        // Route parameter processing
        while (actual_parts.next()) |actual_part| {
            const template_part = template_parts.next() orelse {
                // Hit the end of the actual parts before the end of template parts
                route_params.deinit();
                return null;
            };

            // Handle route params: /{username:str} or /{id:int}, etc
            if (template_part.len >= 3 and template_part[0] == '{' and template_part[template_part.len - 1] == '}') {
                const route_param = parse_route_params(template_part, actual_part) orelse {
                    route_params.deinit();
                    return null;
                };
                try route_params.put(route_param.name, route_param.value);
            } else {
                if (!std.mem.eql(u8, actual_part, template_part)) {
                    route_params.deinit();
                    return null;
                }
            }
        }

        // Query parameter processing
        const query_params_str = actual_query_parts.next();
        var query_params = try parse_query_params(self.arena_allocator, query_params_str);
        var qp_iterator = query_params.iterator();
        while (qp_iterator.next()) |entry| {
            log.debug("qp: {s}", .{entry.key_ptr.*});
        }

        // If there are still remaining template segments, then we have not matched on an entire path,
        // so we return null
        if (actual_parts.next() != null) {
            route_params.deinit();
            query_params.deinit();
            return null;
        }

        return Params{
            .route_params = route_params,
            .query_params = query_params,
        };
    }
};
pub const Route = struct {
    method: std.http.Method,
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

pub const Params = struct {
    route_params: std.StringHashMap(http.RouteParamValue),
    query_params: std.StringHashMap([]const u8),
};

pub const MatchedRoute = struct {
    allocator: std.mem.Allocator,
    route: Route,
    route_params: std.StringHashMap(http.RouteParamValue),
    query_params: std.StringHashMap([]const u8),

    pub fn deinit(self: *MatchedRoute) void {
        self.route_params.deinit();
        self.query_params.deinit();
    }

    pub fn format(
        self: MatchedRoute,
        comptime fmt: []const u8,
        options: std.fmt.FormatOptions,
        writer: anytype,
    ) !void {
        _ = fmt;
        _ = options;

        try writer.print("{s}\n - route_params: \n", .{self.route.path});
        var route_params_iter = self.route_params.iterator();
        while (route_params_iter.next()) |route_param| {
            switch (route_param.value_ptr.*) {
                .int => try writer.print("\t - {s}={d}\n", .{ route_param.key_ptr.*, route_param.value_ptr.int }),
                .str => try writer.print("\t - {s}={s}\n", .{ route_param.key_ptr.*, route_param.value_ptr.str }),
            }
        }

        try writer.print(" - query_params: \n", .{});
        var query_params_iter = self.query_params.iterator();
        while (query_params_iter.next()) |query_param| {
            try writer.print("\t - {s}={s}\n", .{ query_param.key_ptr.*, query_param.value_ptr.* });
        }
    }
};

/// Parse a given route parameter as per a given template string of the form:
/// {param_name:param_type} where param_type can be either int or str
fn parse_route_params(template_param: []const u8, actual_param: []const u8) ?http.RouteParam {
    std.debug.assert(template_param[0] == '{');
    std.debug.assert(template_param[template_param.len - 1] == '}');

    // Strip surrounding "{" and "}"
    const param_def = template_param[1 .. template_param.len - 1];

    var param_parts = std.mem.splitScalar(u8, param_def, ':');
    const param_name = param_parts.first();

    const param_type_str = param_parts.next() orelse return null;
    log.debug("param type str: {s}", .{param_type_str});
    const param_type = std.meta.stringToEnum(http.ParamType, param_type_str) orelse return null;
    log.debug("param type: {any}", .{param_type});
    switch (param_type) {
        .str => {
            return http.RouteParam{ .name = param_name, .value = http.RouteParamValue{ .str = actual_param } };
        },
        .int => {
            const int_actual_part = std.fmt.parseInt(i32, actual_param, 10) catch |err| {
                log.debug("Error converting {s} into an integer, failing route match. Err: {any}", .{ actual_param, err });
                return null;
            };
            return http.RouteParam{ .name = param_name, .value = http.RouteParamValue{ .int = int_actual_part } };
        },
    }
}

///Parse a raw query parameter string, and return a hashmap of extracted keys and values
fn parse_query_params(allocator: std.mem.Allocator, query_params_raw: ?[]const u8) !std.StringHashMap([]const u8) {
    var query_params = std.StringHashMap([]const u8).init(allocator);
    errdefer query_params.deinit();

    // We accept a null value to simplify things and ensure there is always a query params hash map, even
    // if there are no query params
    if (query_params_raw == null) {
        return query_params;
    }

    // Only this first "?" in query params are valid. All others are considered data.
    // Hence, we call `.next()` once, only.
    var query_parts = std.mem.splitScalar(u8, query_params_raw.?, '&');
    while (query_parts.next()) |query_part| {
        var single_param_parts = std.mem.splitScalar(u8, query_part, '=');
        // Allegedly example.com/path?=value1 is valid. Note the lack of a param name. For now, that case is not.
        const param_name = single_param_parts.first();
        const param_value = single_param_parts.next() orelse continue;

        // Multiple params of the same name are valid, and we collapse them into a comma separated list.
        if (query_params.get(param_name)) |existing_value| {
            const combined_value = try std.fmt.allocPrint(allocator, "{s},{s}", .{ existing_value, param_value });
            try query_params.put(param_name, combined_value);
            continue;
        }

        try query_params.put(param_name, param_value);
    }

    return query_params;
}

test parse_query_params {
    const allocator = std.testing.allocator;
    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();
    const arena_allocator = arena.allocator();

    // Basic params
    var query_params_1 = try parse_query_params(arena_allocator, "param1=value1&param2=value2");

    try std.testing.expectEqual(2, query_params_1.count());
    try std.testing.expectEqualStrings(query_params_1.get("param1").?, "value1");
    try std.testing.expectEqualStrings(query_params_1.get("param2").?, "value2");

    // Duplicate params
    var query_params_2 = try parse_query_params(arena_allocator, "param1=value1&param1=value2&param2=value3");

    try std.testing.expectEqual(2, query_params_2.count());
    try std.testing.expectEqualStrings(query_params_2.get("param1").?, "value1,value2");
    try std.testing.expectEqualStrings(query_params_2.get("param2").?, "value3");

    // URL encoded params
    var query_params_3 = try parse_query_params(arena_allocator, "param1=value1%20value2&param2=value3%26value4");

    try std.testing.expectEqual(2, query_params_3.count());
    try std.testing.expectEqualStrings(query_params_3.get("param1").?, "value1%20value2");
    try std.testing.expectEqualStrings(query_params_3.get("param2").?, "value3%26value4");

    // Plus sign encoding for spaces
    var query_params_4 = try parse_query_params(arena_allocator, "param1=value1+value2&param2=value3");

    try std.testing.expectEqual(2, query_params_4.count());
    try std.testing.expectEqualStrings(query_params_4.get("param1").?, "value1+value2");
    try std.testing.expectEqualStrings(query_params_4.get("param2").?, "value3");

    // Question mark in query
    var query_params_5 = try parse_query_params(arena_allocator, "param1=value1?value2&param2=value3");

    try std.testing.expectEqual(2, query_params_5.count());
    try std.testing.expectEqualStrings(query_params_5.get("param1").?, "value1?value2");
    try std.testing.expectEqualStrings(query_params_5.get("param2").?, "value3");
}

pub fn getRoute(routes: []Route, route: []const u8) ?Route {
    for (routes) |r| {
        if (!std.mem.eql(u8, r.path, route)) {
            continue;
        }
        return r;
    }
    return null;
}

fn testHandlerSuccessful(request: *http.Request, response: *http.Response) callconv(.C) void {
    _ = request;
    response.status = 200;
    response.body = "hi there";
}

const TestCase = struct {
    path: []const u8,
    method: std.http.Method,
    expected: ?[]const u8,
};

test "match_get_general" {
    const allocator = std.testing.allocator;
    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();
    const arena_allocator = arena.allocator();

    var routes = [_]Route{
        Route{
            .method = .GET,
            .path = "home",
            .handler = testHandlerSuccessful,
        },
        Route{
            .method = .GET,
            .path = "blogs",
            .handler = testHandlerSuccessful,
        },
        Route{
            .method = .GET,
            .path = "blogs/{id:int}",
            .handler = testHandlerSuccessful,
        },
        Route{
            .method = .GET,
            .path = "blogs/name/{name:str}",
            .handler = testHandlerSuccessful,
        },
        Route{
            .method = .GET,
            .path = "blogs/{id:int}/details",
            .handler = testHandlerSuccessful,
        },
    };

    var router = Router.init(arena_allocator, &routes);

    const test_cases = [_]TestCase{
        .{
            .path = "blogs/23/details?filter=yes",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },
        .{
            .path = "blogs/something/name",
            .method = .GET,
            .expected = null,
        },
        .{
            .path = "blogs/23/details?aslkdjaslfkjasfdlkjha",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },
        .{
            .path = "blogs/23/details?param=",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },
        .{
            .path = "blogs/23/details?",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },
        .{
            .path = "blogs/23/details",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },
        .{
            .path = "blogs",
            .method = .GET,
            .expected = "blogs",
        },
        .{
            .path = "blogs/12",
            .method = .GET,
            .expected = "blogs/{id:int}",
        },
        .{
            .path = "blogssss",
            .method = .GET,
            .expected = null,
        },
        .{
            .path = "somethingelse",
            .method = .GET,
            .expected = null,
        },
        .{
            .path = "somethingelse/23/details",
            .method = .GET,
            .expected = null,
        },
        // Query param edge cases
        // Multiple parameters
        .{
            .path = "blogs/23/details?filter=yes&sort=date&limit=10",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },

        // Duplicate parameters
        .{
            .path = "blogs/23/details?tag=tech&tag=programming",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },

        // URL encoded characters
        .{
            .path = "blogs/23/details?search=hello%20world&category=tech%26dev",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },

        // Plus sign encoding for spaces
        .{
            .path = "blogs/23/details?search=hello+world",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },

        // Question mark in query value
        .{
            .path = "blogs/23/details?query=what?happened",
            .method = .GET,
            .expected = "blogs/{id:int}/details",
        },
    };

    for (test_cases) |test_case| {
        var matched_route = try router.match(test_case.method, test_case.path);
        if (matched_route == null) {
            try std.testing.expect(test_case.expected == null);
            continue;
        }
        std.testing.expect(test_case.expected != null) catch |err| {
            std.debug.print("test_case.path: {s}\nmatched_route.path: {s}\n", .{ test_case.path, matched_route.?.route.path });
            return err;
        };
        defer matched_route.?.deinit();
        try std.testing.expectEqualStrings(test_case.expected.?, matched_route.?.route.path);
    }
}

test "match_multiple_route" {
    const allocator = std.testing.allocator;
    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();
    const arena_allocator = arena.allocator();

    var routes = [_]Route{
        Route{
            .method = .GET,
            .path = "blogs",
            .handler = testHandlerSuccessful,
        },
        Route{
            .method = .GET,
            .path = "blogs/{name:str}",
            .handler = testHandlerSuccessful,
        },
        Route{
            .method = .GET,
            .path = "blogs/{name:str}/details",
            .handler = testHandlerSuccessful,
        },
    };

    var router = Router.init(arena_allocator, &routes);

    const test_cases = [_]TestCase{
        .{
            .path = "blogs/something/details",
            .method = .GET,
            .expected = "blogs/{name:str}/details",
        },
        .{
            .path = "blogs/something",
            .method = .GET,
            .expected = "blogs/{name:str}",
        },
        .{
            .path = "blogs",
            .method = .GET,
            .expected = "blogs",
        },
    };

    for (test_cases) |test_case| {
        var matched_route = try router.match(test_case.method, test_case.path);
        if (matched_route == null) {
            try std.testing.expect(test_case.expected == null);
            continue;
        }
        std.testing.expect(test_case.expected != null) catch |err| {
            std.debug.print("test_case.path: {s}\nmatched_route.path: {s}\n", .{ test_case.path, matched_route.?.route.path });
            return err;
        };
        defer matched_route.?.deinit();
        try std.testing.expectEqualStrings(test_case.expected.?, matched_route.?.route.path);
    }
}

// regression?
// localhost:1234/home?hi=there&param2=value2&v=p
test "match_get_qp" {
    const allocator = std.testing.allocator;
    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();
    const arena_allocator = arena.allocator();

    var routes = [_]Route{
        Route{
            .method = .GET,
            .path = "home",
            .handler = testHandlerSuccessful,
        },
    };

    var router = Router.init(arena_allocator, &routes);

    var matched_route = try router.match(.GET, "home?hi=there&param2=value2&v=p");
    try std.testing.expect(matched_route != null);
    defer matched_route.?.deinit();
    try std.testing.expectEqual(3, matched_route.?.query_params.count());
    // try std.testing.expectEqualStrings(test_case.expected.?, matched_route.?.route.path);
}
