"""The shapes that flow through the loop: messages made of content blocks.

They follow the Anthropic Messages format (text / tool_use / tool_result blocks), kept as plain dicts so
every part of the lab — the stand-in model, the middleware, the traces — can read and count them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

Block = dict[str, Any]
Message = dict[str, Any]


@dataclass
class Section:
    """One labelled piece of the system prompt, so a trace can say where every token came from."""

    source: str  # base | instructions | knowledge | memory
    text: str
    meta: dict = field(default_factory=dict)


def text(value: str) -> Block:
    return {"type": "text", "text": value}


def tool_use(call_id: str, name: str, arguments: dict) -> Block:
    return {"type": "tool_use", "id": call_id, "name": name, "input": arguments}


def tool_result(call_id: str, content: str, is_error: bool = False) -> Block:
    block: Block = {"type": "tool_result", "tool_use_id": call_id, "content": str(content)}
    if is_error:
        block["is_error"] = True
    return block


def user(content: str | list[Block]) -> Message:
    return {"role": "user", "content": [text(content)] if isinstance(content, str) else content}


def assistant(content: list[Block]) -> Message:
    return {"role": "assistant", "content": content}


def text_of(message: Message) -> str:
    return "\n".join(b["text"] for b in message["content"] if b.get("type") == "text")


def estimate_tokens(value: object) -> int:
    """A rough token count (~4 characters per token). Real models report exact usage; this is for the
    stand-in model and for showing what fills the context window."""
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return (len(raw) + 3) // 4


def request_tokens(system: str, messages: list[Message], tools: list[dict]) -> int:
    return estimate_tokens(system) + estimate_tokens(tools) + sum(estimate_tokens(m) for m in messages)
