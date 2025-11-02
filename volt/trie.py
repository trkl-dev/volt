import logging
from typing import Callable


log = logging.getLogger("volt.test.py")
log.setLevel(logging.DEBUG)

class Node:
    def __init__(self) -> None:
        self.children: list['Node'] = []
        self.segment = ""
        self.is_end_of_route = False
        self.handler: Callable | None = None

    def __repr__(self) -> str:
        return f"{self.segment}{self.children}"


def insert(root: Node, route: str, handler: Callable) -> None:
    curr = root

    if route == "/":
        root.handler = handler
        return
    
    if route.startswith("/"):
        route = route[1:]

    segments = route.split("/")
    log.debug(f"inserting segments: {segments}")
    for segment in route.split("/"):
        segment_found = False
        for child in curr.children:
            if child.segment != segment:
                continue

            log.debug(f"segment {segment} found. indexing deeper...")
            curr = child
            segment_found = True
            break

        if segment_found:
            continue

        log.debug(f"segment {segment} not found, creating node")
        new_node = Node()
        new_node.segment = segment
        curr.children.append(new_node)
    
