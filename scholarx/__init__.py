#!/usr/bin/env python
"""ScholarX — Universal Research Paper API.

A single entry point for querying research papers from arXiv, PMC,
bioRxiv, medRxiv, PsyArXiv, OSF, and Semantic Scholar.
"""

import importlib
import inspect

__all__: list[str] = []

CORE_MODULES = [
    "scholarx.models",
    "scholarx.api_client",
    "scholarx.deduplication",
    "scholarx.paper_storage",
]

OPTIONAL_MODULES = {
    "scholarx.agent_server": "agent_server",
    "scholarx.mcp_server": "mcp_server",
}


def _import_module_safely(module_name: str):
    """Try to import a module and return it, or None if not available."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def _expose_members(module):
    """Expose public classes and functions from a module into globals and __all__."""
    for name, obj in inspect.getmembers(module):
        if (inspect.isclass(obj) or inspect.isfunction(obj)) and not name.startswith("_"):
            globals()[name] = obj
            __all__.append(name)


for _module_name in CORE_MODULES:
    _module = _import_module_safely(_module_name)
    if _module is not None:
        _expose_members(_module)

for _module_name, _extra_name in OPTIONAL_MODULES.items():
    _module = _import_module_safely(_module_name)
    if _module is not None:
        _expose_members(_module)
        globals()[f"_{_extra_name.upper()}_AVAILABLE"] = True
    else:
        globals()[f"_{_extra_name.upper()}_AVAILABLE"] = False

__all__.extend(["_MCP_AVAILABLE", "_AGENT_AVAILABLE"])

_MCP_AVAILABLE = globals().get("_MCP_SERVER_AVAILABLE", False)
_AGENT_AVAILABLE = globals().get("_AGENT_SERVER_AVAILABLE", False)
