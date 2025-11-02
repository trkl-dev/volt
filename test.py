from volt.router import HttpRequest, HttpResponse, route, app

@route("/", method="GET")
def root(request: HttpRequest) -> HttpResponse:
    print("HI THERE")
    return HttpResponse("hi there")

@route("/something", method="GET")
def something(request: HttpRequest) -> HttpResponse:
    print("something")
    return HttpResponse("something")
