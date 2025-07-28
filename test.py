from router import HttpRequest, HttpResponse, route, run_server


@route("/home")
def home(request: HttpRequest) -> HttpResponse:
    return HttpResponse("this is the homepage")


@route("/blog")
def blog(request: HttpRequest) -> HttpResponse:
    return HttpResponse("this is the blog page")


if __name__ == "__main__":
    server_addr = "127.0.0.1"
    server_port = 1234

    run_server(server_addr, server_port)
