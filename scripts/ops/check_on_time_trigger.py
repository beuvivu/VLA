from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

WORKFLOW = "daily_update.yml"

DISPATCH_EVENT = "repository_dispatch"

STATE_NEVER = "chưa dựng"
STATE_ALIVE = "đang chạy"
STATE_DEAD = "ĐÃ CHẾT"


def fetch_dispatch_runs(
    repository: str,
    token: str,
    *,
    since: datetime,
    max_pages: int = 5,
    fetch_page: Callable[[str], dict] | None = None,
) -> list[dict]:
    if fetch_page is None:
        fetch_page = lambda url: _get_json(url, token)

    collected: list[dict] = []
    for page in range(1, max_pages + 1):
        url = (
            f"https://api.github.com/repos/{repository}"
            f"/actions/workflows/{WORKFLOW}/runs"
            f"?event={DISPATCH_EVENT}&per_page=100&page={page}"
        )
        payload = fetch_page(url)
        runs = payload.get("workflow_runs")
        if not isinstance(runs, list) or not runs:
            break
        collected.extend(runs)
        if _oldest_start(runs) is not None and _oldest_start(runs) < since:
            break
        if len(runs) < 100:
            break
    return collected


def _oldest_start(runs: Sequence[dict]) -> datetime | None:
    oldest: datetime | None = None
    for run in runs:
        started = _started_at(run)
        if started is not None and (oldest is None or started < oldest):
            oldest = started
    return oldest


def _started_at(run: dict) -> datetime | None:
    raw = str(run.get("run_started_at") or run.get("created_at") or "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _get_json(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"API trả về HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Không gọi được API: {exc.reason}") from exc


def classify(
    runs: Sequence[dict], *, now: datetime, stale_days: int, lookback_days: int
) -> tuple[str, dict]:
    stale_before = now - timedelta(days=stale_days)
    lookback_before = now - timedelta(days=lookback_days)

    newest: datetime | None = None
    in_lookback = 0
    in_window = 0

    for run in runs:
        if run.get("event") != DISPATCH_EVENT:
            continue
        started = _started_at(run)
        if started is None:
            continue
        if started < lookback_before:
            continue
        in_lookback += 1
        if newest is None or started > newest:
            newest = started
        if started >= stale_before:
            in_window += 1

    detail = {
        "lần gọi trong cửa sổ tra cứu": in_lookback,
        "lần gọi gần đây": in_window,
        "lần gọi mới nhất": newest.isoformat() if newest else None,
        "im lặng (ngày)": round((now - newest).total_seconds() / 86400, 2) if newest else None,
    }

    if in_lookback == 0:
        return STATE_NEVER, detail
    if in_window > 0:
        return STATE_ALIVE, detail
    return STATE_DEAD, detail


def report(state: str, detail: dict, *, stale_days: int) -> str:
    lines = [f"Đường đúng giờ ({WORKFLOW} ← {DISPATCH_EVENT}): {state}"]
    for key, value in detail.items():
        lines.append(f"  {key}: {value if value is not None else '—'}")

    if state == STATE_NEVER:
        lines += [
            "",
            "Bộ hẹn giờ ngoài CHƯA từng gọi vào kho này. Lưới cron vẫn chạy, nên",
            "dữ liệu vẫn về — chỉ là muộn khoảng 11,6 % số ngày.",
            "Các bước dựng: documentation/operations/on-time-trigger.md mục 4.",
        ]
    elif state == STATE_DEAD:
        lines += [
            "",
            f"Bộ hẹn giờ ngoài TỪNG chạy nhưng đã im lặng quá {stale_days} ngày.",
            "Nguyên nhân hay gặp nhất: fine-grained PAT hết hạn (mặc định 90 ngày).",
            "Lưới cron đang che triệu chứng — dữ liệu vẫn về nên không có gì khác đỏ.",
            "Kiểm token bằng bước 2 trong documentation/operations/on-time-trigger.md.",
        ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kiểm đường chạy đúng giờ còn sống không.")
    parser.add_argument("--repository", default=os.environ.get("REPOSITORY", ""))
    parser.add_argument("--stale-days", type=int, default=3)
    parser.add_argument("--lookback-days", type=int, default=45)
    args = parser.parse_args(argv)

    token = os.environ.get("GH_TOKEN", "")
    if not args.repository or not token:
        print("Thiếu REPOSITORY hoặc GH_TOKEN — bỏ qua phép kiểm đường đúng giờ.")
        return 0

    try:
        runs = fetch_dispatch_runs(
            args.repository,
            token,
            since=datetime.now(UTC) - timedelta(days=args.lookback_days),
        )
    except RuntimeError as exc:
        print(f"Không kiểm được đường đúng giờ: {exc}")
        return 0

    state, detail = classify(
        runs,
        now=datetime.now(UTC),
        stale_days=args.stale_days,
        lookback_days=args.lookback_days,
    )
    print(report(state, detail, stale_days=args.stale_days))
    return 1 if state == STATE_DEAD else 0


if __name__ == "__main__":
    sys.exit(main())
