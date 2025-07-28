import ctypes

from typing import TYPE_CHECKING, Any


class Header(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("value", ctypes.c_char_p),
    ]


class HttpRequest(ctypes.Structure):
    _fields_ = [
        ("method", ctypes.c_char_p),
        ("path", ctypes.c_char_p),
        ("body", ctypes.POINTER(ctypes.c_ubyte)),
        ("body_len", ctypes.c_size_t),
        ("headers", ctypes.POINTER(Header)),
        ("num_headers", ctypes.c_size_t),
    ]


class HttpResponse(ctypes.Structure):
    _fields_ = [
        ("body", ctypes.c_char_p),
        ("content_type", ctypes.c_char_p),
        ("status", ctypes.c_int),
    ]


CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(HttpRequest), ctypes.POINTER(HttpResponse))


lib = ctypes.CDLL('./librouter.so')
lib.register_route.argtypes = [ctypes.c_char_p, CALLBACK]
lib.register_route.restype = None

lib.run_server.argtypes = [ctypes.c_char_p, ctypes.c_uint16]
lib.run_server.restype = None

lib.shutdown_server.argtypes = []
lib.shutdown_server.restype = None


if TYPE_CHECKING:
    HttpRequestPtr = ctypes._Pointer[HttpRequest]
    HttpResponsePtr = ctypes._Pointer[HttpResponse]
else:
    HttpRequestPtr = Any
    HttpResponsePtr = Any
