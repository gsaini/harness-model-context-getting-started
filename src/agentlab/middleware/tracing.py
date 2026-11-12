"""Record what the agent did and, above all, what was in the context window when it did it.

Two views come out of one trace:

- the trajectory: the sequence of thoughts, tool calls and results (what happened);
- the window:     for any single model call, exactly what was sent and where each part came from (why).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from agentlab.harness import Middleware, Response, RunResult, State
from agentlab.messages import Section, estimate_tokens
from agentlab.models.scripted import SUMMARY_MARKER

CLIP = 2_000


def window_breakdown(sections: list[Section], request: dict) -> dict:
    """Token counts for one request, by where the content came from."""
    parts = {"system": estimate_tokens(request["system"]), "tools": estimate_tokens(request["tools"])}
    seen_task = False
    for message in request["messages"]:
        blocks = message["content"]
        if message["role"] == "assistant":
            kind = "assistant"
        elif any(b.get("type") == "tool_result" for b in blocks):
            kind = "tool_results"
        elif any(SUMMARY_MARKER in b.get("text", "") for b in blocks):
            kind, seen_task = "summary", True
        else:
            kind, seen_task = ("user" if seen_task else "task"), True
        parts[kind] = parts.get(kind, 0) + estimate_tokens(message)
    return {
        "total": sum(parts.values()),
        "parts": parts,
        "system_sections": {s.source: estimate_tokens(s.text) for s in sections},
    }


def _clip(value: str) -> str:
    return value if len(value) <= CLIP else value[:CLIP] + f"… [{len(value) - CLIP:,} more characters]"


class Tracer(Middleware):
    """Put it first in the middleware list: as the outermost layer it also sees calls that others block."""

    name = "tracer"

    def __init__(self, path: Path | None = None, *, keep_windows: bool = True):
        self.path = Path(path) if path else None
        self.keep_windows = keep_windows
        self.events: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def record(self, event: dict) -> None:
        self.events.append(event)
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def before_agent(self, state: State) -> None:
        self.record(
            {
                "type": "run_start",
                "task": state.task,
                "model": state.model.name,
                "context_window": state.model.context_window,
                "tools": [tool["name"] for tool in state.tools],
                "sections": [{"source": s.source, "tokens": estimate_tokens(s.text), **s.meta} for s in state.sections],
            }
        )

    def wrap_model_call(self, request: dict, call_next: Callable[[dict], Response], state: State) -> Response:
        event = {"type": "model_call", "step": state.step, "window": window_breakdown(state.sections, request)}
        if self.keep_windows:  # a snapshot: the live message list keeps growing after this call
            event["request"] = json.loads(json.dumps(request, ensure_ascii=False, default=str))
        started = time.perf_counter()
        try:
            response = call_next(request)
        except Exception as exc:
            self.record({**event, "error": f"{type(exc).__name__}: {exc}"})
            raise
        event.update(
            response={"content": response.content, "stop_reason": response.stop_reason, "meta": response.meta},
            usage=response.usage,
            ms=round((time.perf_counter() - started) * 1000, 1),
        )
        self.record(event)
        return response

    def wrap_tool_call(self, call: dict, call_next: Callable[[dict], str], state: State) -> str:
        event = {"type": "tool_call", "step": state.step, "name": call["name"], "input": call.get("input")}
        try:
            output = call_next(call)
        except Exception as exc:
            self.record({**event, "is_error": True, "output": str(exc)})
            raise
        self.record({**event, "is_error": False, "output": _clip(output)})
        return output

    def on_event(self, event: dict, state: State) -> None:
        self.record({**event, "step": state.step})

    def after_agent(self, result: RunResult, state: State) -> None:
        self.record(
            {
                "type": "run_end",
                "status": result.status,
                "steps": result.steps,
                "answer": result.answer,
                "error": result.error,
                "usage": result.usage,
                "cost": result.cost,
            }
        )


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
