"""Run tasks against harness versions and score what they leave behind."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from agentlab.evals.tasks import Task
from agentlab.harness import Model
from agentlab.lab import Candidate
from agentlab.middleware import Tracer


@dataclass
class Trial:
    """One task, attempted once by one harness version."""

    task: str
    candidate: str
    reward: float
    status: str
    steps: int
    tokens: int
    cost: float
    error: str = ""
    checks: list[dict] = field(default_factory=list)
    trace: Path | None = None

    @property
    def passed(self) -> bool:
        return self.reward == 1.0


def run_trial(
    task: Task,
    candidate: Candidate,
    *,
    model: Model | None = None,
    traces: Path | None = None,
    tracer: Tracer | None = None,
) -> Trial:
    """Fresh sandbox, one run, then the verifier. Pass `traces` (a folder) or your own `tracer` to keep the trace."""
    with tempfile.TemporaryDirectory(prefix=f"agentlab-{task.id}-") as sandbox:
        workspace = task.setup(Path(sandbox))
        trace = traces / candidate.name / f"{task.id}.jsonl" if traces else None
        tracer = tracer or (Tracer(trace) if trace else None)
        agent = candidate.build(workspace, tracer=tracer, model=model)
        result = agent.run(task.instruction)
        verdict = task.verify(workspace)  # score the state of the workspace, not what the agent says it did
    return Trial(
        task=task.id,
        candidate=candidate.name,
        reward=float(verdict["reward"]),
        status=result.status,
        steps=result.steps,
        tokens=result.usage.get("input_tokens", 0) + result.usage.get("output_tokens", 0),
        cost=result.cost,
        error=result.error,
        checks=verdict["checks"],
        trace=trace,
    )


def run_benchmark(
    tasks: Iterable[Task],
    candidates: Iterable[Candidate],
    *,
    model: Model | None = None,
    traces: Path | None = None,
    trials: int = 1,
) -> list[Trial]:
    """Every task x every candidate. With a real model, raise `trials`: one run is an anecdote."""
    tasks = list(tasks)
    return [
        run_trial(task, candidate, model=model, traces=traces)
        for candidate in candidates
        for task in tasks
        for _ in range(trials)
    ]


def oracle(tasks: Iterable[Task]) -> list[dict]:
    """Check the benchmark itself: each task must fail untouched and pass after its reference solution.

    A task that passes untouched measures nothing; one its own solution can't pass is broken.
    """
    report = []
    for task in tasks:
        with tempfile.TemporaryDirectory(prefix=f"agentlab-oracle-{task.id}-") as sandbox:
            workspace = task.setup(Path(sandbox))
            before = task.verify(workspace)["reward"]
            solved = subprocess.run(
                ["bash", str(task.directory / "solution" / "solve.sh")],
                env={**os.environ, "APP_DIR": str(workspace)},
                capture_output=True,
                text=True,
                timeout=60,
            )
            after = task.verify(workspace)
        report.append(
            {
                "task": task.id,
                "untouched": before,
                "solved": after["reward"],
                "ok": before == 0.0 and after["reward"] == 1.0 and solved.returncode == 0,
                "detail": solved.stderr.strip() or "; ".join(c["name"] for c in after["checks"] if not c["passed"]),
            }
        )
    return report
