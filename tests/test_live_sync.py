from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import live_sync
import sources
from sources import PRIZE_ORDER


class FakeSource:
    def __init__(self, name: str, pmap: dict[str, list[str]]):
        self.name = name
        self.pmap = pmap

    def fetch_partial(self, selected_date, http, *, live=False):
        return self.pmap


def _use(monkeypatch, primary, fallback) -> None:
    """Thay hai TẦNG nguồn, không phải danh sách phẳng.

    ``fetch_with_failover`` tra ``primary_sources``/``fallback_sources`` ngay
    tại lúc gọi, nên vá ở module ``sources`` là đủ cho cả hai bên.
    """
    monkeypatch.setattr(sources, "primary_sources", lambda: list(primary))
    monkeypatch.setattr(sources, "fallback_sources", lambda: list(fallback))
    monkeypatch.setattr(live_sync.requests, "Session", lambda: object())


def _map() -> dict[str, list[str]]:
    return {
        "special": ["83772"], "prize1": ["68785"],
        "prize2": ["50518", "27452"],
        "prize3": ["57053", "92810", "56241", "65128", "33811", "42264"],
        "prize4": ["4753", "1152", "6777", "3507"],
        "prize5": ["9460", "2913", "3232", "2999", "3670", "5129"],
        "prize6": ["939", "751", "594"],
        "prize7": ["66", "21", "34", "78"],
    }


def test_live_snapshot_marks_complete_only_when_two_sources_verify_every_slot(monkeypatch) -> None:
    p = _map()
    _use(monkeypatch, [FakeSource("a", p), FakeSource("b", p)], [])
    now = datetime(2026, 8, 30, 18, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    out = live_sync.fetch_snapshot(now=now)
    assert out["status"] == "complete_verified"
    assert out["verified_values"] == 27
    assert out["prizes"]["special"] == ["83772"]
    assert out["checked_at_local"] == "2026-08-30T18:30:00+07:00"
    assert out["checked_at_utc"] == "2026-08-30T11:30:00Z"


def test_live_snapshot_normalizes_utc_clock_before_selecting_date(monkeypatch) -> None:
    p = _map()
    _use(monkeypatch, [FakeSource("a", p), FakeSource("b", p)], [])
    out = live_sync.fetch_snapshot(now=datetime(2026, 8, 30, 11, 30, tzinfo=UTC))
    assert out["draw_date"] == "2026-08-30"
    assert out["status"] == "complete_verified"


def test_live_single_source_is_provisional_not_canonical_verified(monkeypatch) -> None:
    p = _map()
    empty = {k: [] for k in PRIZE_ORDER}
    _use(monkeypatch, [FakeSource("a", p), FakeSource("b", empty)], [])
    now = datetime(2026, 8, 30, 18, 25, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    out = live_sync.fetch_snapshot(now=now)
    assert out["complete"] is True
    assert out["verified_complete"] is False
    assert out["status"] == "complete_provisional"
