"""Lesson 5 · Build or buy, and keeping the in-distribution pieces close."""

from agentlab import show
from agentlab.evals.report import table
from agentlab.lab import build_agent
from agentlab.models import get_model


def attempt(task, model_name, edit):
    with show.sandbox(task) as workspace:
        result = build_agent(get_model(model_name), workspace, edit=edit).run(task.instruction)
        verdict = show.verdict(task, workspace)
        return result, verdict, (workspace / "server.js").read_text()


def main() -> None:
    show.title("Lesson 5 · Build or buy, and keeping the in-distribution pieces close")
    task = show.task("two-edits")
    print(f"\ntask: {task.instruction}")

    show.part("A) One job, two tool shapes, two models")
    print(
        "edit_file(path, old_str, new_str)              replace an exact string   <- what `scripted-careful` is used to"
    )
    print(
        "patch_lines(path, start_line, end_line, text)  replace a range of lines  <- what `scripted-liner` is used to\n"
    )
    rows, broken = [], ""
    for model_name in ("scripted-careful", "scripted-liner"):
        for edit in ("edit_file", "patch_lines"):
            result, verdict, content = attempt(task, model_name, edit)
            native = get_model(model_name).native_edit_tool == edit
            tokens = result.usage["input_tokens"] + result.usage["output_tokens"]
            rows.append(
                {
                    "model": model_name,
                    "edit tool offered": edit + (" (native)" if native else ""),
                    "model calls": result.steps,
                    "tokens": tokens,
                    "result": "pass" if verdict == "PASS" else "FAIL",
                }
            )
            if model_name == "scripted-careful" and edit == "patch_lines":
                broken = content
    print(table(rows))

    show.part("B) The failure made no noise: no tool error, and the agent said it was done")
    print("server.js after `scripted-careful` used patch_lines (line numbers from one read, applied top-down):\n")
    for number, line in enumerate(broken.split("\n")[:5], 1):
        note = "   <- the helmet line was here for a moment; the second patch overwrote it" if number == 3 else ""
        note = "   <- still 3000: the patch meant for this line landed one line up" if number == 4 else note
        print(f"  {number}  {line}{note}")

    show.part("C) The fix is in the harness: give each model the tool shape it knows")
    for model_name in ("scripted-careful", "scripted-liner"):
        model = get_model(model_name)
        result, verdict, _ = attempt(task, model_name, None)  # edit=None: build_agent asks the model's profile
        print(
            f"  {model_name:<17} -> harness offers {model.native_edit_tool:<12} -> {verdict} in {result.steps} model calls"
        )

    print("""
Takeaways:
  - Models are best at what they saw in training. A tool shaped like the ones they trained on is "in distribution".
  - Invent your own harness where your *domain* is unusual. Keep ordinary operations, like editing a file, ordinary.
  - "Out of distribution" rarely looks like an error. It looks like a wrong result, or a right one at twice the cost.

  Simulated here: which shape each stand-in model is "used to" is a setting. With real models, measure it:
  run the same eval with each tool shape (`build_agent(..., edit=...)`) and compare.""")


if __name__ == "__main__":
    main()
