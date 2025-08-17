const std = @import("std");
const router = @import("volt.zig");

pub fn main() !void {
    _ = "127.0.0.1";
    _ = 1234;

    std.debug.print("hi there\n", .{});

    // router.run_server(server_addr, server_port);
}
