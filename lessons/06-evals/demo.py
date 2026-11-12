"""Lesson 6 · Evals define what "good" means."""

import re

from agentlab import ROOT, show
from agentlab.context import Context, KeywordRetriever
from agentlab.evals import compare, load_tasks, oracle, oracle_table, run_benchmark, scoreboard, totals
from agentlab.evals.report import table
from agentlab.lab import CANDIDATES, COMPANY, V3

ROLES = {
    "instruction.md": "what the agent is told",
    "task.toml": "metadata and time limits",
    "environment/Dockerfile": "the sandbox image; copies workspace/ to /app",
    "environment/workspace/CHANGELOG.md": "the files the agent starts with",
    "solution/solve.sh": "a reference solution: proves the task can be solved",
    "tests/test.sh": "the verifier's entry point: writes 1 or 0 to /logs/verifier/reward.txt",
    "tests/verify.py": "the checks",
}


def decide(trials, baseline: str, candidate: str) -> None:
    change = compare(trials, baseline, candidate)
    cost = {row["harness"]: row["cost ($)"] for row in totals(trials)}
    print(f"  fixed:     {', '.join(change['fixed']) or 'nothing'}")
    print(f"  regressed: {', '.join(change['regressed']) or 'nothing'}")
    print(f"  cost:      ${cost[baseline]:.4f} -> ${cost[candidate]:.4f}")
    print(f"  decision:  {'REJECT, it breaks tasks that used to pass' if change['regressed'] else 'ship it'}")


def main() -> None:
    show.title('Lesson 6 · Evals define what "good" means')
    tasks = load_tasks(ROOT / "tasks")

    show.part("A) What a task is (the Harbor layout)")
    example = ROOT / "tasks" / "changelog-entry"
    print(f"tasks/{example.name}/")
    for path in sorted(p for p in example.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        relative = path.relative_to(example).as_posix()
        print(f"  {relative:<36} {ROLES.get(relative, '')}")
    task = show.task("changelog-entry")
    print(f"\ninstruction: {task.instruction}")
    with show.sandbox(task) as workspace:
        print("the verifier checks:")
        for check in task.verify(workspace)["checks"]:
            print(f"  - {check['name']}")

    show.part("B) First, test the benchmark: untouched must fail, the reference solution must pass")
    print(oracle_table(oracle(tasks)))

    show.part("C) Hill-climbing: one harness change at a time, scored on the same eight tasks")
    trials = run_benchmark(tasks, CANDIDATES.values())
    print(scoreboard(trials))
    print()
    print(table(totals(trials)))
    for candidate in CANDIDATES.values():
        print(f"  {candidate.name}: {candidate.label}")

    show.part("D) Catching regressions: two changes that look harmless")
    print('1. "Switch to the cheaper model, it\'s the same harness."')
    cheaper = V3.but("v3-cheaper", "", model="scripted-fast")
    decide(run_benchmark(tasks, [V3, cheaper]), "v3", "v3-cheaper")

    print('\n2. "AGENTS.md is getting long. I removed the changelog section; nobody reads it."')
    tidy = re.sub(r"## Changelog\n.*?(?=## )", "", (COMPANY / "AGENTS.md").read_text(), flags=re.S)
    tidied = V3.but(
        "v3-tidy",
        "",
        context_factory=lambda: Context(instructions=tidy, knowledge=KeywordRetriever(COMPANY / "handbook")),
    )
    decide(run_benchmark(tasks, [V3, tidied]), "v3", "v3-tidy")

    print("""
Takeaways:
  - A public benchmark tells you how good a model is in general. Only your own tasks say what "good" means for you.
  - Score what the agent left behind (files), not what it said. Every FAIL above came from an agent that said "Done".
  - Keep the benchmark honest: every task must fail untouched and pass with a reference solution.
  - Run it before every change to the harness, the model or the context. That is the whole trick.""")


if __name__ == "__main__":
    main()
