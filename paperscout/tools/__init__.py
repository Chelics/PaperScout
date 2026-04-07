from typing import Callable

_registry: dict[str, dict] = {}


def register(schema: dict, executor: Callable[[dict], str]) -> None:
    """Register a tool by its schema and executor function."""
    _registry[schema["name"]] = {"schema": schema, "executor": executor}


def get_all_tools() -> list[dict]:
    """Return all registered tool schemas (passed to Claude API)."""
    return [entry["schema"] for entry in _registry.values()]


def dispatch(tool_name: str, tool_input: dict) -> str:
    """Execute a registered tool by name."""
    if tool_name not in _registry:
        raise ValueError(f"Unknown tool: {tool_name}")
    return _registry[tool_name]["executor"](tool_input)


def load_all() -> None:
    """Import all tool modules to trigger their self-registration."""
    from . import skill_loader  # noqa: F401
    from . import arxiv         # noqa: F401
