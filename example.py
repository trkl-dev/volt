import time
import logging
from http import HTTPStatus

from volt.router import Handler, HttpRequest, HttpResponse, Redirect, route, middleware, run_server

from components_gen import Features, Home, BaseNavbar, Demo, DemoTaskList, DemoProgrammingLanguageList, DemoCounter
from custom_types import NavSelected, DemoProgrammingLanguage


mw_log = logging.getLogger('volt.middleware.py')
log = logging.getLogger('volt.py')


@middleware
def logging_middleware(request: HttpRequest, handler: Handler) -> HttpResponse:
    start = time.time()
    response = handler(request)
    end = time.time() - start
    mw_log.info(f"Request - Path: {request.path}, Time: {end * 1_000 * 1_000 }μs")
    return response


@middleware
def auth(request: HttpRequest, handler: Handler) -> HttpResponse:
    auth_success = True
    if auth_success:
        return handler(request)
    return HttpResponse(body="get outta here!", status=HTTPStatus.FORBIDDEN)


@route("/", method="GET")
def root(request: HttpRequest) -> HttpResponse:
    context = Home.Context(
        request=request,
        selected=NavSelected.HOME,
        oob=[BaseNavbar(BaseNavbar.Context(request=request, selected=NavSelected.HOME, oob=[]))],
    )
    return HttpResponse(
        Home(context).render(request),
    )


@route("/features", method="GET")
def features(request: HttpRequest) -> HttpResponse:
    context = Features.Context(
        request=request,
        selected=NavSelected.FEATURES,
        oob=[BaseNavbar(BaseNavbar.Context(request=request, selected=NavSelected.FEATURES, oob=[]))],
    )
    return HttpResponse(Features(context).render(request))


PROGRAMMING_LANGUAGES: list[DemoProgrammingLanguage] = [
    DemoProgrammingLanguage("Python", "Py", "High-level programming language", "Popular", "text-volt-yellow", "bg-volt-yellow/20"),
    DemoProgrammingLanguage("JavaScript", "JS", "Dynamic web programming language", "Web", "text-blue-400", "bg-blue-400/20"),
    DemoProgrammingLanguage("TypeScript", "TS", "Typed superset of JavaScript", "Web", "text-blue-500", "bg-blue-500/20"),
    DemoProgrammingLanguage("Rust", "Rs", "Systems programming language", "Systems", "text-orange-400", "bg-orange-400/20"),
    DemoProgrammingLanguage("Go", "Go", "Google's systems language", "Systems", "text-cyan-400", "bg-cyan-400/20"),
    DemoProgrammingLanguage("Java", "Jv", "Enterprise programming language", "Enterprise", "text-red-400", "bg-red-400/20"),
    DemoProgrammingLanguage("C++", "C+", "Low-level systems language", "Systems", "text-purple-400", "bg-purple-400/20"),
    DemoProgrammingLanguage("C#", "C#", "Microsoft's .NET language", "Enterprise", "text-green-400", "bg-green-400/20"),
    DemoProgrammingLanguage("Zig", "Zg", "Modern systems programming", "Systems", "text-volt-yellow", "bg-volt-yellow/20"),
    DemoProgrammingLanguage("Swift", "Sw", "Apple's iOS development language", "Mobile", "text-orange-500", "bg-orange-500/20"),
    DemoProgrammingLanguage("Kotlin", "Kt", "Modern Android development", "Mobile", "text-purple-500", "bg-purple-500/20"),
    DemoProgrammingLanguage("Ruby", "Rb", "Developer-friendly scripting", "Web", "text-red-500", "bg-red-500/20"),
    DemoProgrammingLanguage("PHP", "Php", "Server-side web language", "Web", "text-indigo-400", "bg-indigo-400/20"),
    DemoProgrammingLanguage("Dart", "Dt", "Google's Flutter language", "Mobile", "text-blue-600", "bg-blue-600/20"),
    DemoProgrammingLanguage("Elixir", "Ex", "Functional concurrent language", "Functional", "text-purple-600", "bg-purple-600/20"),
    DemoProgrammingLanguage("Haskell", "Hs", "Pure functional language", "Functional", "text-green-500", "bg-green-500/20"),
    DemoProgrammingLanguage("Clojure", "Cl", "Modern Lisp for JVM", "Functional", "text-cyan-500", "bg-cyan-500/20"),
    DemoProgrammingLanguage("Scala", "Sc", "Functional + OOP on JVM", "Enterprise", "text-red-600", "bg-red-600/20"),
    DemoProgrammingLanguage("R", "R", "Statistical computing language", "Data", "text-blue-700", "bg-blue-700/20"),
    DemoProgrammingLanguage("Julia", "Jl", "High-performance scientific computing", "Data", "text-purple-700", "bg-purple-700/20"),
]


@route("/demo", method="GET")
def demo(request: HttpRequest) -> HttpResponse:
    tasks = [
        "Learn about Volt framework",
        "Try HTMX integration",
        "Add a new task!",
    ]

    context = Demo.Context(
        request=request,
        selected=NavSelected.DEMO,
        tasks=tasks,
        searching=False,
        programming_languages=[],
        value=0,
        chat_messages=["something"],
        oob=[BaseNavbar(BaseNavbar.Context(request=request, selected=NavSelected.DEMO, oob=[]))],
    )

    return HttpResponse(Demo(context).render(request))


@route("/demo/counter/{direction:str}", method="POST")
def demo_counter(request: HttpRequest) -> HttpResponse:
    value = request.form_data.get("value", [])

    if len(value) == 0:
        log.warning("given value is empty")
        return HttpResponse(status=HTTPStatus.BAD_REQUEST)

    try:
        int_value = int(value[0])
    except Exception as e:
        log.warning(f"error converting value to integer: {e}")
        return HttpResponse(status=HTTPStatus.BAD_REQUEST)

    match request.route_params.get("direction"):
        case "increment":
            int_value += 1
        case "decrement":
            int_value -= 1
        case "reset":
            int_value = 0
        case _:
            return HttpResponse(status=HTTPStatus.NOT_FOUND)

    context = DemoCounter.Context(
        request=request,
        value=int_value,
        oob=[],
    )

    return HttpResponse(DemoCounter(context).render(request))


@route("/demo/languages/search", method="GET")
def demo_languages_search(request: HttpRequest) -> HttpResponse:
    query = request.query_params.get("query")
    if query is None or query == "":
        context = DemoProgrammingLanguageList.Context(
            request=request,
            programming_languages=[],
            searching=False,
            oob=[],
        )
        return HttpResponse(DemoProgrammingLanguageList(context).render(request))

    results: list[DemoProgrammingLanguage] = []
    for language in PROGRAMMING_LANGUAGES:
        if query.lower() in language.name.lower():
            results.append(language)

        # Just take top 5 results
        if len(results) >= 3:
            break

    context = DemoProgrammingLanguageList.Context(
        request=request,
        programming_languages=results,
        searching=True,
        oob=[],
    )

    return HttpResponse(DemoProgrammingLanguageList(context).render(request))


@route("/demo/add-task", method="POST")
def demo_add_task(request: HttpRequest) -> HttpResponse:
    task = request.form_data.get("task")
    if task is None:
        return HttpResponse(status=HTTPStatus.BAD_REQUEST)
        
    context = DemoTaskList.Context(
        request=request,
        tasks=task,  # takes a list
        oob=[],
    )
    return HttpResponse(DemoTaskList(context).render(request))


@route("/demo/task/delete", method="DELETE")
def demo_delete_task(_request: HttpRequest) -> HttpResponse:
    return HttpResponse(status=HTTPStatus.OK)


@route("/quickstart", method="GET")
def quickstart(_: HttpRequest) -> HttpResponse:
    return Redirect("/")


@route("/home", method="GET")
def home(_: HttpRequest) -> HttpResponse:
    return Redirect("/")


if __name__ == "__main__":
    run_server()
