import ctypes
import threading
import signal
import sys

from collections.abc import Callable
from typing import Any, TypedDict, List

from . import zig_types as zt

Header = TypedDict('Header', {'name': str, 'value': str})

class HttpRequest:
    method: str
    path: str
    body: str
    body_len: int
    headers: list[Header]

    def __init__(self, method: str, path: str, body: str, body_len: int, headers: list[Header]) -> None:
        self.method = method
        self.path = path
        self.body = body
        self.body_len = body_len
        self.headers = headers


class HttpResponse:
    body: str
    content_type: str
    status: int

    def __init__(self, body: str ="", content_type: str="text/plain", status: int=200) -> None:
        self.body = body
        self.content_type = content_type
        self.status = status

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

def route(path: str):
    """Register a route handler on 'path'"""
    def decorator(fn: Callable[[HttpRequest], HttpResponse]) -> Any:
        def RequestHandler(request_ptr: zt.HttpRequestPtr, response_ptr: zt.HttpResponsePtr):
            req = request_ptr.contents

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
            )

            handler_with_middleware = create_middleware_stack(fn, *middleware_list)
            response_object = handler_with_middleware(request_object)

            res = response_ptr.contents
            res.body = response_object.body.encode('utf-8')
            res.content_type = response_object.content_type.encode('utf-8')
            res.status = response_object.status
            

        cb = zt.CALLBACK(RequestHandler)
        # _registered_callbacks.append(cb) # Prevent GC
        zt.lib.register_route(path.encode('utf-8'), cb)
        return cb
    return decorator


def _run_server(server_addr, server_port):
    # TODO: Check that server_port here is only u16
    def run():
        zt.lib.run_server(server_addr.encode('utf-8'), server_port)

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
