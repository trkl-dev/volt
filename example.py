import time

from volt.router import Handler, HttpRequest, HttpResponse, Redirect, route, middleware, run_server

from components import Home, Features, NavSelected


# TODO: Move this out of middleware, could probably even be in Zig
@middleware
def htmx(request: HttpRequest, handler: Handler) -> HttpResponse:
    for header in request.headers:
        if header["name"] == "HX-Request" and header["value"].lower() == "true":
            request.hx_request = True

        if header["name"] == "HX-Fragment":
            request.hx_fragment = header["value"]


    return handler(request)


@middleware
def logging(request: HttpRequest, handler: Handler) -> HttpResponse:
    start = time.time()
    response = handler(request)
    end = time.time() - start
    print(f"Request - Path: {request.path}, Time: {end * 1_000 * 1_000 }μs")
    return response


@middleware
def auth(request: HttpRequest, handler: Handler) -> HttpResponse:
    print("running auth")
    print("auth passed")
    return handler(request)


@route("/", method="GET")
def root(request: HttpRequest) -> HttpResponse:
    context = Home.Context(
        request=request,
        selected=NavSelected.HOME,
    )

    return HttpResponse(Home(context).render(request))


@route("/features", method="GET")
def features(request: HttpRequest) -> HttpResponse:
    context = Features.Context(
        request=request,
        selected=NavSelected.FEATURES,
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


if __name__ == "__main__":
    run_server()
