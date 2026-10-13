#!/usr/bin/env python3
"""List and explicitly delete every Actions cache for one repository.

The GitHub-hosted runner normally contains ``gh``, but local repair jobs do
not.  Using the documented REST endpoints keeps the maintenance action
portable while retaining an explicit confirmation gate for this destructive
operation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request


REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
API_ROOT = "https://api.github.com/repos"


def _request(token: str, url: str, *, method: str = "GET") -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "VLA-cache-maintenance",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub API {exc.code} for {method} {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API unavailable for {method} {url}: {exc.reason}") from exc


def list_caches(token: str, repository: str) -> list[dict[str, object]]:
    caches: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{API_ROOT}/{repository}/actions/caches?per_page=100&page={page}"
        status, raw = _request(token, url)
        if status != 200:
            raise RuntimeError(f"Unexpected cache-list status: HTTP {status}")
        payload = json.loads(raw.decode("utf-8"))
        page_items = payload.get("actions_caches", [])
        if not isinstance(page_items, list):
            raise RuntimeError("GitHub cache response has invalid actions_caches")
        caches.extend(item for item in page_items if isinstance(item, dict))
        if len(page_items) < 100:
            break
        page += 1
    return caches


def purge(token: str, repository: str, *, confirm: bool) -> int:
    if not confirm:
        raise ValueError("refusing destructive purge without --confirm")
    caches = list_caches(token, repository)
    print(f"Found {len(caches)} Actions cache(s) for {repository}.")
    for item in caches:
        print(
            f"- id={item.get('id', '—')} key={item.get('key', '—')} "
            f"ref={item.get('ref', '—')} size={item.get('size_in_bytes', '—')}"
        )
    status, _ = _request(token, f"{API_ROOT}/{repository}/actions/caches", method="DELETE")
    if status != 204:
        raise RuntimeError(f"Unexpected cache-delete status: HTTP {status}")
    print(f"Deleted all Actions caches for {repository}.")
    return len(caches)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "beuvivu/VLA"),
        help="GitHub repository owner/name (default: GITHUB_REPOSITORY or beuvivu/VLA)",
    )
    parser.add_argument("--confirm", action="store_true", help="Confirm destructive deletion")
    args = parser.parse_args(argv)
    if not REPOSITORY_RE.fullmatch(args.repo):
        parser.error("--repo must use owner/name syntax")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GH_TOKEN or GITHUB_TOKEN is required.", file=sys.stderr)
        return 2
    try:
        purge(token, args.repo, confirm=args.confirm)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Cache purge failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
