# Volt ⚡

A lightning-fast Python web framework with a high-performance Zig substrate.

## Vision

Volt combines the simplicity and expressiveness of Python with the raw performance of Zig. Unlike traditional Python web frameworks that rely on slow WSGI/ASGI servers, Volt includes its own blazing-fast web server written in Zig - giving you production-ready performance out of the box.

**Why Volt?**
- **Zero external dependencies for serving** - No need for gunicorn, uvicorn, or other WSGI/ASGI servers
- **Batteries included** - Everything you need for modern web development in one package
- **Performance without complexity** - Write pure Python, get Zig-level speed
- **Simple developer experience** - One command to run, deploy, and scale

## Quick Start

```python
import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from volt.router import Handler, HttpRequest, HttpResponse, route, middleware, run_server
from db import query


@middleware
def logging(request: HttpRequest, handler: Handler) -> HttpResponse:
    """Add custom logging to each request"""
    start = time.time()
    response = handler(request)
    end = time.time() - start
    print(f"Request - Path: {request.path}, Time: {end * 1_000 * 1_000 }μs")
    return response


@route("/home")
def home(request: HttpRequest) -> HttpResponse:
    db_url = os.environ["DB_URL"].replace("postgres", "postgresql+psycopg")
    engine = create_engine(db_url, echo=True)

    with Session(engine) as session:
        querier = query.Querier(session.connection())
        volt = querier.get_volt(id=1)

    return HttpResponse(
        f"this is the homepage. Volt DB response: {volt.stuff if volt is not None else 'None'}",
        headers=[{"name": "custom", "value": "header"}]
    )

@route("/blog")
def blog(request: HttpRequest) -> HttpResponse:
    import time
    time.sleep(0.1)
    return HttpResponse("this is the blog page")


if __name__ == "__main__":
    run_server()
```

## Why Zig?

Zig is a modern systems programming language that compiles to native machine code - the same performance class as C and Rust. While Python is interpreted at runtime, Zig code runs at native CPU speed with better safety than C and simpler syntax than Rust.

You write Python. Volt handles the performance.

## Performance

Traditional Python web frameworks require external servers that add overhead and complexity:
```
Request → nginx → gunicorn → Django/Flask → Your Code
```

Volt eliminates the bottleneck:
```
Request → Volt (Zig) → Your Code
```

The result? Dramatically faster request routing, static file serving, and overall throughput - all while maintaining Python's developer-friendly syntax.

## Current Status

⚠️ **Alpha Release** - Volt is in early development. Core routing and middleware systems are functional, but this is not yet production-ready.

**Working:**
- HTTP server and request routing
- Custom middleware support
- Header handling
- HTTP/1 and HTTP/1.1

**Coming Soon:**
- Static file serving
- Built-in templating engine
- ORM integration
- Advanced middleware (CSRF, CORS, etc.)
- Production deployment tools

## Philosophy

Volt is opinionated by design. Like Django, we believe in convention over configuration, but we take it further - why should you need to choose and configure a separate web server? Why should performance require switching languages or adding complexity?

Volt gives you the full stack in one package, optimized from the ground up.

---

*Volt is in active development. Star this repo to follow progress.*
