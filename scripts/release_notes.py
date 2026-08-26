#!/usr/bin/env python3
"""Validate and aggregate localized SourceLens release notes."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import NotRequired, TypedDict

import yaml

CATEGORY_ORDER = ("feature", "improvement", "fix")
AUDIENCE_ORDER = ("user", "admin")
CATEGORY_HEADINGS = {
    "feature": "Features",
    "improvement": "Improvements",
    "fix": "Fixes",
}
REQUIRED_FRAGMENT_FIELDS = {"type", "audience", "en", "zh-CN"}
FRAGMENT_FIELDS = REQUIRED_FRAGMENT_FIELDS | {"es"}
FRAGMENT_DIRECTORY = "release-notes"
MAX_FRAGMENT_BYTES = 16 * 1024
MAX_ENTRY_CHARACTERS = 1000

ReleaseFragment = TypedDict(
    "ReleaseFragment",
    {
        "type": str,
        "audience": str,
        "en": str,
        "zh-CN": str,
        "es": NotRequired[str],
    },
)
LocalizedEntry = TypedDict(
    "LocalizedEntry",
    {
        "audience": str,
        "en": str,
        "zh-CN": str,
        "es": NotRequired[str],
    },
)


class ReleaseManifest(TypedDict):
    """Build-time release-note manifest consumed by the frontend."""

    version: str
    releaseDate: str
    categories: dict[str, list[LocalizedEntry]]


class ReleaseNoteError(ValueError):
    """Raised when release-note content or Git history is invalid."""


def parse_fragment(path: str | Path) -> ReleaseFragment:
    """Load and validate one release-note fragment from disk."""

    fragment_path = Path(path)
    try:
        size = fragment_path.stat().st_size
    except OSError as exc:
        raise ReleaseNoteError(
            f"unable to read {fragment_path}: {exc}"
        ) from exc
    if size > MAX_FRAGMENT_BYTES:
        raise ReleaseNoteError(
            f"{fragment_path} exceeds {MAX_FRAGMENT_BYTES} bytes"
        )
    try:
        content = fragment_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseNoteError(
            f"unable to read {fragment_path}: {exc}"
        ) from exc
    return parse_fragment_content(content, str(fragment_path))


def parse_fragment_content(content: str, source: str) -> ReleaseFragment:
    """Parse and validate a release-note YAML document."""

    if len(content.encode("utf-8")) > MAX_FRAGMENT_BYTES:
        raise ReleaseNoteError(f"{source} exceeds {MAX_FRAGMENT_BYTES} bytes")
    try:
        payload = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ReleaseNoteError(f"invalid YAML in {source}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ReleaseNoteError(f"{source} must contain a YAML mapping")
    if any(not isinstance(field, str) for field in payload):
        raise ReleaseNoteError(f"{source} field names must be strings")

    fields = set(payload)
    missing = sorted(REQUIRED_FRAGMENT_FIELDS - fields)
    if missing:
        raise ReleaseNoteError(
            f"{source} missing required fields: {', '.join(missing)}"
        )
    unknown = sorted(fields - FRAGMENT_FIELDS)
    if unknown:
        raise ReleaseNoteError(
            f"{source} contains unknown fields: {', '.join(unknown)}"
        )

    note_type = payload["type"]
    if note_type not in CATEGORY_ORDER:
        supported = ", ".join(CATEGORY_ORDER)
        raise ReleaseNoteError(
            f"{source} has unsupported type {note_type!r}; use {supported}"
        )

    audience = payload["audience"]
    if audience not in AUDIENCE_ORDER:
        supported = ", ".join(AUDIENCE_ORDER)
        raise ReleaseNoteError(
            f"{source} has unsupported audience {audience!r}; "
            f"use {supported}"
        )

    fragment: ReleaseFragment = {
        "type": note_type,
        "audience": audience,
        "en": "",
        "zh-CN": "",
    }
    for language in ("en", "zh-CN"):
        text = payload[language]
        if not isinstance(text, str) or not text.strip():
            raise ReleaseNoteError(
                f"{source} field {language} must be a non-empty string"
            )
        normalized = " ".join(text.split())
        if len(normalized) > MAX_ENTRY_CHARACTERS:
            raise ReleaseNoteError(
                f"{source} field {language} exceeds "
                f"{MAX_ENTRY_CHARACTERS} characters"
            )
        fragment[language] = normalized
    if "es" in payload:
        text = payload["es"]
        if not isinstance(text, str) or not text.strip():
            raise ReleaseNoteError(
                f"{source} field es must be a non-empty string"
            )
        normalized = " ".join(text.split())
        if len(normalized) > MAX_ENTRY_CHARACTERS:
            raise ReleaseNoteError(
                f"{source} field es exceeds "
                f"{MAX_ENTRY_CHARACTERS} characters"
            )
        fragment["es"] = normalized
    return fragment


def build_manifest(
    repo: str | Path,
    tag: str,
    version: str,
    release_date: str,
) -> ReleaseManifest:
    """Build the deterministic manifest for one version tag."""

    repository = Path(repo)
    _ensure_ref(repository, tag)
    previous_tag = find_previous_tag(repository, tag)
    paths = collect_fragment_paths(repository, previous_tag, tag)
    categories: dict[str, list[LocalizedEntry]] = {
        category: [] for category in CATEGORY_ORDER
    }

    for path in paths:
        content = _read_fragment_at_ref(repository, tag, path)
        fragment = parse_fragment_content(content, path)
        entry: LocalizedEntry = {
            "audience": fragment["audience"],
            "en": fragment["en"],
            "zh-CN": fragment["zh-CN"],
        }
        if "es" in fragment:
            entry["es"] = fragment["es"]
        categories[fragment["type"]].append(entry)

    return {
        "version": version,
        "releaseDate": release_date,
        "categories": categories,
    }


def find_previous_tag(repo: str | Path, tag: str) -> str | None:
    """Return the highest prior version tag reachable from ``tag``."""

    current_commit = _git(repo, "rev-parse", f"{tag}^{{commit}}").strip()
    tags = _git(
        repo,
        "tag",
        "--merged",
        current_commit,
        "--sort=-version:refname",
        "--list",
        "v*",
    ).splitlines()
    for candidate in tags:
        if candidate != tag:
            return candidate
    return None


def collect_fragment_paths(
    repo: str | Path,
    start_ref: str | None,
    end_ref: str,
) -> list[str]:
    """List fragments added after ``start_ref`` in deterministic order."""

    if start_ref:
        output = _git(
            repo,
            "diff",
            "--diff-filter=A",
            "--name-only",
            f"{start_ref}..{end_ref}",
            "--",
            FRAGMENT_DIRECTORY,
        )
    else:
        output = _git(
            repo,
            "ls-tree",
            "-r",
            "--name-only",
            end_ref,
            "--",
            FRAGMENT_DIRECTORY,
        )
    return sorted(
        path
        for path in output.splitlines()
        if Path(path).suffix in {".yaml", ".yml"}
    )


def validate_pr(
    repo: str | Path,
    base_ref: str,
    head_ref: str,
    skip: bool,
) -> list[str]:
    """Require and validate new fragments, or accept an explicit opt-out."""

    repository = Path(repo)
    _ensure_ref(repository, base_ref)
    _ensure_ref(repository, head_ref)
    output = _git(
        repository,
        "diff",
        "--diff-filter=A",
        "--name-only",
        f"{base_ref}...{head_ref}",
        "--",
        FRAGMENT_DIRECTORY,
    )
    paths = sorted(
        path
        for path in output.splitlines()
        if Path(path).suffix in {".yaml", ".yml"}
    )

    if not paths and not skip:
        raise ReleaseNoteError(
            "add a release-note fragment or apply the "
            "skip-release-note label"
        )

    for path in paths:
        content = _read_fragment_at_ref(repository, head_ref, path)
        parse_fragment_content(content, path)
    return paths


def render_release_body(manifest: ReleaseManifest) -> str:
    """Render the English GitHub Release body for a manifest."""

    lines = [
        f"# SourceLens {manifest['version']}",
        "",
        f"Released {manifest['releaseDate']}.",
    ]
    has_entries = False
    for category in CATEGORY_ORDER:
        entries = manifest["categories"].get(category, [])
        if not entries:
            continue
        has_entries = True
        lines.extend(["", f"## {CATEGORY_HEADINGS[category]}", ""])
        for entry in entries:
            prefix = (
                "**Administrators:** " if entry["audience"] == "admin" else ""
            )
            lines.append(f"- {prefix}{entry['en']}")

    if not has_entries:
        lines.extend(
            ["", "No user-facing changes were included in this release."]
        )
    return "\n".join(lines) + "\n"


def write_artifacts(
    manifest: ReleaseManifest,
    manifest_path: str | Path,
    body_path: str | Path,
) -> None:
    """Write the JSON manifest and English release body."""

    output_manifest = Path(manifest_path)
    output_body = Path(body_path)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_body.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output_body.write_text(
        render_release_body(manifest),
        encoding="utf-8",
    )


def _read_fragment_at_ref(repo: str | Path, ref: str, path: str) -> str:
    """Read a size-bounded fragment from one Git ref."""

    object_name = f"{ref}:{path}"
    size_text = _git(repo, "cat-file", "-s", object_name).strip()
    try:
        size = int(size_text)
    except ValueError as exc:
        raise ReleaseNoteError(
            f"unable to determine fragment size for {path}"
        ) from exc
    if size > MAX_FRAGMENT_BYTES:
        raise ReleaseNoteError(f"{path} exceeds {MAX_FRAGMENT_BYTES} bytes")
    return _git(repo, "show", object_name)


def _ensure_ref(repo: str | Path, ref: str) -> None:
    try:
        _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except ReleaseNoteError as exc:
        raise ReleaseNoteError(f"Git ref does not exist: {ref}") from exc


def _git(repo: str | Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseNoteError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def build_parser() -> argparse.ArgumentParser:
    """Create the release-note command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate-pr",
        help="Validate the release-note decision for a pull request",
    )
    validate.add_argument("--repo", default=".")
    validate.add_argument("--base", required=True)
    validate.add_argument("--head", required=True)
    validate.add_argument("--skip-release-note", action="store_true")

    build = subparsers.add_parser(
        "build",
        help="Aggregate the release-note manifest for a version tag",
    )
    build.add_argument("--repo", default=".")
    build.add_argument("--tag", required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--release-date", required=True)
    build.add_argument("--manifest", required=True)
    build.add_argument("--body", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the release-note command-line interface."""

    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-pr":
            paths = validate_pr(
                repo=args.repo,
                base_ref=args.base,
                head_ref=args.head,
                skip=args.skip_release_note,
            )
            if paths:
                print(f"Validated {len(paths)} release-note fragment(s).")
            else:
                print("Validated skip-release-note decision.")
            return 0

        manifest = build_manifest(
            repo=Path(args.repo),
            tag=args.tag,
            version=args.version,
            release_date=args.release_date,
        )
        write_artifacts(manifest, args.manifest, args.body)
        count = sum(
            len(entries) for entries in manifest["categories"].values()
        )
        print(f"Generated release notes with {count} fragment(s).")
        return 0
    except ReleaseNoteError as exc:
        print(f"release-note error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
