from agentlab.cli import main


def test_all_lessons_run_and_show_their_point(capsys):
    assert main(["lesson", "all"]) == 0
    out = capsys.readouterr().out
    for expected in [
        "Found it at config/settings.json.",  # 1: recovers from a tool error
        "status: max_steps",  # 1: the harness stops a runaway model
        "The fast model costs 13x less and breaks two tasks.",  # 2
        "<- nobody told it this time",  # 3: memory
        "policy:protect-paths blocked read_file on .env",  # 4
        "~~ compaction (summarize)",  # 4
        "scripted-careful  patch_lines",  # 5
        "passed               4/8    6/8    7/8   8/8",  # 6
        "regressed: changelog-entry, secret-safe",  # 6
        "knowledge               0  <- retrieval ran and found NOTHING",  # 7
        "<- retrieved: release-process.md",  # 7
        "decision:  ship prod-v2",  # 8
        "after:  thumbs up 38, thumbs down 2  (95% satisfied)",  # 8
    ]:
        assert expected in out, expected
    assert "Traceback" not in out


def test_eval_oracle_and_trace_commands(capsys, tmp_path):
    assert main(["eval", "--candidates", "v0,v3", "--traces", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "4/8" in out and "8/8" in out
    assert main(["trace", str(tmp_path / "v0" / "invoice-total.jsonl")]) == 0
    assert "MODEL CALL FAILED: ContextOverflow" in capsys.readouterr().out
    assert main(["trace", str(tmp_path / "v3" / "refund-policy.jsonl"), "--step", "1"]) == 0
    assert "<- retrieved: refunds.md" in capsys.readouterr().out
    assert main(["oracle"]) == 0
    assert "NO" not in capsys.readouterr().out


def test_a_paid_model_needs_an_explicit_yes(capsys):
    assert main(["eval", "--model", "claude"]) == 2
    assert "Add --yes" in capsys.readouterr().err
    assert main(["eval", "--candidates", "v9"]) == 2
    assert main(["lesson", "99"]) == 2
