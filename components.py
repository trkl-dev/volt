"""This file would be theoretically generated"""
from collections import namedtuple
from dataclasses import dataclass, asdict
from jinja2 import Environment, FileSystemLoader
from jinja2_fragments import render_block
from typing import List
from volt.router import HttpRequest
from enum import StrEnum


environment = Environment(loader=FileSystemLoader("templates/"))


Block = namedtuple("Block", ["template_name", "block_name"])


class Component:
    template_name: str

    @dataclass
    class Context:
        request: HttpRequest
        oob: List[Block]

    context: Context

    def __init__(self, context: Context) -> None:
        self.context = context

    def render(self, request: HttpRequest) -> str:
        if request.hx_request:
            context = asdict(self.context)
            html = render_block(environment, self.template_name, request.hx_fragment, context)
            for oob in self.context.oob:
                html += render_block(environment, oob.template_name, oob.block_name, context)
            return html

        context = asdict(self.context)
        template = environment.get_template(self.template_name)
        html = template.render(context)
        return html


# NOTE: Not sure how _this_ would be generated
class NavSelected(StrEnum):
    HOME = "home"
    FEATURES = "features"
    PERFORMANCE = "performance"
    QUICKSTART = "quickstart"


# Linked to base.html
@dataclass
class BaseContext():
    selected: NavSelected


# vvv Tentatively thinking these component classes should be generated? vvv #

class Home(Component):
    template_name = "home.html"

    @dataclass
    class Context(BaseContext, Component.Context):
        ...

    def __init__(self, context: Context) -> None:
        super().__init__(context)


class Features(Component):
    template_name = "features.html"

    @dataclass
    class Context(BaseContext, Component.Context):
        ...

    def __init__(self, context: Context) -> None:
        super().__init__(context)
