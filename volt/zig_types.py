# pyright: basic
import ctypes
import faulthandler

from pathlib import Path
import platform
from typing import TYPE_CHECKING, Any

# Better logging of panic errors
faulthandler.enable(
    all_threads=True
)


class UnexpectedOperatingSystem(Exception):
    ...


match platform.system():
    case "Darwin":
        extension = "dylib"
    case "Linux":
        extension = "so"
    case "Windows":
        extension = "dll"
    case _:
        raise UnexpectedOperatingSystem(f"Unexpected platform: {platform.system()}")

libvolt_filename = f"lib/libvolt.{extension}"

_lib_path = Path(__file__).parent / libvolt_filename

if not _lib_path.exists():
    raise RuntimeError(f"{libvolt_filename} not found at {_lib_path}")

lib = ctypes.CDLL(str(_lib_path))

class Header(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("value", ctypes.c_char_p),
    ]

    def __str__(self) -> str:
        return f"ctypes Header<{self.name}: {self.value}>"


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

lib.route_params_get_value.argtypes = [ctypes.POINTER(HttpRequest), ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_int)]
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


lib.save_response.argtypes = [
    ctypes.c_void_p, # ctx_ptr
    ctypes.c_char_p, # body
    ctypes.c_size_t, # content_length
    ctypes.c_int, # status
    ctypes.POINTER(Header), # headers
    ctypes.c_size_t, # num_headers
    ctypes.c_void_p, # response_ptr
]

lib.save_response.restype = ctypes.c_size_t


CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(HttpRequest), ctypes.c_void_p, ctypes.c_void_p)
# FOO = ctypes.POINTER(ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(HttpRequest), ctypes.c_void_p, ctypes.c_void_p))


class Route(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_char_p),
        ("method", ctypes.c_char_p),
        ("handler", CALLBACK),
    ]


lib.run_server.argtypes = [ctypes.c_char_p, ctypes.c_uint16, ctypes.POINTER(Route), ctypes.c_uint16, ctypes.c_void_p, ctypes.c_void_p]  # TODO: Check if these pointers should be more specific
lib.run_server.restype = None

lib.shutdown_server.argtypes = []
lib.shutdown_server.restype = None

lib.server_running.argtypes = []
lib.server_running.restype = ctypes.c_size_t


if TYPE_CHECKING:
    HttpRequestPtr = ctypes._Pointer[HttpRequest]
else:
    HttpRequestPtr = Any
