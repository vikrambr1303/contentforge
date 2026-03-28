import importlib
import pkgutil
from typing import TYPE_CHECKING

import plugins

if TYPE_CHECKING:
    from plugins.base import SocialMediaPlugin

_registry: dict[str, "SocialMediaPlugin"] = {}


def load_plugins() -> None:
    _registry.clear()
    for _finder, name, _ispkg in pkgutil.iter_modules(plugins.__path__):
        if name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"plugins.{name}.plugin")
            if hasattr(module, "Plugin"):
                p = module.Plugin()
                _registry[p.name] = p
        except Exception:
            continue


def get_plugin(name: str) -> "SocialMediaPlugin":
    return _registry[name]


def list_plugins() -> list["SocialMediaPlugin"]:
    return list(_registry.values())
