import ctypes
import faulthandler

from typing import TYPE_CHECKING, Any


# Better logging of panic errors
faulthandler.enable()

lib = ctypes.CDLL('zig-out/lib/libvolt.so')

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
        ("query_params", ctypes.c_void_p),
        ("route_params", ctypes.c_void_p),
    ]


lib.route_params_get_keys.argtypes = [
    ctypes.POINTER(HttpRequest),
    ctypes.POINTER(ctypes.c_char_p),
    ctypes.POINTER(ctypes.c_size_t),
    ctypes.c_size_t,
]

lib.route_params_get_keys.restype = ctypes.c_size_t

lib.route_params_size.argtypes = [ctypes.POINTER(HttpRequest)]
lib.route_params_size.restype = ctypes.c_size_t

class RouteParamValue(ctypes.Union):
    _fields_ = [
        ("int", ctypes.c_int32),
        ("str", ctypes.c_char_p),
    ]

lib.route_params_get_value.argtypes = [ctypes.POINTER(HttpRequest), ctypes.c_char_p, ctypes.POINTER(RouteParamValue), ctypes.POINTER(ctypes.c_int)]
lib.route_params_get_value.restype = ctypes.c_size_t

lib.query_params_get_keys.argtypes = [
    ctypes.POINTER(HttpRequest),
    ctypes.POINTER(ctypes.c_char_p),
    ctypes.POINTER(ctypes.c_size_t),
    ctypes.c_size_t,
]

lib.query_params_get_keys.restype = ctypes.c_size_t

lib.query_params_size.argtypes = [ctypes.POINTER(HttpRequest)]
lib.query_params_size.restype = ctypes.c_size_t

lib.query_params_get_value.argtypes = [ctypes.POINTER(HttpRequest), ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p)]
lib.query_params_get_value.restype = ctypes.c_size_t


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
        ("method", ctypes.c_char_p),
        ("handler", CALLBACK),
    ]



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
