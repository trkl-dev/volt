from collections.abc import Callable
import ctypes
import threading
import signal
import sys
from typing import TYPE_CHECKING, Any

class ZHttpRequest(ctypes.Structure):
    _fields_ = [
        ("method", ctypes.c_char_p),
        ("path", ctypes.c_char_p),
        ("body", ctypes.POINTER(ctypes.c_ubyte)),
        ("body_len", ctypes.c_size_t),
    ]

class ZHttpResponse(ctypes.Structure):
    _fields_ = [
        ("body", ctypes.c_char_p),
        ("content_type", ctypes.c_char_p),
        ("status", ctypes.c_int),
    ]

class HttpRequest:
    method: str
    path: str
    body: str
    body_len: int

    def __init__(self, method: str, path: str, body: str, body_len: int) -> None:
        self.method = method
        self.path = path
        self.body = body
        self.body_len = body_len

class HttpResponse:
    body: str
    content_type: str
    status: int

    def __init__(self, body: str, content_type: str="text/plain", status: int=200) -> None:
        self.body = body
        self.content_type = content_type
        self.status = status

CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(ZHttpRequest), ctypes.POINTER(ZHttpResponse))

lib = ctypes.CDLL('./librouter.so')
lib.register_route.argtypes = [ctypes.c_char_p, CALLBACK]
lib.register_route.restype = None

lib.run_server.argtypes = [ctypes.c_char_p, ctypes.c_uint16]
lib.run_server.restype = None

lib.shutdown_server.argtypes = []
lib.shutdown_server.restype = None

# NOTE: This was to 'prevent Garbage Collection'. Unclear if this is necessary.
# _registered_callbacks = []

if TYPE_CHECKING:
    ZHttpRequestPtr = ctypes._Pointer[ZHttpRequest]
    ZHttpResponsePtr = ctypes._Pointer[ZHttpResponse]
else:
    ZHttpRequestPtr = Any
    ZHttpResponsePtr = Any

def route(path: str):
    def decorator(fn: Callable[[HttpRequest], HttpResponse]) -> Any:
        def RequestHandler(request_ptr: ZHttpRequestPtr, response_ptr: ZHttpResponsePtr):

            req = request_ptr.contents

            request_object = HttpRequest(
                method=ctypes.string_at(req.method).decode('utf-8'),
                path=ctypes.string_at(req.path).decode('utf-8'),
                body=ctypes.string_at(req.body, req.body_len).decode('utf-8'),
                body_len=req.body_len,
            )

            response_object = fn(request_object)

            res = response_ptr.contents
            res.body = response_object.body.encode('utf-8')
            res.content_type = response_object.content_type.encode('utf-8')
            res.status = response_object.status
            

        cb = CALLBACK(RequestHandler)
        # _registered_callbacks.append(cb) # Prevent GC
        lib.register_route(path.encode('utf-8'), cb)
        return cb
    return decorator


def _run_server(server_addr, server_port):
    # TODO: Check that server_port here is only u16
    def run():
        lib.run_server(server_addr.encode('utf-8'), server_port)

    return run


server_thread = None


def run_server(server_addr, server_port):
    global server_thread
    server_thread = threading.Thread(target=_run_server(server_addr, server_port))
    server_thread.start()


def handle_sigint(signum, frame):
    global server_thread
    print("\nCaught ctrl+c - shutting down Zig server...")
    lib.shutdown_server()
    if server_thread is not None:
        server_thread.join()
    sys.exit()


signal.signal(signal.SIGINT, handle_sigint)
