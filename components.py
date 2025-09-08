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
    """
    The Component class is the container for information pertaining to a particular 'block' 
    in a template. A component will associate a block within a template, with a set context 
    class for that block, which should contain all of the fields required for that block to 
    render. Ideally, there should be exactly one Component class defined, for every block.
    """
    template_name: str
    block_name = "content"

    @dataclass
    class Context:
        """
        The component assumes the block to be called 'content' if no alternative is provided, 
        and will natively handle HTMX partial requests, by returning individual blocks. Out-Of-Band
        swaps can be created adding Components to the 'oob' field in the Context, and setting
        hx-select-oob="#id-of-oob-block" in the block template.
        """
        request: HttpRequest
        oob: List['Component']

    context: Context

    def __init__(self, context: Context) -> None:
        self.context = context

    def render(self, request: HttpRequest) -> str:
        if request.hx_request:
            context = asdict(self.context)
            html = render_block(environment, self.template_name, request.hx_fragment, context)
            for component in self.context.oob:
                html += render_block(environment, component.template_name, component.block_name, asdict(component.context))
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


class NavBar(Component):
    template_name = "base.html"
    block_name = "navbar"

    @dataclass
    class Context(Component.Context):
        selected: NavSelected

    def __init__(self, context: Context) -> None:
        super().__init__(context)


class Base(Component):
    template_name = "base.html"

    @dataclass
    class Context(Component.Context):
        selected: NavSelected

    def __init__(self, context: Context) -> None:
        super().__init__(context)


# vvv Tentatively thinking these component classes should be generated? vvv #
class Home(Base):
    template_name = "home.html"

    @dataclass
    class Context(Base.Context): ...

    def __init__(self, context: Context) -> None:
        super().__init__(context)


class Features(Base):
    template_name = "features.html"

    @dataclass
    class Context(Base.Context): ...

    def __init__(self, context: Context) -> None:
        super().__init__(context)
