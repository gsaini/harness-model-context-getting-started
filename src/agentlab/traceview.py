"""Read a trace two ways: as a trajectory (what happened) and as a context window (what the model saw)."""

from __future__ import annotations

import json

from agentlab.messages import estimate_tokens

BAR = 40
# One letter per source, in the order the parts appear in a request.
LETTERS = {"system": "S", "tools": "T", "task": "k", "user": "u", "summary": "Σ", "assistant": "a", "tool_results": "r"}
LEGEND = "S system prompt · T tool definitions · k task · Σ summary · a the model's own turns · r tool results · . free"


def _short(value: object, limit: int = 78) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    raw = " ".join(raw.split())
    return raw if len(raw) <= limit else raw[: limit - 1] + "…"


def _args(arguments: dict | None) -> str:
    return ", ".join(f"{key}={_short(value, 44)!r}" for key, value in (arguments or {}).items())


def bar(window: dict, capacity: int) -> str:
    """The context window as a strip of letters: how full it is, and with what."""
    cells = ""
    for part, letter in LETTERS.items():
        tokens = window["parts"].get(part, 0)
        cells += letter * max(round(BAR * tokens / capacity), 1 if tokens else 0)
    return f"[{cells[:BAR].ljust(BAR, '.')}]"


def _capacity(events: list[dict]) -> int:
    window = events[0].get("context_window", 0)
    largest = max((e["window"]["total"] for e in events if e["type"] == "model_call"), default=1)
    return window if 0 < window <= 50_000 else largest  # a 1M-token window would draw as an empty strip


def trajectory(events: list[dict], *, bars: bool = True) -> str:
    """Step by step: how full the window was, what the model said, what it called, what came back."""
    capacity = _capacity(events)
    start = events[0]
    out = [f"task:  {_short(start['task'], 110)}", f"model: {start['model']}    tools: {', '.join(start['tools'])}"]
    if bars:
        out.append(f"window key: {LEGEND}")
    for event in events[1:]:
        kind = event["type"]
        if kind == "model_call":
            total = event["window"]["total"]
            strip = f"  {bar(event['window'], capacity)}" if bars else ""
            out.append(f"\n#{event['step']:<2} window {total:>5,} tokens ({total / capacity:4.0%}){strip}")
            if "error" in event:
                out.append(f"    MODEL CALL FAILED: {event['error']}")
                continue
            for block in event["response"]["content"]:
                if block.get("type") == "text":
                    out.append(f"    says:  {_short(block['text'], 104)}")
                elif block.get("type") == "tool_use":
                    out.append(f"    calls: {block['name']}({_args(block.get('input'))})")
        elif kind == "tool_call":
            mark = "ERROR " if event["is_error"] else ""
            out.append(f"    gets:  {mark}{_short(event['output'], 98)}")
        elif kind == "compaction":
            out.append(
                f"\n    ~~ compaction ({event['strategy']}): {event['before_tokens']:,} -> {event['after_tokens']:,} tokens ~~"
            )
        elif kind == "blocked":
            out.append(f"    !! {event['by']} blocked {event['tool']} on {event['path']}")
        elif kind == "run_end":
            usage = event["usage"]
            spent = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            detail = f" ({event['error']})" if event["error"] else ""
            out.append(
                f"\nend: {event['status']}{detail} · {event['steps']} model calls · {spent:,} tokens · ${event['cost']:.4f}"
            )
    return "\n".join(out)


def fill(events: list[dict]) -> str:
    """One line per model call: how full the window was and with what. Good for watching it grow."""
    capacity = _capacity(events)
    out = [f"window key: {LEGEND}"]
    for event in events:
        if event["type"] == "model_call":
            total = event["window"]["total"]
            failed = "  <- MODEL CALL FAILED" if "error" in event else ""
            out.append(
                f"#{event['step']:<2} {total:>5,} tokens {total / capacity:4.0%} {bar(event['window'], capacity)}{failed}"
            )
        elif event["type"] == "compaction":
            out.append(
                f"   ~~ compaction ({event['strategy']}): {event['before_tokens']:,} -> {event['after_tokens']:,} tokens ~~"
            )
    return "\n".join(out)


def window(events: list[dict], step: int) -> str:
    """Everything one model call was sent, part by part, with where each part came from."""
    call = next((e for e in events if e["type"] == "model_call" and e["step"] == step), None)
    if call is None:
        return f"no model call at step {step}"
    start, parts = events[0], call["window"]["parts"]
    out = [f"The context window at step {step}: {call['window']['total']:,} tokens", ""]
    out.append(f"  system prompt        {parts['system']:>6,} tokens")
    for section in start["sections"]:
        note = ""
        if section["source"] == "knowledge":
            docs = section.get("docs", [])
            note = f"  <- retrieved: {', '.join(docs)}" if docs else "  <- retrieval ran and found NOTHING"
        elif section["source"] == "memory":
            note = f"  <- {section.get('notes', 0)} saved notes"
        out.append(f"    {section['source']:<18} {section['tokens']:>6,}{note}")
    out.append(f"  tool definitions     {parts['tools']:>6,} tokens  ({', '.join(start['tools'])})")
    if "request" not in call:
        return "\n".join([*out, "", "(this trace was recorded without request bodies)"])
    out.append("  messages")
    for message in call["request"]["messages"]:
        for block in message["content"]:
            kind = block.get("type")
            if kind == "text":
                label, body = ("user" if message["role"] == "user" else "model"), block["text"]
            elif kind == "tool_use":
                label, body = "model calls", f"{block['name']}({_args(block.get('input'))})"
            elif kind == "tool_result":
                label, body = ("tool ERROR" if block.get("is_error") else "tool result"), block.get("content", "")
            else:
                label, body = kind or "block", ""
            out.append(f"    {label:<12} {estimate_tokens(block):>5,}  {_short(body, 84)}")
    return "\n".join(out)
