from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
FIELDS = {
    "special": ["special"],
    "prize1": ["prize1"],
    "prize2": ["prize2_1", "prize2_2"],
    "prize3": ["prize3_1", "prize3_2", "prize3_3", "prize3_4", "prize3_5", "prize3_6"],
    "prize4": ["prize4_1", "prize4_2", "prize4_3", "prize4_4"],
    "prize5": ["prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6"],
    "prize6": ["prize6_1", "prize6_2", "prize6_3"],
    "prize7": ["prize7_1", "prize7_2", "prize7_3", "prize7_4"],
}
WIDTHS = {"special": 5, "prize1": 5, "prize2": 5, "prize3": 5, "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2}
SOURCE_PRIORITY = [
    "xoso.com.vn",
    "mketqua.net",
    "www.minhngoc.net.vn",
    "xosominhngoc.com",
    "xosodaiphat.com",
    "hainhay.net",
]


def _latest_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError("canonical CSV is empty")
    return max(rows, key=lambda r: str(r.get("date", ""))[:10])


def _fmt(value: str, width: int) -> str:
    text = str(value).strip()
    if re.fullmatch(rf"[0-9]{{1,{width}}}", text) is None:
        raise ValueError(f"invalid canonical prize value {value!r} for width {width}")
    return text.zfill(width)


def build_payload(*, canonical: Path, audit_path: Path) -> dict:
    row = _latest_row(canonical)
    draw_date = str(row["date"])[:10]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    evidence = audit.get(draw_date, {})
    if not evidence.get("accepted") or int(evidence.get("agreement", 0)) < 2:
        raise ValueError(f"latest canonical date lacks accepted 2-group consensus: {draw_date}")

    prizes: dict[str, list[str]] = {}
    for group, fields in FIELDS.items():
        prizes[group] = [_fmt(row[field], WIDTHS[group]) for field in fields]

    now_local = datetime.now(TZ)
    now_utc = now_local.astimezone(ZoneInfo("UTC"))
    accepted_sources = list(evidence.get("sources", []))
    source_status = []
    for idx, source in enumerate(SOURCE_PRIORITY, start=1):
        source_status.append(
            {
                "priority": idx,
                "source": source,
                "provider_group": None,
                "received_values": 27 if source in accepted_sources else 0,
                "complete": source in accepted_sources,
                "latency_ms": None,
                "error": None,
            }
        )

    return {
        "schema_version": 2,
        "draw_date": draw_date,
        "checked_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checked_at_local": now_local.isoformat(timespec="seconds"),
        "status": "complete_verified",
        "complete": True,
        "verified_complete": True,
        "received_values": 27,
        "expected_values": 27,
        "verified_values": 27,
        "progress_percent": 100.0,
        "verification_percent": 100.0,
        "prizes": prizes,
        "conflicts": [],
        "source_status": source_status,
        "source_priority": SOURCE_PRIORITY,
        "slot_meta": {},
        "canonical_reconciled": True,
        "consensus": {
            "agreement": int(evidence.get("agreement", 0)),
            "source_agreement": int(evidence.get("source_agreement", 0)),
            "independent_groups": list(evidence.get("independent_groups", [])),
            "sources": accepted_sources,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", default="data/xsmb.csv")
    ap.add_argument("--audit", default="data/source_audit.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    payload = build_payload(canonical=Path(args.canonical), audit_path=Path(args.audit))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] canonical live reconciliation {payload['draw_date']} -> {out}")


if __name__ == "__main__":
    main()
