"""Lesson 1 · An agent is a harness, a model and context."""

from agentlab import show
from agentlab.harness import Agent, Response
from agentlab.lab import company_context
from agentlab.messages import text, tool_use
from agentlab.middleware import Tracer
from agentlab.models import get_model
from agentlab.tools import Workspace, file_tools
from agentlab.traceview import trajectory


class StuckModel:
    """A model that never finishes: it asks to list the files, forever."""

    name, context_window, native_edit_tool = "stuck", 100_000, "edit_file"

    def complete(self, *, system, messages, tools):
        again = tool_use(f"toolu_{len(messages)}", "list_files", {})
        return Response(
            [text("Let me look around once more."), again], "tool_use", {"input_tokens": 0, "output_tokens": 0}
        )

    def cost(self, usage):
        return 0.0


def main() -> None:
    show.title("Lesson 1 · An agent is a harness, a model and context")
    task = show.task("config-missing-file")

    with show.sandbox(task) as workspace:
        model = get_model("scripted-careful")  # 1. the model: swappable (lesson 2)
        context = company_context()  # 2. the context: what makes it *your* agent (lesson 3)
        tracer = Tracer()
        agent = Agent(  # 3. the harness: the loop, the tools, the middleware (lessons 4 and 5)
            model=model,
            context=context,
            tools=file_tools(Workspace(workspace)),
            middleware=[tracer],
            max_steps=20,
        )
        agent.run(task.instruction)

        start = tracer.events[0]
        show.part("A) The three parts")
        print(f"model    {model.name}")
        print(
            "context  "
            + ", ".join(f"{s['source']} ({s['tokens']} tokens)" for s in start["sections"] if s["source"] != "base")
        )
        print(
            f"harness  a loop (at most {agent.max_steps} model calls) + tools ({', '.join(start['tools'])}) + middleware (tracer)"
        )

        show.part("B) The loop, turn by turn")
        print(trajectory(tracer.events, bars=False))
        print(f"\nverifier: {show.verdict(task, workspace)}")

    show.part("C) The harness, not the model, decides when a run is over")
    with show.sandbox(task) as workspace:
        runaway = Agent(model=StuckModel(), tools=file_tools(Workspace(workspace)), max_steps=5)
        result = runaway.run(task.instruction)
    print(f"A model that never stops calling tools -> status: {result.status} ({result.error})")

    print("""
Takeaways:
  - The model only ever produces text and tool requests. The harness runs the tools and feeds the results back.
  - A tool error is a message to the model, not a crash: in step 1 the file was missing, and the model adapted.
  - The run ends when the model answers without calling a tool, or when the harness says "enough".""")


if __name__ == "__main__":
    main()
