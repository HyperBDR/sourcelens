import json
import os
import subprocess
import time
from pathlib import Path

from langchain_core.tools import tool
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .workspace import (
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_EXCLUDED_EXTENSIONS,
    glob_files,
    read_workspace_window,
    search_workspace as search_workspace_files,
)


# Tools that emit their own tool.<name>.start/.done events. The generic
# tool.<name>.invoke event is suppressed for these to avoid duplicate trace
# entries (their .start already carries the richer argument summary).
SELF_REPORTING_TOOLS = {
    "search_workspace",
    "read_workspace_file",
    "find_files",
    "git_log",
    "git_diff",
    "summarize_recent_changes",
}


class _ReadWorkspaceFileArgs(BaseModel):
    """Args schema for read_workspace_file.

    Accepts both ``file_path`` (the name LLMs most often emit, matching the
    common read-file convention) and ``path``. The field has a default so
    LangChain still binds it when the value arrives via the alias, which it
    would otherwise drop for a required field.
    """

    model_config = ConfigDict(populate_by_name=True)

    path: str = Field(
        default="",
        validation_alias=AliasChoices("file_path", "path"),
        description="Workspace file path to read.",
    )
    offset: int = Field(default=1, description="1-based start line.")
    limit: int = Field(default=250, description="Max lines to read.")


def build_agent_tools(command, emit_event=None):
    """Build read-only tools scoped to the selected workspace dirs."""

    target_dirs = command.get("target_dirs") or []
    settings = command.get("settings") or {}
    retrieval_policy = settings.get("retrieval_policy") or {}
    tool_policy = settings.get("tool_policy") or {}
    git_diff_max_calls = _positive_int(
        tool_policy.get("git_diff_max_calls"),
        default=8,
    )
    git_diff_calls = {"count": 0}

    def emit(name, detail=None):
        if emit_event is not None:
            emit_event(name, detail or {})

    @tool("search_workspace")
    def search_workspace(
        query: str,
        max_results: int = 50,
        regex: bool = False,
        glob: str = "",
        output_mode: str = "content",
        context_lines: int = 2,
        case_sensitive: bool = False,
    ) -> str:
        """Search selected workspace dirs, ripgrep-style.

        output_mode: "content" (default) returns matching lines
        {path, line, text, before, after}; "files" returns the files that
        match; "count" returns per-file match counts.

        query is keywords (fixed-string, case-folded) by default; set
        regex=True to pass a ripgrep regular expression. glob restricts the
        search by path/type (e.g. "**/*.md", "*.py"). Use keywords/terms as
        they appear in the files (translate names into the documents'
        language when needed). File size is not a constraint. In content
        mode, when nothing matches a 'files' listing of the scope is
        returned so you can read files directly with read_workspace_file.
        """

        emit(
            "tool.search_workspace.start",
            {
                "query": query,
                "max_results": max_results,
                "regex": regex,
                "glob": glob,
                "output_mode": output_mode,
                "summary": _search_summary(query, regex, glob, output_mode),
            },
        )
        started = time.monotonic()
        result = search_workspace_files(
            target_dirs,
            query,
            max_results=max_results,
            policy=retrieval_policy,
            regex=regex,
            glob=glob,
            output_mode=output_mode,
            context_lines=context_lines,
            case_sensitive=case_sensitive,
        )
        matches = result.get("matches") or []
        files = result.get("files") or []
        counts = result.get("counts") or []
        paths = list(dict.fromkeys(item["path"] for item in matches))
        emit(
            "tool.search_workspace.done",
            {
                "mode": result.get("mode"),
                "count": len(matches) or len(files) or len(counts),
                "paths": paths[:8],
                "summary": _search_done_summary(
                    result, matches, files, counts, paths
                ),
                "preview": _clip(matches[0]["text"], 140) if matches else "",
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return _json(result)

    @tool("read_workspace_file", args_schema=_ReadWorkspaceFileArgs)
    def read_workspace_file(path: str, offset: int = 1, limit: int = 250) -> str:
        """Read a window of a workspace file: limit lines from offset (1-based).

        Returns numbered lines plus has_more so you can page through any file
        by increasing offset; file size is not a constraint. Call
        search_workspace first to get the line numbers worth reading.
        """

        emit(
            "tool.read_workspace_file.start",
            {
                "path": path,
                "offset": offset,
                "limit": limit,
                "summary": (
                    f"{_basename(path)} · lines {offset}-{offset + limit - 1}"
                ),
            },
        )
        resolved = _resolve_allowed_path(path, target_dirs)
        if resolved is None:
            directory = _resolve_allowed_directory(path, target_dirs)
            if directory is not None:
                candidates = _list_directory_files(directory)
                emit(
                    "tool.read_workspace_file.directory",
                    {
                        "path": str(directory),
                        "candidate_count": len(candidates),
                    },
                )
                return _json(
                    {
                        "error": "PATH_IS_DIRECTORY",
                        "path": str(directory),
                        "candidate_files": candidates,
                    }
                )
            emit("tool.read_workspace_file.denied", {"path": path})
            return _json({"error": "PATH_NOT_ALLOWED", "path": path})
        started = time.monotonic()
        window = read_workspace_window(
            str(resolved),
            offset=offset,
            limit=limit,
            policy=retrieval_policy,
        )
        emit(
            "tool.read_workspace_file.done",
            {
                "path": str(resolved),
                "start": window.get("start_line"),
                "end": window.get("end_line"),
                "has_more": window.get("has_more"),
                "summary": (
                    f"{_basename(resolved)} · lines "
                    f"{window.get('start_line')}-{window.get('end_line')}"
                    f"{' (+more)' if window.get('has_more') else ''}"
                ),
                "preview": _clip(window.get("content") or "", 200),
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return _json(window)

    @tool("find_files")
    def find_files(pattern: str, max_results: int = 50) -> str:
        """Find files by name/path glob across the workspace (newest first).

        Use when you know a filename or want to enumerate files of a type,
        e.g. pattern="**/*.md", "**/*install*", "src/**/*.py". Returns file
        paths sorted by modification time; read them with
        read_workspace_file.
        """

        emit(
            "tool.find_files.start",
            {
                "pattern": pattern,
                "max_results": max_results,
                "summary": pattern,
            },
        )
        started = time.monotonic()
        files = glob_files(
            target_dirs,
            pattern,
            max_results=max_results,
            policy=retrieval_policy,
        )
        emit(
            "tool.find_files.done",
            {
                "count": len(files),
                "paths": files[:8],
                "summary": (
                    f"{len(files)} files · {_names(files)}" if files else "0 files"
                ),
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return _json({"files": files})

    @tool("git_log")
    def git_log(path: str = "", max_count: int = 10) -> str:
        """Show recent git commits for a selected workspace repository."""

        root = _resolve_repo_path(path, target_dirs)
        if root is None:
            repos = _discover_git_repositories(path, target_dirs)
            if repos:
                emit(
                    "tool.git_log.repositories",
                    {
                        "path": path,
                        "count": len(repos),
                    },
                )
                return _json(
                    {
                        "error": "PATH_IS_NOT_REPOSITORY",
                        "repositories": repos,
                    }
                )
            emit("tool.git_log.denied", {"path": path})
            return _json({"error": "PATH_NOT_ALLOWED", "path": path})
        commit_count = min(_positive_int(max_count, default=10), 50)
        emit(
            "tool.git_log.start",
            {
                "path": str(root),
                "max_count": commit_count,
            },
        )
        result = _run_git(
            root,
            [
                "log",
                f"--max-count={commit_count}",
                "--date=iso",
                "--pretty=format:%h%x09%ad%x09%s",
            ],
        )
        emit("tool.git_log.done", {"path": str(root), "ok": result["ok"]})
        return _json(result)

    @tool("git_diff")
    def git_diff(path: str = "", ref: str = "HEAD~1..HEAD") -> str:
        """Show a read-only git diff for a selected workspace repository."""

        root = _resolve_repo_path(path, target_dirs)
        if root is None:
            repos = _discover_git_repositories(path, target_dirs)
            if repos:
                emit(
                    "tool.git_diff.repositories",
                    {
                        "path": path,
                        "count": len(repos),
                    },
                )
                return _json(
                    {
                        "error": "PATH_IS_NOT_REPOSITORY",
                        "repositories": repos,
                    }
                )
            emit("tool.git_diff.denied", {"path": path})
            return _json({"error": "PATH_NOT_ALLOWED", "path": path})
        git_diff_calls["count"] += 1
        if git_diff_calls["count"] > git_diff_max_calls:
            emit(
                "tool.git_diff.budget_exceeded",
                {
                    "path": str(root),
                    "ref": ref,
                    "max_calls": git_diff_max_calls,
                },
            )
            return _json(
                {
                    "error": "TOOL_BUDGET_EXCEEDED",
                    "tool": "git_diff",
                    "max_calls": git_diff_max_calls,
                    "instruction": (
                        "Stop requesting more git_diff calls. Summarize the "
                        "available git_log and git_diff evidence now."
                    ),
                }
            )
        emit("tool.git_diff.start", {"path": str(root), "ref": ref})
        result = _run_git(root, ["diff", "--stat", ref])
        if result["ok"]:
            detail = _run_git(root, ["diff", "--find-renames", ref])
            result["diff"] = detail.get("stdout", "")[:20000]
        emit("tool.git_diff.done", {"path": str(root), "ok": result["ok"]})
        return _json(result)

    @tool("summarize_recent_changes")
    def summarize_recent_changes(query: str, max_commits: int = 20) -> str:
        """Collect recent git evidence for repositories matching a query."""

        emit(
            "tool.summarize_recent_changes.start",
            {
                "query": query,
                "max_commits": max_commits,
            },
        )
        repositories = _matching_repositories(query, target_dirs)
        if not repositories:
            candidates = _discover_git_repositories("", target_dirs, limit=20)
            emit(
                "tool.summarize_recent_changes.no_match",
                {
                    "query": query,
                    "candidate_count": len(candidates),
                },
            )
            return _json(
                {
                    "error": "NO_MATCHING_REPOSITORY",
                    "query": query,
                    "candidate_repositories": candidates,
                    "instruction": (
                        "Choose a repository from candidate_repositories or "
                        "ask the user to clarify the project name."
                    ),
                }
            )
        summaries = []
        for repo in repositories[:3]:
            commit_count = min(
                _positive_int(max_commits, default=20),
                30,
            )
            log_result = _run_git(
                repo,
                [
                    "log",
                    f"--max-count={commit_count}",
                    "--date=iso",
                    "--pretty=format:%h%x09%ad%x09%s",
                ],
            )
            diff_ref = f"HEAD~{commit_count}..HEAD"
            diff_stat = _run_git(repo, ["diff", "--stat", diff_ref])
            diff_detail = _run_git(repo, ["diff", "--find-renames", diff_ref])
            summaries.append(
                {
                    "repository": str(repo),
                    "commits": log_result.get("stdout", ""),
                    "diff_ref": diff_ref,
                    "diff_stat": diff_stat.get("stdout", ""),
                    "diff": diff_detail.get("stdout", "")[:20000],
                }
            )
        emit(
            "tool.summarize_recent_changes.done",
            {
                "query": query,
                "repository_count": len(summaries),
                "repositories": [item["repository"] for item in summaries],
            },
        )
        return _json({"repositories": summaries})

    return [
        search_workspace,
        read_workspace_file,
        find_files,
        summarize_recent_changes,
        git_log,
        git_diff,
    ]


def _resolve_allowed_path(path, target_dirs):
    """Resolve a file path and ensure it is under selected dirs."""

    candidate = Path(path).resolve()
    for item in target_dirs:
        root = Path(item.get("path", "")).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def _resolve_allowed_directory(path, target_dirs):
    """Resolve a directory path and ensure it is under selected dirs."""

    candidate = Path(path).resolve()
    for item in target_dirs:
        root = Path(item.get("path", "")).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_dir():
            return candidate
    return None


def _resolve_repo_path(path, target_dirs):
    """Resolve a repo path under selected dirs."""

    candidates = []
    if path:
        candidates.append(Path(path).resolve())
    candidates.extend(
        Path(item.get("path", "")).resolve()
        for item in target_dirs
    )
    for candidate in candidates:
        for root_item in target_dirs:
            root = Path(root_item.get("path", "")).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if candidate.exists() and (candidate / ".git").exists():
                return candidate
    return None


def _discover_git_repositories(path, target_dirs, limit=20):
    """Discover candidate Git repositories under an allowed directory."""

    directory = _resolve_allowed_directory(path, target_dirs)
    if directory is None and not path:
        first = next(iter(target_dirs or []), {})
        directory = _resolve_allowed_directory(first.get("path", ""), target_dirs)
    if directory is None:
        return []

    repos = []
    for child in sorted(directory.iterdir(), key=lambda item: item.name):
        if len(repos) >= limit:
            break
        if child.is_dir() and (child / ".git").exists():
            repos.append(str(child))
    return repos


def _matching_repositories(query, target_dirs):
    """Return repositories whose directory names match query tokens."""

    tokens = _query_tokens(query)
    repositories = []
    for item in target_dirs:
        root = Path(item.get("path", "")).resolve()
        if (root / ".git").exists():
            repositories.append(root)
            continue
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if not child.is_dir() or not (child / ".git").exists():
                continue
            name_tokens = set(_name_tokens(child.name))
            if any(token in name_tokens for token in tokens):
                repositories.append(child)
    if repositories:
        return repositories
    return []


def _query_tokens(query):
    """Return meaningful lowercase query tokens."""

    tokens = []
    current = []
    for char in str(query or "").lower():
        if char.isalnum() or char in {"-", "_"}:
            current.append(char)
            continue
        if current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    ignored = {
        "recent",
        "changes",
        "features",
        "bug",
        "fix",
        "fixes",
        "new",
        "project",
    }
    return [token for token in tokens if len(token) >= 3 and token not in ignored]


def _name_tokens(name):
    """Return lowercase tokens from a repository directory name."""

    tokens = []
    current = []
    for char in str(name or "").lower():
        if char.isalnum():
            current.append(char)
            continue
        if current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _list_directory_files(directory, limit=50):
    """Return a bounded, recursive list of candidate files in a directory."""

    files = []
    for current, subdirs, filenames in os.walk(directory):
        subdirs[:] = sorted(
            name
            for name in subdirs
            if not name.startswith(".") and name not in DEFAULT_EXCLUDED_DIRS
        )
        for name in sorted(filenames):
            if len(files) >= limit:
                return files
            if name.startswith("."):
                continue
            path = Path(current) / name
            if path.suffix in DEFAULT_EXCLUDED_EXTENSIONS:
                continue
            files.append(str(path))
    return files


def _run_git(root, args):
    """Run a read-only git command in a repository."""

    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "error": str(exc),
        }
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[:20000],
        "stderr": completed.stderr[:4000],
    }


def _positive_int(value, default):
    """Return a positive integer setting value."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _basename(path):
    """Return a path's file name for compact event summaries."""

    return Path(str(path)).name or str(path)


def _clip(text, limit):
    """Collapse whitespace and clip to `limit` chars for a bounded preview."""

    text = " ".join(str(text or "").split())
    return text[:limit] + "…" if len(text) > limit else text


def _names(paths, limit=3):
    """Return up to `limit` comma-joined basenames, with a +N overflow tag."""

    items = paths or []
    names = [Path(str(item)).name for item in items[:limit]]
    text = ", ".join(names)
    extra = len(items) - len(names)
    if extra > 0:
        text += f" +{extra}"
    return text


def _search_summary(query, regex, glob, output_mode):
    """Build a compact summary of a search request for the trace."""

    parts = [f"/{query}/" if regex else f'"{query}"']
    if glob:
        parts.append(f"in {glob}")
    if output_mode and output_mode != "content":
        parts.append(f"({output_mode})")
    return " ".join(parts)


def _search_done_summary(result, matches, files, counts, paths):
    """Build a compact summary of a search result for the trace."""

    mode = result.get("mode")
    if mode == "files":
        return f"{len(files)} files · {_names(files)}" if files else "0 files"
    if mode == "count":
        return f"{len(counts)} files"
    if matches:
        return (
            f"{len(matches)} matches in {len(paths)} files · {_names(paths)}"
        )
    if files:
        return f"no matches · listing {len(files)} files"
    return "no matches"


def _json(payload):
    """Serialize tool output as JSON."""

    return json.dumps(payload, ensure_ascii=False)
