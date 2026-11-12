"""Lesson 8 · The data flywheel: run, collect, curate, experiment, ship."""

from collections import Counter
from dataclasses import replace

from agentlab import ROOT, show
from agentlab.evals import compare, load_tasks, run_benchmark, totals
from agentlab.evals.report import table
from agentlab.flywheel import analyze, cluster, generate, run_traffic
from agentlab.lab import V1

PROPOSED = ROOT / "fixtures" / "proposed"  # a handbook page a human wrote after reading the engine's report


def satisfaction(runs) -> str:
    up = sum(run.thumbs_up for run in runs)
    return f"thumbs up {up}, thumbs down {len(runs) - up}  ({up / len(runs):.0%} satisfied)"


def main() -> None:
    show.title("Lesson 8 · The data flywheel: run, collect, curate, experiment, ship")
    live = V1.but("prod-v1", "context + policy guard", protect=(".env",))
    requests = generate(count=40, seed=42)

    show.part("1) Run: a day of production traffic on the current harness (prod-v1)")
    runs = run_traffic(requests, live)
    kinds = Counter(request.meta["kind"] for request in requests)
    print(f"{len(requests)} requests: " + ", ".join(f"{kind} {n}" for kind, n in kinds.most_common()))
    print(satisfaction(runs))

    show.part("2) Collect and curate: every run left a trace; group the unhappy ones by what the trace shows")
    clusters = cluster(runs)
    issues = analyze(clusters)
    print(
        table([{"signature": i.signature, "runs": i.count, "what the traces have in common": i.detail} for i in issues])
    )

    show.part("3) Suggest: one issue per cluster, with its evidence and the part of the agent to change")
    for issue in issues:
        print(f"[{issue.pillar}] {issue.title}  ({issue.count} runs: {', '.join(issue.evidence)})")
        print(f"    seen in:    {'; '.join(issue.examples)}")
        print(f"    suggestion: {issue.suggestion}\n")

    show.part("4) Curate a dataset: unhappy runs become regression tasks")
    core = load_tasks(ROOT / "tasks")
    regressions = [
        replace(run.task, id=f"prod-{run.task.id}")
        for issue in issues
        if issue.change  # only issues an experiment can test
        for run in clusters[issue.signature][:3]
    ]
    print(
        f"benchmark = {len(core)} core tasks + {len(regressions)} tasks promoted from production: {', '.join(t.id for t in regressions)}"
    )

    show.part("5) Experiment: does the proposed change help, and does it break anything?")
    candidate = live.but("prod-v2", "", compaction="summarize", extra_knowledge=(PROPOSED,))
    print(
        "prod-v2 = prod-v1 + summarizing compaction (harness) + a new handbook page, fixtures/proposed/pricing.md (context)\n"
    )
    trials = run_benchmark([*core, *regressions], [live, candidate])
    print(table(totals(trials)))
    change = compare(trials, "prod-v1", "prod-v2")
    print(f"\nfixed:     {', '.join(change['fixed']) or 'nothing'}")
    print(f"regressed: {', '.join(change['regressed']) or 'nothing'}")
    print(f"decision:  {'do not ship' if change['regressed'] or not change['fixed'] else 'ship prod-v2'}")

    show.part("6) Ship, and go round again: the same day of traffic on prod-v2")
    after = run_traffic(requests, candidate)
    print(f"before: {satisfaction(runs)}")
    print(f"after:  {satisfaction(after)}")
    for issue in analyze(cluster(after)):
        print(f"still open: [{issue.pillar}] {issue.title} ({issue.count} runs). {issue.suggestion}")

    print("""
Takeaways:
  - The loop is: run the agent, keep the traces, curate the failures into a dataset, experiment, ship. Then again.
  - Each fix landed in a different part of the agent: one in the harness, one in the context. None needed a new model.
  - A tool that reads traces can find and group the small, specific failures. It did not decide what the agent
    should be for: the out-of-scope requests are still a product question.

  Simulated here: the "users" are a script, their thumbs come from a hidden check per request, and the engine is
  a lookup table. The loop, the traces, the regression tasks and the before/after scores are real.""")


if __name__ == "__main__":
    main()
