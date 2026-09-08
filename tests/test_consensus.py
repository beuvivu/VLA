from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dtos import Result
from lottery import Lottery, RepoPaths


def _result(d: date, *, special: int) -> Result:
    values = {
        "date": d,
        "special": special,
        "prize1": 12345,
        "prize2_1": 11111,
        "prize2_2": 22222,
        "prize3_1": 30001,
        "prize3_2": 30002,
        "prize3_3": 30003,
        "prize3_4": 30004,
        "prize3_5": 30005,
        "prize3_6": 30006,
        "prize4_1": 4001,
        "prize4_2": 4002,
        "prize4_3": 4003,
        "prize4_4": 4004,
        "prize5_1": 5001,
        "prize5_2": 5002,
        "prize5_3": 5003,
        "prize5_4": 5004,
        "prize5_5": 5005,
        "prize5_6": 5006,
        "prize6_1": 601,
        "prize6_2": 602,
        "prize6_3": 603,
        "prize7_1": 71,
        "prize7_2": 72,
        "prize7_3": 73,
        "prize7_4": 74,
    }
    return Result(**values)


@dataclass
class FakeSource:
    name: str
    result: Result | None

    def fetch(self, selected_date: date, http: object) -> Result | None:
        return self.result


def _lottery(tmp_path: Path, sources: list[FakeSource]) -> Lottery:
    paths = RepoPaths(root=tmp_path, data_dir=tmp_path / "data", images_dir=tmp_path / "images")
    return Lottery(paths=paths, http=object(), sources=sources)  # type: ignore[arg-type]


def test_consensus_accepts_two_matching_sources(tmp_path: Path) -> None:
    d = date(2026, 8, 30)
    a = _result(d, special=12345)
    lot = _lottery(tmp_path, [FakeSource("a", a), FakeSource("b", a), FakeSource("c", _result(d, special=99999))])

    assert lot.fetch(d, min_agreement=2) is True
    assert lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]  # regression: audit is part of persisted provenance contract
    assert audit["agreement"] == 2
    assert audit["accepted"] is True
    assert audit["ambiguous_tie"] is False


def test_consensus_rejects_conflicting_single_sources_without_mutating_canonical(tmp_path: Path) -> None:
    d = date(2026, 8, 30)
    lot = _lottery(
        tmp_path,
        [FakeSource("a", _result(d, special=12345)), FakeSource("b", _result(d, special=54321))],
    )

    assert lot.fetch(d, min_agreement=2) is False
    assert not lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]
    assert audit["accepted"] is False
    assert audit["distinct_results"] == 2
    assert audit["ambiguous_tie"] is False


def test_two_minhnngoc_mirrors_alone_do_not_satisfy_two_provider_consensus(tmp_path: Path) -> None:
    d = date(2026, 8, 30)
    a = _result(d, special=12345)
    lot = _lottery(
        tmp_path,
        [
            FakeSource("www.minhngoc.net.vn", a),
            FakeSource("xosominhngoc.com", a),
        ],
    )

    assert lot.fetch(d, min_agreement=2) is False
    assert not lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]
    assert audit["agreement"] == 1
    assert audit["source_agreement"] == 2


def test_consensus_rejects_equal_independent_group_tie(tmp_path: Path) -> None:
    d = date(2026, 9, 1)
    a = _result(d, special=12345)
    b = _result(d, special=54321)
    lot = _lottery(
        tmp_path,
        [
            FakeSource("xoso.com.vn", a),
            FakeSource("xosodaiphat.com", a),
            FakeSource("mketqua.net", b),
            FakeSource("hainhay.net", b),
        ],
    )

    assert lot.fetch(d, min_agreement=2) is False
    assert not lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]
    assert audit["accepted"] is False
    assert audit["agreement"] == 2
    assert audit["runner_up_agreement"] == 2
    assert audit["ambiguous_tie"] is True


def test_consensus_accepts_unique_two_group_winner_over_mirror_pair(tmp_path: Path) -> None:
    d = date(2026, 9, 1)
    winner = _result(d, special=12345)
    mirror_result = _result(d, special=54321)
    lot = _lottery(
        tmp_path,
        [
            FakeSource("xoso.com.vn", winner),
            FakeSource("xosodaiphat.com", winner),
            FakeSource("www.minhngoc.net.vn", mirror_result),
            FakeSource("xosominhngoc.com", mirror_result),
        ],
    )

    assert lot.fetch(d, min_agreement=2) is True
    assert lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]
    assert audit["accepted"] is True
    assert audit["agreement"] == 2
    assert audit["runner_up_agreement"] == 1
    assert audit["ambiguous_tie"] is False


# --- Ngày không quay -------------------------------------------------------
#
# XSMB nghỉ dịp Tết và suốt đợt giãn cách 01-22/4/2020. Vào những ngày đó trang
# nguồn vẫn trả kết quả gần nhất, nên trình cào ghi lại như thể đó là kỳ của
# ngày ấy. Đo trên kho: 50 bản ghi bịa, trong đó 4 bản lọt qua CẢ kiểm đồng
# thuận hai nguồn — sáu nguồn cùng đọc một trang tin nên ở dạng hỏng này chúng
# không độc lập.


def test_rejects_a_draw_identical_to_the_previous_day(tmp_path: Path) -> None:
    """Hai kỳ liền kề trùng khít có xác suất 10^-107 (107 chữ số giải). Không
    phải "hiếm" mà là bất khả: trùng khít luôn là hiện vật."""
    yesterday, today = date(2026, 2, 15), date(2026, 2, 16)
    stale = _result(today, special=22601)

    lot = _lottery(tmp_path, [FakeSource("a", _result(yesterday, special=22601))])
    assert lot.fetch(yesterday, min_agreement=1) is True

    lot._sources = [FakeSource("a", stale)]  # type: ignore[attr-defined]
    assert lot.fetch(today, min_agreement=1) is False, "ngày không quay bị ghi thành kỳ"
    assert not lot.has_date(today)


def test_consensus_does_not_rescue_a_repeated_draw(tmp_path: Path) -> None:
    """Đồng thuận hai nguồn KHÔNG cứu được: cả sáu nguồn cùng đọc một trang
    tin nên chúng nhất trí về chính kết quả cũ. Bốn bản ghi đã lọt vào 393 kỳ
    gốc đúng theo đường này."""
    yesterday, today = date(2026, 2, 15), date(2026, 2, 16)
    stale = _result(today, special=22601)

    lot = _lottery(tmp_path, [FakeSource("a", _result(yesterday, special=22601))])
    assert lot.fetch(yesterday, min_agreement=1) is True

    lot._sources = [FakeSource("a", stale), FakeSource("b", stale)]  # type: ignore[attr-defined]
    assert lot.fetch(today, min_agreement=2) is False
    assert not lot.has_date(today)
    audit = lot._fetch_audit[today.isoformat()]
    assert audit["accepted"] is False
    assert "trùng khít" in audit["rejected_reason"]


def test_looks_at_the_next_day_too_because_backfill_runs_backwards(tmp_path: Path) -> None:
    """Backfill lấy từ mới về cũ: khi tới ngày D thì D+1 thường đã trong kho."""
    earlier, later = date(2026, 2, 15), date(2026, 2, 16)
    shared = _result(later, special=22601)

    lot = _lottery(tmp_path, [FakeSource("a", shared)])
    assert lot.fetch(later, min_agreement=1) is True

    lot._sources = [FakeSource("a", _result(earlier, special=22601))]  # type: ignore[attr-defined]
    assert lot.fetch(earlier, min_agreement=1) is False


def test_a_genuinely_different_draw_is_still_accepted(tmp_path: Path) -> None:
    """Chốt chặn không được rộng tay: chỉ trùng KHÍT mới bị loại."""
    yesterday, today = date(2026, 2, 15), date(2026, 2, 16)

    lot = _lottery(tmp_path, [FakeSource("a", _result(yesterday, special=22601))])
    assert lot.fetch(yesterday, min_agreement=1) is True

    lot._sources = [FakeSource("a", _result(today, special=22602))]  # type: ignore[attr-defined]
    assert lot.fetch(today, min_agreement=1) is True
    assert lot.has_date(today)


def test_rejects_a_repeat_even_when_the_days_between_were_removed(tmp_path: Path) -> None:
    """So kề nhau là chưa đủ — bản đó đã thủng thật trong sản xuất.

    Sau khi dọn cụm Tết 2026, quy trình hàng ngày cào lại các ngày thiếu. Với
    2026-02-17 thì cả 02-16 lẫn 02-18 đều đã bị xoá nên không còn ngày liền kề
    nào để so, và bản bịa lọt lại vào kho. Hai bản ghi quay lại đúng như vậy.

    Trùng khít ở BẤT KỲ đâu trong lịch sử đều là hiện vật: xác suất 10^-107
    không đổi theo khoảng cách ngày.
    """
    kept, refetched = date(2026, 2, 15), date(2026, 2, 17)  # 02-16 đã bị dọn
    stale = _result(refetched, special=22601)

    lot = _lottery(tmp_path, [FakeSource("a", _result(kept, special=22601))])
    assert lot.fetch(kept, min_agreement=1) is True

    lot._sources = [FakeSource("a", stale)]  # type: ignore[attr-defined]
    assert lot.fetch(refetched, min_agreement=1) is False
    assert not lot.has_date(refetched)


def test_refetching_the_same_date_is_not_treated_as_a_repeat(tmp_path: Path) -> None:
    """Cào lại đúng ngày đã có phải là thao tác không đổi, không bị coi là bịa."""
    d = date(2026, 2, 15)
    lot = _lottery(tmp_path, [FakeSource("a", _result(d, special=22601))])
    assert lot.fetch(d, min_agreement=1) is True
    assert lot.fetch(d, min_agreement=1) is True
    assert lot.has_date(d)
