import gc
import logging
import signal
import threading
import time
from collections.abc import Awaitable, Callable
from http import HTTPMethod, HTTPStatus
from http import cookies as http_cookies
from types import CoroutineType, FrameType
from typing import Any, Coroutine, TypedDict, override
from urllib.parse import parse_qs

from volt import config
from volt.asgi_types import ASGIReceiveCallable, ASGISendCallable, HTTPRequestEvent, HTTPResponseBodyEvent, HTTPResponseStartEvent, HTTPScope


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
    form_data: FormData
    headers: list[Header]
    cookies: http_cookies.SimpleCookie
    query_params: dict[str, list[str]]
    route_params: dict[str, str | int]
    hx_request: bool
    hx_fragment: str | None

    def __init__(
        self,
        method: str,
        path: str,
        body: str,
        form_data: FormData,
        headers: list[Header],
        cookies: http_cookies.SimpleCookie,
        query_params: dict[str, list[str]],
        route_params: dict[str, str | int],
    ) -> None:
        self.method = HTTPMethod[method]
        self.path = path
        self.body = body
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

RouteHandler =  Callable[[HttpRequest], HttpResponse]

RouteRegister = TypedDict(
    "RouteRegister",
    {"path": str, "method": str, "handler":  Callable[[HTTPScope, ASGIReceiveCallable, ASGISendCallable], CoroutineType[Any, Any, RouteHandler]]},
)
routes: list[RouteRegister] = []

class RouteParam:
    name: str
    value: str | int

def parse_route_param(template_part: str, actual_part: str) -> RouteParam | None:
    assert False


def route(path: str, method: str = "GET"):
    """Register a route handler on 'path'"""

    def decorator(handler_fn: RouteHandler) -> None:
        async def request_handler(scope: HTTPScope, receive: ASGIReceiveCallable, send: ASGISendCallable) -> RouteHandler:
            log.debug("starting handler")

            query_string = scope["query_string"]
            query_params = parse_qs(query_string.decode())

            # Handle route params: /{username:str} or /{id:int}, etc
            route_params: dict[str, str | int] = {}
            template_parts = path.split("/")
            num_template_parts = len(template_parts)
            for part_idx, route_part in enumerate(scope["path"].split("/")):
                if part_idx >= num_template_parts:
                    break  # TODO: Check this
                
                template_part = template_parts[part_idx]
                if len(template_part) >= 3 and template_part[0] == "{" and template_part[-1] == "}":
                    route_param = parse_route_param(template_part, route_part)
                    if route_param is None:
                        log.error("unexpected")
                        break  # TODO: Check this
                    route_params[route_param.name] = route_param.value  # Does this need to go via this class?
                    continue
                
                if route_part != template_part:
                    break

            request_headers: list[Header] = []
            for header_key, header_value in scope["headers"]:
                request_headers.append(Header( header_key.decode(), header_value.decode()))

            request_event = await receive()
            match request_event["type"]:
                case "http.request":
                    request_body = request_event["body"].decode()
                case _:
                    raise Exception(f"Unexpected event: {request_event}")

            log.debug(f"request body: {request_body}")

            request_cookies = http_cookies.SimpleCookie()
            form_data: dict[str, list[str]] = {}
            # TODO: Don't need to iterate through headers a second time. Move this to above
            for header in request_headers:
                if header.name.lower() == "cookie":
                    request_cookies.load(header.value)
                if (
                    header.name.lower() == "content-type"
                    and header.value == "application/x-www-form-urlencoded"
                ):
                    form_data = parse_qs(request_body)
                    log.debug(f"parsed form data: {form_data}")

            try:
                method = HTTPMethod(scope["method"])
            except ValueError as e:
                log.error("unexpected HTTP method")
                raise e

            request_object = HttpRequest(
                method=method,
                path=scope["path"],
                body=request_body,
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

            handler_response.headers.insert(0, Header("content-type", handler_response.content_type))

            if handler_response.cookies is not None:
                for cookie in handler_response.cookies.items():
                    handler_response.headers.append(Header("Set-Cookie", cookie[1].OutputString()))

            start_event: HTTPResponseStartEvent = {
                "type": "http.response.start",
                "status": 200,
                "headers": [(header.name.encode(), header.value.encode()) for header in request_headers],
            }
            
            await send(start_event)
            response_body: HTTPResponseBodyEvent = {
                'type': 'http.response.body',
                'body': handler_response.body.encode(),
            }
            await send(response_body)

            log.debug("finished")

            return handler_fn

        routes.append(
            {
                "path": path,
                "method": method,
                "handler": request_handler,
            }
        )

    return decorator


def get_route(routes, route) -> route:
    ...

def get_route_old(routes: list[RouteRegister], path: str, method: HTTPMethod) -> RouteRegister | None:
    log.debug(f"matching path: {path}")
    for route in routes:
        log.debug(f"checking path against {route['path']}")
        found = False

        if route["method"] != method:
            continue

        if route["path"] == "/" and path == "/":
            return route

        route_params: dict[str, str | int] = {}
        template_parts = route["path"][1:].split("/")  # Strip initial '/'
        num_template_parts = len(template_parts)
        path_parts = path[1:].split("/")  # Strip initial '/'
        log.debug(f"path parts: {path_parts}, template parts: {template_parts}")
        for part_idx, route_part in enumerate(path_parts):
            if part_idx >= num_template_parts:
                break
            
            template_part = template_parts[part_idx]
            log.debug(f"Comparing {route_part} with {template_part}")
            if len(template_part) >= 3 and template_part[0] == "{" and template_part[-1] == "}":
                route_param = parse_route_param(template_part, route_part)
                if route_param is None:
                    break
                route_params[route_param.name] = route_param.value  # Does this need to go via this class?
                continue
            
            if route_part != template_part:
                break

            found = True
            break

        if found:
            return route


async def not_found(send: ASGISendCallable) -> None:
    start_event: HTTPResponseStartEvent = {
        "type": "http.response.start",
        "status": 404,
    }
    
    await send(start_event)
    response_body: HTTPResponseBodyEvent = {
        'type': 'http.response.body',
        'body': b'not found',
    }
    await send(response_body)


async def app(scope: HTTPScope, receive: ASGIReceiveCallable, send: ASGISendCallable) -> None:
    assert scope['type'] == 'http'
    
    route = get_route_old(routes, scope['path'], HTTPMethod(scope["method"]))
    if route is None:
        await not_found(send)
        return 

    await route["handler"](scope, receive, send)




class TrieNode:
    def __init__(self) -> None:
        self.children = []
        self.segment = ""


def insert(root: TrieNode, route: str) -> None:
    for segment in route.split("/"):
        for child in root.children:
            if child.segment != route:
                continue


