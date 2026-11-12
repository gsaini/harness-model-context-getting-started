"""Context: the data that makes a general model behave like *your* agent.

Three kinds, assembled into labelled sections of the system prompt when a run starts:

- instructions: how we do things here. Always included (like an AGENTS.md file).
- knowledge:    facts looked up for this task. Only the pages that match are included.
- memory:       things learned in earlier sessions. Grows over time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agentlab.messages import Section
from agentlab.tools import Tool, ToolError

_STOP = set(
    "a an and are as at be by can do for from has have how in into is it its of on or our that the their this to "
    "was we what when where which who will with you your write answer txt".split()
)


def keywords(value: str) -> set[str]:
    """Lower-case words of 3+ letters, minus filler, with a plural 's' stripped."""
    found = re.findall(r"[a-z0-9]+", value.lower())
    words = (w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 3 else w for w in found)
    return {w for w in words if len(w) >= 3 and w not in _STOP}


@dataclass
class Doc:
    id: str
    title: str
    text: str


class Retriever(Protocol):
    def search(self, query: str) -> list[Doc]: ...


class KeywordRetriever:
    """Rank pages by how many of the query's keywords they contain. Deliberately simple: the lessons are
    about what retrieval puts in the window (or fails to), not about embedding models."""

    def __init__(self, *directories: Path, k: int = 2, min_overlap: int = 2, aliases: dict[str, str] | None = None):
        self.k = k
        self.min_overlap = min_overlap
        self.aliases = aliases or {}
        self.docs: list[Doc] = []
        for directory in directories:
            for path in sorted(Path(directory).glob("*.md")):
                body = path.read_text(encoding="utf-8").strip()
                title = body.splitlines()[0].lstrip("# ").strip() if body else path.stem
                self.docs.append(Doc(path.name, title, body))

    def search(self, query: str) -> list[Doc]:
        wanted = {self.aliases.get(word, word) for word in keywords(query)}
        scored = [(len(wanted & keywords(doc.text)), doc) for doc in self.docs]
        hits = sorted((item for item in scored if item[0] >= self.min_overlap), key=lambda item: (-item[0], item[1].id))
        return [doc for _, doc in hits[: self.k]]


class FileMemory:
    """Notes that outlive a session: one JSON string per line."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[str]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def add(self, note: str) -> None:
        note = " ".join(note.split())
        if not note:
            raise ToolError("note must not be empty")
        if note not in self.load():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(note) + "\n")


def remember_tool(memory: FileMemory) -> Tool:
    def remember(note: str) -> str:
        memory.add(note)
        return "saved to memory"

    return Tool(
        "remember",
        "Save a lasting fact or preference so that future sessions know it. Use it when the user states a rule.",
        {
            "type": "object",
            "properties": {"note": {"type": "string", "description": "The fact, in one or two sentences."}},
            "required": ["note"],
            "additionalProperties": False,
        },
        remember,
    )


class Context:
    def __init__(
        self,
        *,
        instructions: str | None = None,
        knowledge: Retriever | None = None,
        memory: FileMemory | None = None,
    ):
        self.instructions = instructions
        self.knowledge = knowledge
        self.memory = memory

    def assemble(self, task: str) -> list[Section]:
        sections = []
        if self.instructions:
            sections.append(Section("instructions", "# Project instructions\n" + self.instructions.strip()))
        if self.knowledge:
            docs = self.knowledge.search(task)
            body = "\n\n".join(doc.text for doc in docs)
            # An empty section stays in the list so a trace can show "retrieval ran and found nothing".
            sections.append(
                Section(
                    "knowledge",
                    "# Reference material retrieved for this task\n" + body if docs else "",
                    {"docs": [doc.id for doc in docs]},
                )
            )
        if self.memory:
            notes = self.memory.load()
            if notes:
                listed = "\n".join(f"- {note}" for note in notes)
                sections.append(Section("memory", "# Memory from earlier sessions\n" + listed, {"notes": len(notes)}))
        return sections
