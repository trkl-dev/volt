import time

from volt.router import Handler, HttpRequest, HttpResponse, route, middleware, run_server


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
    auth = False
    for header in request.headers:
        if header["name"] == "Auth":
            auth = True

    if not auth:
        resp = HttpResponse(status=403)
        print(resp.status)
        return resp

    print("auth passed")
    return handler(request)


@route("/home", method="GET")
def home(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        f"this is the homepage. query_params: {request.query_params}",
        headers=[{
            "name": "Something",
            "value": "Elsee",
        }]
    )


@route("/blog/{id:int}")
def blog(request: HttpRequest) -> HttpResponse:
    print(request.route_params)
    return HttpResponse(f"this is the blog page by id\n{request.route_params}\n{request.query_params}")


@route("/blog/name/{name:str}")
def blog_name(request: HttpRequest) -> HttpResponse:
    print(request.route_params)
    return HttpResponse("this is the blog by name")


if __name__ == "__main__":
    run_server()
