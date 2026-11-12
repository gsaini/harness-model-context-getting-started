"""Lesson 7 · Observability: what was in the window?"""

from pathlib import Path

from agentlab import show
from agentlab.context import Context, KeywordRetriever, keywords
from agentlab.lab import COMPANY, build_agent
from agentlab.middleware import Tracer
from agentlab.models import get_model
from agentlab.traceview import trajectory, window

HERE = Path(__file__).parent
BASICS = (
    "- Change only what the task asks for. Leave formatting and unrelated settings as they are.\n"
    "- If a file is not where the task says, look for it before you create a new one."
)


def context(**retriever_options) -> Context:
    """This team keeps its changelog conventions in the knowledge base (kb/release-process.md), not in AGENTS.md."""
    return Context(
        instructions=BASICS, knowledge=KeywordRetriever(COMPANY / "handbook", HERE / "kb", **retriever_options)
    )


def run(task, ctx):
    with show.sandbox(task) as workspace:
        tracer = Tracer()
        result = build_agent(get_model(), workspace, context=ctx, tracer=tracer).run(task.instruction)
        return result, show.verdict(task, workspace), tracer.events


def main() -> None:
    show.title("Lesson 7 · Observability: what was in the window?")
    task = show.task("changelog-entry")

    show.part("A) What you see from the outside")
    result, verdict, events = run(task, context())
    print(f"task:     {task.instruction}")
    print(f"agent:    {result.answer}   (status: {result.status}, no errors)")
    print(f"verifier: {verdict}")
    print(
        "\nThe conventions are written down, in kb/release-process.md. So is the model bad, or is something else wrong?"
    )

    show.part("B) The trajectory: what the agent did")
    print(trajectory(events, bars=False))

    show.part("C) The window: what the model was actually sent at step 2, when it decided")
    print(window(events, 2))

    show.part("D) The cause is in the context, not the model")
    page = (HERE / "kb" / "release-process.md").read_text()
    asked, has = keywords(task.instruction), keywords(page)
    print(f"keywords in the task:    {sorted(asked)}")
    print(f"keywords in the page:    {sorted(has)}")
    print(f"shared:                  {sorted(asked & has)}   (retrieval needs at least 2)")
    print('The task says "changelog"; the page says "release notes". Retrieval never connected them.')

    show.part('E) Fix the retrieval (treat "changelog" as "release"), run again')
    result, verdict, events = run(task, context(aliases={"changelog": "release"}))
    print(f"agent:    {result.answer}")
    print(f"verifier: {verdict}\n")
    print(window(events, 2))

    print("""
Takeaways:
  - When an agent gets something wrong, the model call usually did its job with what it was given.
    Look at what it was given first: more often than not, the context was poor.
  - Keep both views: the trajectory (the sequence of steps) and the full window of any one model call.
  - Label where every part of the prompt came from. "knowledge: 0 tokens" took one glance to spot.

Keep traces as files and read them later:
  uv run agentlab eval --traces runs
  uv run agentlab trace runs/v0/changelog-entry.jsonl            # the trajectory
  uv run agentlab trace runs/v0/changelog-entry.jsonl --step 2   # one window""")


if __name__ == "__main__":
    main()
