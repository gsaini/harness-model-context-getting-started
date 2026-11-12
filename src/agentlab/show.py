"""Small helpers the lesson demos share."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from agentlab import ROOT
from agentlab.evals.tasks import Task, load_task


def title(text: str) -> None:
    print(f"\n=== {text} ===")


def part(text: str) -> None:
    print(f"\n--- {text} ---\n")


def task(name: str) -> Task:
    return load_task(ROOT / "tasks" / name)


@contextmanager
def sandbox(task: Task) -> Iterator[Path]:
    """A fresh copy of the task's starting files in a temporary directory, deleted afterwards."""
    with tempfile.TemporaryDirectory(prefix=f"agentlab-{task.id}-") as tmp:
        yield task.setup(Path(tmp))


def verdict(task: Task, workspace: Path) -> str:
    result = task.verify(workspace)
    if result["reward"] == 1.0:
        return "PASS"
    return "FAIL: " + "; ".join(c["name"] for c in result["checks"] if not c["passed"])


def indent(text: str, by: str = "  ") -> str:
    return "\n".join(by + line if line else line for line in text.splitlines())
