"""Rules the model cannot talk its way around, because the harness enforces them outside the model."""

from __future__ import annotations

import posixpath
from collections.abc import Callable, Sequence

from agentlab.harness import Middleware, State
from agentlab.tools import ToolError


class ProtectPaths(Middleware):
    """Block every tool call that names a protected file, whatever the tool and however the path is spelled."""

    name = "policy:protect-paths"

    def __init__(self, names: Sequence[str] = (".env",)):
        self.names = set(names)

    def wrap_tool_call(self, call: dict, call_next: Callable[[dict], str], state: State) -> str:
        arguments = call.get("input") or {}
        for key in ("path", "dir"):
            value = arguments.get(key)
            if isinstance(value, str) and self._protected(value):
                state.emit({"type": "blocked", "tool": call["name"], "path": value, "by": self.name})
                raise ToolError(f"blocked by policy: {value} is protected and agents may not touch it")
        return call_next(call)

    def _protected(self, path: str) -> bool:
        parts = posixpath.normpath(path.replace("\\", "/")).split("/")
        return any(part in self.names for part in parts)
