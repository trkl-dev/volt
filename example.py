from http import HTTPStatus

import uvicorn

from volt import Request, Response, Volt

app = Volt()

@app.route("/", method="GET")
async def root(request: Request) -> Response:
    _ = request
    return Response(
        body="hello, world!",
        status=HTTPStatus.OK,
    )


@app.route("/home", method="GET")
async def home(request: Request) -> Response:
    _ = request
    return Response(
        body="hello, world!",
        status=HTTPStatus.OK,
    )

@app.route("/thing", method="GET")
async def thing(request: Request) -> Response:
    _ = request
    return Response(
        body="hello, thing!",
        status=HTTPStatus.OK,
    )

if __name__ == "__main__":
    uvicorn.run("example:app", port=1234, log_level="debug", reload=True)
