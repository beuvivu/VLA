#!/usr/bin/env python3
"""Chụp danh sách cache Actions, xóa từng ID và kiểm chứng sau khi xóa.

Dùng REST API để runner và máy bảo trì đều chạy được mà không cần ``gh``.
Chỉ xóa các ID đã chụp khi có ``--confirm``; cache mới sinh trong lúc chạy
được báo riêng và không bị cuốn vào lượt xóa này.
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


class GitHubAPIError(RuntimeError):
    """Giữ mã HTTP để chỉ bỏ qua cache vừa hết hạn ở bước DELETE theo ID."""

    def __init__(self, status: int, method: str, url: str) -> None:
        self.status = status
        super().__init__(f"GitHub API HTTP {status} for {method} {url}")


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
        # Không in nội dung lỗi bên ngoài: máy chủ có thể phản chiếu bí mật.
        exc.close()
        raise GitHubAPIError(exc.code, method, url) from exc
    except OSError as exc:
        raise RuntimeError(f"GitHub API unavailable for {method} {url}") from exc


def list_caches(token: str, repository: str) -> list[dict[str, object]]:
    caches: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{API_ROOT}/{repository}/actions/caches?per_page=100&page={page}"
        status, raw = _request(token, url)
        if status != 200:
            raise RuntimeError(f"Unexpected cache-list status: HTTP {status}")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("actions_caches"), list):
            raise RuntimeError("GitHub cache response has invalid actions_caches")
        page_items = payload["actions_caches"]
        if any(not isinstance(item, dict) for item in page_items):
            raise RuntimeError("GitHub cache response has an invalid cache entry")
        caches.extend(page_items)
        if len(page_items) < 100:
            break
        page += 1
    return caches


def _cache_ids(caches: list[dict[str, object]]) -> list[int]:
    """Kiểm toàn bộ ID trước khi xóa; loại trùng nhưng giữ thứ tự ảnh chụp."""
    cache_ids: dict[int, None] = {}
    for item in caches:
        cache_id = item.get("id")
        if type(cache_id) is not int or cache_id <= 0:
            raise RuntimeError("GitHub cache ID must be a positive integer")
        cache_ids[cache_id] = None
    return list(cache_ids)


def purge(token: str, repository: str, *, confirm: bool) -> int:
    if not confirm:
        raise ValueError("refusing destructive purge without --confirm")
    caches = list_caches(token, repository)
    target_ids = _cache_ids(caches)
    print(f"Found {len(target_ids)} Actions cache(s) for {repository} in the initial snapshot.")
    for cache_id in target_ids:
        try:
            status, _ = _request(
                token, f"{API_ROOT}/{repository}/actions/caches/{cache_id}", method="DELETE"
            )
        except GitHubAPIError as exc:
            if exc.status != 404:
                raise
            print(f"- id={cache_id} already absent (HTTP 404).")
            continue
        if status != 204:
            raise RuntimeError(f"Unexpected cache-delete status: HTTP {status}")
        print(f"- deleted id={cache_id}")

    remaining_ids = set(_cache_ids(list_caches(token, repository)))
    lingering_ids = remaining_ids.intersection(target_ids)
    if lingering_ids:
        ids = ", ".join(str(cache_id) for cache_id in sorted(lingering_ids))
        raise RuntimeError(f"Verification failed: initially targeted cache ID(s) still present: {ids}")
    print(f"Verified removal of {len(target_ids)} initially targeted cache(s) for {repository}.")
    new_ids = remaining_ids.difference(target_ids)
    if new_ids:
        print(f"{len(new_ids)} new cache(s) created concurrently remain; they were not targeted.")
    return len(target_ids)


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
