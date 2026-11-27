from __future__ import annotations

from datetime import date

import pytest

from ingest.backfill_history import (
    EARLIEST_SUPPORTED,
    BackfillReport,
    backfill,
    date_range,
    missing_dates,
)


class FakeLottery:

    def __init__(self, have: set[date] | None = None, fail_on: set[date] | None = None,
                 raise_on: set[date] | None = None) -> None:
        self._have = set(have or ())
        self._fail_on = set(fail_on or ())
        self._raise_on = set(raise_on or ())
        self.dumps = 0
        self.fetch_calls: list[date] = []
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
        self._frame = set(self._have)

    def dump(self) -> None:
        self.dumps += 1
        self.persisted = set(self._frame)


def _run(lot, start, end, **kw):
    kw.setdefault("delay_range", (0.0, 0.0))
    kw.setdefault("sleeper", lambda _s: None)
    return backfill(lot, start, end, **kw)


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
    got = missing_dates(date_range(date(2026, 1, 1), date(2026, 1, 4)), set())
    assert got == sorted(got, reverse=True)


def test_rejects_a_reversed_range() -> None:
    with pytest.raises(ValueError, match="phải trước"):
        _run(FakeLottery(), date(2026, 1, 5), date(2026, 1, 1))


def test_rejects_a_start_before_archives_exist() -> None:
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


def test_fetches_only_the_missing_days() -> None:
    lot = FakeLottery(have={date(2026, 1, 2)})
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 3))
    assert rep.requested == 3
    assert rep.already_present == 1
    assert rep.fetched == 2
    assert date(2026, 1, 2) not in lot.fetch_calls


def test_a_fully_covered_range_makes_no_network_calls() -> None:
    have = set(date_range(date(2026, 1, 1), date(2026, 1, 5)))
    lot = FakeLottery(have=have)
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 5))
    assert lot.fetch_calls == []
    assert rep.fetched == 0
    assert rep.success_rate == 1.0, "không thử lần nào thì coi như thành công"


def test_writes_a_checkpoint_so_a_crash_does_not_lose_everything() -> None:
    lot = FakeLottery()
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 10), checkpoint_every=3)
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
    all_days = set(date_range(date(2026, 1, 1), date(2026, 2, 1)))
    lot = FakeLottery(fail_on=all_days)
    rep = _run(lot, date(2026, 1, 1), date(2026, 2, 1), max_failures=5)
    assert len(rep.failed) == 5
    assert len(lot.fetch_calls) == 5, "phải dừng, không thử hết dải"


def test_a_success_resets_the_consecutive_failure_counter() -> None:
    days = date_range(date(2026, 1, 1), date(2026, 1, 10))
    lot = FakeLottery(fail_on={days[1], days[3], days[5], days[7]})
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 10), max_failures=3)
    assert len(lot.fetch_calls) == 10, "không được dừng sớm"
    assert rep.fetched == 6


def test_waits_between_requests() -> None:
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


def test_persists_the_days_it_fetched_not_a_stale_snapshot() -> None:
    lot = FakeLottery()
    days = {date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)}
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 3))

    assert rep.fetched == 3
    assert lot.persisted == days, (
        "kỳ đã lấy không có trong dữ liệu ghi ra — dump đã ghi đè bằng ảnh "
        "chụp cũ"
    )


def test_every_checkpoint_persists_what_was_fetched_so_far() -> None:
    lot = FakeLottery()
    rep = _run(lot, date(2026, 1, 1), date(2026, 1, 10), checkpoint_every=3)

    assert rep.checkpoints >= 3
    assert len(lot.persisted) == 10


def test_backfill_never_dumps_without_rebuilding_the_frames() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2] / "src" / "ingest" / "backfill_history.py"
    ).read_text(encoding="utf-8")

    body = src[src.index("def _persist(") :]
    persist_body = body[: body.index("\ndef ", 1)]
    assert "generate_dataframes()" in persist_body
    assert persist_body.index("generate_dataframes()") < persist_body.index("dump()")

    outside = src.replace(persist_body, "")
    assert "lottery.dump()" not in outside, (
        "còn lời gọi dump() không đi qua _persist — kỳ vừa lấy sẽ bị ghi đè"
    )


def test_repeated_draw_dates_finds_the_non_draw_days() -> None:
    from ingest.backfill_history import repeated_draw_dates

    records = [
        {"date": "2026-02-14", "special": 90630, "prize1": 11111},
        {"date": "2026-02-15", "special": 22601, "prize1": 22222},
        {"date": "2026-02-16", "special": 22601, "prize1": 22222},
        {"date": "2026-02-17", "special": 22601, "prize1": 22222},
        {"date": "2026-02-18", "special": 33333, "prize1": 44444},
    ]
    assert repeated_draw_dates(records) == ["2026-02-16", "2026-02-17"], (
        "phải giữ bản ghi ĐẦU cụm — đó là kỳ thật cuối trước khi tạm ngừng"
    )


def test_repeated_draw_dates_spans_a_hole_in_the_history() -> None:
    from ingest.backfill_history import repeated_draw_dates

    records = [
        {"date": "2026-02-15", "special": 22601},
        {"date": "2026-02-17", "special": 22601},
        {"date": "2026-02-19", "special": 22601},
        {"date": "2026-02-20", "special": 77777},
    ]
    assert repeated_draw_dates(records) == ["2026-02-17", "2026-02-19"]


def test_repeated_draw_dates_ignores_a_single_matching_field() -> None:
    from ingest.backfill_history import repeated_draw_dates

    records = [
        {"date": "2026-01-01", "special": 12345, "prize1": 11111},
        {"date": "2026-01-02", "special": 12345, "prize1": 99999},
    ]
    assert repeated_draw_dates(records) == []


def test_repeated_draw_dates_is_order_independent() -> None:
    from ingest.backfill_history import repeated_draw_dates

    rows = [
        {"date": "2026-02-17", "special": 22601},
        {"date": "2026-02-15", "special": 22601},
        {"date": "2026-02-16", "special": 22601},
    ]
    assert repeated_draw_dates(rows) == ["2026-02-16", "2026-02-17"]


def test_fake_lottery_matches_the_real_api() -> None:
    import inspect

    from ingest.lottery import Lottery

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
    import re
    from pathlib import Path

    from ingest.lottery import Lottery

    src = Path(__file__).resolve().parents[2] / "src" / "ingest" / "backfill_history.py"
    used = set(re.findall(r"\blottery\.(\w+)\(", src.read_text(encoding="utf-8")))
    assert used, "không tìm thấy lời gọi nào tới lottery"
    for name in used:
        assert hasattr(Lottery, name), f"backfill gọi lottery.{name}() nhưng Lottery không có"


def _store(tmp_path, name, dates):
    import json
    p = tmp_path / name
    p.write_text(json.dumps([{"date": d, "special": 1} for d in dates]), encoding="utf-8")
    return p


def test_merge_keeps_records_from_both_sides(tmp_path) -> None:
    from ingest.backfill_history import merge_stores

    mine = _store(tmp_path, "mine.json", ["2020-01-01", "2020-01-02"])
    theirs = _store(tmp_path, "theirs.json", ["2026-09-07", "2026-09-08"])
    out = tmp_path / "out.json"
    assert merge_stores(mine, theirs, out) == (2, 2, 4)


def test_merge_prefers_the_branch_copy_on_a_shared_date(tmp_path) -> None:
    import json
    from ingest.backfill_history import merge_stores

    mine = tmp_path / "mine.json"
    mine.write_text(json.dumps([{"date": "2026-01-01", "special": 111}]), encoding="utf-8")
    theirs = tmp_path / "theirs.json"
    theirs.write_text(json.dumps([{"date": "2026-01-01", "special": 999}]), encoding="utf-8")
    out = tmp_path / "out.json"
    merge_stores(mine, theirs, out)
    assert json.loads(out.read_text())[0]["special"] == 999


def test_merge_output_is_sorted_by_date(tmp_path) -> None:
    import json
    from ingest.backfill_history import merge_stores

    mine = _store(tmp_path, "mine.json", ["2020-05-05", "2020-01-01"])
    theirs = _store(tmp_path, "theirs.json", ["2026-09-08", "2020-03-03"])
    out = tmp_path / "out.json"
    merge_stores(mine, theirs, out)
    dates = [r["date"] for r in json.loads(out.read_text())]
    assert dates == sorted(dates)


def test_merge_tolerates_a_missing_branch_copy(tmp_path) -> None:
    from ingest.backfill_history import merge_stores

    mine = _store(tmp_path, "mine.json", ["2020-01-01"])
    out = tmp_path / "out.json"
    assert merge_stores(mine, tmp_path / "khong-ton-tai.json", out) == (1, 0, 1)


def test_merge_stores_is_defined_before_the_main_guard() -> None:
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "src" / "ingest" / "backfill_history.py").read_text(
        encoding="utf-8"
    )
    assert src.index("def merge_stores") < src.index('if __name__ == "__main__"')


def test_merge_store_flag_does_not_require_start() -> None:
    import argparse
    from ingest import backfill_history as mod

    parser = argparse.ArgumentParser()
    src = mod.__file__
    with open(src, encoding="utf-8") as handle:
        text = handle.read()
    assert '"--start", required=False' in text, "--start phải là tuỳ chọn"
    assert "--merge-store" in text
    del parser
