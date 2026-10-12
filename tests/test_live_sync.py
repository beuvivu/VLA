from __future__ import annotations

from datetime import UTC, date, datetime
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


# --- Nguồn còn hiện kỳ trước -------------------------------------------------
# Đo trên runner lúc 00:37 ngày 13-10-2026: trang live của cả ba nguồn hiện trọn kỳ 12-10.


def _other_map() -> dict[str, list[str]]:
    other = _map()
    other["special"] = ["00000"]
    return other


def test_a_page_still_showing_the_previous_draw_is_not_todays_result(monkeypatch) -> None:
    _use(
        monkeypatch,
        [FakeSource("xoso.com.vn", _map())],
        [FakeSource("mketqua.net", _map()), FakeSource("www.minhngoc.net.vn", _map())],
    )
    payload = live_sync.fetch_snapshot(now=datetime(2026, 10, 13, 18, 8, tzinfo=VN), previous=_map())
    assert payload["status"] == "waiting"
    assert payload["received_values"] == 0
    assert payload["failover"]["fallback_activated"] is True, "nguồn chính còn hiện kỳ trước là sự cố"
    assert {row["error"] for row in payload["source_status"]} == {sources.STALE_PAGE_ERROR}


def test_a_new_draw_coming_in_is_not_mistaken_for_the_previous_one(monkeypatch) -> None:
    """Kỳ mới về dần: ô nào đã về mà khác kỳ trước là đủ để không phải trang cũ."""
    drawing = {k: [] for k in PRIZE_ORDER}
    drawing["prize1"] = ["12345"]
    _use(monkeypatch, [FakeSource("xoso.com.vn", drawing)], [])
    payload = live_sync.fetch_snapshot(now=datetime(2026, 10, 13, 18, 16, tzinfo=VN), previous=_map())
    assert payload["status"] == "live"
    assert payload["prizes"]["prize1"] == ["12345"]
    assert payload["source_status"][0]["error"] is None


def test_without_a_stored_draw_nothing_is_called_stale(monkeypatch) -> None:
    _use(monkeypatch, [FakeSource("xoso.com.vn", _map())], [])
    payload = live_sync.fetch_snapshot(now=datetime(2026, 10, 13, 18, 31, tzinfo=VN), previous=None)
    assert payload["status"] == "complete_verified"


def test_one_differing_value_is_enough_to_be_a_new_draw() -> None:
    assert sources.shows_previous_draw(_map(), _map()) is True
    assert sources.shows_previous_draw(_other_map(), _map()) is False
    partial = {k: (v[:1] if k == "prize1" else []) for k, v in _map().items()}
    assert sources.shows_previous_draw(partial, _map()) is True
    assert sources.shows_previous_draw(EMPTY, _map()) is False, "bảng rỗng không phải trang cũ"
    longer = {**_map(), "prize7": [*_map()["prize7"], "99"]}
    assert sources.shows_previous_draw(longer, _map()) is False


def test_the_previous_draw_is_read_from_the_canonical_ledger(tmp_path) -> None:
    """Kỳ gần nhất TRƯỚC hôm nay, và số 0 đầu mà CSV có thể đã mất được trả lại đúng độ rộng."""
    header = (
        "date,special,prize1,prize2_1,prize2_2,prize3_1,prize3_2,prize3_3,prize3_4,prize3_5,"
        "prize3_6,prize4_1,prize4_2,prize4_3,prize4_4,prize5_1,prize5_2,prize5_3,prize5_4,"
        "prize5_5,prize5_6,prize6_1,prize6_2,prize6_3,prize7_1,prize7_2,prize7_3,prize7_4"
    )
    row = ",".join(["83772", "68785", "50518", "27452", "57053", "92810", "56241", "65128",
                    "33811", "42264", "4753", "1152", "6777", "3507", "9460", "2913", "3232",
                    "2999", "3670", "5129", "939", "751", "594", "66", "21", "34", "78"])
    older = row.replace("83772", "11111", 1)
    today = row.replace("83772", "22222", 1).replace(",66,", ",6,", 1)
    ledger = tmp_path / "xsmb.csv"
    ledger.write_text(
        f"{header}\n2026-10-11,{older}\n2026-10-12,{row.replace(',66,', ',6,', 1)}\n2026-10-13,{today}\n",
        encoding="utf-8",
    )
    previous = sources.load_previous_draw(ledger, before=date(2026, 10, 13))
    assert previous["special"] == ["83772"], "kỳ 12-10, không phải 11-10 hay chính hôm nay"
    assert previous["prize7"] == ["06", "21", "34", "78"], "số 0 đầu phải được trả lại"
    assert sources.load_previous_draw(tmp_path / "khong-co.csv", before=date(2026, 10, 13)) is None


def test_the_command_line_passes_the_previous_draw_to_the_snapshot(tmp_path, monkeypatch) -> None:
    header = "date," + ",".join(
        key if len(values) == 1 else ",".join(f"{key}_{i}" for i in range(1, len(values) + 1))
        for key, values in _map().items()
    )
    row = "2000-01-01," + ",".join(v for values in _map().values() for v in values)
    ledger = tmp_path / "xsmb.csv"
    ledger.write_text(f"{header}\n{row}\n", encoding="utf-8")

    seen: list[dict] = []
    real_snapshot = live_sync.fetch_snapshot

    def fake_snapshot(**kwargs):
        seen.append(kwargs)
        return real_snapshot(now=datetime(2026, 10, 13, 10, 0, tzinfo=VN), previous=None)

    _use(monkeypatch, [FakeSource("xoso.com.vn", EMPTY)], [])
    monkeypatch.setattr(live_sync, "fetch_snapshot", fake_snapshot)
    monkeypatch.setattr("sys.argv", ["live_sync.py", "--out", str(tmp_path / "live.json"),
                                     "--history", str(ledger)])
    live_sync.main()
    assert seen[0]["previous"] == _map()


def test_a_two_group_threshold_calls_the_fallbacks_and_keeps_a_healthy_primary(monkeypatch) -> None:
    """Nguồn chính là MỘT nhóm: ngưỡng 2 cần nhân chứng, và nguồn chính lành vẫn được tính."""
    backups = [CountingSource("mketqua.net", _map()), CountingSource("www.minhngoc.net.vn", EMPTY)]
    _use(monkeypatch, [FakeSource("xoso.com.vn", _map())], backups)
    payload = live_sync.fetch_snapshot(now=datetime(2026, 10, 13, 18, 33, tzinfo=VN), min_agreement=2)
    assert [b.calls for b in backups] == [1, 1]
    assert payload["failover"]["primary_failed"] is False
    assert payload["failover"]["fallback_activated"] is True
    assert payload["status"] == "complete_verified", "nguồn chính + một dự phòng = hai nhóm"
    supporters = {name for meta in payload["slot_meta"].values() for name in meta["support"]}
    assert supporters == {"xoso.com.vn", "mketqua.net"}
