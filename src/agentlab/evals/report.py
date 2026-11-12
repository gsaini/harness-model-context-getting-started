"""Turn trials into something you can read: a scoreboard, totals, and a before/after comparison."""

from __future__ import annotations

from collections import defaultdict

from agentlab.evals.runner import Trial

MARKS = {"error": "CRASH", "max_steps": "LOOP", "refusal": "REFUSED", "max_tokens": "CUT OFF"}


def table(rows: list[dict]) -> str:
    """A plain aligned text table from a list of dicts (numbers right-aligned)."""
    columns = list(rows[0])

    def show(value: object) -> str:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return str(value)
        return f"{value:,}" if isinstance(value, int) else f"{value:.4f}"

    cells = [[show(row[c]) for c in columns] for row in rows]
    width = [max(len(c), *(len(r[i]) for r in cells)) for i, c in enumerate(columns)]
    numeric = [all(isinstance(row[c], int | float) and not isinstance(row[c], bool) for row in rows) for c in columns]

    def line(values: list[str]) -> str:
        return "  ".join(
            v.rjust(w) if n else v.ljust(w) for v, w, n in zip(values, width, numeric, strict=True)
        ).rstrip()

    return "\n".join([line(columns), "  ".join("-" * w for w in width), *(line(r) for r in cells)])


def _grouped(trials: list[Trial]) -> dict[str, dict[str, list[Trial]]]:
    by: dict[str, dict[str, list[Trial]]] = defaultdict(lambda: defaultdict(list))
    for t in trials:
        by[t.candidate][t.task].append(t)
    return by


def _cell(runs: list[Trial]) -> str:
    if len(runs) > 1:
        return f"{sum(t.passed for t in runs)}/{len(runs)}"
    t = runs[0]
    return "pass" if t.passed else MARKS.get(t.status, "FAIL")


def scoreboard(trials: list[Trial]) -> str:
    """Tasks down, harness versions across. FAIL = wrong result, CRASH = the run died, LOOP = hit the step limit."""
    by = _grouped(trials)
    candidates = list(by)
    tasks = list(dict.fromkeys(t.task for t in trials))
    rows = [{"task": task, **{c: _cell(by[c][task]) for c in candidates}} for task in tasks]
    rows.append({"task": "passed", **{c: f"{_passed(by[c])}/{len(tasks)}" for c in candidates}})
    return table(rows)


def _passed(per_task: dict[str, list[Trial]]) -> int:
    """A task counts as passed only if every trial of it passed."""
    return sum(all(t.passed for t in runs) for runs in per_task.values())


def totals(trials: list[Trial]) -> list[dict]:
    """Accuracy is one number; steps, tokens and cost are the others you trade it against."""
    rows = []
    for candidate, per_task in _grouped(trials).items():
        runs = [t for task_runs in per_task.values() for t in task_runs]
        rows.append(
            {
                "harness": candidate,
                "passed": f"{_passed(per_task)}/{len(per_task)}",
                "model calls": sum(t.steps for t in runs),
                "tokens": sum(t.tokens for t in runs),
                "cost ($)": sum(t.cost for t in runs),
            }
        )
    return rows


def oracle_table(report: list[dict]) -> str:
    """The oracle check in words: every task should read fail / pass / yes."""
    word = {0.0: "fail", 1.0: "pass"}
    return table(
        [
            {
                "task": row["task"],
                "untouched": word.get(row["untouched"], str(row["untouched"])),
                "after solve.sh": word.get(row["solved"], str(row["solved"])),
                "usable": "yes" if row["ok"] else "NO",
            }
            for row in report
        ]
    )


def compare(trials: list[Trial], baseline: str, candidate: str) -> dict[str, list[str]]:
    """What changed between two harness versions: tasks fixed, and tasks broken (regressions)."""
    by = _grouped(trials)

    def ok(name: str, task: str) -> bool:
        return all(t.passed for t in by[name][task])

    tasks = list(by[baseline])
    return {
        "fixed": [t for t in tasks if not ok(baseline, t) and ok(candidate, t)],
        "regressed": [t for t in tasks if ok(baseline, t) and not ok(candidate, t)],
    }
