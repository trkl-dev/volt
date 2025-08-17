const std = @import("std");
const http = @import("http.zig");

const logging_middleware_log = std.log.scoped(.zig_middleware);

pub const Logging = struct {
    start_time: i64,

    pub fn init() Logging {
        return Logging{
            .start_time = std.time.milliTimestamp(),
        };
    }

    pub fn post(self: Logging, path: []const u8, status: std.http.Status, method: std.http.Method) void {
        const elapsed_time: i64 = std.time.milliTimestamp() - self.start_time;

        logging_middleware_log.info("request: path={s}, method={s}, status={d} ({s}), duration={d}ms\n", .{
            path,
            @tagName(method),
            status,
            @tagName(status),
            elapsed_time,
        });
    }
};

pub const CORS = struct {
    // TODO: Redo this. Need to _actually_ do CORS properly
    pub fn allowed(request: *std.http.Server.Request) !bool {
        const valid_request = true;
        if (!valid_request) {
            try request.respond("CORS Failed\n", .{ .status = std.http.Status.forbidden });
            std.debug.print("CORS pre-processing failed: path={s}\n", .{request.head.target});
        }
        return valid_request;
    }
};
