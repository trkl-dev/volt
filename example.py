import threading
import time
from http import HTTPStatus, cookies as HTTPCookies

from volt.router import Handler, Header, HttpRequest, HttpResponse, Redirect, route, middleware, run_server

from components import Home, Features, NavSelected, NavBar



@middleware
def logging(request: HttpRequest, handler: Handler) -> HttpResponse:
    start = time.time()
    response = handler(request)
    end = time.time() - start
    print(f"Request - Path: {request.path}, Time: {end * 1_000 * 1_000 }μs")
    return response


@middleware
def auth(request: HttpRequest, handler: Handler) -> HttpResponse:
    auth_success = True
    if auth_success:
        return handler(request)
    return HttpResponse(body="get outta here!", status=HTTPStatus.FORBIDDEN)


@route("/", method="GET")
def root(request: HttpRequest) -> HttpResponse:
    assert False, "this has gone poorly"
    raise Exception("hi there")
    context = Home.Context(
        request=request,
        selected=NavSelected.HOME,
        oob=[NavBar(NavBar.Context(request=request, selected=NavSelected.HOME, oob=[]))],
    )

    cookies = HTTPCookies.SimpleCookie()
    cookies["this"] = "that"
    cookies["this"]["path"] = "other"
    cookies["something"] = "else"
    return HttpResponse(
        Home(context).render(request),
        cookies=cookies,
        headers=[
            Header("custom-header-1", "a value"),
            Header("custom-header-2", "another value"),
            Header("custom-header-a", "a value"),
            Header("custom-header-b", "a value"),
            Header("custom-header-c", "a value"),
            Header("custom-header-d", "another value"),
            Header("custom-header-e", "another value"),
            Header("custom-header-r", "another value"),
        ]
    )


@route("/test/{name:str}/{id:int}", method="GET")
def test(request: HttpRequest) -> HttpResponse:
    context = Features.Context(
        request=request,
        selected=NavSelected.FEATURES,
        oob=[NavBar(NavBar.Context(request=request, selected=NavSelected.FEATURES, oob=[]))],
    )
    return HttpResponse(Features(context).render(request))

@route("/features", method="GET")
def features(request: HttpRequest) -> HttpResponse:
    context = Features.Context(
        request=request,
        selected=NavSelected.FEATURES,
        oob=[NavBar(NavBar.Context(request=request, selected=NavSelected.FEATURES, oob=[]))],
    )
    return HttpResponse(Features(context).render(request))


@route("/quickstart", method="GET")
def quickstart(_: HttpRequest) -> HttpResponse:
    return Redirect("/")


@route("/home", method="GET")
def home(_: HttpRequest) -> HttpResponse:
    return Redirect("/")


@route("/blog/{id:int}")
def blog(request: HttpRequest) -> HttpResponse:
    print(request.route_params)
    return HttpResponse(f"this is the blog page by id\n{request.route_params}\n{request.query_params}")


@route("/blog/name/{name:str}")
def blog_name(request: HttpRequest) -> HttpResponse:
    print("inside /blog/name/{name:str} route")
    print(request.route_params)
    return HttpResponse("this is the blog by name")


@route("/content", method="POST")
def content(request: HttpRequest) -> HttpResponse:
    return HttpResponse(f"this is the content page. Content: {request.body=}")


@route("/slow")
def slow(_: HttpRequest) -> HttpResponse:
    time.sleep(10)
    return HttpResponse(f"this is the slow page")


@route("/cpu-heavy")
def cpu_heavy_handler(request: HttpRequest) -> HttpResponse:
    """CPU-intensive handler that will hold the GIL"""
    thread_id = threading.get_ident()
    start_time = time.time()
    
    # Pure CPU work - no I/O, will hold GIL the entire time
    result = 0
    for i in range(10_000_000):  # 10 million iterations
        result += i * i
        if i % 1_000_000 == 0:
            # This won't help with GIL, but shows progress
            elapsed = time.time() - start_time
            print(f"Thread {thread_id}: Progress {i//1_000_000}/10, elapsed: {elapsed:.2f}s")
    
    total_time = time.time() - start_time
    body =  f"CPU work complete! Thread: {thread_id}, Result: {result}, Time: {total_time:.2f}s"
    content_type = "text/plain"
    name = "X-Thread-ID"
    headers = [Header(name=name, value=str(thread_id)), Header(name="something", value="else")]
    return HttpResponse(
        body,
        content_type=content_type,
        headers=headers,
    )

@route("/mixed-work") 
def mixed_work_handler(request: HttpRequest) -> HttpResponse:
    """Mixed CPU + I/O handler - shows when GIL gets released"""
    thread_id = threading.get_ident()
    start_time = time.time()
    
    print(f"Thread {thread_id}: Starting mixed work")
    
    # CPU work (holds GIL)
    result = 0
    for i in range(3_000_000):  # 3 million iterations
        result += i * i
    
    cpu_time = time.time() - start_time
    print(f"Thread {thread_id}: CPU work done in {cpu_time:.2f}s")
    
    # I/O work (releases GIL during the sleep)
    time.sleep(2.0)  # This will release the GIL!
    
    # More CPU work (re-acquires and holds GIL)
    for i in range(2_000_000):  # 2 million more
        result += i * i
    
    total_time = time.time() - start_time
    return HttpResponse(
        f"Mixed work complete! Thread: {thread_id}, Result: {result}, Total time: {total_time:.2f}s",
        headers=[{"name": "X-Thread-ID", "value": str(thread_id)}]
    )

if __name__ == "__main__":
    # gc.set_debug(gc.DEBUG_LEAK)
    # gc.disable()
    run_server()
