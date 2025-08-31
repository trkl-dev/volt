import time
from jinja2 import Environment, FileSystemLoader

from volt.router import Handler, HttpRequest, HttpResponse, Redirect, route, middleware, run_server


# TODO: Move this out of middleware, could probably even be in Zig
@middleware
def htmx(request: HttpRequest, handler: Handler) -> HttpResponse:
    for header in request.headers:
        if header:
            request.is_hx_request = True
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


def get_base_context() -> dict:
    return {
        "extraitems": [
            "item1",
            "item2",
            "item3",
        ],
    }


@route("/", method="GET")
def root(request: HttpRequest) -> HttpResponse:
    environment = Environment(loader=FileSystemLoader("templates/"))
    template = environment.get_template("home.html")

    if request.is_hx_request:
        # load just content without 'extends'
        pass
    else:
        # load with extends
        pass

    # Loading just a node without extends (parents), makes sense
    # something to consider is the need for additional context. Context 
    # _might_ need to be associated at the template level?

    context = {
        "selected": "home",
    }
    
    base_context = get_base_context()

    content = template.render(context | base_context)

    return HttpResponse(content)

@route("/features", method="GET")
def features(request: HttpRequest) -> HttpResponse:
    environment = Environment(loader=FileSystemLoader("templates/"))
    template = environment.get_template("features.html")

    base_context = get_base_context()
    
    context = {
        "selected": "features",
    }

    content = template.render(context | base_context)

    return HttpResponse(content)


@route("/home", method="GET")
def home(request: HttpRequest) -> HttpResponse:
    # This should be able to handle HTMX requests, and only render what is necesary.
    # Ideally, this might not actually require a redirect.
    # Should just render what is at the desired route, and update the URL accordingly?
    # return Redirect("/")
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

if __name__ == "__main__":
    run_server()
