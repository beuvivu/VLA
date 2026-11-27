from __future__ import annotations


import csv
from pathlib import Path

from core.calendar_alignment import known_non_draw_days, missing_calendar_dates

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / "data" / "xsmb.csv"


def _shipped_dates() -> list[str]:
    with CANONICAL.open(encoding="utf-8") as handle:
        return [row["date"] for row in csv.DictReader(handle)]


def test_every_gap_in_shipped_history_is_a_declared_non_draw_day() -> None:
    gaps = set(missing_calendar_dates(_shipped_dates()))
    undeclared = sorted(gaps - known_non_draw_days())
    assert not undeclared, (
        "Lịch sử đã xuất bản có ngày vắng chưa khai trong data/non_draw_days.json. "
        "Vắng vì KHÔNG QUAY thì thêm vào tệp đó; vắng vì CÀO HỤT thì phải cào lại. "
        f"{len(undeclared)} ngày: {undeclared[:10]}"
    )


def test_declared_non_draw_days_are_not_silently_stale() -> None:
    present = set(_shipped_dates())
    first, last = min(present), max(present)
    contradictions = sorted(
        d for d in known_non_draw_days() if first <= d <= last and d in present
    )
    assert not contradictions, (
        "Ngày vừa được khai là KHÔNG QUAY vừa có bản ghi trong data/xsmb.csv: "
        f"{contradictions[:10]}"
    )
