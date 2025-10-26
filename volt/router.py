import ctypes
import gc
import logging
import signal
import threading
import time
from collections.abc import Callable
from http import HTTPMethod, HTTPStatus
from http import cookies as http_cookies
from types import FrameType
from typing import Literal, TypedDict, override
from urllib.parse import parse_qs

from . import zig_types as zt

zig_logger = logging.getLogger("volt.zig")
log = logging.getLogger("volt.py")


class Header:
    """
    Format Ref: https://developers.cloudflare.com/rules/transform/request-header-modification/reference/header-format/
    """

    name: str
    value: str

    def __init__(self, name: str, value: str) -> None:
        self.validate_name(name)
        self.validate_value(value)

        self.name = name
        self.value = value

    @classmethod
    def validate_name(cls, name: str):
        for char in name:
            if char in "-_":
                continue

            if char.isalnum():
                continue

            raise Exception(
                f"Header name is invalid. Invalid char: {char}. Valid characters are: a-z, A-Z, 0-9 - and _"
            )

    @classmethod
    def validate_value(cls, value: str) -> None:
        for char in value:
            if char in r"_ :;.,\/\"'?!(){}[]@<>=-+*#$&`|~^%":
                continue

            if char.isalnum():
                continue

            raise Exception(
                rf"Header name is invalid. Invalid char: {char}. Valid characters are: a-z, A-Z, 0-9, _ :;.,\/\"'?!(){{}}[]@<>=-+*#$&`|~^%"
            )

    @override
    def __repr__(self) -> str:
        return f"Header<{self.name}: {self.value}>"


type FormData = dict[str, list[str]]


class HttpRequest:
    method: HTTPMethod
    path: str
    body: str
    body_len: int
    form_data: FormData
    headers: list[Header]
    cookies: http_cookies.SimpleCookie
    query_params: dict[str, str]
    route_params: dict[str, str | int]
    hx_request: bool
    hx_fragment: str | None

    def __init__(
        self,
        method: str,
        path: str,
        body: str,
        body_len: int,
        form_data: FormData,
        headers: list[Header],
        cookies: http_cookies.SimpleCookie,
        query_params: dict[str, str],
        route_params: dict[str, str | int],
    ) -> None:
        self.method = HTTPMethod[method]
        self.path = path
        self.body = body
        self.body_len = body_len
        self.form_data = form_data
        self.headers = headers
        self.cookies = cookies
        self.query_params = query_params
        self.route_params = route_params
        self.hx_request = False
        self.hx_fragment = None


class HttpResponse:
    body: str
    content_type: str
    status: HTTPStatus
    headers: list[Header]
    cookies: http_cookies.SimpleCookie | None

    def __init__(
        self,
        body: str = "",
        content_type: str = "text/html",
        status: HTTPStatus = HTTPStatus.OK,
        headers: list[Header] | None = None,
        cookies: http_cookies.SimpleCookie | None = None,
    ) -> None:
        self.body = body
        self.content_type = content_type
        self.status = status

        self.headers = headers if headers is not None else []
        self.cookies = cookies


class Redirect(HttpResponse):
    """
    Redirect the browser to the location at 'route'.
    This is not htmx-aware at this point
    """

    def __init__(self, route: str) -> None:
        headers = [
            Header(name="Location", value=route),
        ]
        super().__init__(status=HTTPStatus.FOUND, headers=headers)


type Middleware = Callable[[HttpRequest, Handler], HttpResponse]
type Handler = Callable[[HttpRequest], HttpResponse]


# TODO: Move this out of middleware, could probably even be in Zig
def htmx_parse_request(request: HttpRequest):
    """Parse the provided request and update HTMX related attributes accordingly"""
    for header in request.headers:
        if header.name.lower() == "hx-request" and header.value.lower() == "true":
            request.hx_request = True

        if header.name.lower() == "hx-fragment":
            request.hx_fragment = header.value


def wrap_middleware(middleware: Middleware, handler: Handler) -> Handler:
    def wrapped(request: HttpRequest):
        return middleware(request, handler)

    return wrapped


def create_middleware_stack(handler: Handler, *middlewares: Middleware) -> Handler:
    for middleware in reversed(middlewares):
        handler = wrap_middleware(middleware, handler)
    return handler


middleware_list: list[Middleware] = []


def middleware(fn: Callable[[HttpRequest, Handler], HttpResponse]):
    middleware_list.append(fn)
    return None


path_list: list[bytes] = []


RouteRegister = TypedDict(
    "RouteRegister",
    {"path": bytes, "method": bytes, "handler": Callable[[HttpRequest], HttpResponse]},
)
routes: list[RouteRegister] = []


def route(path: str, method: str = "GET"):
    """Register a route handler on 'path'"""

    def decorator(
        handler_fn: Callable[[HttpRequest], HttpResponse],
    ) -> Callable[[zt.HttpRequestPtr, ctypes.c_void_p, ctypes.c_void_p], ctypes.c_int]:
        def request_handler(
            request_ptr: zt.HttpRequestPtr,
            response_ptr: ctypes.c_void_p,
            context_ptr: ctypes.c_void_p,
        ) -> int:
            try:
                log.debug("starting handler")
                req = request_ptr.contents

                # QUERY PARAMS HANDLING
                num_query_params: int = zt.lib.query_params_size(request_ptr)
                keys_array = (ctypes.c_char_p * num_query_params)()
                key_lengths_array = (ctypes.c_size_t * num_query_params)()
                num_keys = zt.lib.query_params_get_keys(
                    request_ptr, keys_array, key_lengths_array, num_query_params
                )

                query_params: dict[str, str] = {}
                for i in range(num_keys):
                    if keys_array[i]:
                        key_bytes = ctypes.string_at(
                            keys_array[i], key_lengths_array[i]
                        )
                        key = key_bytes.decode("utf-8")

                        value_out = ctypes.c_char_p()
                        size = zt.lib.query_params_get_value(
                            request_ptr, key_bytes, ctypes.byref(value_out)
                        )
                        # An empty value is actually valid I think. I.e. /search?query= would be size 0, but valid
                        # if size == 0:
                        #     raise Exception(f"Somehow we have a key: {key}, that can not be found")
                        value_bytes = ctypes.string_at(value_out, size)
                        value = value_bytes.decode("utf-8")

                        query_params[key] = value

                # ROUTE PARAMS HANDLING
                size: int = zt.lib.route_params_size(request_ptr)
                keys_array = (ctypes.c_char_p * size)()
                key_lengths_array = (ctypes.c_size_t * size)()
                num_keys = zt.lib.route_params_get_keys(
                    request_ptr, keys_array, key_lengths_array, size
                )

                route_params: dict[str, str | int] = {}
                for i in range(num_keys):
                    key_bytes = ctypes.string_at(keys_array[i], key_lengths_array[i])
                    key = key_bytes.decode("utf-8")

                    # This was originally using a Union ctype, but I think the memory layout between the ctypes.Union
                    # and the zig union may be different, causing some memory issues. Either that, or my understanding
                    # still needs some work. This works for now.
                    str_out = ctypes.c_char_p()
                    int_out = ctypes.c_int32()
                    tag_out = ctypes.c_int()

                    size = zt.lib.route_params_get_value(
                        request_ptr,
                        key_bytes,
                        ctypes.byref(int_out),
                        ctypes.byref(str_out),
                        ctypes.byref(tag_out),
                    )
                    if tag_out.value == -1:
                        raise Exception(
                            "Somehow we have a key: {key}, that can not be found"
                        )
                    elif tag_out.value == 0:
                        route_params[key] = int_out.value
                    elif tag_out.value == 1:
                        if size == 0:
                            raise Exception(
                                "String type route param with invalid size 0"
                            )
                        if str_out.value is None:
                            raise Exception("String type route param value is None")

                        str_bytes = ctypes.string_at(str_out.value, size)
                        route_params[key] = str_bytes.decode("utf-8")

                request_headers: list[Header] = []
                for i in range(req.num_headers):
                    request_headers.append(
                        Header(
                            req.headers[i].name.decode("utf-8"),
                            req.headers[i].value.decode("utf-8"),
                        )
                    )

                request_body = ctypes.string_at(req.body, req.body_len).decode("utf-8")
                log.debug(f"request body: {request_body}")

                request_cookies = http_cookies.SimpleCookie()
                form_data: dict[str, list[str]] = {}
                for header in request_headers:
                    if header.name.lower() == "cookie":
                        request_cookies.load(header.value)
                    if (
                        header.name.lower() == "content-type"
                        and header.value == "application/x-www-form-urlencoded"
                    ):
                        form_data = parse_qs(request_body)
                        log.debug(f"parsed form data: {form_data}")

                request_object = HttpRequest(
                    method=ctypes.string_at(req.method).decode("utf-8"),
                    path=ctypes.string_at(req.path).decode("utf-8"),
                    body=request_body,
                    body_len=req.body_len,
                    form_data=form_data,
                    headers=request_headers,
                    cookies=request_cookies,
                    query_params=query_params,
                    route_params=route_params,
                )

                htmx_parse_request(request_object)

                handler_with_middleware = create_middleware_stack(
                    handler_fn, *middleware_list
                )
                handler_response = handler_with_middleware(request_object)

                num_headers = len(handler_response.headers) + 1
                if handler_response.cookies is not None:
                    # Each cookie is a separate header
                    num_headers += len(handler_response.cookies.items())

                log.debug(f"Num headers: {num_headers}")
                header_array = (zt.Header * num_headers)()

                # set content-type as the next headers after the custom headers
                header_array[0].name = "content-type".encode("utf-8")
                header_array[0].value = handler_response.content_type.encode("utf-8")

                if len(handler_response.headers) != 0:
                    for i, header in enumerate(handler_response.headers, start=1):
                        header_array[i].name = header.name.encode("utf-8")
                        header_array[i].value = header.value.encode("utf-8")
                else:
                    log.debug("no custom headers in response")

                if handler_response.cookies is not None:
                    for i, cookie in enumerate(
                        handler_response.cookies.items(),
                        start=len(handler_response.headers) + 1,
                    ):
                        header_array[i].name = "Set-Cookie".encode("utf-8")
                        header_array[i].value = cookie[1].OutputString().encode("utf-8")
                else:
                    log.debug("no cookies in response")

                success: Literal[0, 1] = zt.lib.save_response(
                    context_ptr,
                    handler_response.body.encode("utf-8"),
                    len(handler_response.body.encode("utf-8")),
                    handler_response.status.value,
                    header_array,
                    num_headers,
                    response_ptr,
                )

                log.debug(header_array)

                if success == 0:
                    return 0

                log.debug("finished")
                return 1
            except Exception as e:
                log.error(f"Exception occurred: {e}")
                return 0

        cb = zt.CALLBACK(request_handler)
        p = path.encode("utf-8")
        log.info("registering_route: %s", p)
        path_list.append(p)  # Prevent GC of path
        routes.append(
            {
                "path": p,
                "method": method.encode("utf-8"),
                "handler": cb,
            }
        )
        return cb

    return decorator


@ctypes.PYFUNCTYPE(None)
def collect_garbage():
    log.debug("running garbage collection...")
    _ = gc.collect()
    log.debug("garbage collection complete.")


@ctypes.PYFUNCTYPE(None, ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t, ctypes.c_int)
def log_message(message_ptr: ctypes.c_char_p, message_len: int, level: int):
    message = ctypes.string_at(message_ptr, message_len).decode("utf-8")
    match level:
        case 0:
            zig_logger.debug(message)
        case 1:
            zig_logger.info(message)
        case 2:
            zig_logger.warning(message)
        case 3:
            zig_logger.error(message)
        case _:
            raise Exception(f"Unexpected level for log_message: {level}")


def _run_server(server_addr: str, server_port: int):
    # TODO: Check that server_port here is only u16
    def run():
        routes_array_type = zt.Route * len(routes)
        routes_array = routes_array_type()

        for i, r in enumerate(routes):
            routes_array[i].path = r["path"]
            routes_array[i].method = r["method"]
            routes_array[i].handler = r["handler"]

        log.info("calling zig run_server")
        zt.lib.run_server(
            server_addr.encode("utf-8"),
            server_port,
            routes_array,
            len(routes),
            collect_garbage,
            log_message,
        )

    return run


server_thread = None


def run_server(server_addr: str = "127.0.0.1", server_port: int = 1234):
    global server_thread
    server_thread = threading.Thread(target=_run_server(server_addr, server_port))
    server_thread.start()
    # Wait for server to start
    while not zt.lib.server_running():
        log.debug("waiting for server to be running...")
        time.sleep(0.1)
    log.debug("server running.")


def shutdown():
    global server_thread
    zt.lib.shutdown_server()
    if server_thread is not None:
        server_thread.join(timeout=3)
    while zt.lib.server_running():
        log.debug("waiting for server to stop running...")
        time.sleep(0.1)
    log.debug("server stopped.")


def handle_sigint(_signum: int, _frame: FrameType | None):
    log.warning("Caught ctrl+c - shutting down Zig server...")
    shutdown()


_ = signal.signal(signal.SIGINT, handle_sigint)
_ = signal.signal(signal.SIGTERM, handle_sigint)
