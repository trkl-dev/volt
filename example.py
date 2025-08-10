import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from volt.router import Handler, HttpRequest, HttpResponse, route, middleware, run_server
from db import query


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


@route("/home")
def home(request: HttpRequest) -> HttpResponse:
    db_url = os.environ["DB_URL"].replace("postgres", "postgresql+psycopg")
    engine = create_engine(db_url, echo=True)

    with Session(engine) as session:
        querier = query.Querier(session.connection())
        volt = querier.get_volt(id=1)

    if volt is None:
        print("Volt is None")
    else:
        print(volt)

    return HttpResponse(
        f"this is the homepage. Volt DB response: {volt.stuff if volt is not None else 'None'}",
        headers=[{
            "name": "Something",
            "value": "Elsee",
        }]
    )


@route("/blog")
def blog(request: HttpRequest) -> HttpResponse:
    return HttpResponse("this is the blog pages% aslkdjasldkjasdkjhasdflkajsdhfalskshdahsdkjhakdfjhasdlfkjhasdfl\n%jh")


if __name__ == "__main__":
    run_server()
