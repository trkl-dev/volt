from collections.abc import Generator
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import threading
from http import HTTPStatus, cookies as HTTPCookies

import pytest
import requests
import uvicorn

from volt import HttpRequest, HttpResponse, Volt, Header


log = logging.getLogger("volt.py")
app = Volt()


@pytest.fixture(scope="session", autouse=True)
def server():
    started = threading.Event()

    async def callback():
        log.debug("callback called!")
        started.set()

    config = uvicorn.Config(app, port=1235, log_level="debug", callback_notify=callback)
    server = uvicorn.Server(config)

    def run_server():
        server.run()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    if not started.wait(timeout=2.0):
        raise RuntimeError("Server failed to start")

    yield

    server.should_exit = True
    thread.join(timeout=5)


@app.route("/", method="GET")
async def root(request: HttpRequest) -> HttpResponse:
    return HttpResponse(body="success")


def test_root():
    response = requests.get("http://localhost:1235/")

    assert response.content == b"success"
    assert response.status_code == HTTPStatus.OK

    assert response.headers.get("content-type") == "text/html"

    response = requests.post("http://localhost:1235/")

    assert response.content == b"Not Found"
    assert response.status_code == HTTPStatus.NOT_FOUND


@app.route("/success", method="GET")
async def success(request: HttpRequest) -> HttpResponse:
    return HttpResponse(body="success")


def test_success():
    response = requests.get("http://localhost:1235/success")

    assert response.content == b"success"
    assert response.status_code == HTTPStatus.OK

    assert response.headers.get("content-type") == "text/html"


@app.route("/forbidden", method="GET")
async def forbidden(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        body="forbidden",
        status=HTTPStatus.FORBIDDEN,
    )


def test_forbidden():
    response = requests.get("http://localhost:1235/forbidden")

    assert response.content == b"forbidden"
    assert response.status_code == HTTPStatus.FORBIDDEN

    assert response.headers.get("content-type") == "text/html"


@app.route("/post", method="POST")
async def post(request: HttpRequest) -> HttpResponse:
    assert request.form_data.get("foo") == ["bar"]
    return HttpResponse(body="post data success", status=HTTPStatus.CREATED)


def test_post():
    response = requests.post(
        "http://localhost:1235/post", data={"foo": "bar", "something": {"else": "here"}}, timeout=10
    )

    assert response.content == b"post data success"
    assert response.status_code == HTTPStatus.CREATED

    assert response.headers.get("content-type") == "text/html"


@app.route("/query-params", method="GET")
async def query_params(request: HttpRequest) -> HttpResponse:
    assert request.query_params.get("param1") == ["value1", "value2"]
    assert request.query_params.get("param2") == ["value3"]

    return HttpResponse(
        body="query params query successful",
        status=HTTPStatus.OK,
    )


def test_query_params():
    response = requests.get("http://localhost:1235/query-params?param1=value1&param1=value2&param2=value3")

    assert response.content == b"query params query successful"
    assert response.status_code == HTTPStatus.OK


@app.route("/route-params/{name:str}/{id:int}", method="GET")
async def route_params(request: HttpRequest) -> HttpResponse:
    assert request.route_params.get("name") == "dirty"
    assert request.route_params.get("id") == 3

    return HttpResponse(
        body="route params success",
        status=HTTPStatus.OK,
        content_type="text/plain",
    )


def test_route_params():
    response = requests.get("http://localhost:1235/route-params/dirty/3")

    assert response is not None

    assert response.content == b"route params success"
    assert response.status_code == HTTPStatus.OK


@app.route("/headers", method="GET")
async def headers(_request: HttpRequest) -> HttpResponse:
    headers = [
        Header("A-Header", "here"),
        Header("Green-eggs-and", "ham"),
    ]
    return HttpResponse(
        body="request with headers success",
        status=HTTPStatus.OK,
        headers=headers,
        content_type="text/plain",
    )


def test_headers():
    response = requests.get("http://localhost:1235/headers")

    assert response is not None

    assert response.content == b"request with headers success"
    assert response.status_code == HTTPStatus.OK

    log.debug(response.headers)
    assert response.headers.get("content-type") == "text/plain"
    assert response.headers.get("A-Header") == "here"
    assert response.headers.get("Green-eggs-and") == "ham"


@app.route("/cookies", method="GET")
async def cookies(_request: HttpRequest) -> HttpResponse:
    cookies = HTTPCookies.SimpleCookie()
    cookies["cookie"] = "yummy"
    cookies["cookie"]["path"] = "/expect-cookies"
    cookies["something"] = "else"
    cookies["another"] = "cookie"
    cookies["another"]["path"] = "elsewhere"

    return HttpResponse(
        body="cookies request success",
        status=HTTPStatus.OK,
        cookies=cookies,
        content_type="text/plain",
    )


@app.route("/expect-cookies", method="GET")
async def expect_cookies(request: HttpRequest) -> HttpResponse:
    assert len(request.cookies.items()) == 2

    cookie_cookie = request.cookies.get("cookie")
    assert cookie_cookie is not None
    assert cookie_cookie.value == "yummy"

    something_cookie = request.cookies.get("something")
    assert something_cookie is not None
    assert something_cookie.value == "else"

    another_cookie = request.cookies.get("another")
    assert another_cookie is None

    return HttpResponse(
        body="cookies request success",
        status=HTTPStatus.OK,
        content_type="text/plain",
    )


def test_cookies():
    session = requests.Session()

    # Initial request to set cookies
    response = session.get("http://localhost:1235/cookies")
    assert response.status_code == HTTPStatus.OK

    assert response.content == b"cookies request success"

    assert response.cookies.get("cookie") == "yummy"
    assert response.cookies.get("cookie", path="/expect-cookies") == "yummy"

    assert response.cookies.get("something") == "else"

    # Ensure that cookies are persisted in the session and are passed through subsequent requests
    # correctly
    response_expect_cookies = session.get("http://localhost:1235/expect-cookies")
    assert response_expect_cookies.status_code == 200


@app.route("/kitchen-sink/{name:str}/{id:int}", method="GET")
async def kitchen_sink(request: HttpRequest) -> HttpResponse:
    assert request.query_params.get("param1") == ["value1", "value2"]
    assert request.query_params.get("param2") == ["value3"]

    assert request.route_params.get("name") == "dirty"
    assert request.route_params.get("id") == 3

    cookies = HTTPCookies.SimpleCookie()
    cookies["cookie"] = "yummy"
    cookies["cookie"]["path"] = "overhere"
    cookies["something"] = "else"

    headers = [
        Header("A-Header", "here"),
        Header("Green-eggs-and", "ham"),
    ]
    return HttpResponse(
        body="everything but the kitchen sink",
        status=HTTPStatus.OK,
        cookies=cookies,
        headers=headers,
        content_type="text/plain",
    )


def test_kitchen_sink():
    response = requests.get("http://localhost:1235/kitchen-sink/dirty/3?param1=value1&param1=value2&param2=value3")

    assert response is not None

    assert response.content == b"everything but the kitchen sink"
    assert response.status_code == HTTPStatus.OK

    assert response.headers.get("content-type") == "text/plain"
    assert response.headers.get("A-Header") == "here"
    assert response.headers.get("Green-eggs-and") == "ham"

    assert response.cookies.get("cookie") == "yummy"
    assert response.cookies.get("cookie", path="overhere") == "yummy"

    assert response.cookies.get("something") == "else"


@app.route("/nested/second", method="GET")
async def nested_2(_request: HttpRequest) -> HttpResponse:
    return HttpResponse(body="second nested")


@app.route("/nested", method="GET")
async def nested_1(_request: HttpRequest) -> HttpResponse:
    return HttpResponse(body="first nested")


# NOTE:: This tests a regression
def test_out_of_order():
    response = requests.get("http://localhost:1235/nested")

    assert response.content == b"first nested"
    assert response.status_code == HTTPStatus.OK


@pytest.fixture(scope="function")
def styles_css_file() -> Generator[None]:
    """Create a static styles.css file for the duration of the test"""
    css_content = """
a {
  color: inherit;
  -webkit-text-decoration: inherit;
  text-decoration: inherit;
}
"""
    path = Path(__file__).parent
    static_dir = path / "static"
    styles_file = static_dir / "styles.css"
    _ = styles_file.write_text(css_content, encoding="utf-8")

    app.static_location = "volt/static"
    yield
    styles_file.unlink()
    app.static_location = None


def test_static(styles_css_file: None):
    _ = styles_css_file

    response = requests.get("http://localhost:1235/static/not_present.css")
    assert response.status_code == HTTPStatus.NOT_FOUND

    response = requests.get("http://localhost:1235/static/styles.css")
    assert response.status_code == HTTPStatus.OK

    assert response.headers.get("content-type") == "text/css"
    assert response.headers.get("content-length") == "89"


def test_lifespan():
    started = threading.Event()
    lifespan_run = threading.Event()

    @asynccontextmanager
    async def dummy_lifespan(app: Volt):
        lifespan_run.set()
        yield
        lifespan_run.clear()

    async def callback():
        log.debug("callback called!")
        started.set()

    app = Volt(static_location="volt/static", lifespan=dummy_lifespan)

    config = uvicorn.Config(app, port=9999, callback_notify=callback)
    server = uvicorn.Server(config)

    def run_server():
        server.run()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    if not started.wait(timeout=2.0):
        raise RuntimeError("Server failed to start")

    assert lifespan_run.is_set()

    server.should_exit = True
    thread.join(timeout=5)

    assert not lifespan_run.is_set()
