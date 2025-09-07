"""This file would be theoretically generated"""
from dataclasses import dataclass
from volt.router import HttpRequest, Component
from enum import StrEnum


# NOTE: Not sure how _this_ would be generated
class NavSelected(StrEnum):
    HOME = "home"
    FEATURES = "features"


# Linked to base.html
@dataclass
class BaseContext:
    request: HttpRequest
    selected: NavSelected


class Home(Component):
    template_name = "home.html"

    @dataclass
    class Context(BaseContext):
        ...

    def __init__(self, context: Context) -> None:
        super().__init__()

        self.context = context


class Features(Component):
    template_name = "features.html"

    @dataclass
    class Context(BaseContext):
        ...

    def __init__(self, context: Context) -> None:
        super().__init__()

        self.context = context
