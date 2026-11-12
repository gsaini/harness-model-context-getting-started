"""Lesson 2 · Swap the model, keep the harness."""

from agentlab import ROOT, show
from agentlab.evals import load_tasks, run_benchmark, scoreboard, totals
from agentlab.evals.report import table
from agentlab.lab import V3, build_agent, company_context
from agentlab.middleware import Tracer
from agentlab.models import get_model
from agentlab.traceview import trajectory


def main() -> None:
    show.title("Lesson 2 · Swap the model, keep the harness")
    tasks = load_tasks(ROOT / "tasks")

    show.part("A) Same harness, same tasks, two models")
    print('The whole change:  get_model("scripted-careful")  ->  get_model("scripted-fast")\n')
    columns = [V3.but(name, "", model=name) for name in ("scripted-careful", "scripted-fast")]
    trials = run_benchmark(tasks, columns)
    print(scoreboard(trials))
    print()
    rows = totals(trials)
    print(table([{"model": r["harness"], **{k: v for k, v in r.items() if k != "harness"}} for r in rows]))
    careful, fast = (r["cost ($)"] for r in rows)
    print(
        f"\nThe fast model costs {careful / fast:.0f}x less and breaks two tasks. (Prices of the stand-in models are made up.)"
    )

    show.part("B) Why it broke: the trace of `config-timeout` on the fast model")
    task = show.task("config-timeout")
    with show.sandbox(task) as workspace:
        tracer = Tracer()
        agent = build_agent(get_model("scripted-fast"), workspace, context=company_context(), tracer=tracer)
        agent.run(task.instruction)
        print(trajectory(tracer.events, bars=False))
        print(f"\nverifier: {show.verdict(task, workspace)}")
        print("\nconfig.json afterwards:")
        print(show.indent((workspace / "config.json").read_text().rstrip()))

    show.part("C) The same benchmark on a real model")
    print("  uv run agentlab eval --model claude --yes              # Claude Opus 5.5")
    print("  uv run agentlab eval --model claude-haiku-5-5 --yes    # a cheaper Claude model")
    print("  (needs ANTHROPIC_API_KEY; costs money; results vary from run to run, so add --trials 3)")

    print("""
Takeaways:
  - The model sits behind one small interface: complete(system, messages, tools) -> content, stop reason, usage.
  - Because the harness doesn't care which model answers, switching is a one-line change, not a rewrite.
  - Whether a switch is *safe* is a question only your own eval can answer. The agent said "Done" both times.""")


if __name__ == "__main__":
    main()
