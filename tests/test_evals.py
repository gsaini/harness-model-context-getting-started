from agentlab import ROOT
from agentlab.evals import compare, load_tasks, oracle, run_benchmark, run_trial, scoreboard, totals
from agentlab.lab import CANDIDATES, V0, V3


def test_every_task_fails_untouched_and_passes_its_reference_solution(tasks):
    report = oracle(tasks.values())
    assert len(report) == 8
    assert all(row["ok"] for row in report), [row for row in report if not row["ok"]]


def test_tasks_have_the_harbor_layout():
    for task_dir in (ROOT / "tasks").iterdir():
        for part in (
            "instruction.md",
            "task.toml",
            "environment/Dockerfile",
            "solution/solve.sh",
            "tests/test.sh",
            "tests/verify.py",
        ):
            assert (task_dir / part).is_file(), f"{task_dir.name}/{part}"
    assert (ROOT / "tasks" / "secret-safe" / "environment" / "workspace" / ".env").is_file()


def test_each_harness_version_fixes_what_it_was_built_for(tasks):
    trials = run_benchmark(tasks.values(), CANDIDATES.values())
    passed = {name: {t.task for t in trials if t.candidate == name and t.passed} for name in CANDIDATES}
    assert [len(passed[name]) for name in ("v0", "v1", "v2", "v3")] == [4, 6, 7, 8]
    assert passed["v1"] - passed["v0"] == {"changelog-entry", "refund-policy"}  # context
    assert passed["v2"] - passed["v1"] == {"invoice-total"}  # compaction
    assert passed["v3"] - passed["v2"] == {"secret-safe"}  # policy guard
    assert compare(trials, "v0", "v3") == {
        "fixed": ["changelog-entry", "invoice-total", "refund-policy", "secret-safe"],
        "regressed": [],
    }
    assert "8/8" in scoreboard(trials).splitlines()[-1]
    assert [row["passed"] for row in totals(trials)] == ["4/8", "6/8", "7/8", "8/8"]


def test_a_cheaper_model_is_a_regression_the_benchmark_catches(tasks):
    cheaper = V3.but("cheaper", "", model="scripted-fast")
    trials = run_benchmark(tasks.values(), [V3, cheaper])
    assert compare(trials, "v3", "cheaper")["regressed"] == ["config-missing-file", "config-timeout"]
    cost = {row["harness"]: row["cost ($)"] for row in totals(trials)}
    assert cost["cheaper"] < cost["v3"] / 10


def test_tool_shape_decides_the_outcome(tasks):
    task = tasks["two-edits"]

    def outcome(model, edit):
        trial = run_trial(task, V0.but("x", "", model=model, edit=edit))
        return trial.passed, trial.steps

    assert outcome("scripted-careful", "edit_file") == (True, 3)
    assert outcome("scripted-careful", "patch_lines") == (False, 3)  # no error raised: a silently wrong file
    assert outcome("scripted-liner", "patch_lines") == (True, 3)
    assert outcome("scripted-liner", "edit_file") == (True, 5)  # recovers, at a price
    assert outcome("scripted-liner", None) == (True, 3)  # the harness picks the model's own shape


def test_traces_are_written_per_harness_and_task(tasks, tmp_path):
    trial = run_trial(tasks["config-port"], V0, traces=tmp_path)
    assert trial.trace == tmp_path / "v0" / "config-port.jsonl" and trial.trace.is_file()
    assert load_tasks(ROOT / "tasks")[0].meta["category"]
