import logging
from collections.abc import Callable, Coroutine
from http import HTTPMethod, HTTPStatus
from http import cookies as http_cookies
from typing import Any, TypedDict, override

from volt import asgi


log = logging.getLogger("volt")


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


type Handler = Callable[[HttpRequest], Coroutine[Any, Any, HttpResponse]]


async def generic_response(send: asgi.ASGISendCallable, status: HTTPStatus) -> None:
    start_event: asgi.HTTPResponseStartEvent = {
        "type": "http.response.start",
        "status": status,
    }

    await send(start_event)

    response_body: asgi.HTTPResponseBodyEvent = {
        "type": "http.response.body",
        "body": status.phrase.encode(),
    }
    await send(response_body)
