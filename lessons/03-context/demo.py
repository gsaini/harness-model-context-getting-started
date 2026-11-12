"""Lesson 3 · Context: instructions, knowledge and memory."""

import tempfile
from pathlib import Path

from agentlab import show
from agentlab.context import Context, FileMemory, KeywordRetriever
from agentlab.lab import COMPANY, build_agent, company_context
from agentlab.middleware import Tracer
from agentlab.models import get_model
from agentlab.traceview import window

FEEDBACK = (
    "That's not how we write our changelog. Remember: changelog entries go under the "
    '"## Unreleased" heading. Entry format: "- **{version}** — {text}"'
)


def attempt(task, context, **options):
    """Run a task in a fresh sandbox. Returns (verdict, what the agent said, the tracer)."""
    with show.sandbox(task) as workspace:
        tracer = Tracer()
        result = build_agent(get_model(), workspace, context=context, tracer=tracer, **options).run(task.instruction)
        return show.verdict(task, workspace), result.answer, tracer


def main() -> None:
    show.title("Lesson 3 · Context: instructions, knowledge and memory")
    model = get_model()

    show.part("A) Instructions: how we do things here (always in the window)")
    task = show.task("changelog-entry")
    print(f"task: {task.instruction}\n")
    for label, context in [
        ("no context", None),
        ("with AGENTS.md", Context(instructions=(COMPANY / "AGENTS.md").read_text())),
    ]:
        verdict, answer, _ = attempt(task, context)
        print(f"  {label:<15} agent: {answer:<52} verifier: {verdict}")

    show.part("B) Knowledge: facts looked up for this task (only the pages that match)")
    task = show.task("refund-policy")
    print(f"task: {task.instruction}\n")
    retriever = KeywordRetriever(COMPANY / "handbook")
    print(
        f"  the handbook has {len(retriever.docs)} pages; retrieval picks: {[d.id for d in retriever.search(task.instruction)]}\n"
    )
    for label, context in [("no context", None), ("with handbook", Context(knowledge=retriever))]:
        verdict, answer, _ = attempt(task, context)
        print(f"  {label:<15} agent: {answer}\n  {'':<15} verifier: {verdict}")

    show.part("C) Memory: what the agent learned in an earlier session")
    task = show.task("changelog-entry")
    with tempfile.TemporaryDirectory() as tmp:
        memory = FileMemory(Path(tmp) / "memory.jsonl")
        with show.sandbox(task) as workspace:
            agent = build_agent(model, workspace, context=Context(memory=memory), memory=memory)
            first = agent.run(task.instruction)
            print(f"  session 1   agent: {first.answer}")
            print(f"              verifier: {show.verdict(task, workspace)}")
            print("              user:  That's not how we write our changelog. Remember: ...")
            second = agent.run(FEEDBACK, history=first.messages)
            print(f"              agent: {second.answer}")
        print(f"\n  memory file now holds: {memory.load()}\n")
        with show.sandbox(task) as workspace:  # a new session: new conversation, new workspace, same memory
            agent = build_agent(model, workspace, context=Context(memory=memory), memory=memory)
            again = agent.run(task.instruction)
            print(f"  session 2   agent: {again.answer}")
            print(f"              verifier: {show.verdict(task, workspace)}   <- nobody told it this time")

    show.part("D) Context is not free: it is in the window on every model call")
    task = show.task("refund-policy")
    _, _, tracer = attempt(task, company_context())
    print(window(tracer.events, 1))
    calls = [e for e in tracer.events if e["type"] == "model_call"]
    system = calls[0]["window"]["parts"]["system"]
    print(
        f"\n  {len(calls)} model calls in this run x {system} system-prompt tokens = {len(calls) * system} tokens spent on context."
    )

    print("""
Takeaways:
  - The model is general. Context is what makes it answer like someone who works at your company.
  - Instructions are always on, knowledge is fetched per task, memory accumulates. All three end up as text in the window.
  - Own this data. It is the part of the agent a competitor can't download.""")


if __name__ == "__main__":
    main()
