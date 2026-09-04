from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from time_policy import DEFAULT_DRAW_CUTOFF, VIETNAM_TIMEZONE, latest_complete_draw_date


def _load_health(path: Path) -> dict:
    if not path.exists():
        return {"ok": False, "reason": "missing health.json", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def _now(tz: str | None) -> datetime:
    if tz:
        return datetime.now(ZoneInfo(tz))
    return datetime.now().astimezone()


def _parse_hhmm(value: str) -> dtime:
    hour, minute = value.split(":", 1)
    return dtime(int(hour), int(minute))


def expected_latest_draw_date(*, now: datetime, cutoff: dtime) -> date:
    """Latest draw date that should be complete at ``now``.

    Before the evening draw cutoff, yesterday is the newest draw that can be
    required.  At/after the cutoff, today's draw is expected.  This prevents a
    morning bootstrap run from being marked stale merely because today's draw
    has not happened yet.
    """
    return latest_complete_draw_date(now=now, cutoff=cutoff)


def _write_github_summary(md: str) -> None:
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if not p:
        return
    Path(p).write_text(md, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Monitor data health and optionally fail the job.")
    ap.add_argument("--health", default="data/health.json")
    ap.add_argument("--tz", default=VIETNAM_TIMEZONE)
    ap.add_argument("--max-staleness-days", type=int, default=1, help="Allowed lag behind the expected latest draw.")
    ap.add_argument(
        "--cutoff",
        default=DEFAULT_DRAW_CUTOFF.strftime("%H:%M"),
        help="Giờ Việt Nam hoàn tất kỳ quay (HH:MM; mặc định UTC+7).",
    )
    ap.add_argument(
        "--cutoff-aware",
        action="store_true",
        help="Before cutoff, compare freshness to yesterday instead of requiring today's unfinished draw.",
    )
    ap.add_argument("--fail-on-missing", action="store_true", help="Fail if missing_count > 0 in lookback window.")
    ap.add_argument("--fail-on-stale", action="store_true", help="Fail if staleness > max-staleness-days.")
    args = ap.parse_args()

    health = _load_health(Path(args.health))
    latest = health.get("latest_date")
    missing = int(health.get("missing_count", 0) or 0)
    ok = bool(health.get("ok", False))

    now = _now(args.tz)
    today = now.date()
    expected = expected_latest_draw_date(now=now, cutoff=_parse_hhmm(args.cutoff)) if args.cutoff_aware else today

    staleness = None
    if latest:
        try:
            y, m, d = map(int, str(latest).split("-"))
            latest_d = date(y, m, d)
            staleness = (expected - latest_d).days
        except Exception:
            staleness = None

    md = [
        "# XSMB Data Health",
        "",
        f"- **Latest date:** `{latest}`",
        f"- **Today ({args.tz}):** `{today.isoformat()}`",
        f"- **Expected latest completed draw:** `{expected.isoformat()}`",
        f"- **Staleness vs expected draw (days):** `{staleness}`",
        f"- **Missing in lookback:** `{missing}`",
        "",
    ]
    if missing:
        md.append("## Missing dates (first 50)")
        md.append("")
        for d in (health.get("missing_dates") or [])[:50]:
            md.append(f"- `{d}`")
        md.append("")

    _write_github_summary("\n".join(md))

    fail = False
    reasons = []
    if args.fail_on_missing and missing > 0:
        fail = True
        reasons.append(f"missing_count={missing}")
    if args.fail_on_stale and staleness is not None and staleness > int(args.max_staleness_days):
        fail = True
        reasons.append(f"staleness={staleness} > {args.max_staleness_days}")

    print(
        "[HEALTH]",
        json.dumps(
            {
                "ok": ok,
                "latest": latest,
                "today": today.isoformat(),
                "expected_latest": expected.isoformat(),
                "missing": missing,
                "staleness": staleness,
            },
            ensure_ascii=False,
        ),
    )
    if fail:
        raise SystemExit("Health check failed: " + ", ".join(reasons))


if __name__ == "__main__":
    main()
