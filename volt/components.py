from datetime import datetime
import logging
from collections import namedtuple
from dataclasses import asdict, dataclass
from typing import Any

from jinja2 import Environment, FileSystemLoader
from jinja2_fragments import render_block

from volt.router import HttpRequest

log = logging.getLogger("volt.py")

environment = Environment(loader=FileSystemLoader("templates/"))

def nice_time(value: Any):
    if not isinstance(value, datetime):
        raise ValueError("nice_time filter only accepts type 'datetime'")

    return value.strftime("%H:%M%p") 

environment.filters['nice_time'] = nice_time

Block = namedtuple("Block", ["template_name", "block_name"])


class Component:
    """
    The Component class is the container for information pertaining to a particular 'block'
    in a template. A component will associate a block within a template, with a set context
    class for that block, which should contain all of the fields required for that block to
    render. Ideally, there should be exactly one Component class defined, for every block.
    """

    template_name: str
    block_name: str = "content"

    @dataclass
    class Context:
        """
        The component assumes the block to be called 'content' if no alternative is provided,
        and will natively handle HTMX partial requests, by returning individual blocks. Out-Of-Band
        swaps can be created adding Components to the 'oob' field in the Context, and setting
        hx-select-oob="#id-of-oob-block" in the block template.
        """

        request: HttpRequest
        oob: list["Component"]

    context: Context

    def __init__(self, context: Context) -> None:
        self.context = context

    def render(self, request: HttpRequest) -> str:
        if request.hx_request:
            context = asdict(self.context)
            html = render_block(
                environment,
                self.template_name,
                request.hx_fragment
                if request.hx_fragment is not None
                else self.block_name,
                context,
            )
            for component in self.context.oob:
                html += render_block(
                    environment,
                    component.template_name,
                    component.block_name,
                    asdict(component.context),
                )
            return html

        context = asdict(self.context)
        template = environment.get_template(self.template_name)
        html = template.render(context)
        return html

#
# # NOTE: Not sure how _this_ would be generated
# class NavSelected(StrEnum):
#     HOME = "home"
#     FEATURES = "features"
#     DEMO = "demo"
#     PERFORMANCE = "performance"
#     QUICKSTART = "quickstart"
#
#
# class NavBar(Component):
#     template_name: str = "base.html"
#     block_name: str = "navbar"
#
#     @dataclass
#     class Context(Component.Context):
#         selected: NavSelected
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
#
#
# class Base(Component):
#     template_name: str = "base.html"
#
#     @dataclass
#     class Context(Component.Context):
#         selected: NavSelected
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
#
#
# # vvv Tentatively thinking these component classes should be generated? vvv #
# class Home(Base):
#     template_name: str = "home.html"
#
#     @dataclass
#     class Context(Base.Context): ...
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
#
#
# class Features(Base):
#     template_name: str = "features.html"
#
#     @dataclass
#     class Context(Base.Context): ...
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
#
#
# @dataclass
# class ProgrammingLanguage:
#     name: str
#     abbrev: str
#     description: str
#     category: str
#     text_colour: str
#     bg_colour: str
#
#
# class DemoLanguages(Component):
#     template_name: str = "demo.html"
#     block_name: str = "programming_language_list"
#
#     @dataclass
#     class Context(Component.Context):
#         programming_languages: list[ProgrammingLanguage]
#         searching: bool
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
#
#
# class DemoCounter(Component):
#     template_name: str = "demo.html"
#     block_name: str = "counter"
#
#     @dataclass
#     class Context(Component.Context):
#         value: int
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
#
#
# class DemoTasks(Component):
#     template_name: str = "demo.html"
#     block_name: str = "task_list"
#
#     @dataclass
#     class Context(Component.Context):
#         tasks: list[str]
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
#
# @dataclass
# class ChatMessage:
#     message: str
#     time: datetime
#
# class DemoChatMessages(Component):
#     template_name: str = "demo.html"
#     block_name: str = "chat_messages"
#
#     @dataclass
#     class Context(Component.Context):
#         messages: list[ChatMessage]
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
#
# class Demo(Base):
#     template_name: str = "demo.html"
#
#     @dataclass
#     class Context(
#         Base.Context,
#         DemoLanguages.Context,
#         DemoCounter.Context,
#         DemoTasks.Context,
#     ):
#         tasks: list[str]
#         value: int
#
#     def __init__(self, context: Context) -> None:
#         super().__init__(context)
