from http import HTTPMethod
import logging
from enum import StrEnum
from typing import Generic, TypeVar, final, override

log = logging.getLogger("volt.test.py")
log.setLevel(logging.DEBUG)

RouteParams = dict[str, str | int]


class ParamValueType(StrEnum):
    STRING = "str"
    INTEGER = "int"


T = TypeVar("T")


@final
class Node(Generic[T]):
    def __init__(self) -> None:
        self.children: dict[str, "Node[T]"] = {}
        self.is_end_of_route = False
        self.handlers: dict[HTTPMethod, T] = {}
        self.route_param_name = ""
        self.route_param_value_type: ParamValueType | None = None

    @override
    def __repr__(self) -> str:
        if self.route_param_name == "":
            return f"[end={self.is_end_of_route}]{self.children}"
        return f"{self.route_param_name}|{self.route_param_value_type}[end={self.is_end_of_route}]{self.children}"


class MultipleRouteParamsError(Exception): ...


class DuplicateMethodHandlersError(Exception):
    def __init__(self, route: str, method: HTTPMethod, *args: object) -> None:
        super().__init__(
            f"Multiple handlers cannot be assigned to the same method for a route, {route}, {method}", *args
        )


def insert(root: Node[T], route: str, method: HTTPMethod, handler: T) -> None:
    current_node = root

    if route == "/":
        if root.handlers.get(method):
            raise DuplicateMethodHandlersError(route, method)
        root.handlers[method] = handler
        return

    if route.startswith("/"):
        route = route[1:]

    segments = route.split("/")
    log.debug(f"inserting segments: {segments}")
    for segment in segments:
        child = current_node.children.get(segment)

        if child is not None:
            log.debug(f"segment {segment} found")
            current_node = child
            continue

        log.debug(f"segment {segment} not found, creating node")

        new_node = Node[T]()
        current_node.children[segment] = new_node

        # Check if segment contains route params, i.e. {id:int}, {name:str}, etc.
        if len(segment) > 3 and segment.startswith("{") and segment.endswith("}"):
            log.debug("children: %s", list(current_node.children))

            for existing_child_key, existing_child_value in current_node.children.items():
                if existing_child_value.route_param_name != "":
                    raise MultipleRouteParamsError(
                        f"Unable to insert route {route} which contains route param segment {segment} which conflicts with existing segment {existing_child_key}"
                    )
            params = segment[1:-1].split(":")
            assert len(params) == 2
            log.debug("params: %s, options: %s", params, ParamValueType)
            new_node.route_param_name = params[0]
            new_node.route_param_value_type = ParamValueType(params[1])

        current_node = new_node

    if current_node.handlers.get(method):
        raise DuplicateMethodHandlersError(route, method)

    current_node.is_end_of_route = True
    current_node.handlers[method] = handler

    log.debug("Finished insert. Trie: %s", root)


@final
class MatchedRoute(Generic[T]):
    def __init__(self, handler: T, route_params: RouteParams) -> None:
        self.handler = handler
        self.route_params = route_params


class RouteParamParseError(Exception): ...


def get(root: Node[T], route: str, method: HTTPMethod) -> MatchedRoute[T] | None:
    current_node = root

    if route == "/":
        if current_node.handlers.get(method) is None:
            return

        return MatchedRoute(current_node.handlers[method], {})

    if route.startswith("/"):
        route = route[1:]

    segments = route.split("/")
    log.debug("route: %s, get segments %s", route, segments)

    route_params: RouteParams = {}

    for segment in segments:
        child = current_node.children.get(segment)
        if child is not None:
            log.debug("segment %s found. indexing deeper...", segment)
            current_node = child
            continue

        # We want to check for any params segments if we don't find a child
        log.debug("checking route params for segment %s", segment)
        route_params_found = False
        for child_segment, child_node in current_node.children.items():
            if child_node.route_param_name == "":
                continue

            log.debug("found route param %s", child_node.route_param_name)

            assert child_node.route_param_value_type is not None
            match child_node.route_param_value_type:
                case ParamValueType.STRING:
                    route_params[child_node.route_param_name] = segment
                case ParamValueType.INTEGER:
                    try:
                        route_params[child_node.route_param_name] = int(segment)
                    except ValueError:
                        raise RouteParamParseError(
                            f"Unable to parse route param segment {segment} as integer, as per {child_segment}"
                        )

            route_params_found = True
            current_node = child_node
            break

        # Not finding route params means the route doesn't match, so we exit
        if not route_params_found:
            log.debug("could not find child segment or route params, no route found")
            return

    if not current_node.is_end_of_route:
        log.debug("not end of route, no route found")
        return

    if current_node.handlers.get(method) is None:
        return

    return MatchedRoute(current_node.handlers[method], route_params)
