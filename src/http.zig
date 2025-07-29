pub const Request = extern struct {
    method: [*:0]const u8,
    path: [*:0]const u8,
    body: [*]const u8,
    body_len: usize,
    headers: [*]Header,
    num_headers: usize,
};

pub const Response = extern struct {
    body: ?[*:0]const u8,
    content_type: ?[*:0]const u8,
    status: c_int,
};

pub const Header = extern struct {
    key: [*:0]const u8,
    value: [*:0]const u8,
};

pub const HandlerFn = *const fn (*Request, *Response) callconv(.C) void;
