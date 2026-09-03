from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import live_sync
from sources import PRIZE_ORDER


class FakeSource:
    def __init__(self, name: str, pmap: dict[str, list[str]]):
        self.name = name
        self.pmap = pmap

    def fetch_partial(self, selected_date, http, *, live=False):
        return self.pmap


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
    monkeypatch.setattr(live_sync, "default_sources", lambda: [FakeSource("a", p), FakeSource("b", p)])
    monkeypatch.setattr(live_sync.requests, "Session", lambda: object())
    now = datetime(2026, 8, 30, 18, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    out = live_sync.fetch_snapshot(now=now)
    assert out["status"] == "complete_verified"
    assert out["verified_values"] == 27
    assert out["prizes"]["special"] == ["83772"]


def test_live_single_source_is_provisional_not_canonical_verified(monkeypatch) -> None:
    p = _map()
    empty = {k: [] for k in PRIZE_ORDER}
    monkeypatch.setattr(live_sync, "default_sources", lambda: [FakeSource("a", p), FakeSource("b", empty)])
    monkeypatch.setattr(live_sync.requests, "Session", lambda: object())
    now = datetime(2026, 8, 30, 18, 25, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    out = live_sync.fetch_snapshot(now=now)
    assert out["complete"] is True
    assert out["verified_complete"] is False
    assert out["status"] == "complete_provisional"
