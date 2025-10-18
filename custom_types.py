# pyright: basic
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypedDict


class NavSelected(StrEnum):
    HOME = "home"
    FEATURES = "features"
    DEMO = "demo"
    PERFORMANCE = "performance"
    QUICKSTART = "quickstart"


class BaseNavbarTypes:
    selected = NavSelected


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


class Sender(StrEnum):
    ME = "me"
    THEM = "them"


Message = TypedDict("Message", {"message": str, "sender": Sender, "time": datetime})


class DemoChatMessagesTypes:
    chat_messages = list[Message]


class DemoContentTypes:
    searching = DemoProgrammingLanguageListTypes.searching
    programming_languages = DemoProgrammingLanguageListTypes.programming_languages
    tasks = DemoTaskListTypes.tasks
    value = DemoCounterTypes.value
    chat_messages = DemoChatMessagesTypes.chat_messages
