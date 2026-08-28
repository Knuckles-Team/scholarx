#!/usr/bin/env python

import importlib
import inspect
from typing import Any

__all__: list[str] = []

CORE_MODULES: list[str] = ["scholarx.models", "scholarx.api_client", "scholarx.deduplication", "scholarx.paper_storage"]

OPTIONAL_MODULES = {"scholarx.agent_server": "agent_server", "scholarx.mcp_server": "mcp_server"}


def _expose_members(module):
    """Expose public classes and functions from a module into globals and __all__."""
    for name, obj in inspect.getmembers(module):
        if (inspect.isclass(obj) or inspect.isfunction(obj)) and not name.startswith("_"):
            globals()[name] = obj
            if name not in __all__:
                __all__.append(name)


# Eagerly import core modules (keeps API wrappers fast & light)
for module_name in CORE_MODULES:
    if module_name:
        module = importlib.import_module(module_name)
        _expose_members(module)

# Dynamic/lazy loading of optional modules (agent_server, mcp_server)
_loaded_optional_modules: dict[str, Any] = {}


def _import_module_safely(module_name: str):
    """Try to import a module and return it, or None if not available."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


_AVAILABILITY_FLAG_MARKERS = {"_MCP_AVAILABLE": "mcp_server", "_AGENT_AVAILABLE": "agent_server"}


def _resolve_availability_flag(name: str) -> bool | None:
    """Resolve a dynamic `_..._AVAILABLE` flag without eager imports.

    Returns the flag's bool value, or None if `name` isn't one of these flags.
    """
    marker = _AVAILABILITY_FLAG_MARKERS.get(name)
    if marker is None:
        return None
    module_key = next((k for k in OPTIONAL_MODULES if marker in k), None)
    if not module_key:
        return False
    return _import_module_safely(module_key) is not None


def _lookup_optional_attribute(name: str) -> Any:
    """Lazily import each optional module (exposing its public members) until
    one defines `name`; raise AttributeError if none do."""
    for module_name in OPTIONAL_MODULES:
        if module_name not in _loaded_optional_modules:
            module = _import_module_safely(module_name)
            if module is not None:
                _loaded_optional_modules[module_name] = module
                _expose_members(module)

        module = _loaded_optional_modules.get(module_name)
        if module is not None and hasattr(module, name):
            return getattr(module, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __getattr__(name: str) -> Any:
    flag = _resolve_availability_flag(name)
    if flag is not None:
        return flag
    return _lookup_optional_attribute(name)


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
