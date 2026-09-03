from __future__ import annotations

"""Near-live multi-source XSMB snapshot for GitHub-only hosting.

Canonical history is intentionally NOT mutated here.  During the draw window we
poll six public sources, merge prize slots by agreement and expose a provisional
value only when consensus has not yet formed.  Final history promotion remains
in ``sync.py`` where complete results require multi-source agreement.
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from sources import (
    EXPECTED_COUNTS,
    PRIZE_ORDER,
    default_sources,
    source_consensus_partial,
    source_independence_key,
)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def fetch_snapshot(*, now: datetime | None = None, min_agreement: int = 2) -> dict:
    now = now or datetime.now(TZ)
    sources = default_sources()
    partial_by_priority: dict[int, tuple[str, dict[str, list[str]]]] = {}
    status_by_priority: dict[int, dict[str, object]] = {}

    def fetch_one(priority: int, source) -> tuple[int, str, dict[str, list[str]], str | None, int]:
        started = time.perf_counter()
        error: str | None = None
        try:
            # Separate sessions avoid thread-safety surprises and
            # bound a full six-source snapshot by the slowest source, not their sum.
            http = requests.Session()
            prize_map = source.fetch_partial(now.date(), http, live=True)
        except Exception as exc:  # noqa: BLE001
            prize_map = {k: [] for k in PRIZE_ORDER}
            error = f"{type(exc).__name__}: {str(exc)[:120]}"
        latency_ms = int(round((time.perf_counter() - started) * 1000.0))
        return priority, source.name, prize_map, error, latency_ms

    with ThreadPoolExecutor(max_workers=min(6, len(sources))) as pool:
        futures = [
            pool.submit(fetch_one, priority, source)
            for priority, source in enumerate(sources, start=1)
        ]
        for future in as_completed(futures):
            priority, name, prize_map, error, latency_ms = future.result()
            received = sum(len(prize_map.get(k, [])) for k in PRIZE_ORDER)
            partial_by_priority[priority] = (name, prize_map)
            status_by_priority[priority] = {
                "priority": priority,
                "source": name,
                "provider_group": source_independence_key(name),
                "received_values": received,
                "complete": received == sum(EXPECTED_COUNTS.values()),
                "latency_ms": latency_ms,
                "error": error,
            }

    partials = [partial_by_priority[i] for i in sorted(partial_by_priority)]
    source_status = [status_by_priority[i] for i in sorted(status_by_priority)]

    merged, meta = source_consensus_partial(partials, min_agreement=min_agreement)
    received = int(meta["received_slots"])
    expected = int(meta["total_slots"])
    verified = int(meta["verified_slots"])
    conflicts = list(meta["conflicts"])

    complete = received == expected
    verified_complete = complete and verified == expected and not conflicts
    in_window = now.hour == 18 and 5 <= now.minute <= 55

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
        "checked_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "checked_at_local": now.isoformat(timespec="seconds"),
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
        "source_priority": [source.name for source in default_sources()],
        "slot_meta": meta["slot_meta"],
        "note": (
            "GitHub near-live snapshot. Single-source values are provisional; "
            "canonical history is promoted only after complete multi-source consensus."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build multi-source near-live XSMB JSON.")
    ap.add_argument("--out", default="docs/data/live.json")
    ap.add_argument("--min-agreement", type=int, default=2)
    args = ap.parse_args()

    payload = fetch_snapshot(min_agreement=max(2, args.min_agreement))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "[OK] live snapshot: "
        f"status={payload['status']} progress={payload['progress_percent']}% "
        f"verified={payload['verification_percent']}% -> {out}"
    )


if __name__ == "__main__":
    main()
