const http = @import("http.zig");
const std = @import("std");

/// Potential, complex route:
/// https://something:port/blogs/<pk:int>/details?query_param=here
/// to consider
/// - trailing slash
/// - query params
/// - route/path parameters
///
/// should the registered routes already be split? probably, no point doing it every time
/// trie structure?
/// split the route by '/'
/// ['blogs', '<pk:int>', 'details' OR 'details?...' depending on trailing slash]
pub const Route = struct {
    method: []const u8,
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
    query_params: std.StringHashMap([]const u8),
    route_params: std.StringHashMap([]const u8),
};

pub const MatchedRoute = struct {
    route: Route,
    params: Params,
};

pub const Router = struct {
    routes: []Route,
    allocator: std.mem.Allocator, // Should this just be an arena?

    pub fn match(self: *Router, method: []const u8, path: []const u8) !?MatchedRoute {
        for (self.routes) |route| {
            if (!std.mem.eql(u8, route.method, method)) {
                continue;
            }

            if (try self.matchPath(route.path, path)) |params| {
                return MatchedRoute{
                    .route = route,
                    .query_params = params.query_params,
                    .route_params = params.route_params,
                };
            }
        }
        return null;
    }

    const ParamType = enum {
        str,
        int,
    };

    const RouteParam = union(ParamType) {
        int: i32,
        str: []const u8,
    };

    pub fn matchPath(self: *Router, template: []const u8, actual: []const u8) !void {
        var query_params = std.StringArrayHashMap([]const u8).init(self.allocator);
        var route_params = std.StringHashMap(RouteParam).init(self.allocator);

        var template_parts = std.mem.splitScalar(u8, template, "/");
        var actual_parts = std.mem.splitScalar(u8, template, "/");

        while (template_parts.next()) |template_part| {
            const actual_part = actual_parts.next() orelse {
                // Hit the end of the actual parts before the end of template parts
                query_params.deinit();
                route_params.deinit();
                return null;
            };

            // Params: /{username:str} or /{id:int}, etc
            if (template_part.len >= 3 and template_part[0] == '{' and template_part[template_part.len - 1] == '}') {
                const param_def = template_part[1 .. template_part.len - 1];
                const param_parts = std.mem.splitScalar(u8, param_def, ":");
                const param_name = param_parts.first();
                const param_type_str = param_parts.next();
                const param_type = std.meta.stringToEnum(ParamType, param_type_str) orelse @panic(std.fmt.bufPrint("unexpected parameter type: {s}", .{param_type_str}));
                // @unionInit
                const p = std.meta.unin
                switch (param_type) {
                    .str => {
                        route_params.put(param_name, RouteParam{ .str = actual_part }) catch unreachable;
                    },
                    .int => {
                        const int_actual_part = std.fmt.parseInt(i32, actual_part, 10);
                        route_params.put(param_name, RouteParam{ .int = int_actual_part }) catch unreachable;
                    },
                }
            }
        }
    }
};

pub fn getRoute(routes: []Route, route: []const u8) ?Route {
    for (routes) |r| {
        if (!std.mem.eql(u8, r.path, route)) {
            continue;
        }
        return r;
    }
    return null;
}
