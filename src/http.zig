pub const Request = extern struct {
    method: [*:0]const u8,
    path: [*:0]const u8,
    body: [*]const u8,
    content_length: usize,
    headers: [*]Header,
    num_headers: usize,
};

pub const Response = extern struct {
    body: [*:0]const u8,
    content_length: usize,
    content_type: ?[*:0]const u8,
    status: c_int,
    headers: [*]Header,
    num_headers: usize,
};

pub const Header = extern struct {
    name: [*:0]const u8,
    value: [*:0]const u8,
};

pub const Route = extern struct {
    name: [*:0]const u8,
    handler: HandlerFn,
};

pub const HandlerFn = *const fn (*Request, *Response) callconv(.C) void;
