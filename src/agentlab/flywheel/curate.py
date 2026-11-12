"""Collect and curate: run traffic with tracing on, then sort the unhappy runs by what went wrong.

`signature` reads only the trace and the feedback, never the hidden check. That is the constraint a real
curation step works under.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from agentlab.evals.runner import Trial, run_trial
from agentlab.evals.tasks import Task
from agentlab.lab import Candidate
from agentlab.middleware import Tracer


@dataclass
class Run:
    task: Task
    trial: Trial
    events: list[dict]

    @property
    def thumbs_up(self) -> bool:
        """The signal production gives you. Here it comes from the request's hidden check."""
        return self.trial.passed


def run_traffic(requests: list[Task], candidate: Candidate) -> list[Run]:
    runs = []
    for request in requests:
        tracer = Tracer()
        runs.append(Run(request, run_trial(request, candidate, tracer=tracer), tracer.events))
    return runs


def signature(run: Run) -> str:
    """A coarse label for why an unhappy run went wrong, from its trace alone."""
    start, end = run.events[0], run.events[-1]
    if "ContextOverflow" in end["error"]:
        return "context_overflow"
    if end["status"] == "max_steps":
        return "step_limit"
    tool_calls = [e for e in run.events if e["type"] == "tool_call"]
    if not tool_calls:
        return "declined"  # the agent answered without acting: it did not know how
    knowledge = next((s for s in start["sections"] if s["source"] == "knowledge"), None)
    if "?" in start["task"] and knowledge is not None and not knowledge.get("docs"):
        return "no_knowledge_retrieved"  # a question, and retrieval put nothing in the window
    if any(e["is_error"] for e in tool_calls):
        return "tool_error"
    return "wrong_output"


def cluster(runs: list[Run]) -> dict[str, list[Run]]:
    """Group the thumbs-down runs by signature, biggest group first."""
    groups: dict[str, list[Run]] = defaultdict(list)
    for run in runs:
        if not run.thumbs_up:
            groups[signature(run)].append(run)
    return dict(sorted(groups.items(), key=lambda item: -len(item[1])))
