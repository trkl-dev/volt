import logging
import os
from typing import override


class ColorFormatter(logging.Formatter):
    COLORS: dict[str, str] = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET: str = "\033[0m"

    @override
    def format(self, record: logging.LogRecord):
        log_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


# Setup logging configuration
formatter = ColorFormatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s", datefmt="%H:%M:%S"
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)

volt_parent = logging.getLogger("volt")
volt_parent.addHandler(handler)

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
volt_parent.setLevel(log_level)
