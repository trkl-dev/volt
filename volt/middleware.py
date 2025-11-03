from collections.abc import Coroutine
from typing import Any, Callable

from volt import http

type MiddlewareType = Callable[[http.HttpRequest, http.Handler], Coroutine[Any, Any, http.HttpResponse]]


def wrap_middleware(middleware: MiddlewareType, handler: http.Handler) -> http.Handler:
    async def wrapped(request: http.HttpRequest):
        return await middleware(request, handler)

    return wrapped


def create_middleware_stack(handler: http.Handler, *middlewares: MiddlewareType) -> http.Handler:
    for middleware in reversed(middlewares):
        handler = wrap_middleware(middleware, handler)
    return handler


async def htmx(request: http.HttpRequest, handler: http.Handler) -> http.HttpResponse:
    """Parse the provided request and update HTMX related attributes accordingly"""
    for header in request.headers:
        if header.name.lower() == "hx-request" and header.value.lower() == "true":
            request.hx_request = True

        if header.name.lower() == "hx-fragment":
            request.hx_fragment = header.value

    return await handler(request)
