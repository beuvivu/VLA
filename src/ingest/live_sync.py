from __future__ import annotations


import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

from ingest.sources import (
    EXPECTED_COUNTS,
    PRIZE_ORDER,
    STALE_PAGE_ERROR,
    SourceObservation,
    anonymise_snapshot,
    fetch_with_failover,
    load_previous_draw,
    shows_previous_draw,
    source_consensus_partial,
    source_independence_key,
)
from core.time_policy import VIETNAM_TZ, iso_local, iso_utc

TZ = VIETNAM_TZ


def fetch_snapshot(
    *,
    now: datetime | None = None,
    min_agreement: int = 1,
    previous: dict[str, list[str]] | None = None,
) -> dict:
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(TZ)
    def fetch_one(source, tier: str, priority: int) -> SourceObservation:
        started = time.perf_counter()
        error: str | None = None
        try:
            http = requests.Session()
            prize_map = source.fetch_partial(now.date(), http, live=True)
        except Exception as exc:
            prize_map = {k: [] for k in PRIZE_ORDER}
            error = f"{type(exc).__name__}: {str(exc)[:120]}"
        if shows_previous_draw(prize_map, previous):
            prize_map = {k: [] for k in PRIZE_ORDER}
            error = STALE_PAGE_ERROR
        return SourceObservation(
            name=source.name,
            tier=tier,
            priority=priority,
            prize_map=prize_map,
            error=error,
            latency_ms=int(round((time.perf_counter() - started) * 1000.0)),
        )

    def run_batch(jobs):
        if not jobs:
            return []
        with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as pool:
            futures = [pool.submit(fetch_one, *job) for job in jobs]
            done = [future.result() for future in as_completed(futures)]
        return sorted(done, key=lambda o: o.priority)

    observations, failover_log = fetch_with_failover(
        fetch_one, target=now.date(), now=now, run_batch=run_batch, min_agreement=min_agreement
    )

    partials = [
        (o.name, o.prize_map)
        for o in observations
        if not (failover_log["primary_failed"] and o.tier == "primary")
    ]
    source_status = [
        {
            "priority": o.priority,
            "tier": o.tier,
            "source": o.name,
            "provider_group": source_independence_key(o.name),
            "received_values": sum(len(o.prize_map.get(k, [])) for k in PRIZE_ORDER),
            "complete": sum(len(o.prize_map.get(k, [])) for k in PRIZE_ORDER)
            == sum(EXPECTED_COUNTS.values()),
            "latency_ms": o.latency_ms,
            "error": o.error,
        }
        for o in observations
    ]

    merged, meta = source_consensus_partial(partials, min_agreement=min_agreement)
    received = int(meta["received_slots"])
    expected = int(meta["total_slots"])
    verified = int(meta["verified_slots"])
    conflicts = list(meta["conflicts"])

    complete = received == expected
    verified_complete = complete and verified == expected and not conflicts
    in_window = (now.hour == 17 and now.minute >= 55) or (
        now.hour == 18 and now.minute <= 55
    )

    if verified_complete:
        status = "complete_verified"
    elif complete:
        status = "complete_provisional" if not conflicts else "complete_conflict"
    elif received > 0 and in_window:
        status = "live"
    elif received > 0:
        status = "partial"
    else:
        status = "waiting"

    return {
        "schema_version": 2,
        "draw_date": now.date().isoformat(),
        "checked_at_utc": iso_utc(now),
        "checked_at_local": iso_local(now),
        "status": status,
        "complete": complete,
        "verified_complete": verified_complete,
        "received_values": received,
        "expected_values": expected,
        "verified_values": verified,
        "progress_percent": round(100.0 * received / expected, 1),
        "verification_percent": round(100.0 * verified / expected, 1),
        "prizes": merged,
        "conflicts": conflicts,
        "source_status": source_status,
        "slot_meta": meta["slot_meta"],
        "failover": failover_log,
        "note": (
            "GitHub near-live snapshot from the primary source; fallback sources are read "
            "only when it fails. Canonical history is written from the dated results page."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build multi-source near-live XSMB JSON.")
    ap.add_argument("--out", default="docs/data/live.json")
    ap.add_argument("--min-agreement", type=int, default=1)
    ap.add_argument(
        "--history", default="data/xsmb.csv",
        help="Sổ chuẩn; kỳ đã lưu gần nhất dùng để nhận ra nguồn còn hiện kỳ trước.",
    )
    args = ap.parse_args()

    today = datetime.now(TZ).date()
    payload = fetch_snapshot(
        min_agreement=max(1, args.min_agreement),
        previous=load_previous_draw(Path(args.history), before=today),
    )
    public = anonymise_snapshot(payload)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "[OK] live snapshot: "
        f"status={payload['status']} progress={payload['progress_percent']}% "
        f"verified={payload['verification_percent']}% -> {out}"
    )


if __name__ == "__main__":
    main()
