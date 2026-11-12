from agentlab import ROOT
from agentlab.flywheel import analyze, cluster, generate, run_traffic, signature
from agentlab.lab import V1

LIVE = V1.but("prod-v1", "", protect=(".env",))
NEXT = LIVE.but("prod-v2", "", compaction="summarize", extra_knowledge=(ROOT / "fixtures" / "proposed",))


def test_traffic_is_reproducible():
    first, second = generate(20, seed=3), generate(20, seed=3)
    assert [r.instruction for r in first] == [r.instruction for r in second]
    assert [r.instruction for r in first] != [r.instruction for r in generate(20, seed=4)]


def test_failures_are_clustered_from_traces_and_the_fix_improves_the_same_traffic():
    requests = generate(40, seed=42)
    before = run_traffic(requests, LIVE)
    issues = {issue.signature: issue for issue in analyze(cluster(before))}
    assert set(issues) == {"context_overflow", "no_knowledge_retrieved", "declined"}
    assert issues["context_overflow"].pillar == "harness" and issues["context_overflow"].change == {
        "compaction": "summarize"
    }
    assert issues["no_knowledge_retrieved"].pillar == "context"
    assert issues["declined"].change is None  # nothing a harness setting can fix
    assert all(signature(run) == "context_overflow" for run in cluster(before)["context_overflow"])

    after = run_traffic(requests, NEXT)
    assert sum(r.thumbs_up for r in before) == 31 and sum(r.thumbs_up for r in after) == 38
    assert set(cluster(after)) == {"declined"}
