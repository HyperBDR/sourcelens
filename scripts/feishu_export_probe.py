#!/usr/bin/env python3
"""Probe Feishu Drive export APIs from the LensNode network."""

import argparse
import json
import time
from urllib import error, parse, request


BASE_URL = "https://open.feishu.cn/open-apis"


def request_json(url, method="GET", token=None, payload=None):
    """Send a JSON request and return the decoded response."""

    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        print(f"HTTP {exc.code}: {raw}")
        raise
    print(raw)
    return json.loads(raw)


def tenant_token(app_id, app_secret):
    """Fetch tenant_access_token for a Feishu internal app."""

    payload = {"app_id": app_id, "app_secret": app_secret}
    data = request_json(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        method="POST",
        payload=payload,
    )
    token = data.get("tenant_access_token")
    if not token:
        raise SystemExit("tenant_access_token missing")
    return token


def create_export_task(token, file_token, file_type, extension):
    """Create a Drive export task."""

    payload = {
        "token": file_token,
        "type": file_type,
        "file_extension": extension,
    }
    data = request_json(
        f"{BASE_URL}/drive/v1/export_tasks",
        method="POST",
        token=token,
        payload=payload,
    )
    return (data.get("data") or {}).get("ticket") or data.get("ticket")


def poll_export_task(token, ticket, file_token, file_type):
    """Poll a Drive export task until Feishu returns a terminal result."""

    query = parse.urlencode({"token": file_token, "type": file_type})
    url = f"{BASE_URL}/drive/v1/export_tasks/{ticket}?{query}"
    result = None
    for _ in range(30):
        data = request_json(url, token=token)
        result = (data.get("data") or {}).get("result") or {}
        status = result.get("job_status")
        if status == 0:
            break
        if status not in (1, 2):
            break
        time.sleep(2)
    return result


def download_export_file(token, file_token, output):
    """Download an exported file by file_token."""

    url = f"{BASE_URL}/drive/v1/export_tasks/file/{file_token}/download"
    req = request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with request.urlopen(req, timeout=120) as response:
        data = response.read()
    with open(output, "wb") as handle:
        handle.write(data)
    print(f"saved {len(data)} bytes to {output}")


def main():
    """Run the export probe."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-secret", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--type", default="docx")
    parser.add_argument("--extension", default="markdown")
    parser.add_argument("--output", default="feishu-export.md")
    args = parser.parse_args()

    token = tenant_token(args.app_id, args.app_secret)
    ticket = create_export_task(
        token,
        args.token,
        args.type,
        args.extension,
    )
    if not ticket:
        raise SystemExit("export ticket missing")
    result = poll_export_task(token, ticket, args.token, args.type)
    print("EXPORT RESULT:", json.dumps(result, ensure_ascii=False, indent=2))
    file_token = result.get("file_token")
    if not file_token:
        raise SystemExit("export file_token missing")
    download_export_file(token, file_token, args.output)


if __name__ == "__main__":
    main()
