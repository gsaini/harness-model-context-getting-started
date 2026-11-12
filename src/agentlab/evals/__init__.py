"""Evals: tasks with verifiers, a runner that scores harness versions on them, and a report."""

from agentlab.evals.report import compare, oracle_table, scoreboard, totals
from agentlab.evals.runner import Trial, oracle, run_benchmark, run_trial
from agentlab.evals.tasks import Task, load_tasks

__all__ = [
    "Task",
    "Trial",
    "compare",
    "load_tasks",
    "oracle",
    "oracle_table",
    "run_benchmark",
    "run_trial",
    "scoreboard",
    "totals",
]
