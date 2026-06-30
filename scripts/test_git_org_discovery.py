#!/usr/bin/env python3
"""Diagnose Git organization discovery for SourceLens datasource setup."""

import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import error, parse, request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Git organization/group or repository URL")
    parser.add_argument("--token", default="", help="Git access token")
    parser.add_argument(
        "--branches",
        action="store_true",
        help="Fetch branches for discovered repositories",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    parsed = parse.urlsplit(args.url.rstrip("/"))
    group_path = parsed.path.strip("/")
    base_url = parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    print(f"base_url={base_url}")
    print(f"group_path={group_path}")

    print("\n[1] git ls-remote")
    timed("git ls-remote", lambda: git_ls_remote(args.url, args.token))

    print("\n[2] GitLab group projects API")
    projects = timed(
        "gitlab projects",
        lambda: gitlab_projects(base_url, group_path, args.token),
    )
    if not projects:
        print("No GitLab projects found.")
        return

    print(f"projects={len(projects)}")
    for item in projects[: args.limit]:
        print(
            "-",
            item.get("id"),
            item.get("path_with_namespace") or item.get("path"),
            item.get("default_branch"),
            item.get("http_url_to_repo"),
        )

    if not args.branches:
        print("\nUse --branches to test branch discovery time.")
        return

    print("\n[3] GitLab repository branches API")
    selected = projects[: args.limit]
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(
                gitlab_branches,
                base_url,
                project.get("id"),
                args.token,
            )
            for project in selected
        ]
        for project, future in zip(selected, futures):
            try:
                branches = future.result()
            except Exception as exc:
                branches = []
                print("branch_error", project.get("path"), exc)
            print(project.get("path"), len(branches), branches[:10])
    print(f"branch_elapsed={time.monotonic() - start:.2f}s")


def timed(name, func):
    start = time.monotonic()
    try:
        result = func()
        print(f"{name}_elapsed={time.monotonic() - start:.2f}s")
        return result
    except Exception as exc:
        print(f"{name}_elapsed={time.monotonic() - start:.2f}s")
        print(f"{name}_error={exc}")
        return None


def git_ls_remote(url, token):
    auth_url = git_auth_url(url, token)
    result = subprocess.run(
        ["git", "ls-remote", "--heads", auth_url],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(f"returncode={result.returncode}")
    if result.stderr:
        print(result.stderr.strip()[:500])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    print(f"heads={len(lines)}")
    return lines


def gitlab_projects(base_url, group_path, token):
    projects = []
    encoded_group = parse.quote(group_path, safe="")
    for page in range(1, 11):
        url = (
            f"{base_url}/api/v4/groups/{encoded_group}/projects"
            f"?include_subgroups=true&simple=true&per_page=100&page={page}"
        )
        payload = api_json(url, token)
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected payload: {payload!r}")
        if not payload:
            break
        projects.extend(payload)
        if len(payload) < 100:
            break
    return projects


def gitlab_branches(base_url, project_id, token):
    branches = []
    for page in range(1, 11):
        url = (
            f"{base_url}/api/v4/projects/{parse.quote(str(project_id), safe='')}"
            f"/repository/branches?per_page=100&page={page}"
        )
        payload = api_json(url, token, timeout=10)
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected payload: {payload!r}")
        if not payload:
            break
        branches.extend(item.get("name") for item in payload if item.get("name"))
        if len(payload) < 100:
            break
    return branches


def api_json(url, token, timeout=30):
    headers = {"Accept": "application/json"}
    if token:
        headers["PRIVATE-TOKEN"] = token
    req = request.Request(url, headers=headers)
    print("GET", url)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return json.loads(text)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def git_auth_url(url, token):
    if not token:
        return url
    parsed = parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return url
    netloc = f"oauth2:{parse.quote(token)}@{parsed.netloc}"
    return parse.urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )


if __name__ == "__main__":
    main()
