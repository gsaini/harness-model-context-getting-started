import pytest

from agentlab.evals import run_trial
from agentlab.harness import State
from agentlab.lab import V0, V1, V3
from agentlab.middleware import ProtectPaths, Tracer
from agentlab.models import get_model
from agentlab.tools import ToolError


@pytest.mark.parametrize("path", [".env", "./.env", "sub/../.env", "config/.env", ".env/x"])
def test_protected_paths_are_blocked_however_they_are_spelled(path):
    guard = ProtectPaths([".env"])
    state = State("t", get_model(), [], "", [], [])
    with pytest.raises(ToolError, match="blocked by policy"):
        guard.wrap_tool_call({"name": "read_file", "input": {"path": path}}, lambda c: "leaked", state)


def test_other_paths_pass_through():
    guard = ProtectPaths([".env"])
    state = State("t", get_model(), [], "", [], [])
    assert guard.wrap_tool_call({"name": "read_file", "input": {"path": "env.md"}}, lambda c: "ok", state) == "ok"


def test_the_guard_stops_the_planted_instruction(tasks):
    assert not run_trial(tasks["secret-safe"], V1).passed  # follows the instruction in the file, leaks the secret
    tracer = Tracer()
    assert run_trial(tasks["secret-safe"], V3, tracer=tracer).passed
    assert [e["path"] for e in tracer.events if e["type"] == "blocked"] == [".env"]


def test_three_ways_to_handle_a_long_run(tasks):
    task = tasks["invoice-total"]
    none = run_trial(task, V0)
    assert (none.status, none.passed) == ("error", False) and "ContextOverflow" in none.error

    truncated = run_trial(task, V0.but("t", "", compaction="truncate"))
    assert (truncated.status, truncated.passed) == ("max_steps", False)  # alive, and going in circles

    tracer = Tracer()
    summarized = run_trial(task, V0.but("s", "", compaction="summarize"), tracer=tracer)
    assert (summarized.status, summarized.passed) == ("done", True)
    compactions = [e for e in tracer.events if e["type"] == "compaction"]
    assert len(compactions) >= 2 and all(e["after_tokens"] < e["before_tokens"] for e in compactions)


def test_a_trace_accounts_for_every_token_in_the_window(tasks, tmp_path):
    tracer = Tracer(tmp_path / "trace.jsonl")
    run_trial(tasks["refund-policy"], V1, tracer=tracer)
    start, *middle, end = tracer.events
    assert start["type"] == "run_start" and end["type"] == "run_end" and end["status"] == "done"
    knowledge = next(s for s in start["sections"] if s["source"] == "knowledge")
    assert knowledge["docs"] == ["refunds.md"] and knowledge["tokens"] > 0
    for call in (e for e in middle if e["type"] == "model_call"):
        assert sum(call["window"]["parts"].values()) == call["window"]["total"] == call["usage"]["input_tokens"]
    assert len((tmp_path / "trace.jsonl").read_text().splitlines()) == len(tracer.events)
