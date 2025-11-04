import logging
from http import HTTPMethod
from typing import Callable

import pytest

from volt import trie

log = logging.getLogger("volt.test.py")
log.setLevel(logging.DEBUG)


def dummy_handler():
    log.debug("handler called")
    return


type TestHandler = Callable[[], None]


def test_trie():
    root = trie.Node[TestHandler]()
    trie.insert(root, "/something", HTTPMethod.GET, dummy_handler)
    log.debug(f"trie state: {root}")

    trie.insert(root, "/something/else", HTTPMethod.GET, dummy_handler)
    log.debug(f"trie state: {root}")

    trie.insert(root, "/hi/there", HTTPMethod.GET, dummy_handler)
    log.debug(f"trie state: {root}")

    assert root.children["something"] is not None
    assert root.children["something"].is_end_of_route
    assert root.children["something"].handlers[HTTPMethod.GET] == dummy_handler

    assert root.children["something"].children["else"] is not None
    assert root.children["something"].children["else"].is_end_of_route
    assert root.children["something"].children["else"].handlers[HTTPMethod.GET] == dummy_handler

    assert root.children["hi"] is not None
    assert not root.children["hi"].is_end_of_route
    assert root.children["hi"].handlers.get(HTTPMethod.GET) is None

    assert root.children["hi"].children["there"] is not None
    assert root.children["hi"].children["there"].is_end_of_route
    assert root.children["hi"].children["there"].handlers[HTTPMethod.GET] == dummy_handler


def test_trie_root_path():
    root = trie.Node[TestHandler]()
    trie.insert(root, "/", HTTPMethod.GET, dummy_handler)

    assert len(root.children) == 0
    assert root.handlers[HTTPMethod.GET] == dummy_handler


def test_get():
    root = trie.Node[TestHandler]()
    trie.insert(root, "/foo/bar", HTTPMethod.GET, dummy_handler)
    trie.insert(root, "/foo/bar/baz", HTTPMethod.GET, dummy_handler)

    matched_route = trie.get(root, "/foo", HTTPMethod.GET)
    assert matched_route is None

    matched_route = trie.get(root, "/foo/bar", HTTPMethod.GET)
    assert matched_route is not None
    assert matched_route.handler == dummy_handler
    assert matched_route.route_params == {}

    matched_route = trie.get(root, "/foo/bar/baz", HTTPMethod.GET)
    assert matched_route is not None
    assert matched_route.handler == dummy_handler
    assert matched_route.route_params == {}

    matched_route = trie.get(root, "/not/present", HTTPMethod.GET)
    assert matched_route is None


def test_with_params():
    root = trie.Node[TestHandler]()
    trie.insert(root, "/foo/{id:int}", HTTPMethod.GET, dummy_handler)
    matched_route = trie.get(root, "/foo/3", HTTPMethod.GET)

    assert matched_route is not None
    assert matched_route.handler == dummy_handler
    assert matched_route.route_params["id"] == 3


def test_with_duplicate_params():
    root = trie.Node[TestHandler]()
    trie.insert(root, "/foo/{id:int}", HTTPMethod.GET, dummy_handler)
    with pytest.raises(trie.MultipleRouteParamsError):
        trie.insert(root, "/foo/{name:str}", HTTPMethod.GET, dummy_handler)


def test_with_invalid_route_params():
    root = trie.Node[TestHandler]()
    trie.insert(root, "/foo/{id:int}", HTTPMethod.GET, dummy_handler)
    with pytest.raises(trie.RouteParamParseError):
        _ = trie.get(root, "/foo/string", HTTPMethod.GET)


def test_with_methods():
    root = trie.Node[TestHandler]()
    trie.insert(root, "/foo/{id:int}", HTTPMethod.GET, dummy_handler)
    matched_route = trie.get(root, "/foo/3", HTTPMethod.POST)

    assert matched_route is None
