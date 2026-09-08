"""Kiểm thử trình bổ sung lịch sử.

Không test nào chạm mạng: ``Lottery`` được thay bằng bản giả có kịch bản, và
hàm chờ được tiêm vào nên bộ test chạy trong mili-giây thay vì hàng giờ.
"""

from __future__ import annotations

from datetime import date

import pytest

from backfill_history import (
    EARLIEST_SUPPORTED,
    BackfillReport,
    backfill,
    date_range,
    missing_dates,
)


class FakeLottery:
    """Kho giả: giữ tập ngày trong bộ nhớ và đếm số lần ghi."""

    def __init__(self, have: set[date] | None = None, fail_on: set[date] | None = None,
                 raise_on: set[date] | None = None) -> None:
        self._have = set(have or ())
        self._fail_on = set(fail_on or ())
        self._raise_on = set(raise_on or ())
        self.dumps = 0
        self.fetch_calls: list[date] = []
        # Bảng được chụp lúc nạp, đúng như Lottery.load() làm.
        self._frame = set(self._have)
        self.persisted: set[date] = set()

    def get_dates(self) -> set[date]:
        return set(self._have)

    def fetch(self, day: date, *, min_agreement: int = 1) -> bool:
        self.fetch_calls.append(day)
        if day in self._raise_on:
            raise RuntimeError("nguồn sập")
        if day in self._fail_on:
            return False
        self._have.add(day)
        return True

    def generate_dataframes(self) -> None:
        """Chụp ``_have`` vào bảng, y như ``Lottery.generate_dataframes``."""
        self._frame = set(self._have)

    def dump(self) -> None:
        """Ghi **bảng đã chụp**, không phải ``_have``.

        Đây là điểm mấu chốt: ``Lottery.dump`` ghi ``_raw_data`` chứ không
        ghi ``_data``. Bản giả cũ chỉ đếm số lần gọi nên nó không thể lộ ra
        lỗi mất dữ liệu — backfill dump mà quên dựng lại bảng thì ghi đè kho
        bằng ảnh chụp cũ.
        """
        self.dumps += 1
        self.persisted = set(self._frame)


def _run(lot, start, end, **kw):
    kw.setdefault("delay_range", (0.0, 0.0))
    kw.setdefault("sleeper", lambda _s: None)
    return backfill(lot, start, end, **kw)


# --- Tiện ích dải ngày -----------------------------------------------------


def test_date_range_is_inclusive_at_both_ends() -> None:
    got = date_range(date(2026, 1, 1), date(2026, 1, 3))
    assert got == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]


def test_date_range_of_a_single_day() -> None:
    assert date_range(date(2026, 1, 1), date(2026, 1, 1)) == [date(2026, 1, 1)]


def test_date_range_reversed_is_empty_not_an_error() -> None:
    assert date_range(date(2026, 1, 5), date(2026, 1, 1)) == []


def test_missing_dates_skips_what_we_already_have() -> None:
    wanted = date_range(date(2026, 1, 1), date(2026, 1, 5))
    have = {date(2026, 1, 2), date(2026, 1, 4)}
    assert missing_dates(wanted, have) == [
        date(2026, 1, 5), date(2026, 1, 3), date(2026, 1, 1)
    ]


def test_missing_dates_returns_newest_first() -> None:
    """Kỳ gần đây được nhiều nguồn lưu trữ hơn và có giá trị phân tích cao
    hơn, nên đứt sớm thì phần thu được vẫn là phần đáng giá nhất."""
    got = missing_dates(date_range(date(2026, 1, 1), date(2026, 1, 4)), set())
    assert got == sorted(got, reverse=True)


# --- Kiểm tra tham số ------------------------------------------------------


def test_rejects_a_reversed_range() -> None:
    with pytest.raises(ValueError, match="phải trước"):
        _run(FakeLottery(), date(2026, 1, 5), date(2026, 1, 1))


def test_rejects_a_start_before_archives_exist() -> None:
    """Dữ liệu thiếu giải còn tệ hơn không có dữ liệu: nó lặng lẽ làm lệch
    mọi thống kê."""
    with pytest.raises(ValueError, match="sớm hơn mốc"):
        _run(FakeLottery(), date(2000, 1, 1), date(2000, 1, 5))


@pytest.mark.parametrize("kw", [
    {"checkpoint_every": 0},
    {"max_failures": 0},
    {"delay_range": (-1.0, 2.0)},
    {"delay_range": (5.0, 1.0)},
])
def test_rejects_impossible_settings(kw) -> None:
    with pytest.raises(ValueError):
        _run(FakeLottery(), date(2026, 1, 1), date(2026, 1, 2), **kw)


def test_earliest_supported_is_a_real_boundary() -> None:
    assert EARLIEST_SUPPORTED < date(2020, 1, 1)


# --- Hành vi chính ---------------------------------------------------------


def test_fetches_only_the_missing_days() -> None:
    lot = FakeLottery(have={date(2026, 1, 2)})
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 3))
    assert rep.requested == 3
    assert rep.already_present == 1
    assert rep.fetched == 2
    assert date(2026, 1, 2) not in lot.fetch_calls


def test_a_fully_covered_range_makes_no_network_calls() -> None:
    """Chạy lại phải rẻ; đây là điều kiện để công cụ dùng được thật."""
    have = set(date_range(date(2026, 1, 1), date(2026, 1, 5)))
    lot = FakeLottery(have=have)
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 5))
    assert lot.fetch_calls == []
    assert rep.fetched == 0
    assert rep.success_rate == 1.0, "không thử lần nào thì coi như thành công"


def test_writes_a_checkpoint_so_a_crash_does_not_lose_everything() -> None:
    lot = FakeLottery()
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 10), checkpoint_every=3)
    # 10 kỳ, ghi mỗi 3 kỳ -> 3 lần trong vòng lặp + 1 lần cuối cho phần dư.
    assert rep.checkpoints == 4
    assert lot.dumps == 4


def test_final_partial_batch_is_still_written() -> None:
    lot = FakeLottery()
    _run(lot, date(2026, 1, 1), date(2026, 1, 2), checkpoint_every=100)
    assert lot.dumps == 1, "phần dư cuối cùng không được bỏ quên"


def test_nothing_to_do_writes_nothing() -> None:
    lot = FakeLottery(have={date(2026, 1, 1)})
    _run(lot, date(2026, 1, 1), date(2026, 1, 1))
    assert lot.dumps == 0


# --- Chịu lỗi --------------------------------------------------------------


def test_one_bad_day_does_not_stop_the_range() -> None:
    lot = FakeLottery(fail_on={date(2026, 1, 3)})
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 5))
    assert rep.fetched == 4
    assert rep.failed == [date(2026, 1, 3)]


def test_an_exception_is_treated_as_a_failed_day_not_a_crash() -> None:
    lot = FakeLottery(raise_on={date(2026, 1, 3)})
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 5))
    assert rep.fetched == 4
    assert rep.failed == [date(2026, 1, 3)]


def test_stops_after_too_many_consecutive_failures() -> None:
    """Hỏng liên tiếp nghĩa là nguồn đã chặn; chạy tiếp chỉ tốn thời gian và
    làm tình hình tệ hơn."""
    all_days = set(date_range(date(2026, 1, 1), date(2026, 2, 1)))
    lot = FakeLottery(fail_on=all_days)
    rep = _run(lot, date(2026, 1, 1), date(2026, 2, 1), max_failures=5)
    assert len(rep.failed) == 5
    assert len(lot.fetch_calls) == 5, "phải dừng, không thử hết dải"


def test_a_success_resets_the_consecutive_failure_counter() -> None:
    """Hỏng rải rác là bình thường; chỉ chuỗi hỏng LIÊN TIẾP mới đáng dừng."""
    days = date_range(date(2026, 1, 1), date(2026, 1, 10))
    # hỏng xen kẽ: không bao giờ đạt 3 lần liên tiếp
    lot = FakeLottery(fail_on={days[1], days[3], days[5], days[7]})
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 10), max_failures=3)
    assert len(lot.fetch_calls) == 10, "không được dừng sớm"
    assert rep.fetched == 6


# --- Nhịp chờ --------------------------------------------------------------


def test_waits_between_requests() -> None:
    """Nã hàng nghìn yêu cầu liên tiếp vào một trang tin sẽ bị chặn IP."""
    naps: list[float] = []
    lot = FakeLottery()
    backfill(lot, date(2026, 1, 1), date(2026, 1, 5),
             delay_range=(1.5, 3.0), sleeper=naps.append)
    assert len(naps) == 4, "chờ giữa các kỳ, không chờ sau kỳ cuối"
    assert all(1.5 <= n <= 3.0 for n in naps)


def test_delay_is_jittered() -> None:
    naps: list[float] = []
    backfill(FakeLottery(), date(2026, 1, 1), date(2026, 1, 20),
             delay_range=(1.0, 3.0), sleeper=naps.append)
    assert len(set(round(n, 6) for n in naps)) > 1


# --- Báo cáo ---------------------------------------------------------------


def test_report_success_rate_counts_only_attempted_days() -> None:
    rep = BackfillReport(requested=10, already_present=8, fetched=1,
                         failed=[date(2026, 1, 1)])
    assert rep.attempted == 2
    assert rep.success_rate == 0.5


def test_report_summary_is_one_readable_line() -> None:
    lot = FakeLottery(fail_on={date(2026, 1, 2)})
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 3))
    text = rep.summary()
    assert "lấy mới 2" in text and "hỏng 1" in text
    assert "\n" not in text


# --- Hợp đồng với Lottery thật ---------------------------------------------


def test_persists_the_days_it_fetched_not_a_stale_snapshot() -> None:
    """Kỳ đã lấy phải nằm trong tệp ghi ra, không chỉ trong bộ nhớ.

    Lần chạy thật 34174095945 lấy 2049 kỳ, hỏng 0, báo "Kho: 393 → 2442 kỳ"
    rồi ghi ra một tệp 393 kỳ: ``fetch`` thêm vào ``_data`` còn ``dump`` ghi
    ``_raw_data``, và không ai gọi ``generate_dataframes`` ở giữa. Báo cáo
    khi đó nói về bộ nhớ, còn đĩa thì trống — mất trọn 1 giờ 35 phút cào.
    """
    lot = FakeLottery()
    days = {date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)}
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 3))

    assert rep.fetched == 3
    assert lot.persisted == days, (
        "kỳ đã lấy không có trong dữ liệu ghi ra — dump đã ghi đè bằng ảnh "
        "chụp cũ"
    )


def test_every_checkpoint_persists_what_was_fetched_so_far() -> None:
    """Checkpoint tồn tại để một lần chạy đứt không mất trắng. Checkpoint ghi
    ảnh chụp cũ thì nó không cứu được gì mà còn che mất lỗi."""
    lot = FakeLottery()
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 10), checkpoint_every=3)

    assert rep.checkpoints >= 3
    assert len(lot.persisted) == 10


def test_backfill_never_dumps_without_rebuilding_the_frames() -> None:
    """Chặn tận gốc: mọi lời gọi ``dump`` trong backfill phải đi qua
    ``_persist``, nơi duy nhất gọi ``generate_dataframes`` ngay trước đó."""
    import re
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1] / "src" / "backfill_history.py"
    ).read_text(encoding="utf-8")

    body = src[src.index("def _persist(") :]
    persist_body = body[: body.index("\ndef ", 1)]
    assert "generate_dataframes()" in persist_body
    assert persist_body.index("generate_dataframes()") < persist_body.index("dump()")

    outside = src.replace(persist_body, "")
    assert "lottery.dump()" not in outside, (
        "còn lời gọi dump() không đi qua _persist — kỳ vừa lấy sẽ bị ghi đè"
    )


def test_fake_lottery_matches_the_real_api() -> None:
    """FakeLottery phải khớp chữ ký thật, nếu không cả tệp test này vô nghĩa.

    Một bản giả trôi khỏi API thật vẫn cho test xanh trong khi mã sản xuất đã
    hỏng — đó là kiểu hỏng tệ nhất vì nó im lặng.
    """
    import inspect

    from lottery import Lottery

    for name in ("fetch", "dump", "get_dates", "load", "generate_dataframes"):
        assert hasattr(Lottery, name), f"Lottery thiếu {name}"
        assert hasattr(FakeLottery, name) or name == "load", f"bản giả thiếu {name}"

    real = inspect.signature(Lottery.fetch)
    fake = inspect.signature(FakeLottery.fetch)
    assert "min_agreement" in real.parameters
    assert "min_agreement" in fake.parameters
    assert real.parameters["min_agreement"].kind == fake.parameters["min_agreement"].kind
    assert real.parameters["min_agreement"].default == fake.parameters["min_agreement"].default


def test_backfill_only_uses_methods_the_real_lottery_has() -> None:
    """Chặn việc vô tình gọi một phương thức chỉ bản giả mới có."""
    import re
    from pathlib import Path

    from lottery import Lottery

    src = Path(__file__).resolve().parents[1] / "src" / "backfill_history.py"
    used = set(re.findall(r"\blottery\.(\w+)\(", src.read_text(encoding="utf-8")))
    assert used, "không tìm thấy lời gọi nào tới lottery"
    for name in used:
        assert hasattr(Lottery, name), f"backfill gọi lottery.{name}() nhưng Lottery không có"


# --- Hợp nhất kho khi nhánh chính đã tiến lên ------------------------------
#
# Một lần backfill chạy 1,5 giờ; quy trình hàng ngày đẩy commit vài lần mỗi
# giờ. Đến lúc ghi thì `git push` bị từ chối — đã xảy ra thật và mất trọn một
# lần chạy đã lấy xong dữ liệu.


def _store(tmp_path, name, dates):
    import json
    p = tmp_path / name
    p.write_text(json.dumps([{"date": d, "special": 1} for d in dates]), encoding="utf-8")
    return p


def test_merge_keeps_records_from_both_sides(tmp_path) -> None:
    """Backfill thêm kỳ CŨ, quy trình hàng ngày thêm kỳ MỚI — hai tập gần như
    rời nhau, nên hợp nhất phải giữ cả hai."""
    from backfill_history import merge_stores

    mine = _store(tmp_path, "mine.json", ["2020-01-01", "2020-01-02"])
    theirs = _store(tmp_path, "theirs.json", ["2026-09-07", "2026-09-08"])
    out = tmp_path / "out.json"
    assert merge_stores(mine, theirs, out) == (2, 2, 4)


def test_merge_prefers_the_branch_copy_on_a_shared_date(tmp_path) -> None:
    """Kỳ trên nhánh chính đã qua kiểm đồng thuận hai nguồn; backfill chỉ đòi
    một nguồn."""
    import json
    from backfill_history import merge_stores

    mine = tmp_path / "mine.json"
    mine.write_text(json.dumps([{"date": "2026-01-01", "special": 111}]), encoding="utf-8")
    theirs = tmp_path / "theirs.json"
    theirs.write_text(json.dumps([{"date": "2026-01-01", "special": 999}]), encoding="utf-8")
    out = tmp_path / "out.json"
    merge_stores(mine, theirs, out)
    assert json.loads(out.read_text())[0]["special"] == 999


def test_merge_output_is_sorted_by_date(tmp_path) -> None:
    """Lottery.load và bộ máy JS đều giả định thứ tự tăng dần."""
    import json
    from backfill_history import merge_stores

    mine = _store(tmp_path, "mine.json", ["2020-05-05", "2020-01-01"])
    theirs = _store(tmp_path, "theirs.json", ["2026-09-08", "2020-03-03"])
    out = tmp_path / "out.json"
    merge_stores(mine, theirs, out)
    dates = [r["date"] for r in json.loads(out.read_text())]
    assert dates == sorted(dates)


def test_merge_tolerates_a_missing_branch_copy(tmp_path) -> None:
    from backfill_history import merge_stores

    mine = _store(tmp_path, "mine.json", ["2020-01-01"])
    out = tmp_path / "out.json"
    assert merge_stores(mine, tmp_path / "khong-ton-tai.json", out) == (1, 0, 1)


def test_merge_stores_is_defined_before_the_main_guard() -> None:
    """merge_stores từng bị đặt SAU khối `if __name__ == "__main__"`, nên
    main() chạy trước khi def được thực thi và ném NameError ngay trên runner.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "backfill_history.py").read_text(
        encoding="utf-8"
    )
    assert src.index("def merge_stores") < src.index('if __name__ == "__main__"')


def test_merge_store_flag_does_not_require_start() -> None:
    """--merge-store là chế độ riêng, không quét ngày nào."""
    import argparse
    import backfill_history as mod

    parser = argparse.ArgumentParser()
    # Đọc lại đúng cách khai báo trong main() thay vì đoán.
    src = mod.__file__
    with open(src, encoding="utf-8") as handle:
        text = handle.read()
    assert '"--start", required=False' in text, "--start phải là tuỳ chọn"
    assert "--merge-store" in text
    del parser
