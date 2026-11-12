from agentlab.context import Context, FileMemory, KeywordRetriever, keywords, remember_tool
from agentlab.lab import COMPANY, company_context


def test_keywords_drop_filler_and_plurals():
    assert keywords("What is our refund window for annual plans?") == {"refund", "window", "annual", "plan"}
    assert "process" in keywords("the release process")


def test_retrieval_returns_only_pages_that_match():
    retriever = KeywordRetriever(COMPANY / "handbook")
    assert [d.id for d in retriever.search("What is our refund window for annual plans?")] == ["refunds.md"]
    assert retriever.search("Set the port to 8080") == []


def test_aliases_and_thresholds_change_what_is_found(tmp_path):
    (tmp_path / "release.md").write_text(
        "# Release process\nRelease notes: new items go under the heading.\nItem format uses {version}.\n"
    )
    task = "Add a changelog entry for version 1.4.0"
    assert KeywordRetriever(tmp_path).search(task) == []
    assert [d.id for d in KeywordRetriever(tmp_path, aliases={"changelog": "release"}).search(task)] == ["release.md"]
    assert [d.id for d in KeywordRetriever(tmp_path, min_overlap=1).search(task)] == ["release.md"]


def test_memory_persists_and_ignores_duplicates(tmp_path):
    memory = FileMemory(tmp_path / "m" / "memory.jsonl")
    assert memory.load() == []
    remember = remember_tool(memory)
    remember.fn(note="Use  bullets.\n")
    remember.fn(note="Use bullets.")
    assert FileMemory(tmp_path / "m" / "memory.jsonl").load() == ["Use bullets."]


def test_sections_are_labelled_and_an_empty_retrieval_is_still_recorded(tmp_path):
    memory = FileMemory(tmp_path / "memory.jsonl")
    memory.add("Prefer short answers.")
    sections = company_context(memory=memory).assemble("Set the port to 8080")
    assert [s.source for s in sections] == ["instructions", "knowledge", "memory"]
    assert sections[1].text == "" and sections[1].meta == {"docs": []}
    assert "Prefer short answers." in sections[2].text
    assert Context().assemble("anything") == []
