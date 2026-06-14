import json

from lensnode.agent_tools import build_agent_tools
from lensnode.workspace import (
    glob_files,
    read_workspace_window,
    search_workspace,
)

OLD_SIZE_CAP = 256 * 1024
TRUNCATED_LINE_CEILING = 2000 + len("…[truncated]")


def _make_big_file(path, keyword_line_no, keyword="Horcrux", total=10000):
    """Write a UTF-8 file larger than the old 256KB cap."""

    lines = []
    for index in range(1, total + 1):
        if index == keyword_line_no:
            lines.append(f"line {index}: the {keyword} secret was shared")
        else:
            lines.append(f"line {index}: ordinary narrative filler text here")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_search_returns_line_matches_for_large_file(tmp_path):
    root = tmp_path / "books"
    root.mkdir()
    big = _make_big_file(root / "book.txt", keyword_line_no=5000)
    assert big.stat().st_size > OLD_SIZE_CAP

    result = search_workspace([{"path": str(root)}], "Horcrux")

    matches = result["matches"]
    assert matches, "a >256KB file must still be searchable"
    hit = next(item for item in matches if item["line"] == 5000)
    assert "Horcrux" in hit["text"]
    assert hit["path"].endswith("book.txt")
    assert any(item["n"] == 4999 for item in hit["before"])
    assert any(item["n"] == 5001 for item in hit["after"])


def test_max_file_size_policy_is_ignored(tmp_path):
    root = tmp_path / "books"
    root.mkdir()
    _make_big_file(root / "book.txt", keyword_line_no=20)

    result = search_workspace(
        [{"path": str(root)}],
        "Horcrux",
        policy={"max_file_size": 1024},
    )

    assert result["matches"], "deprecated max_file_size must no longer exclude"


def test_ranking_prioritizes_broad_term_coverage(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    # alphabetically first, but only one query term repeated -> noise
    (root / "aaa.txt").write_text(
        "\n".join(["alpha noise"] * 5) + "\n", encoding="utf-8"
    )
    # alphabetically last, but covers all three query terms -> relevant
    (root / "zzz.txt").write_text(
        "alpha line\nbeta line\ngamma line\n", encoding="utf-8"
    )

    result = search_workspace([{"path": str(root)}], "alpha beta gamma")

    assert result["matches"]
    assert result["matches"][0]["path"].endswith("zzz.txt")


def test_image_and_vector_assets_excluded_from_search(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "diagram.svg").write_text(
        "<text>deployment topology</text>\n", encoding="utf-8"
    )
    (root / "guide.md").write_text("deployment steps here\n", encoding="utf-8")

    result = search_workspace([{"path": str(root)}], "deployment")

    paths = [match["path"] for match in result["matches"]]
    assert any(path.endswith("guide.md") for path in paths)
    assert not any(path.endswith(".svg") for path in paths)


def test_regex_search_matches_pattern(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "log.txt").write_text(
        "start\nERROR_CODE_42 happened\nok\nERROR_CODE_99 again\n",
        encoding="utf-8",
    )

    result = search_workspace(
        [{"path": str(root)}], r"ERROR_CODE_\d+", regex=True
    )

    assert sorted(match["line"] for match in result["matches"]) == [2, 4]


def test_output_mode_files_lists_matching_files(tmp_path):
    root = tmp_path / "ws"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("deploy here\n", encoding="utf-8")
    (root / "sub" / "b.txt").write_text("nothing\n", encoding="utf-8")

    result = search_workspace(
        [{"path": str(root)}], "deploy", output_mode="files"
    )

    assert result["mode"] == "files"
    assert any(path.endswith("a.txt") for path in result["files"])
    assert not any(path.endswith("b.txt") for path in result["files"])


def test_output_mode_count_returns_per_file_counts(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.txt").write_text("deploy\ndeploy\nother\n", encoding="utf-8")

    result = search_workspace(
        [{"path": str(root)}], "deploy", output_mode="count"
    )

    assert result["mode"] == "count"
    assert result["counts"][0]["path"].endswith("a.txt")
    assert result["counts"][0]["count"] == 2


def test_glob_filter_restricts_search_by_type(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.md").write_text("deploy steps\n", encoding="utf-8")
    (root / "b.py").write_text("deploy = 1\n", encoding="utf-8")

    result = search_workspace([{"path": str(root)}], "deploy", glob="**/*.md")

    paths = [match["path"] for match in result["matches"]]
    assert any(path.endswith("a.md") for path in paths)
    assert not any(path.endswith("b.py") for path in paths)


def test_glob_files_finds_by_type(tmp_path):
    root = tmp_path / "ws"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "one.md").write_text("x\n", encoding="utf-8")
    (root / "docs" / "two.md").write_text("y\n", encoding="utf-8")
    (root / "code.py").write_text("z\n", encoding="utf-8")

    files = glob_files([{"path": str(root)}], "**/*.md")

    assert len(files) == 2
    assert all(path.endswith(".md") for path in files)


def test_glob_files_by_name_pattern(tmp_path):
    root = tmp_path / "ws"
    (root / "installation").mkdir(parents=True)
    (root / "installation" / "agione-quick-install.md").write_text(
        "x\n", encoding="utf-8"
    )
    (root / "readme.md").write_text("y\n", encoding="utf-8")

    files = glob_files([{"path": str(root)}], "**/*install*")

    assert any(path.endswith("agione-quick-install.md") for path in files)
    assert not any(path.endswith("readme.md") for path in files)


def test_glob_files_handles_invalid_pattern(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.md").write_text("x\n", encoding="utf-8")

    # an absolute pattern is invalid for pathlib glob and must not raise
    assert glob_files([{"path": str(root)}], "/etc/passwd") == []


def test_read_window_pages_with_offset_and_limit(tmp_path):
    target = tmp_path / "doc.txt"
    target.write_text(
        "\n".join(f"row {index}" for index in range(1, 1001)) + "\n",
        encoding="utf-8",
    )

    window = read_workspace_window(str(target), offset=1, limit=100)
    assert window["start_line"] == 1
    assert window["end_line"] == 100
    assert window["returned_lines"] == 100
    assert window["has_more"] is True
    assert window["content"].startswith("1\trow 1")

    deep = read_workspace_window(str(target), offset=950, limit=100)
    assert deep["start_line"] == 950
    assert deep["end_line"] == 1000
    assert deep["has_more"] is False
    assert "950\trow 950" in deep["content"]


def test_read_window_rejects_binary(tmp_path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"PK\x03\x04\x00\x00binary\x00content")

    window = read_workspace_window(str(target))

    assert window["error"] == "BINARY_FILE"


def test_long_lines_are_truncated(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    long_line = "x" * 5000 + " NEEDLE " + "y" * 5000
    (root / "wide.txt").write_text(long_line + "\n", encoding="utf-8")

    result = search_workspace([{"path": str(root)}], "NEEDLE")

    text = result["matches"][0]["text"]
    assert "truncated" in text
    assert len(text) <= TRUNCATED_LINE_CEILING


def test_search_without_match_lists_nested_files(tmp_path):
    root = tmp_path / "ws"
    nested = root / "inner"
    nested.mkdir(parents=True)
    (nested / "a.txt").write_text("alpha beta gamma\n", encoding="utf-8")

    result = search_workspace([{"path": str(root)}], "zzzznomatchquery")

    assert result["matches"] == []
    assert any(path.endswith("a.txt") for path in result["files"])
    assert "note" in result


def test_tools_search_and_read_large_file_through_wrapper(tmp_path):
    root = tmp_path / "books"
    root.mkdir()
    big = _make_big_file(root / "book.txt", keyword_line_no=10)
    tools = {
        tool.name: tool
        for tool in build_agent_tools(
            {"target_dirs": [{"path": str(root)}], "settings": {}}
        )
    }

    search_out = json.loads(
        tools["search_workspace"].invoke({"query": "Horcrux"})
    )
    assert search_out["matches"]
    line = search_out["matches"][0]["line"]

    read_out = json.loads(
        tools["read_workspace_file"].invoke(
            {"path": str(big), "offset": line, "limit": 5}
        )
    )
    assert read_out["start_line"] == line
    assert "Horcrux" in read_out["content"]


def test_tool_lists_nested_files_when_path_is_directory(tmp_path):
    root = tmp_path / "harrypotter"
    inner = root / "HarryPotter"
    inner.mkdir(parents=True)
    (inner / "book01.txt").write_text("once upon a time\n", encoding="utf-8")
    tools = {
        tool.name: tool
        for tool in build_agent_tools(
            {"target_dirs": [{"path": str(root)}], "settings": {}}
        )
    }

    out = json.loads(tools["read_workspace_file"].invoke({"path": str(root)}))

    assert out["error"] == "PATH_IS_DIRECTORY"
    assert any(path.endswith("book01.txt") for path in out["candidate_files"])
