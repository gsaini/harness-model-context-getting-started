"""File tools confined to one workspace directory.

Two edit tools do the same job in different shapes: `edit_file` (replace an exact string, the shape most
coding models were trained on) and `patch_lines` (replace a range of line numbers). Lesson 5 shows why the
shape matters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MAX_READ_CHARS = 20_000
MAX_LISTED = 200
_TYPES = {"string": str, "integer": int, "boolean": bool}


class ToolError(Exception):
    """A tool refused or failed in a way the model can act on. The harness sends the message back to it."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., str]

    def spec(self) -> dict:
        """What the model sees."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    def validate(self, arguments: object) -> dict:
        """Tool input is model output: check it before running anything."""
        if not isinstance(arguments, dict):
            raise ToolError(f"{self.name}: input must be an object")
        properties = self.input_schema.get("properties", {})
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            raise ToolError(f"{self.name}: unknown field(s) {', '.join(unknown)}")
        for key in self.input_schema.get("required", []):
            if key not in arguments:
                raise ToolError(f"{self.name}: missing required field {key!r}")
        for key, value in arguments.items():
            expected = _TYPES.get(properties[key].get("type"))
            if expected and (not isinstance(value, expected) or (expected is int and isinstance(value, bool))):
                raise ToolError(f"{self.name}: {key!r} must be a {properties[key]['type']}")
        return arguments


class Workspace:
    """The one directory the agent may touch. Every path a tool receives goes through `resolve`."""

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    def resolve(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative.strip():
            raise ToolError("path must be a non-empty string")
        target = (self.root / relative).resolve()  # follows symlinks and `..`; an absolute path replaces root
        if target != self.root and self.root not in target.parents:
            raise ToolError(f"{relative!r} is outside the workspace")
        return target

    def read(self, relative: str) -> str:
        target = self.resolve(relative)
        if not target.is_file():
            raise ToolError(f"{relative}: no such file")
        return target.read_text(encoding="utf-8")


def _schema(required: list[str], **properties: tuple[str, str]) -> dict:
    return {
        "type": "object",
        "properties": {name: {"type": kind, "description": about} for name, (kind, about) in properties.items()},
        "required": required,
        "additionalProperties": False,
    }


def file_tools(workspace: Workspace, edit: str = "edit_file") -> list[Tool]:
    """list / read / write plus one edit tool: "edit_file" or "patch_lines"."""

    def list_files(dir: str = ".") -> str:
        base = workspace.resolve(dir)
        if not base.is_dir():
            raise ToolError(f"{dir}: no such directory")
        found = sorted(
            p.relative_to(workspace.root).as_posix() for p in base.rglob("*") if p.is_file() and ".git" not in p.parts
        )
        extra = f"\n… and {len(found) - MAX_LISTED} more" if len(found) > MAX_LISTED else ""
        return "\n".join(found[:MAX_LISTED]) + extra if found else "(no files)"

    def read_file(path: str) -> str:
        content = workspace.read(path)
        if len(content) > MAX_READ_CHARS:
            return content[:MAX_READ_CHARS] + f"\n… [{len(content) - MAX_READ_CHARS:,} more characters not shown]"
        return content

    def write_file(path: str, content: str) -> str:
        target = workspace.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} characters to {path}"

    def edit_file(path: str, old_str: str, new_str: str) -> str:
        content = workspace.read(path)
        count = content.count(old_str) if old_str else 0
        if count == 0:
            raise ToolError(f"old_str not found in {path}. Read the file and copy the exact text.")
        if count > 1:
            raise ToolError(f"old_str matches {count} places in {path}. Include more surrounding text.")
        workspace.resolve(path).write_text(content.replace(old_str, new_str, 1), encoding="utf-8")
        return f"edited {path}"

    def patch_lines(path: str, start_line: int, end_line: int, new_text: str) -> str:
        content = workspace.read(path)
        lines = content.split("\n")
        if not 1 <= start_line <= len(lines) or not start_line - 1 <= end_line <= len(lines):
            raise ToolError(f"lines {start_line}-{end_line} are out of range: {path} has {len(lines)} lines")
        lines[start_line - 1 : end_line] = new_text.split("\n")
        workspace.resolve(path).write_text("\n".join(lines), encoding="utf-8")
        return f"replaced lines {start_line}-{end_line} of {path}"

    path = ("string", "Path relative to the workspace root.")
    tools = [
        Tool(
            "list_files",
            "List every file under a directory (recursive), as paths relative to the workspace root.",
            _schema([], dir=("string", "Directory to list. Defaults to the workspace root.")),
            list_files,
        ),
        Tool("read_file", "Read a text file.", _schema(["path"], path=path), read_file),
        Tool(
            "write_file",
            "Create a file, or replace its whole content.",
            _schema(["path", "content"], path=path, content=("string", "The complete new content.")),
            write_file,
        ),
    ]
    if edit == "edit_file":
        tools.append(
            Tool(
                "edit_file",
                "Replace one exact string in a file. old_str must appear exactly once.",
                _schema(
                    ["path", "old_str", "new_str"],
                    path=path,
                    old_str=("string", "Exact text to replace, copied from the file."),
                    new_str=("string", "Text to put in its place."),
                ),
                edit_file,
            )
        )
    elif edit == "patch_lines":
        tools.append(
            Tool(
                "patch_lines",
                "Replace lines start_line..end_line (1-based, inclusive) of a file with new_text.",
                _schema(
                    ["path", "start_line", "end_line", "new_text"],
                    path=path,
                    start_line=("integer", "First line to replace."),
                    end_line=("integer", "Last line to replace."),
                    new_text=("string", "Replacement text; may span several lines."),
                ),
                patch_lines,
            )
        )
    else:
        raise ValueError(f"unknown edit tool {edit!r}")
    return tools
