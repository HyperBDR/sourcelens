import json
from pathlib import Path
import re
import subprocess

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}

DEFAULT_EXCLUDED_EXTENSIONS = {
    ".lock",
    ".pyc",
    ".sqlite3",
}


def available_dirs(workspace_path):
    """Return first-level directories with their immediate subdirectories."""

    root = Path(workspace_path)
    if not root.exists():
        return []

    dirs = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        children = []
        try:
            for sub in sorted(child.iterdir(), key=lambda x: x.name):
                if sub.is_dir() and not sub.name.startswith("."):
                    children.append({"path": str(sub), "name": sub.name})
                    if len(children) >= 30:
                        break
        except PermissionError:
            pass
        dirs.append({"path": str(child), "name": child.name, "children": children})
    return dirs


def search_workspace(target_dirs, query, max_files=12, policy=None):
    """Search selected directories and return ranked candidate files."""

    policy = policy or {}
    terms = _query_terms(query)
    hits = []
    for item in target_dirs:
        root = Path(item.get("path", ""))
        if not root.exists() or not root.is_dir():
            continue
        scope = item.get("retrieval_scope") or {}
        candidate_paths = _rg_candidate_paths(root, terms, scope, policy)
        if not candidate_paths:
            candidate_paths = _iter_allowed_paths(root, scope, policy)
        for path in candidate_paths:
            if not _is_allowed(root, path, scope, policy):
                continue
            score = _score_path(root, path, terms, scope, policy)
            if score <= 0:
                continue
            hits.append(
                {
                    "path": str(path),
                    "score": score,
                    "size": path.stat().st_size,
                }
            )

    hits.sort(key=lambda item: (-item["score"], item["path"]))
    return hits[:max_files]


def read_selected_workspace_files(
    paths,
    query="",
    max_chars=30000,
    context_lines=2,
    max_matches=4,
    policy=None,
):
    """Read selected files and return evidence snippets for the query."""

    policy = policy or {}
    samples = []
    remaining_chars = max_chars
    terms = _query_terms(query)
    for path_value in paths:
        path = Path(path_value)
        if not _is_allowed(None, path, {}, policy):
            continue
        text = _read_text(path)
        if not text:
            continue
        snippets = _extract_snippets(
            text,
            terms,
            context_lines=context_lines,
            max_matches=max_matches,
        )
        content = "\n\n".join(snippets) if snippets else text
        content = content[:remaining_chars]
        remaining_chars -= len(content)
        samples.append(
            {
                "path": str(path),
                "content": content,
            }
        )
        if remaining_chars <= 0:
            break
    return samples


def read_text_samples(target_dirs, max_files=16, max_chars=30000, policy=None):
    """Collect small readable text samples from selected directories."""

    policy = policy or {}
    samples = []
    remaining_chars = max_chars
    for item in target_dirs:
        root = Path(item.get("path", ""))
        if not root.exists() or not root.is_dir():
            continue
        scope = item.get("retrieval_scope") or {}
        for path in _iter_allowed_paths(root, scope, policy):
            if len(samples) >= max_files or remaining_chars <= 0:
                return samples
            text = _read_text(path)
            if not text:
                continue
            text = text[:remaining_chars]
            remaining_chars -= len(text)
            samples.append(
                {
                    "path": str(path),
                    "content": text,
                }
            )
    return samples


def summarize_hits(hits):
    """Return a JSON summary string compatible with ai-query events."""

    return json.dumps({"hits": hits}, ensure_ascii=False)


def summarize_snippets(samples):
    """Return a JSON summary string compatible with ai-query events."""

    snippets = []
    for sample in samples:
        snippets.append(
            {
                "path": sample["path"],
                "excerpt": sample["content"][:500],
            }
        )
    return json.dumps({"snippets": snippets}, ensure_ascii=False)


def _is_allowed(root, path, scope, policy):
    """Return whether a path is useful as a workspace sample."""

    if not path.is_file():
        return False
    if _is_excluded_path(root, path, scope, policy):
        return False
    max_file_size = _option(scope, policy, "max_file_size", 256 * 1024)
    if path.stat().st_size > int(max_file_size):
        return False
    exclude_extensions = _option(
        scope,
        policy,
        "exclude_extensions",
        DEFAULT_EXCLUDED_EXTENSIONS,
    )
    if path.suffix in _normalize_extensions(exclude_extensions):
        return False
    return True


def _query_terms(query):
    """Extract lightweight search terms from a user question."""

    terms = []
    for term in re.findall(r"[\w\u4e00-\u9fff]+", query.lower()):
        if len(term) < 2:
            continue
        terms.append(term)
        if _contains_cjk(term):
            terms.extend(_ngrams(term, 2))
            terms.extend(_ngrams(term, 3))
    seen = set()
    unique_terms = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    return unique_terms


def _rg_candidate_paths(root, terms, scope, policy):
    """Return files matched by ripgrep, or an empty list when unavailable."""

    if not terms:
        return []

    cmd = ["rg", "-l", "-i", "-F"]
    for pattern in scope.get("include_paths") or ["**/*"]:
        cmd.extend(["-g", pattern])
    for pattern in _exclude_globs(scope, policy):
        cmd.extend(["-g", f"!{pattern}"])
    for term in terms:
        cmd.extend(["-e", term])
    cmd.append(str(root))

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return []

    if completed.returncode not in {0, 1}:
        return []

    paths = []
    seen = set()
    for line in completed.stdout.splitlines():
        path = Path(line.strip())
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            paths.append(path)
    return paths


def _iter_allowed_paths(root, scope, policy):
    """Yield allowed files from include paths without applying weights."""

    paths = []
    for pattern in scope.get("include_paths") or ["**/*"]:
        paths.extend(
            path
            for path in root.glob(pattern)
            if _is_allowed(root, path, scope, policy)
        )
    return sorted(set(paths))


def _score_path(root, path, terms, scope, policy):
    """Score a candidate file by path/content query overlap."""

    max_file_size = _option(scope, policy, "max_file_size", 256 * 1024)
    if path.stat().st_size > int(max_file_size):
        return 0
    relative = str(path.relative_to(root)).lower()
    score = 1
    for term in terms:
        if term in relative:
            score += 12
    if not terms:
        return score
    text_scan_chars = _option(scope, policy, "text_scan_chars", 12000)
    text = _read_text(path)[: int(text_scan_chars)].lower()
    for term in terms:
        if term in text:
            score += min(text.count(term), 8)
    return score


def _extract_snippets(text, terms, context_lines=2, max_matches=4):
    """Extract context snippets around matching terms."""

    if not terms:
        return []
    lines = text.splitlines()
    snippets = []
    matched_ranges = []
    for index, line in enumerate(lines):
        lower = line.lower()
        if not any(term in lower for term in terms):
            continue
        start = max(0, index - context_lines)
        end = min(len(lines), index + context_lines + 1)
        overlaps = (
            start <= old_end and end >= old_start
            for old_start, old_end in matched_ranges
        )
        if any(overlaps):
            continue
        matched_ranges.append((start, end))
        snippet = "\n".join(lines[start:end]).strip()
        if snippet:
            snippets.append(snippet)
        if len(snippets) >= max_matches:
            break
    return snippets


def _option(scope, policy, key, default):
    """Read a retrieval option from scope first, then policy."""

    if key in scope:
        return scope[key]
    if key in policy:
        return policy[key]
    return default


def _is_excluded_path(root, path, scope, policy):
    """Return whether a path is excluded by configured rules."""

    if any(part.startswith(".") for part in path.parts):
        return True
    parts = set(path.parts if root is None else path.relative_to(root).parts)
    exclude_dirs = set(
        _option(scope, policy, "exclude_dirs", DEFAULT_EXCLUDED_DIRS)
    )
    if parts.intersection(exclude_dirs):
        return True
    max_depth = _option(scope, policy, "max_depth", None)
    if root is not None and max_depth is not None:
        if len(path.relative_to(root).parts) > int(max_depth):
            return True
    exclude_paths = _option(scope, policy, "exclude_paths", [])
    if root is None:
        return False
    relative = path.relative_to(root)
    return any(relative.match(pattern) for pattern in exclude_paths)


def _exclude_globs(scope, policy):
    """Build ripgrep glob exclusions from scope and policy."""

    globs = []
    exclude_dirs = _option(scope, policy, "exclude_dirs", DEFAULT_EXCLUDED_DIRS)
    for dirname in exclude_dirs:
        globs.append(f"**/{dirname}/**")
    globs.extend(_option(scope, policy, "exclude_paths", []))
    exclude_extensions = _option(
        scope,
        policy,
        "exclude_extensions",
        DEFAULT_EXCLUDED_EXTENSIONS,
    )
    for extension in _normalize_extensions(exclude_extensions):
        globs.append(f"**/*{extension}")
    return globs


def _normalize_extensions(values):
    """Normalize extension values to dotted lowercase suffixes."""

    extensions = set()
    for value in values or []:
        extension = str(value).lower().strip()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = f".{extension}"
        extensions.add(extension)
    return extensions


def _contains_cjk(value):
    """Return whether a string contains CJK characters."""

    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _ngrams(value, size):
    """Return character n-grams for compact CJK query terms."""

    if len(value) < size:
        return []
    return [value[index : index + size] for index in range(len(value) - size + 1)]


def _read_text(path):
    """Read a text file, returning an empty string when unreadable."""

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""
    except OSError:
        return ""
