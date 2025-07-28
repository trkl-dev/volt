from collections.abc import Callable
import ctypes
import threading
import signal
import sys
from typing import Any

import zig_types as zt


class HttpRequest:
    method: str
    path: str
    body: str
    body_len: int
    headers: list[dict[str, str]]

    def __init__(self, method: str, path: str, body: str, body_len: int, headers: list[dict[str, str]]) -> None:
        self.method = method
        self.path = path
        self.body = body
        self.body_len = body_len
        self.headers = headers


class HttpResponse:
    body: str
    content_type: str
    status: int

    def __init__(self, body: str, content_type: str="text/plain", status: int=200) -> None:
        self.body = body
        self.content_type = content_type
        self.status = status


def route(path: str):
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

            response_object = fn(request_object)

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


def run_server(server_addr, server_port):
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
