import ctypes
import faulthandler

import platform
from typing import TYPE_CHECKING, Any


# Better logging of panic errors
faulthandler.enable()


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
        ("content_length", ctypes.c_size_t),
        ("content_type", ctypes.c_char_p),
        ("status", ctypes.c_int),
        ("headers", ctypes.POINTER(Header)),
        ("num_headers", ctypes.c_size_t),
    ]


CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(HttpRequest), ctypes.POINTER(HttpResponse))

class Route(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_char_p),
        ("handler", CALLBACK),
    ]


lib = None
if platform.system() == 'Darwin':
    lib = ctypes.CDLL('zig-out/lib/libvolt.dylib')
else:
    lib = ctypes.CDLL('zig-out/lib/libvolt.so')

if lib is None:
    raise Exception("Failed to load libvolt")

lib.run_server.argtypes = [ctypes.c_char_p, ctypes.c_uint16, ctypes.POINTER(Route), ctypes.c_uint16]
lib.run_server.restype = None

lib.shutdown_server.argtypes = []
lib.shutdown_server.restype = None


if TYPE_CHECKING:
    HttpRequestPtr = ctypes._Pointer[HttpRequest]
    HttpResponsePtr = ctypes._Pointer[HttpResponse]
else:
    HttpRequestPtr = Any
    HttpResponsePtr = Any
