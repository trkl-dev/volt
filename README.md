# Volt ⚡

An opinionated, lightning-fast ASGI-based Python web framework with rich and expressive Developer Experience.

## Installation
```bash
pip install volt-framework
```

## Vision

**Why Volt?**
- **Create easy SPA-like applications** - Built with HTMX in mind, you can create high quality, responsive applications, without a separate frontend
- **Type-safe templating** - The Jinja templating you know and love, with the power to generate type safe dataclass components for template context
- **Batteries included** - Everything you need for modern web development in one package
- **Simple developer experience** - One command to run, deploy, and scale

## Quick Start

```python
import logging

from volt import Request, Response, Volt, config, http
from custom_types import NavSelected
from components import Home

log = logging.getLogger()
app = Volt()

# Easily wrap your handlers in middleware!
@app.middleware
async def logging_middleware(request, handler):
    start = time.time()
    response = await handler(request)
    end = time.time() - start
    log.info(f"Request - Path: {request.path}, Time: {end * 1_000 * 1_000}μs")
    return response

# Routes and handlers are simple to define
@app.route("/", method="GET")
def root(request: HttpRequest) -> HttpResponse:
    context = Home.Context(
        request=request,
        selected=NavSelected.HOME,  # HTMX Powered!
    )
    return http.Response(
        Home(context).render(request),
    )


if __name__ == "__main__":
    uvicorn.run(...)
```

## Platform Support:
- ✅ Linux
- ✅ macOS
- ✅ Windows

## Why ASGI?

WSGI servers limit your web application to one request being handled at a time, to completion. ASGI supercharges your handlers, leveraging Pythons asynchronous capabilities, enabling efficient task switching _across handlers, across requests_! Learn more [here](https://asgi.readthedocs.io)

## Current Status

⚠️ **Alpha Release** - Volt is in early development. Core functionality is well underway, but Volt is not production-ready just yet. Keep an eye out for a 1.x release!

**Working:**
- HTTP server and request routing
- Custom middleware support
- Header handling
- Static file serving
- Built-in templating engine
- Template component generation

**Coming Soon:**
- ORM integration
- Advanced middleware (CSRF, CORS, etc.)
- Production deployment tools

## Philosophy

Volt is opinionated by design. Like Django, we believe in convention over configuration, but we take it further - aiming to make it as simple as possible to create a production ready SPA-like web application that is a delight to work on, and doesn't compromise.

Volt gives you the full stack in one package, optimized from the ground up.

---

*Volt is in active development. Star this repo to follow progress.*
