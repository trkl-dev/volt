import ipaddress
import logging
import os
from pathlib import Path
import tomllib
from typing import Any, TypeVar

from volt.log import volt_parent

log = logging.getLogger("volt.config.py")

pyproject_toml = {}
if Path("pyproject.toml").exists():
    with open("pyproject.toml", "rb") as f:
        pyproject_toml = tomllib.load(f)
    log.info("Found project pyproject.toml... Checking for configuration options")
else:
    log.info("No project pyproject.toml... Using config defaults")

# If not given an explicit config name, we take the top level tool.volt from pyproject.toml
# If we do receive an explicit config name, we take that as tool.volt.<config_name>
# Variables should be able to be defined at the top level, and be overwritten on a per config basis
# i.e. a base config, then say dev/prod specific overrides
volt_config_name = os.environ.get("VOLT_CONFIG")
log.info("volt_config_name: %s", volt_config_name)
# Top level config
_volt_config: dict[str, Any] = pyproject_toml.get("tool", {}).get("volt", {})
# Env specific config
_volt_config_env: dict[str, Any] = {}
if volt_config_name is not None:
    _volt_config_env = _volt_config.get(volt_config_name, {})


T = TypeVar("T")


def get_config_value(name: str, default: T) -> T:
    value = os.environ.get(
        f"VOLT_{name.upper()}",
        _volt_config_env.get(name, _volt_config.get(name, default)),
    )
    if not isinstance(value, type(default)):
        log.warning(
            f"{name} config var could not be parsed as {type(default)}, defaulting to {default}"
        )
        return default

    return value


# For logging levels throughout the application
log_level = get_config_value("log_level", default="INFO").upper()
log.info("log_level: %s", log_level)
volt_parent.setLevel(log_level)


# For Jinja2 Environment.auto_reload. Default: False
template_auto_reload = get_config_value("template_auto_reload", default=False)
log.debug("template_auto_reload: %s", template_auto_reload)


# IP Address to run the server on. Default 127.0.0.1
server_host = get_config_value("server_host", default="127.0.0.1")
# Validate IP Address
_ = ipaddress.ip_address(server_host)
log.debug("server_host: %s", server_host)


# Port to run the server on. Default 1234
server_port = get_config_value("server_port", default=1234)
log.debug("server_port: %s", server_port)

debug = get_config_value("debug", default=False)
log.debug("debug: %s", debug)
