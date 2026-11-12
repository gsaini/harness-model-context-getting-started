"""A very small "engine": turn clusters of failing traces into issues with evidence and a suggested change.

LangSmith Engine does this with an agent reading production traces. This one is a lookup table, to show
where such a tool sits in the loop: after curation, before the experiment. It proposes; the eval decides.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from agentlab.flywheel.curate import Run


@dataclass
class Issue:
    signature: str
    title: str
    pillar: str  # which part of the agent the fix belongs to: harness | context | model | product
    count: int
    detail: str  # what the traces of these runs have in common
    evidence: list[str]  # ids of the runs that show it
    examples: list[str]
    suggestion: str
    change: dict | None  # a harness-configuration change an experiment can try; None = needs a human


PLAYBOOK = {
    "context_overflow": (
        "Runs crash when the conversation outgrows the context window",
        "harness",
        "Turn on summarizing compaction.",
        {"compaction": "summarize"},
    ),
    "step_limit": (
        "Runs hit the step limit without finishing",
        "harness",
        "Look at one trace for a repeated tool call. If old results were dropped, switch compaction to summarize.",
        {"compaction": "summarize"},
    ),
    "no_knowledge_retrieved": (
        "Questions answered with nothing retrieved from the handbook",
        "context",
        "Add reference pages for the topics below, or loosen retrieval if the pages already exist.",
        {"extra_knowledge": "a page covering the topics in the examples"},
    ),
    "declined": (
        "Requests the agent has no way to do",
        "product",
        "No harness fix. Decide whether the agent should support these, and build the tools if so.",
        None,
    ),
    "tool_error": (
        "Tool errors the agent did not recover from",
        "harness",
        "Read the traces: is the error message actionable?",
        None,
    ),
    "wrong_output": (
        "Finished without errors, but the result was wrong",
        "context",
        "Read the traces: what did the window lack?",
        None,
    ),
}


def _example(run: Run) -> str:
    topic = re.search(r"what is (?:our|the) (.+?)\?", run.task.instruction, re.I)
    return topic[1] if topic else run.task.instruction.splitlines()[0]


def _detail(name: str, runs: list[Run]) -> str:
    """One sentence of evidence, computed from the traces."""
    if name == "context_overflow":
        last = [[e for e in run.events if e["type"] == "model_call"][-1] for run in runs]
        share = sum(e["window"]["parts"].get("tool_results", 0) / e["window"]["total"] for e in last) / len(last)
        steps = sorted(e["step"] for e in last)
        where = str(steps[0]) if steps[0] == steps[-1] else f"{steps[0]}-{steps[-1]}"
        return f"crashed at model call {where}, with tool results filling {share:.0%} of the window"
    if name == "no_knowledge_retrieved":
        return "retrieval ran and returned 0 pages in every one of these runs"
    if name == "declined":
        return "the agent made 0 tool calls in every one of these runs"
    return ""


def analyze(clusters: dict[str, list[Run]]) -> list[Issue]:
    issues = []
    for name, runs in clusters.items():
        title, pillar, suggestion, change = PLAYBOOK.get(name, (name, "harness", "Read the traces.", None))
        examples = [
            f"{text} (x{n})" if n > 1 else text for text, n in Counter(_example(r) for r in runs).most_common(4)
        ]
        evidence = [r.task.id for r in runs]
        issues.append(
            Issue(name, title, pillar, len(runs), _detail(name, runs), evidence, examples, suggestion, change)
        )
    return issues
