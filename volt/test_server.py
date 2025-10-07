import pytest
import requests

from http import HTTPStatus
from http import cookies as HTTPCookies

from volt.router import Header, HttpRequest, HttpResponse, route, run_server, shutdown


@pytest.fixture(scope="session", autouse=True)
def server():
    """
    Start the zig webserver in a separate thread and yield. 
    Teardown will stop the server and wait for the thread to close.
    """
    run_server(server_port=1236)
    yield
    shutdown()


@route("/success")
def success(_request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        body="success" * 10_000
    )


def test_success():
    response = requests.get("http://localhost:1236/success")

    assert response.content == b"success" * 10_000
    assert response.status_code == HTTPStatus.OK

    assert len(response.headers) == 2
    assert response.headers.get("content-type") == "text/html"


@route("/forbidden", method="GET")
def forbidden(_request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        body="forbidden",
        status=HTTPStatus.FORBIDDEN,
    )


def test_forbidden():
    response = requests.get("http://localhost:1236/forbidden")

    assert response.content == b"forbidden"
    assert response.status_code == HTTPStatus.FORBIDDEN

    assert len(response.headers) == 2
    assert response.headers.get("content-type") == "text/html"


@route("/post", method="POST")
def post(request: HttpRequest) -> HttpResponse:
    assert request.form_data.get("foo") == ["bar"]
    return HttpResponse(
        body="post data success",
        status=HTTPStatus.CREATED
    )


def test_post():
    response = requests.post("http://localhost:1236/post", data={"foo": "bar", "something": {"else": "here"}}, timeout=10)

    assert response.content == b"post data success"
    assert response.status_code == HTTPStatus.CREATED

    assert len(response.headers) == 2
    assert response.headers.get("content-type") == "text/html"


@route("/query-params", method="GET")
def query_params(request: HttpRequest) -> HttpResponse:
    assert request.query_params.get("param1") == "value1,value2"
    assert request.query_params.get("param2") == "value3"

    return HttpResponse(
        body="query params query successful",
        status=HTTPStatus.OK,
    )


def test_query_params():
    response = requests.get("http://localhost:1236/query-params?param1=value1&param1=value2&param2=value3")
    
    assert response.content == b"query params query successful"
    assert response.status_code == HTTPStatus.OK


@route("/route-params/{name:str}/{id:int}", method="GET")
def route_params(request: HttpRequest) -> HttpResponse:
    assert request.route_params.get("name") == "dirty"
    assert request.route_params.get("id") == 3
    
    return HttpResponse(
        body="route params success",
        status=HTTPStatus.OK,
        content_type="text/plain",
    )


def test_route_params():
    response = requests.get("http://localhost:1236/route-params/dirty/3")
    
    assert response is not None

    assert response.content == b"route params success"
    assert response.status_code == HTTPStatus.OK


@route("/headers", method="GET")
def headers(_request: HttpRequest) -> HttpResponse:
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
    response = requests.get("http://localhost:1236/headers")
    
    assert response is not None

    assert response.content == b"request with headers success"
    assert response.status_code == HTTPStatus.OK

    assert len(response.headers) == 4
    assert response.headers.get("content-type") == "text/plain"
    assert response.headers.get("content-length") == "28"
    assert response.headers.get("A-Header") == "here"
    assert response.headers.get("Green-eggs-and") == "ham"


@route("/cookies", method="GET")
def cookies(_request: HttpRequest) -> HttpResponse:
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


@route("/expect-cookies", method="GET")
def expect_cookies(request: HttpRequest) -> HttpResponse:
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
    response = session.get("http://localhost:1236/cookies")
    assert response.status_code == HTTPStatus.OK
    
    assert response.content == b"cookies request success"

    assert len(response.headers) == 3

    assert response.cookies.get("cookie") == "yummy"
    assert response.cookies.get("cookie", path="/expect-cookies") == "yummy"

    assert response.cookies.get("something") == "else"

    # Ensure that cookies are persisted in the session and are passed through subsequent requests
    # correctly
    response_expect_cookies = session.get("http://localhost:1236/expect-cookies")
    assert response_expect_cookies.status_code == 200


@route("/kitchen-sink/{name:str}/{id:int}", method="GET")
def kitchen_sink(request: HttpRequest) -> HttpResponse:
    assert request.query_params.get("param1") == "value1,value2"
    assert request.query_params.get("param2") == "value3"

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
    response = requests.get("http://localhost:1236/kitchen-sink/dirty/3?param1=value1&param1=value2&param2=value3")
    
    assert response is not None

    assert response.content == b"everything but the kitchen sink"
    assert response.status_code == HTTPStatus.OK

    assert len(response.headers) == 5
    assert response.headers.get("content-type") == "text/plain"
    assert response.headers.get("content-length") == "31"
    assert response.headers.get("A-Header") == "here"
    assert response.headers.get("Green-eggs-and") == "ham"

    assert response.cookies.get("cookie") == "yummy"
    assert response.cookies.get("cookie", path="overhere") == "yummy"

    assert response.cookies.get("something") == "else"

