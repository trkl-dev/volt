import ctypes
import threading
import signal
import sys

from collections.abc import Callable
from typing import Any, Optional, TypedDict, List

from . import zig_types as zt


Header = TypedDict('Header', {'name': str, 'value': str})


class HttpRequest:
    method: str
    path: str
    body: str
    body_len: int
    headers: list[Header]
    query_params: dict[str, str]
    route_params: dict[str, str|int]
    hx_request: bool
    hx_fragment: str

    def __init__(self, method: str, path: str, body: str, body_len: int, headers: list[Header], query_params: dict[str, str], route_params: dict[str, str|int]) -> None:
        self.method = method
        self.path = path
        self.body = body
        self.body_len = body_len
        self.headers = headers
        self.query_params = query_params
        self.route_params = route_params
        self.hx_request = False
        self.hx_fragment = "content"


class HttpResponse:
    body: str
    content_type: str
    status: int
    headers: list[Header]

    def __init__(self, body: str = "", content_type: str = "text/plain", status: int = 200, headers: Optional[List[Header]] = None) -> None:
        self.body = body
        self.content_type = content_type
        self.status = status

        self.headers = []
        if headers is not None:
            self.headers = headers


type Middleware = Callable[[HttpRequest, Handler], HttpResponse]
type Handler = Callable[[HttpRequest], HttpResponse]


def wrap_middleware(middleware: Middleware, handler: Handler) -> Handler:
    def wrapped(request: HttpRequest):
        return middleware(request, handler)
    return wrapped


def create_middleware_stack(handler: Handler, *middlewares: Middleware) -> Handler:
    for middleware in reversed(middlewares):
        handler = wrap_middleware(middleware, handler)
    return handler


middleware_list: List[Middleware]= []


def middleware(fn: Callable[[HttpRequest, Handler], HttpResponse]):
    middleware_list.append(fn)
    return None


path_list: List[bytes] = []


RouteRegister = TypedDict('RouteRegister', {'path': bytes, 'method': bytes, 'handler': Callable[[HttpRequest], HttpResponse]})
routes: List[RouteRegister] = []


def c_encode_string(string: str) -> tuple[ctypes.c_char_p, int]:
    encoded = string.encode('utf-8')
    buffer = ctypes.create_string_buffer(encoded, len(encoded) + 1)
    return ctypes.cast(buffer, ctypes.c_char_p), len(encoded)


def route(path: str, method: str = "GET"):
    """Register a route handler on 'path'"""
    def decorator(handler_fn: Callable[[HttpRequest], HttpResponse]) -> Any:
        def request_handler(request_ptr: zt.HttpRequestPtr, response_ptr: zt.HttpResponsePtr):
            req = request_ptr.contents

            # QUERY PARAMS HANDLING
            size = zt.lib.query_params_size(request_ptr)
            keys_array = (ctypes.c_char_p * size)()
            key_lengths_array = (ctypes.c_size_t * size)()
            num_keys = zt.lib.query_params_get_keys(
                request_ptr,
                keys_array,
                key_lengths_array,
                size
            )
            
            # raise Exception()
            query_params = {}
            for i in range(num_keys):
                if keys_array[i]:
                    key_bytes = ctypes.string_at(keys_array[i], key_lengths_array[i])
                    key = key_bytes.decode('utf-8')

                    value_out = ctypes.c_char_p()
                    size = zt.lib.query_params_get_value(request_ptr, key_bytes, ctypes.byref(value_out))
                    if size == 0:
                        raise Exception(f"Somehow we have a key: {key}, that can not be found")
                    value_bytes = ctypes.string_at(value_out, size)
                    value = value_bytes.decode('utf-8')
                    
                    query_params[key] = value

            # ROUTE PARAMS HANDLING
            size = zt.lib.route_params_size(request_ptr)
            keys_array = (ctypes.c_char_p * size)()
            key_lengths_array = (ctypes.c_size_t * size)()
            num_keys = zt.lib.route_params_get_keys(
                request_ptr,
                keys_array,
                key_lengths_array,
                size
            )
            
            route_params = {}
            for i in range(num_keys):
                if keys_array[i]:
                    key_bytes = ctypes.string_at(keys_array[i], key_lengths_array[i])
                    key = key_bytes.decode('utf-8')

                    value_out = zt.RouteParamValue()
                    tag_out = ctypes.c_int()
                    size = zt.lib.route_params_get_value(request_ptr, key_bytes, ctypes.byref(value_out), ctypes.byref(tag_out))
                    if tag_out.value == -1:
                        raise Exception("Somehow we have a key: {key}, that can not be found")
                    elif tag_out.value == 0:
                        route_params[key] = value_out.int
                    elif tag_out.value == 1:
                        if size == 0:
                            raise Exception("String type route param with invalid size 0")
                        str_bytes = ctypes.string_at(value_out.str, size)
                        route_params[key] = str_bytes.decode('utf-8')
                    print(f"py: route param key: {key}, value: {route_params[key]}")

            request_headers = []
            for i in range(req.num_headers):
                request_headers.append({
                    "name": req.headers[i].name.decode('utf-8'),
                    "value": req.headers[i].value.decode('utf-8'),
                })

            request_object = HttpRequest(
                method=ctypes.string_at(req.method).decode('utf-8'),
                path=ctypes.string_at(req.path).decode('utf-8'),
                body=ctypes.string_at(req.body, req.body_len).decode('utf-8'),
                body_len=req.body_len,
                headers=request_headers,
                query_params=query_params,
                route_params=route_params,
            )

            handler_with_middleware = create_middleware_stack(handler_fn, *middleware_list)
            handler_response = handler_with_middleware(request_object)

            response = response_ptr.contents


            # NOTE: Was previously directly assigning response_body to response.body, rather than using string_buffer.
            # Something about this was allowing GC to cause issues with the response body not persisting, and being 
            # collected. Using string_buffer _seems_ to create an additional reference that otherwise would not exist,
            # which seems to have prevented GC. That being said, rigorous simulation testing on this, and other fields
            # to ensure GC is not still occurring at random is necessary. Ideally a better understanding in general too.
            # response.body = handler_response.body.encode('utf-8')
            response.body, response.content_length = c_encode_string(handler_response.body)

            # Content-Type parsing/handling
            response_content_type = handler_response.content_type.encode('utf-8')
            response_content_type_buffer = ctypes.create_string_buffer(response_content_type)

            response.content_type = ctypes.cast(response_content_type_buffer, ctypes.c_char_p)

            response.status = handler_response.status
            
            header_array_type = zt.Header * len(handler_response.headers)
            header_array = header_array_type()

            response.num_headers = len(handler_response.headers)
            for i, h in enumerate(handler_response.headers):
                header_array[i].name, _ = c_encode_string(h["name"])
                header_array[i].value, _ = c_encode_string(h["value"])

            response.headers = header_array

        cb = zt.CALLBACK(request_handler)
        p = path.encode('utf-8')
        print("py: registering_route: ", p)
        path_list.append(p)  # Prevent GC of path
        routes.append({
            'path': p,
            'method': method.encode('utf-8'),
            'handler': cb,
        })
        return cb
        
    return decorator


def _run_server(server_addr, server_port):
    # TODO: Check that server_port here is only u16
    def run():
        routes_array_type = zt.Route * len(routes)
        routes_array = routes_array_type()

        for i, r in enumerate(routes):
            routes_array[i].path = r["path"]
            routes_array[i].method = r["method"]
            routes_array[i].handler = r["handler"]
        
        print("py: calling zig run_server")
        zt.lib.run_server(server_addr.encode('utf-8'), server_port, routes_array, len(routes))

    return run


server_thread = None


def run_server(server_addr: str = "127.0.0.1", server_port: int = 1234):
    global server_thread
    server_thread = threading.Thread(target=_run_server(server_addr, server_port))
    server_thread.start()


def handle_sigint(signum, frame):
    global server_thread
    print("\nCaught ctrl+c - shutting down Zig server...")
    zt.lib.shutdown_server()
    if server_thread is not None:
        server_thread.join()
    sys.exit()


signal.signal(signal.SIGINT, handle_sigint)


class Redirect(HttpResponse):
    """
    Redirect the browser to the location at 'route'.
    This is not htmx-aware at this point
    """
    def __init__(self, route: str) -> None:
        headers = [
            Header(name="Location", value=route),
        ]
        super().__init__(status=303, headers=headers)


