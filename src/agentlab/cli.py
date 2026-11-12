"""agentlab: run the lessons, the benchmark, and the trace viewer.

agentlab lesson 3                      run one lesson's demo (1-8, or "all")
agentlab eval                          score harness versions v0..v3 on the benchmark
agentlab eval --model claude --yes     the same benchmark with a real model (costs money)
agentlab oracle                        check the benchmark itself with the reference solutions
agentlab trace runs/v0/config-port.jsonl [--step 2]
"""

from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

from agentlab import ROOT, traceview
from agentlab.evals import load_tasks, oracle, oracle_table, run_benchmark, scoreboard, totals
from agentlab.evals.report import table
from agentlab.lab import CANDIDATES
from agentlab.middleware.tracing import load
from agentlab.models import get_model, is_live


def _lesson(number: str) -> int:
    demos = sorted((ROOT / "lessons").glob("[0-9][0-9]-*/demo.py"))
    chosen = (
        demos if number == "all" else [d for d in demos if number.isdigit() and int(d.parent.name[:2]) == int(number)]
    )
    if not chosen:
        print(f"no lesson {number!r}. Lessons: {', '.join(d.parent.name for d in demos)}", file=sys.stderr)
        return 2
    for demo in chosen:
        runpy.run_path(str(demo), run_name="__main__")
    return 0


def _eval(args: argparse.Namespace) -> int:
    unknown = [name for name in args.candidates.split(",") if name not in CANDIDATES]
    if unknown:
        print(
            f"unknown harness version(s): {', '.join(unknown)}. Choose from {', '.join(CANDIDATES)}.", file=sys.stderr
        )
        return 2
    candidates = [CANDIDATES[name] for name in args.candidates.split(",")]
    tasks = load_tasks(args.tasks)
    model = None
    if args.model:
        runs = len(tasks) * len(candidates) * args.trials
        if is_live(args.model) and not args.yes:
            print(
                f"{args.model} is a paid API: this would start {runs} agent runs, each up to 20 model calls.\n"
                "Add --yes to go ahead.",
                file=sys.stderr,
            )
            return 2
        model = get_model(args.model)
    trials = run_benchmark(tasks, candidates, model=model, traces=args.traces, trials=args.trials)
    print(scoreboard(trials))
    print()
    print(table(totals(trials)))
    for name, candidate in zip(args.candidates.split(","), candidates, strict=True):
        print(f"  {name}: {candidate.label}")
    if args.traces:
        print(f"\ntraces written to {args.traces}/<harness>/<task>.jsonl  (view one with: agentlab trace <file>)")
    return 0


def _oracle(args: argparse.Namespace) -> int:
    report = oracle(load_tasks(args.tasks))
    print(oracle_table(report))
    broken = [row for row in report if not row["ok"]]
    for row in broken:
        print(f"{row['task']}: {row['detail']}", file=sys.stderr)
    return 1 if broken else 0


def _trace(args: argparse.Namespace) -> int:
    events = load(args.path)
    print(traceview.window(events, args.step) if args.step else traceview.trajectory(events))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentlab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    lesson = sub.add_parser("lesson", help="run a lesson's demo")
    lesson.add_argument("number", help='1-8, or "all"')

    ev = sub.add_parser("eval", help="score harness versions on the benchmark")
    ev.add_argument("--candidates", default="v0,v1,v2,v3", help="comma-separated harness versions (default: all four)")
    ev.add_argument("--model", help="run every version with this model instead of its own (e.g. scripted-fast, claude)")
    ev.add_argument("--tasks", type=Path, default=ROOT / "tasks")
    ev.add_argument("--traces", type=Path, help="write one trace per run under this folder")
    ev.add_argument("--trials", type=int, default=1, help="attempts per task; use 3+ with a real model")
    ev.add_argument("--yes", action="store_true", help="confirm spending money on a paid model")

    orc = sub.add_parser("oracle", help="check that every task fails untouched and passes its reference solution")
    orc.add_argument("--tasks", type=Path, default=ROOT / "tasks")

    tr = sub.add_parser("trace", help="show a trace: the trajectory, or one step's context window")
    tr.add_argument("path", type=Path)
    tr.add_argument("--step", type=int, help="show exactly what the model was sent at this step")

    args = parser.parse_args(argv)
    if args.command == "lesson":
        return _lesson(args.number)
    return {"eval": _eval, "oracle": _oracle, "trace": _trace}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
