import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from lensnode.plugin_package_loader import load_runtime_contract
from lensnode.plugin_runtime import PluginRuntimeError


GITHUB_RUNTIME = load_runtime_contract("github", "1.0.0")


def _execute(tool_key, arguments, handler):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return GITHUB_RUNTIME.execute_tool(
            tool_key,
            client,
            arguments,
            "github-secret",
            "https://github.com",
            {
                "__allowed_scope": {
                    "repositories": ["HyperBDR/sourcelens"],
                }
            },
        )


def test_builds_structured_tools_from_manifest_schemas():
    definition = {
        "key": "github_issue_get",
        "description": "Get one issue from an approved repository.",
        "capability": "repository.read",
        "side_effect": "none",
        "input_schema": {
            "type": "object",
            "properties": {
                "repository": {"type": "string"},
                "number": {"type": "integer"},
            },
            "required": ["repository", "number"],
            "additionalProperties": False,
        },
    }

    tool = GITHUB_RUNTIME.build_tool(
        definition,
        lambda key, arguments, runtime: (key, arguments, runtime),
    )

    assert set(tool.args) == {"repository", "number"}
    assert "runtime" not in tool.args


def test_every_bundled_manifest_tool_builds_with_its_declared_schema():
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "plugins"
        / "github"
        / "1.0.0"
        / "plugin.json"
    )
    definitions = json.loads(manifest_path.read_text())["tools"]

    tools = [
        GITHUB_RUNTIME.build_tool(
            definition,
            lambda key, arguments, runtime: (key, arguments, runtime),
        )
        for definition in definitions
    ]

    assert [tool.name for tool in tools] == [
        definition["key"] for definition in definitions
    ]
    assert all("runtime" not in tool.args for tool in tools)


def test_repository_and_branch_results_are_bounded_and_sanitized():
    def repository_handler(request):
        assert request.url.path == "/repos/HyperBDR/sourcelens"
        return httpx.Response(
            200,
            json={
                "full_name": "HyperBDR/sourcelens",
                "description": "Source analysis",
                "private": True,
                "default_branch": "main",
                "archived": False,
                "fork": False,
                "language": "Python",
                "stargazers_count": 12,
                "forks_count": 3,
                "open_issues_count": 4,
                "updated_at": "2026-09-02T00:00:00Z",
                "html_url": "https://github.com/HyperBDR/sourcelens",
                "owner": {"login": "HyperBDR", "secret": "ignored"},
                "unexpected": "ignored",
            },
            request=request,
        )

    repository = _execute(
        "github_repository_get",
        {"repository": "HyperBDR/sourcelens"},
        repository_handler,
    )

    assert repository == {
        "ok": True,
        "repository": "HyperBDR/sourcelens",
        "description": "Source analysis",
        "private": True,
        "default_branch": "main",
        "archived": False,
        "fork": False,
        "language": "Python",
        "stars": 12,
        "forks": 3,
        "open_issues": 4,
        "updated_at": "2026-09-02T00:00:00Z",
        "url": "https://github.com/HyperBDR/sourcelens",
        "owner": "HyperBDR",
    }

    def branches_handler(request):
        assert request.url.path == "/repos/HyperBDR/sourcelens/branches"
        assert parse_qs(request.url.query.decode()) == {
            "page": ["2"],
            "per_page": ["20"],
        }
        return httpx.Response(
            200,
            json=[
                {
                    "name": "main",
                    "protected": True,
                    "commit": {"sha": "abc", "url": "ignored"},
                }
            ],
            request=request,
        )

    branches = _execute(
        "github_branch_list",
        {"repository": "HyperBDR/sourcelens", "page": 2, "per_page": 20},
        branches_handler,
    )

    assert branches["items"] == [
        {"name": "main", "protected": True, "sha": "abc"}
    ]
    assert branches["page"] == 2


def test_commit_list_and_get_return_stable_fields():
    def list_handler(request):
        assert request.url.path == "/repos/HyperBDR/sourcelens/commits"
        assert parse_qs(request.url.query.decode()) == {
            "page": ["1"],
            "path": ["backend/lens"],
            "per_page": ["20"],
            "sha": ["main"],
            "since": ["2026-09-01T16:00:00Z"],
            "until": ["2026-09-02T15:59:59Z"],
        }
        return httpx.Response(
            200,
            json=[
                {
                    "sha": "abc",
                    "html_url": "https://github.com/c/abc",
                    "commit": {
                        "message": "feat: expand GitHub tools\n\nbody",
                        "author": {
                            "name": "Developer",
                            "date": "2026-09-02T00:00:00Z",
                        },
                    },
                    "author": {"login": "developer"},
                }
            ],
            request=request,
        )

    commits = _execute(
        "github_commit_list",
        {
            "repository": "HyperBDR/sourcelens",
            "ref": "main",
            "path": "backend/lens",
            "page": 1,
            "per_page": 20,
            "since": "2026-09-01T16:00:00Z",
            "until": "2026-09-02T15:59:59Z",
        },
        list_handler,
    )

    assert commits["items"][0]["message"] == "feat: expand GitHub tools"
    assert commits["items"][0]["login"] == "developer"

    def get_handler(request):
        assert request.url.path == "/repos/HyperBDR/sourcelens/commits/abc"
        return httpx.Response(
            200,
            json={
                "sha": "abc",
                "html_url": "https://github.com/c/abc",
                "stats": {"additions": 10, "deletions": 2, "total": 12},
                "commit": {
                    "message": "feat: expand GitHub tools",
                    "author": {"name": "Developer", "date": "now"},
                    "committer": {"name": "Developer", "date": "now"},
                },
                "author": {"login": "developer"},
                "files": [
                    {
                        "filename": "runtime.py",
                        "status": "modified",
                        "additions": 10,
                        "deletions": 2,
                        "changes": 12,
                        "patch": "must not be returned",
                    }
                ],
            },
            request=request,
        )

    commit = _execute(
        "github_commit_get",
        {"repository": "HyperBDR/sourcelens", "ref": "abc"},
        get_handler,
    )

    assert commit["stats"] == {"additions": 10, "deletions": 2, "total": 12}
    assert commit["files"] == [
        {
            "path": "runtime.py",
            "status": "modified",
            "additions": 10,
            "deletions": 2,
            "changes": 12,
        }
    ]
    assert "patch" not in str(commit)


@pytest.mark.parametrize(
    ("tool_key", "path", "payload", "expected"),
    [
        (
            "github_issue_get",
            "/repos/HyperBDR/sourcelens/issues/488",
            {
                "number": 488,
                "title": "Expand tools",
                "state": "open",
                "body": "Bounded body",
                "user": {"login": "author"},
                "labels": [{"name": "feature"}],
                "comments": 2,
                "created_at": "created",
                "updated_at": "updated",
                "closed_at": None,
                "html_url": "https://github.com/i/488",
            },
            {"number": 488, "title": "Expand tools", "author": "author"},
        ),
        (
            "github_pull_request_get",
            "/repos/HyperBDR/sourcelens/pulls/488",
            {
                "number": 488,
                "title": "Expand tools",
                "state": "open",
                "body": "Bounded body",
                "draft": False,
                "merged": False,
                "mergeable": True,
                "user": {"login": "author"},
                "head": {"ref": "feature", "sha": "abc"},
                "base": {"ref": "main", "sha": "def"},
                "commits": 3,
                "additions": 20,
                "deletions": 4,
                "changed_files": 2,
                "comments": 1,
                "review_comments": 2,
                "created_at": "created",
                "updated_at": "updated",
                "merged_at": None,
                "closed_at": None,
                "html_url": "https://github.com/p/488",
            },
            {"number": 488, "title": "Expand tools", "head_ref": "feature"},
        ),
        (
            "github_workflow_run_get",
            "/repos/HyperBDR/sourcelens/actions/runs/99",
            {
                "id": 99,
                "name": "CI",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "workflow_id": 7,
                "run_number": 8,
                "run_attempt": 1,
                "head_branch": "main",
                "head_sha": "abc",
                "actor": {"login": "author"},
                "created_at": "created",
                "updated_at": "updated",
                "html_url": "https://github.com/a/99",
                "jobs_url": "must not be returned",
            },
            {"id": 99, "name": "CI", "actor": "author"},
        ),
    ],
)
def test_detail_tools_use_fixed_endpoints_and_safe_projections(
    tool_key,
    path,
    payload,
    expected,
):
    def handler(request):
        assert request.url.path == path
        return httpx.Response(200, json=payload, request=request)

    identifier = 99 if tool_key == "github_workflow_run_get" else 488
    field = "run_id" if tool_key == "github_workflow_run_get" else "number"
    result = _execute(
        tool_key,
        {"repository": "HyperBDR/sourcelens", field: identifier},
        handler,
    )

    for key, value in expected.items():
        assert result[key] == value
    assert "jobs_url" not in result


def test_list_tools_bound_pages_and_filter_pull_requests_from_issue_results():
    def handler(request):
        assert request.url.path == "/repos/HyperBDR/sourcelens/issues"
        assert parse_qs(request.url.query.decode()) == {
            "labels": ["bug"],
            "page": ["1"],
            "per_page": ["20"],
            "state": ["open"],
        }
        return httpx.Response(
            200,
            json=[
                {
                    "number": 1,
                    "title": "Issue",
                    "state": "open",
                    "user": {"login": "author"},
                    "labels": [{"name": "bug"}],
                    "comments": 0,
                    "created_at": "created",
                    "updated_at": "updated",
                    "html_url": "https://github.com/i/1",
                },
                {
                    "number": 2,
                    "title": "PR returned by issues API",
                    "pull_request": {"url": "ignored"},
                },
            ],
            request=request,
        )

    result = _execute(
        "github_issue_list",
        {
            "repository": "HyperBDR/sourcelens",
            "state": "open",
            "labels": "bug",
            "page": 1,
            "per_page": 20,
        },
        handler,
    )

    assert [item["number"] for item in result["items"]] == [1]
    assert result["has_more"] is False


def test_list_tools_reject_oversized_pages():
    with pytest.raises(PluginRuntimeError, match="PLUGIN_ARGUMENTS_INVALID"):
        _execute(
            "github_commit_list",
            {
                "repository": "HyperBDR/sourcelens",
                "per_page": 21,
            },
            lambda request: httpx.Response(200, json=[], request=request),
        )


def test_comments_files_reviews_releases_and_runs_have_bounded_shapes():
    cases = [
        (
            "github_issue_comments",
            {"repository": "HyperBDR/sourcelens", "number": 1},
            "/repos/HyperBDR/sourcelens/issues/1/comments",
            [{"id": 1, "body": "comment", "user": {"login": "author"}}],
            "body",
        ),
        (
            "github_pull_request_files",
            {"repository": "HyperBDR/sourcelens", "number": 1},
            "/repos/HyperBDR/sourcelens/pulls/1/files",
            [{"filename": "a.py", "status": "modified", "patch": "ignored"}],
            "path",
        ),
        (
            "github_pull_request_reviews",
            {"repository": "HyperBDR/sourcelens", "number": 1},
            "/repos/HyperBDR/sourcelens/pulls/1/reviews",
            [{"id": 2, "state": "APPROVED", "user": {"login": "reviewer"}}],
            "state",
        ),
        (
            "github_release_list",
            {"repository": "HyperBDR/sourcelens"},
            "/repos/HyperBDR/sourcelens/releases",
            [{"id": 3, "tag_name": "v1.0.0", "name": "V1", "assets": [{}]}],
            "tag",
        ),
        (
            "github_workflow_run_list",
            {"repository": "HyperBDR/sourcelens"},
            "/repos/HyperBDR/sourcelens/actions/runs",
            {"workflow_runs": [{"id": 4, "name": "CI", "actor": {}}]},
            "id",
        ),
    ]

    for tool_key, arguments, path, payload, expected_field in cases:
        def handler(request, expected_path=path, response=payload):
            assert request.url.path == expected_path
            return httpx.Response(200, json=response, request=request)

        result = _execute(tool_key, arguments, handler)

        assert expected_field in result["items"][0], tool_key
        assert "patch" not in str(result), tool_key
        assert "assets" not in str(result), tool_key


def test_runtime_rejects_unknown_tools_and_redirects():
    def unknown_handler(request):
        raise AssertionError(request.url)

    with pytest.raises(PluginRuntimeError, match="PLUGIN_TOOL_UNSUPPORTED"):
        _execute(
            "github_api",
            {"repository": "HyperBDR/sourcelens"},
            unknown_handler,
        )

    def redirect_handler(request):
        return httpx.Response(
            302,
            headers={"Location": "https://evil.example"},
            request=request,
        )

    with pytest.raises(PluginRuntimeError, match="GITHUB_REDIRECT_REJECTED"):
        _execute(
            "github_issue_get",
            {"repository": "HyperBDR/sourcelens", "number": 1},
            redirect_handler,
        )


def test_runtime_rejects_scope_and_path_escape_even_with_a_valid_snapshot():
    """Runtime enforces repository and path boundaries independently."""

    def handler(request):
        raise AssertionError(request.url)

    with pytest.raises(PluginRuntimeError, match="PLUGIN_SCOPE_MISMATCH"):
        _execute(
            "github_issue_get",
            {"repository": "other/repository", "number": 1},
            handler,
        )

    with pytest.raises(PluginRuntimeError, match="PLUGIN_ARGUMENTS_INVALID"):
        _execute(
            "github_read_file",
            {
                "repository": "HyperBDR/sourcelens",
                "path": "../secrets.txt",
            },
            handler,
        )
