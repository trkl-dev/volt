import asyncio
from contextlib import _AsyncGeneratorContextManager, asynccontextmanager
import logging
from http import HTTPMethod, HTTPStatus
from http import cookies as http_cookies
import mimetypes
from pathlib import Path
import traceback
from typing import Callable
from urllib.parse import parse_qs

from volt import asgi, middleware, http, trie

log = logging.getLogger("volt")


@asynccontextmanager
async def default_lifespan(app: "Volt"):
    log.info("starting...")
    yield
    log.info("shutting down...")


type LifespanContextManager = Callable[["Volt"], _AsyncGeneratorContextManager[None, None]]


class Volt:
    routes: trie.Node[trie.Handler]
    middlewares: list[middleware.MiddlewareType]
    lifespan: LifespanContextManager
    _started: bool = False
    static_path: str = "/static"
    static_location: str

    def __init__(self, static_location: str = "static", lifespan: LifespanContextManager | None = None) -> None:
        self.routes = trie.Node[trie.Handler]()
        self.middlewares = [middleware.htmx]
        self.lifespan = lifespan if lifespan is not None else default_lifespan
        if not Path(static_location).exists():
            raise RuntimeError(f"static directory: {static_location} could not be found at {Path().resolve()}")
        self.static_location = static_location

    async def __call__(self, scope: asgi.Scope, receive: asgi.ASGIReceiveCallable, send: asgi.ASGISendCallable) -> None:
        if scope["type"] == "lifespan":
            await self.handle_lifespan(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await http.generic_response(send, HTTPStatus.NOT_FOUND)
            return

        assert scope["type"] == "http"

        if scope["path"].startswith("/static"):
            return await self.handle_static_route(scope, receive, send)

        matched_route = trie.get(self.routes, scope["path"], HTTPMethod(scope["method"]))
        if matched_route is None:
            await http.generic_response(send, HTTPStatus.NOT_FOUND)
            return

        response = await matched_route.handler(scope, receive, send, matched_route.route_params)

        response.headers.insert(0, http.Header("content-type", response.content_type))

        if response.cookies is not None:
            for cookie in response.cookies.items():
                response.headers.append(http.Header("Set-Cookie", cookie[1].OutputString()))

        start_event: asgi.HTTPResponseStartEvent = {
            "type": "http.response.start",
            "status": response.status,
            "headers": [(header.name.encode(), header.value.encode()) for header in response.headers],
        }

        await send(start_event)
        response_body: asgi.HTTPResponseBodyEvent = {
            "type": "http.response.body",
            "body": response.body.encode(),
        }
        await send(response_body)

        log.debug("finished")

    def middleware(self, middleware_fn: middleware.MiddlewareType):
        self.middlewares.append(middleware_fn)

    def route(self, path: str, method: str):
        """Register a route handler on 'path'"""

        def decorator(handler: http.Handler) -> None:
            async def request_handler(
                scope: asgi.HTTPScope,
                receive: asgi.ASGIReceiveCallable,
                send: asgi.ASGISendCallable,
                route_params: trie.RouteParams,
            ) -> http.HttpResponse:
                _ = send  # Keeping this around for now
                log.debug("registering handler")

                query_string = scope["query_string"]
                query_params = parse_qs(query_string.decode())

                request_headers: list[http.Header] = []
                for header_key, header_value in scope["headers"]:
                    request_headers.append(http.Header(header_key.decode(), header_value.decode()))

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
                    if header.name.lower() == "content-type" and header.value == "application/x-www-form-urlencoded":
                        form_data = parse_qs(request_body)
                        log.debug(f"parsed form data: {form_data}")

                try:
                    method = HTTPMethod(scope["method"])
                except ValueError as e:
                    log.error("unexpected HTTP method")
                    raise e

                request_object = http.HttpRequest(
                    method=method,
                    path=scope["path"],
                    body=request_body,
                    form_data=form_data,
                    headers=request_headers,
                    cookies=request_cookies,
                    query_params=query_params,
                    route_params=route_params,
                )

                handler_with_middleware = middleware.create_middleware_stack(handler, *self.middlewares)
                handler_response = await handler_with_middleware(request_object)

                return handler_response

            trie.insert(self.routes, path, HTTPMethod(method), request_handler)

        return decorator

    async def handle_static_route(
        self, scope: asgi.HTTPScope, receive: asgi.ASGIReceiveCallable, send: asgi.ASGISendCallable
    ) -> None:
        path = scope["path"]
        if ".." in path:
            log.debug("path %s cannot contain '..'", path)
            return await http.generic_response(send, HTTPStatus.FORBIDDEN)

        # Prevent a URL like something.io/static/////
        while path.startswith("/"):
            path = path[1:]

        # filename, plus '.', plus extension _should_ be at least 3 chars. I.e. static/c.h
        if len(path) < 3:
            log.debug("path %s is too short", path)
            return await http.generic_response(send, HTTPStatus.NOT_FOUND)

        file_path = Path(path.replace("static", self.static_location))
        if not file_path.exists():
            log.debug("path %s does not exist", file_path.resolve())
            return await http.generic_response(send, HTTPStatus.NOT_FOUND)

        log.debug("reading file %s", file_path.resolve())
        if not file_path.is_file():
            log.debug("path %s is not a file", path)
            return await http.generic_response(send, HTTPStatus.NOT_FOUND)

        file_size = file_path.stat().st_size
        content_type, content_encoding = mimetypes.guess_file_type(path)

        # TODO: Check this
        if content_type is None:
            content_type = "application/octet-stream"

        headers = [
            (b"content-type", content_type.encode()),
            (b"content-length", str(file_size).encode()),
        ]

        if content_encoding is not None:
            headers.append((b"content-encoding", content_encoding.encode()))

        log.debug("starting read...")
        log.debug("headers %s", headers)
        start_response: asgi.HTTPResponseStartEvent = {
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": headers,
        }
        await send(start_response)

        chunk_size = 64 * 1024  # 64KB Chunk size

        f = await asyncio.to_thread(open, file_path, "rb")
        try:
            while True:
                log.debug("reading chunk...")
                chunk = await asyncio.to_thread(f.read, chunk_size)
                if not chunk:
                    break

                log.debug("chunk read.")
                response_body: asgi.HTTPResponseBodyEvent = {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": True,
                }
                await send(response_body)
                log.debug("chunk sent.")
        finally:
            await asyncio.to_thread(f.close)

        final_response_body: asgi.HTTPResponseBodyEvent = {
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        }
        await send(final_response_body)

    async def handle_lifespan(
        self, scope: asgi.LifespanScope, receive: asgi.ASGIReceiveCallable, send: asgi.ASGISendCallable
    ):
        started = False
        message = await receive()
        assert message["type"] == "lifespan.startup"
        try:
            async with self.lifespan(self):
                await send({"type": "lifespan.startup.complete"})
                started = True
                message = await receive()
                assert message["type"] == "lifespan.shutdown"
        except BaseException:
            event: asgi.LifespanStartupFailedEvent | asgi.LifespanShutdownFailedEvent
            if started:
                event = {"type": "lifespan.shutdown.failed", "message": traceback.format_exc()}
            else:
                event = {"type": "lifespan.startup.failed", "message": traceback.format_exc()}
            await send(event)
            raise
        await send({"type": "lifespan.shutdown.complete"})
