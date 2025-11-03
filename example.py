from http import HTTPStatus

import uvicorn

from volt import HttpRequest, HttpResponse, Volt

app = Volt()

@app.route("/", method="GET")
async def root(request: HttpRequest) -> HttpResponse:
    _ = request
    return HttpResponse(
        body="hello, world!",
        status=HTTPStatus.OK,
    )

@app.route("/thing", method="GET")
async def thing(request: HttpRequest) -> HttpResponse:
    _ = request
    return HttpResponse(
        body="hello, thing!",
        status=HTTPStatus.OK,
    )

if __name__ == "__main__":
    uvicorn.run("example:app", port=1234, log_level="debug", reload=True)
