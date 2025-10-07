# pyright: basic
from dataclasses import dataclass
from enum import StrEnum


class NavSelected(StrEnum):
    HOME = "home"
    FEATURES = "features"
    DEMO = "demo"
    PERFORMANCE = "performance"
    QUICKSTART = "quickstart"


class BaseNavbarTypes:
    selected = NavSelected


class DemoContentTypes:
    searching = bool
    programming_languages = list[str]
    tasks = list[str]
    value = int
    chat_messages = list[str]


@dataclass
class DemoProgrammingLanguage:
    name: str
    abbrev: str
    description: str
    category: str
    text_colour: str
    bg_colour: str


class DemoProgrammingLanguageListTypes:
    searching = bool
    programming_languages = list[DemoProgrammingLanguage]


class DemoTaskListTypes:
    tasks = list[str]


class DemoCounterTypes:
    value = int


class DemoChatMessagesTypes:
    chat_messages = list[str]
