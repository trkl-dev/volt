const std = @import("std");
const router = @import("router.zig");

pub fn main() !void {
    const server_addr = "127.0.0.1";
    const server_port = 1234;

    const addr = std.net.Address.resolveIp(server_addr, server_port) catch |err| {
        std.debug.print("An error occurred while resolving the IP address: {}\n", .{err});
        return;
    };

    var server = try addr.listen(.{});

    router.run_server(&server);
}
