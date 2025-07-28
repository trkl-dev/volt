const std = @import("std");
const router = @import("router.zig");

pub fn main() !void {
    const server_addr = "127.0.0.1";
    const server_port = 1234;

    router.run_server(server_addr, server_port);
}
