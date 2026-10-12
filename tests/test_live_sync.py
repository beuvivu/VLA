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


class CountingSource(FakeSource):
    def __init__(self, name: str, pmap: dict[str, list[str]]):
        super().__init__(name, pmap)
        self.calls = 0

    def fetch_partial(self, selected_date, http, *, live=False):
        self.calls += 1
        return self.pmap


VN = ZoneInfo("Asia/Ho_Chi_Minh")
EMPTY = {k: [] for k in PRIZE_ORDER}


def test_a_complete_primary_is_verified_and_the_fallbacks_stay_untouched(monkeypatch) -> None:
    """Chính sách từ 13-10-2026: nguồn chính đủ 27 giá trị là đủ; dự phòng không bị gọi."""
    backups = [CountingSource("mketqua.net", _map()), CountingSource("www.minhngoc.net.vn", _map())]
    _use(monkeypatch, [FakeSource("xoso.com.vn", _map())], backups)
    out = live_sync.fetch_snapshot(now=datetime(2026, 8, 30, 18, 33, tzinfo=VN))
    assert out["status"] == "complete_verified"
    assert out["verified_values"] == 27
    assert out["prizes"]["special"] == ["83772"]
    assert out["failover"]["fallback_activated"] is False
    assert [b.calls for b in backups] == [0, 0]
    assert out["checked_at_local"] == "2026-08-30T18:33:00+07:00"
    assert out["checked_at_utc"] == "2026-08-30T11:33:00Z"


def test_live_snapshot_normalizes_utc_clock_before_selecting_date(monkeypatch) -> None:
    _use(monkeypatch, [FakeSource("xoso.com.vn", _map())], [])
    out = live_sync.fetch_snapshot(now=datetime(2026, 8, 30, 11, 30, tzinfo=UTC))
    assert out["draw_date"] == "2026-08-30"
    assert out["status"] == "complete_verified"


def test_a_primary_still_drawing_shows_live_without_calling_the_fallbacks(monkeypatch) -> None:
    partial = {**EMPTY, "prize1": ["68785"], "prize2": ["50518", "27452"]}
    backup = CountingSource("mketqua.net", _map())
    _use(monkeypatch, [FakeSource("xoso.com.vn", partial)], [backup])
    out = live_sync.fetch_snapshot(now=datetime(2026, 8, 30, 18, 20, tzinfo=VN))
    assert out["status"] == "live"
    assert out["received_values"] == 3
    assert backup.calls == 0


def test_a_dead_primary_is_replaced_by_the_fallbacks(monkeypatch) -> None:
    _use(monkeypatch, [FakeSource("xoso.com.vn", EMPTY)],
         [FakeSource("mketqua.net", _map()), FakeSource("www.minhngoc.net.vn", _map())])
    out = live_sync.fetch_snapshot(now=datetime(2026, 8, 30, 18, 33, tzinfo=VN))
    assert out["failover"]["fallback_activated"] is True
    assert out["status"] == "complete_verified"
    assert [row["source"] for row in out["source_status"]] == ["xoso.com.vn", "mketqua.net", "www.minhngoc.net.vn"]


def test_a_stuck_primary_does_not_mask_the_fallback_values(monkeypatch) -> None:
    """Sau 18:40 nguồn chính còn thiếu ô là sự cố: chỉ dữ liệu dự phòng được hợp nhất,
    nên giá trị kẹt của nguồn chính không thành "xung đột" che mất kết quả."""
    stuck = {**_map(), "special": ["99999"], "prize7": []}
    _use(monkeypatch, [FakeSource("xoso.com.vn", stuck)], [FakeSource("mketqua.net", _map())])
    out = live_sync.fetch_snapshot(now=datetime(2026, 8, 30, 18, 45, tzinfo=VN))
    assert out["prizes"]["special"] == ["83772"]
    assert out["conflicts"] == []
    assert out["status"] == "complete_verified"


def test_two_disagreeing_fallbacks_are_a_conflict_not_a_verified_result(monkeypatch) -> None:
    other = {**_map(), "special": ["11111"]}
    _use(monkeypatch, [FakeSource("xoso.com.vn", EMPTY)],
         [FakeSource("mketqua.net", _map()), FakeSource("www.minhngoc.net.vn", other)])
    out = live_sync.fetch_snapshot(now=datetime(2026, 8, 30, 18, 33, tzinfo=VN))
    assert out["complete"] is True
    assert out["verified_complete"] is False
    assert out["status"] == "complete_conflict"
    assert out["conflicts"] == ["special[0]"]
