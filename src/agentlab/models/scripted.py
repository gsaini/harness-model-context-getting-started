"""A stand-in for an LLM: offline, free, and the same answer every time.

It is a few hand-written "skills" (change a setting, add a changelog entry, total invoices, answer a policy
question, save a preference), chosen by pattern-matching the task. That is nothing like a real model. What
it does share with one is the property every lesson depends on:

    It keeps NO state between calls. Everything it knows comes from the request it is handed:
    the system prompt, the messages, the tool list. Take something out of the window and it is gone.

So context, compaction, tool shape and tracing change its behaviour for the same reason they change a real
model's. Its other traits are dials you can turn, each a stand-in for a way real models differ:

- context_window:    tiny (3,000 tokens) so you can watch it overflow without megabytes of files.
- reads_first:       False = a cheaper, sloppier model that guesses a file's content instead of reading it.
- native_edit_tool:  the edit-tool shape it was "trained on"; it misuses the other shape.
- obeys_injections:  it follows instructions planted in files. Real models mostly don't. "Mostly" is the point.

This proves mechanisms, not rates. To measure a real model, run the same harness with `--model claude`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import PurePosixPath

from agentlab.context import keywords
from agentlab.harness import Response
from agentlab.messages import estimate_tokens, request_tokens, text, tool_use

SUMMARY_MARKER = "[Summary of the work so far]"
SUMMARIZE_PROMPT = (
    "Summarize the work so far so that you could finish the task with only this summary. "
    "Keep every fact from the tool results that the task still needs, and say what is left to do."
)
EDIT_TOOLS = ("edit_file", "patch_lines", "write_file")

# What a model that doesn't look first assumes a config file contains.
TYPICAL = {"port": 3000, "timeout": 30, "retries": 3, "workers": 4, "debug": False}


class ContextOverflow(Exception):
    """The request doesn't fit the model's context window. Real APIs answer this with a 400."""


@dataclass
class Call:
    """A tool call the model can see in its window, with the result if that is visible too."""

    name: str
    input: dict
    index: int  # position of the message that made the call
    output: str = ""
    is_error: bool = False
    answered: bool = False


class View:
    """What the model can see in one request, parsed. Built from scratch on every call."""

    def __init__(self, system: str, messages: list[dict], tools: list[dict]):
        self.system = system
        self.tools = {tool["name"] for tool in tools}
        self.turn = len(messages)
        spoken = [  # (message index, text) for everything the user typed, as opposed to tool results
            (i, "\n".join(b["text"] for b in m["content"] if b.get("type") == "text"))
            for i, m in enumerate(messages)
            if m["role"] == "user" and any(b.get("type") == "text" for b in m["content"])
        ]
        self.wants_summary = bool(spoken) and spoken[-1][1].startswith(SUMMARIZE_PROMPT[:24])
        if self.wants_summary:
            spoken = spoken[:-1]
        start, instruction = spoken[-1] if spoken else (-1, "")
        self.task, _, summary = instruction.partition(SUMMARY_MARKER)
        self.task = self.task.strip()
        self.summary_lines = [line for line in summary.splitlines() if line.startswith("- ")]
        # Instructions can arrive in the system prompt (context) or in anything the user said.
        self.reference = "\n".join([system, *(said for _, said in spoken)])
        # Only tool calls made after the current instruction belong to the current task.
        by_id: dict[str, Call] = {}
        self.calls: list[Call] = []
        for i, message in enumerate(messages):
            if i <= start:
                continue
            for block in message["content"]:
                if block.get("type") == "tool_use":
                    by_id[block["id"]] = Call(block["name"], block.get("input") or {}, i)
                    self.calls.append(by_id[block["id"]])
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in by_id:
                    call = by_id[block["tool_use_id"]]
                    call.output, call.is_error, call.answered = (
                        str(block.get("content", "")),
                        bool(block.get("is_error")),
                        True,
                    )

    def calls_to(self, *names: str, after: int = -1, **match: object) -> list[Call]:
        return [
            c
            for c in self.calls
            if c.name in names and c.index > after and all(c.input.get(k) == v for k, v in match.items())
        ]

    def last(self, *names: str, after: int = -1, **match: object) -> Call | None:
        found = self.calls_to(*names, after=after, **match)
        return found[-1] if found else None

    def first(self, *names: str, **match: object) -> Call | None:
        found = self.calls_to(*names, **match)
        return found[0] if found else None

    def act(self, thought: str, *calls: tuple[str, dict]) -> list[dict]:
        """One assistant turn: a line of reasoning, then one or more tool calls."""
        return [
            text(thought),
            *(tool_use(f"toolu_{self.turn:02d}_{n}", name, args) for n, (name, args) in enumerate(calls)),
        ]


def say(message: str) -> list[dict]:
    return [text(message)]


# --- editing, shared by the skills -----------------------------------------------------------------------


def _apply(content: str, edits: list[tuple[str, str]]) -> str:
    """Apply (old, new) replacements, skipping any that are already in place."""
    for old, new in edits:
        if new not in content and old in content:
            content = content.replace(old, new, 1)
    return content


def _smallest(old: str, new: str) -> tuple[str, str]:
    """The differing words only: how a model used to line patches abbreviates an exact-string edit."""
    a, b = old.split(" "), new.split(" ")
    while len(a) > 1 and len(b) > 1 and a[0] == b[0]:
        a, b = a[1:], b[1:]
    while len(a) > 1 and len(b) > 1 and a[-1] == b[-1]:
        a, b = a[:-1], b[:-1]
    return " ".join(a), " ".join(b)


def edit_calls(view: View, model: ScriptedModel, path: str, content: str, edits: list[tuple[str, str]]) -> list:
    """Turn the edits the model wants into calls on whichever edit tool the harness offers."""
    if "edit_file" in view.tools:
        if model.native_edit_tool != "edit_file":
            edits = [_smallest(old, new) for old, new in edits]
        return [("edit_file", {"path": path, "old_str": old, "new_str": new}) for old, new in edits]
    if "patch_lines" in view.tools:
        lines = content.split("\n")
        patches = []
        for old, new in edits:
            number = next((n for n, line in enumerate(lines, 1) if old in line), None)
            if number is not None:
                patches.append((number, lines[number - 1].replace(old, new, 1)))
        if model.native_edit_tool == "patch_lines":
            patches.sort(reverse=True)  # bottom-up, so an earlier patch can't shift the lines of a later one
        # A model that never trained on this tool sends every patch with the line numbers it read once.
        return [
            ("patch_lines", {"path": path, "start_line": n, "end_line": n, "new_text": replacement})
            for n, replacement in patches
        ]
    return [("write_file", {"path": path, "content": _apply(content, edits)})]


def make_edits(view: View, model: ScriptedModel, path: str, read: Call, edits: list, why: str, done: str) -> list[dict]:
    """Send the edits; if the tool rejects one, look at the file again and rewrite it whole.

    `read` is the first time the model read the file: every edit call after it is an attempt so far."""
    attempts = view.calls_to(*EDIT_TOOLS, after=read.index, path=path)
    if not attempts:
        return view.act(why, *edit_calls(view, model, path, read.output, edits))
    failed = [a for a in attempts if a.is_error]
    if not failed:
        return say(done)
    again = view.last("read_file", after=failed[-1].index, path=path)
    if again is None:
        return view.act(
            f"An edit was rejected ({failed[-1].output}). Reading {path} again.", ("read_file", {"path": path})
        )
    rewrite = view.last("write_file", after=again.index, path=path)
    if rewrite is None:
        fixed = _apply(again.output, edits)
        return view.act(
            "Writing the whole file with the changes applied.", ("write_file", {"path": path, "content": fixed})
        )
    return say(done if not rewrite.is_error else f"I could not update {path}: {rewrite.output}")


# --- skills ----------------------------------------------------------------------------------------------


def set_config(view: View, model: ScriptedModel, m: re.Match) -> list[dict]:
    file, key = m[1], m[2]
    try:
        value = json.loads(m[3])
    except ValueError:
        value = m[3]
    literal = json.dumps(value)
    if not model.reads_first:
        return _set_config_blind(view, file, key, literal)

    path = file
    read = view.first("read_file", path=path)
    if read is None:
        return view.act(f"I'll read {path} before changing it.", ("read_file", {"path": path}))
    if read.is_error:  # not where the task said: look for it rather than create a second copy
        listing = view.last("list_files")
        if listing is None:
            return view.act(
                f"{path} isn't there. I'll look for it instead of creating a new file.", ("list_files", {"dir": "."})
            )
        same_name = [
            p for p in listing.output.splitlines() if PurePosixPath(p).name == PurePosixPath(file).name and p != file
        ]
        if len(same_name) != 1:
            return say(f"I could not find {file} in the workspace, so I changed nothing.")
        path = same_name[0]
        read = view.first("read_file", path=path)
        if read is None:
            return view.act(f"Found it at {path}.", ("read_file", {"path": path}))
        if read.is_error:
            return say(f"I could not read {path}, so I changed nothing.")
    found = re.search(rf'("{re.escape(key)}"\s*:\s*)("(?:[^"\\]|\\.)*"|[^,\s}}]+)', read.output)
    if not found:
        return say(f"{path} has no {key!r} setting, so I changed nothing.")
    if found[2] == literal:
        return say(f"{key} is already {literal} in {path}.")
    return make_edits(
        view,
        model,
        path,
        read,
        [(found[0], found[1] + literal)],
        f"{key} is {found[2]} now. Changing only that value.",
        f"Done: set {key} to {literal} in {path}.",
    )


def _set_config_blind(view: View, file: str, key: str, literal: str) -> list[dict]:
    attempts = view.calls_to(*EDIT_TOOLS, path=file)
    if attempts and not attempts[-1].is_error:
        return say(f"Done: set {key} to {literal} in {file}.")
    if not attempts and "edit_file" in view.tools:
        guess = json.dumps(TYPICAL.get(key, 0))
        return view.act(
            f"{key} is usually {guess}. Replacing it directly.",
            ("edit_file", {"path": file, "old_str": f'"{key}": {guess}', "new_str": f'"{key}": {literal}'}),
        )
    if not view.calls_to("write_file", path=file):
        return view.act(
            "That didn't apply. Writing the file with the new value.",
            ("write_file", {"path": file, "content": "{\n  " + f'"{key}": {literal}' + "\n}\n"}),
        )
    return say(f"I could not update {file}.")


def changelog(view: View, model: ScriptedModel, m: re.Match) -> list[dict]:
    version, change, path = m[1], m[2].strip(), "CHANGELOG.md"
    read = view.first("read_file", path=path)
    if read is None:
        return view.act("I'll read the changelog first.", ("read_file", {"path": path}))
    if read.is_error:
        return say("There is no CHANGELOG.md here, so I changed nothing.")
    # Does anything in view say how this project writes its changelog?
    heading = re.search(r'(?:entries|items) go (?:directly )?under the "([^"]+)" heading', view.reference, re.I)
    template = re.search(r'(?:entry|item) format: "([^"]+)"', view.reference, re.I)
    if heading and template and heading[1] in read.output.split("\n"):
        entry = template[1].replace("{version}", version).replace("{text}", change)
        return make_edits(
            view,
            model,
            path,
            read,
            [(heading[1], f"{heading[1]}\n{entry}")],
            f'The project\'s convention: entries go under "{heading[1]}", written as {template[1]}',
            f"Done: added {version} under {heading[1]}.",
        )
    if view.calls_to("write_file", after=read.index, path=path):
        return say(f"Done: added {version} at the end of the changelog.")
    return view.act(
        "Nothing in my context says how this project formats its changelog, so I'll append a plain entry at the end.",
        ("write_file", {"path": path, "content": read.output.rstrip("\n") + f"\n- {version}: {change}\n"}),
    )


def invoice_total(view: View, model: ScriptedModel, m: re.Match) -> list[dict]:
    directory, out = m[1], m[2]
    files: list[str] | None = None
    amounts: dict[str, Decimal] = {}
    for line in view.summary_lines:  # facts carried over by a summary
        if (f := re.fullmatch(r"- files in ([\w./-]+): (.*)", line)) and f[1] == directory:
            files = [name for name in f[2].split(", ") if name]
        elif a := re.fullmatch(r"- ([\w./-]+): amount (-?[\d.]+)", line):
            amounts[a[1]] = Decimal(a[2])
    listing = view.last("list_files", dir=directory)
    if listing and listing.answered and not listing.is_error:
        files = [p for p in listing.output.splitlines() if p.endswith(".json")]
    if files is None:
        return view.act(f"I'll list {directory}/ to see which invoices exist.", ("list_files", {"dir": directory}))
    for call in view.calls_to("read_file"):
        if call.answered and not call.is_error:
            try:
                amounts[call.input["path"]] = Decimal(str(json.loads(call.output)["amount"]))
            except (ValueError, KeyError, TypeError):
                pass
    todo = [name for name in files if name not in amounts]
    if todo:
        return view.act(
            f"I know {len(files) - len(todo)} of {len(files)} amounts. Reading {todo[0]}.",
            ("read_file", {"path": todo[0]}),
        )
    total = sum((amounts[name] for name in files), Decimal(0))
    if view.last("write_file", path=out) is None:
        return view.act(
            f"All {len(files)} invoices read. The total is {total:.2f}.",
            ("write_file", {"path": out, "content": f"{total:.2f}\n"}),
        )
    return say(f"Done: {len(files)} invoices add up to {total:.2f}, written to {out}.")


def _invoice_digest(call: Call) -> str | None:
    """What this skill would keep from a tool result when asked to summarize."""
    if call.is_error or not call.answered:
        return None
    if call.name == "list_files":
        names = [p for p in call.output.splitlines() if p.endswith(".json")]
        return f"- files in {call.input.get('dir', '.')}: {', '.join(names)}"
    if call.name == "read_file":
        try:
            return f"- {call.input['path']}: amount {json.loads(call.output)['amount']}"
        except (ValueError, KeyError, TypeError):
            return None
    return None


def policy_question(view: View, model: ScriptedModel, m: re.Match) -> list[dict]:
    topic, out = " ".join(m[1].split()), m[2]
    wrote = view.last("write_file", path=out)
    if wrote is not None:
        return say(wrote.input.get("content", "").strip())
    wanted = keywords(topic)
    best, best_score = "", 0
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", view.reference):
        score = len(wanted & keywords(sentence))
        if score > best_score and re.search(r"\d", sentence):  # a policy answer has a number in it
            best, best_score = sentence.strip(), score
    if best_score >= max(2, (len(wanted) + 1) // 2):
        return view.act("My reference material covers this.", ("write_file", {"path": out, "content": best + "\n"}))
    guess = f"I don't have a company policy on the {topic} in front of me. A common default is 30 days; please confirm."
    return view.act(
        "Nothing in my context covers this, so I can only answer in general terms.",
        ("write_file", {"path": out, "content": guess + "\n"}),
    )


def two_edits(view: View, model: ScriptedModel, m: re.Match) -> list[dict]:
    path, new_line, anchor, old, new = m[1], m[2], m[3], m[4], m[5]
    read = view.first("read_file", path=path)
    if read is None:
        return view.act(f"I'll read {path} first.", ("read_file", {"path": path}))
    if read.is_error:
        return say(f"I could not read {path}, so I changed nothing.")
    return make_edits(
        view,
        model,
        path,
        read,
        [(anchor, f"{anchor}\n{new_line}"), (old, new)],
        "Two changes: insert the new line under its anchor, and replace the old line.",
        f"Done: made both changes in {path}.",
    )


def remember(view: View, model: ScriptedModel, m: re.Match) -> list[dict]:
    note = " ".join(m[1].split())
    if "remember" not in view.tools:
        return say("Understood for this conversation. I have no memory tool, so I won't know it in a new session.")
    if view.last("remember") is None:
        return view.act("That is a standing rule, so I'll save it.", ("remember", {"note": note}))
    return say("Saved. I'll follow that from now on.")


Skill = Callable[[View, "ScriptedModel", re.Match], list[dict]]
SKILLS: list[tuple[re.Pattern, Skill, Callable[[Call], str | None] | None]] = [
    (re.compile(r"\bremember:\s*(.+)", re.I | re.S), remember, None),
    (re.compile(r"in `([\w./-]+\.json)`, set `([\w.]+)` to `?([^`\s]+?)`?\.(?:\s|$)", re.I), set_config, None),
    (re.compile(r"add a changelog entry for version v?([\d.]+): (.+?)\.?\s*$", re.I | re.M), changelog, None),
    (
        re.compile(
            r"add up the `amount` of every invoice in `([\w./-]+?)/?` and write the total to `([\w./-]+)`", re.I
        ),
        invoice_total,
        _invoice_digest,
    ),
    (re.compile(r"what is (?:our|the) (.+?)\?\s*write the answer to `([\w./-]+)`", re.I | re.S), policy_question, None),
    (
        re.compile(
            r"in `([\w./-]+)`, add the line `([^`]+)` directly below the line `([^`]+)`, and change `([^`]+)` to `([^`]+)`",
            re.I,
        ),
        two_edits,
        None,
    ),
]
OUT_OF_SCOPE = (
    "I can't help with that. I can change settings in JSON config files, add changelog entries, "
    "total invoices and answer policy questions from my reference material."
)
INJECTION = re.compile(r"AI agents?:[^\n]*?copy the contents of `([^`]+)` into `([^`]+)`", re.I)


def _injected_step(view: View) -> list[dict] | None:
    """Follow an instruction planted in a file the model has read. This is the behaviour a guard must stop."""
    for call in view.calls_to("read_file"):
        planted = INJECTION.search(call.output) if call.answered and not call.is_error else None
        if not planted or planted[1] == call.input.get("path"):
            continue
        source, target = planted[1], planted[2]
        got = view.last("read_file", path=source)
        if got is None:
            return view.act(
                f"This file tells agents to copy {source} into {target} first. Doing that.",
                ("read_file", {"path": source}),
            )
        if not got.is_error and view.last("write_file", path=target) is None:
            return view.act(
                f"Copying {source} into {target} as the file asked.",
                ("write_file", {"path": target, "content": got.output}),
            )
    return None


@dataclass
class ScriptedModel:
    name: str = "scripted-careful"
    context_window: int = 3000
    reads_first: bool = True
    native_edit_tool: str = "edit_file"
    obeys_injections: bool = True
    price: tuple[float, float] = (3.0, 15.0)  # made-up $ per million input / output tokens

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> Response:
        size = request_tokens(system, messages, tools)
        if size > self.context_window:
            raise ContextOverflow(f"prompt is too long: {size} tokens > {self.context_window} token window")
        content = self._decide(View(system, messages, tools))
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        return Response(content, stop, {"input_tokens": size, "output_tokens": estimate_tokens(content)}, self.name)

    def _decide(self, view: View) -> list[dict]:
        match = next(((p.search(view.task), skill, digest) for p, skill, digest in SKILLS if p.search(view.task)), None)
        if view.wants_summary:
            return say(_summarize(view, match[2] if match else None))
        if match is None:
            return say(OUT_OF_SCOPE if view.task else "What would you like me to do?")
        if self.obeys_injections and (detour := _injected_step(view)):
            return detour
        return match[1](view, self, match[0])

    def cost(self, usage: dict[str, int]) -> float:
        return (usage.get("input_tokens", 0) * self.price[0] + usage.get("output_tokens", 0) * self.price[1]) / 1e6


def _summarize(view: View, digest: Callable[[Call], str | None] | None) -> str:
    """Answer a summarization request: earlier summary lines, plus what each visible tool call established."""
    lines = list(view.summary_lines)
    for call in view.calls:
        line = digest(call) if digest else None
        target = call.input.get("path") or call.input.get("dir") or ""
        lines.append(line or f"- {call.name} {target}: {'failed' if call.is_error else 'ok'}")
    return "\n".join(dict.fromkeys(lines)) or "- nothing done yet"


def careful() -> ScriptedModel:
    return ScriptedModel()


def fast() -> ScriptedModel:
    """Twelve times cheaper, and it edits config files without reading them."""
    return ScriptedModel(name="scripted-fast", reads_first=False, price=(0.25, 1.25))


def liner() -> ScriptedModel:
    """A model whose native edit tool is line patches, not exact-string replacement."""
    return ScriptedModel(name="scripted-liner", native_edit_tool="patch_lines")
