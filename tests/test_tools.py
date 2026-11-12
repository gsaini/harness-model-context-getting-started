import pytest

from agentlab.tools import ToolError, Workspace, file_tools


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "work").mkdir()
    (tmp_path / "secret.txt").write_text("outside")
    (tmp_path / "work" / "a.txt").write_text("one\ntwo\nthree\n")
    return Workspace(tmp_path / "work")


def tool(ws, name, edit="edit_file"):
    return next(t for t in file_tools(ws, edit) if t.name == name)


@pytest.mark.parametrize("path", ["../secret.txt", "sub/../../secret.txt", "/etc/passwd", ""])
def test_paths_cannot_leave_the_workspace(ws, path):
    with pytest.raises(ToolError):
        tool(ws, "read_file").fn(path=path)
    with pytest.raises(ToolError):
        tool(ws, "write_file").fn(path=path, content="x")


def test_a_symlink_out_of_the_workspace_is_refused(ws, tmp_path):
    (ws.root / "link").symlink_to(tmp_path / "secret.txt")
    with pytest.raises(ToolError, match="outside the workspace"):
        tool(ws, "read_file").fn(path="link")


def test_list_read_write(ws):
    tool(ws, "write_file").fn(path="deep/b.txt", content="hi")
    assert tool(ws, "list_files").fn().splitlines() == ["a.txt", "deep/b.txt"]
    assert tool(ws, "list_files").fn(dir="deep") == "deep/b.txt"
    assert tool(ws, "read_file").fn(path="deep/b.txt") == "hi"
    with pytest.raises(ToolError, match="no such file"):
        tool(ws, "read_file").fn(path="missing.txt")


def test_edit_file_needs_exactly_one_match(ws):
    (ws.root / "dup.txt").write_text("x = 1\ny = 1\n")
    edit = tool(ws, "edit_file")
    with pytest.raises(ToolError, match="not found"):
        edit.fn(path="dup.txt", old_str="z", new_str="q")
    with pytest.raises(ToolError, match="matches 2 places"):
        edit.fn(path="dup.txt", old_str="1", new_str="2")
    edit.fn(path="dup.txt", old_str="x = 1", new_str="x = 2")
    assert (ws.root / "dup.txt").read_text() == "x = 2\ny = 1\n"


def test_patch_lines_replaces_a_range_and_checks_bounds(ws):
    patch = tool(ws, "patch_lines", edit="patch_lines")
    patch.fn(path="a.txt", start_line=2, end_line=2, new_text="TWO\n2b")
    assert (ws.root / "a.txt").read_text() == "one\nTWO\n2b\nthree\n"
    with pytest.raises(ToolError, match="out of range"):
        patch.fn(path="a.txt", start_line=9, end_line=9, new_text="x")


def test_tool_input_is_validated(ws):
    read = tool(ws, "read_file")
    assert read.validate({"path": "a.txt"}) == {"path": "a.txt"}
    for bad in ({}, {"path": 3}, {"path": "a.txt", "extra": 1}, "a.txt"):
        with pytest.raises(ToolError):
            read.validate(bad)
    with pytest.raises(ToolError):  # a bool is not an integer
        tool(ws, "patch_lines", edit="patch_lines").validate(
            {"path": "a", "start_line": True, "end_line": 1, "new_text": ""}
        )
