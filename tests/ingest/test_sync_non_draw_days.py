from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ingest import sync
from core.dtos import Result
from ingest.lottery import Lottery, RepoPaths
from core.time_policy import VIETNAM_TIMEZONE


def _result(d: date, *, special: int) -> Result:
    fields = {
        "special": special, "prize1": 12345, "prize2_1": 11111, "prize2_2": 22222,
        **{f"prize3_{i}": 30000 + i for i in range(1, 7)},
        **{f"prize4_{i}": 4000 + i for i in range(1, 5)},
        **{f"prize5_{i}": 5000 + i for i in range(1, 7)},
        **{f"prize6_{i}": 600 + i for i in range(1, 4)},
        **{f"prize7_{i}": 70 + i for i in range(1, 5)},
    }
    return Result(date=d, **fields)


@dataclass
class CountingSource:

    answers: dict[date, Result]
    calls: list[date] = field(default_factory=list)
    name: str = "fake"

    def fetch(self, selected_date: date, http: object) -> Result | None:
        self.calls.append(selected_date)
        return self.answers.get(selected_date)


def _target() -> date:
    now = datetime.now(ZoneInfo(VIETNAM_TIMEZONE))
    return sync.latest_complete_draw_date(now=now)


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(sync.time, "sleep", sleeps.append)
    target = _target()
    gap_known, gap_fresh, gap_real = (target - timedelta(days=k) for k in (5, 6, 8))
    source = CountingSource(answers={})
    paths = RepoPaths(root=tmp_path, data_dir=tmp_path / "data", images_dir=tmp_path / "images")
    lot = Lottery(paths=paths, http=object(), sources=[source])  # type: ignore[arg-type]
    for k in range(10):
        day = target - timedelta(days=k)
        if day not in (gap_known, gap_fresh, gap_real):
            lot._data[day] = _result(day, special=10000 + k)  # type: ignore[attr-defined]
    lot.generate_dataframes()
    monkeypatch.setattr(lot, "dump", lambda: None)
    before = gap_fresh - timedelta(days=1)
    source.answers[gap_fresh] = _result(gap_fresh, special=lot._data[before].special)  # type: ignore[attr-defined]
    return lot, source, sleeps, (gap_known, gap_fresh, gap_real)


def _run(lot: Lottery, known: set[str]) -> None:
    sync.ensure_up_to_date(
        lottery=lot, fill_missing_days_back=9, polite_sleep_s=0.0,
        max_retries=3, retry_backoff_s=0.8, non_draw_days=known,
    )


def test_a_day_in_the_non_draw_ledger_is_never_requested(setup) -> None:
    lot, source, _, (gap_known, gap_fresh, gap_real) = setup
    _run(lot, {gap_known.isoformat()})
    assert gap_known not in source.calls
    assert {gap_fresh, gap_real} <= set(source.calls)


def test_a_day_found_to_be_non_draw_is_not_retried(setup, caplog) -> None:
    lot, source, _, (_, gap_fresh, _) = setup
    with caplog.at_level("WARNING"):
        _run(lot, set())
    assert source.calls.count(gap_fresh) == 1
    assert lot.is_no_draw(gap_fresh) and not lot.has_date(gap_fresh)
    notes = [r.getMessage() for r in caplog.records if gap_fresh.isoformat() in r.getMessage()]
    assert any("non_draw_days.json" in n for n in notes)
    assert not any("will retry" in n for n in notes)


def test_an_ordinary_miss_is_still_retried(setup) -> None:
    lot, source, sleeps, (gap_known, gap_fresh, gap_real) = setup
    _run(lot, {gap_known.isoformat()})
    assert source.calls.count(gap_real) == 3
    assert [s for s in sleeps if s] == pytest.approx([0.8, 1.6, 2.4])
    assert not lot.is_no_draw(gap_real)


def test_by_default_the_shipped_ledger_is_used() -> None:
    from core.calendar_alignment import known_non_draw_days

    assert {"2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19"} <= known_non_draw_days()


def test_by_default_ensure_up_to_date_skips_the_shipped_ledger(setup, monkeypatch) -> None:
    lot, source, _, (gap_known, _, _) = setup
    monkeypatch.setattr(sync, "known_non_draw_days", lambda: frozenset({gap_known.isoformat()}))
    sync.ensure_up_to_date(lottery=lot, fill_missing_days_back=9, polite_sleep_s=0.0)
    assert gap_known not in source.calls


def test_a_twin_inside_the_recent_window_is_still_retried(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync.time, "sleep", lambda s: None)
    target = _target()
    paths = RepoPaths(root=tmp_path, data_dir=tmp_path / "data", images_dir=tmp_path / "images")
    first, second = CountingSource(answers={}, name="a"), CountingSource(answers={}, name="b")
    lot = Lottery(paths=paths, http=object(), sources=[first, second])  # type: ignore[arg-type]
    for k in range(1, 10):
        day = target - timedelta(days=k)
        lot._data[day] = _result(day, special=10000 + k)  # type: ignore[attr-defined]
    lot.generate_dataframes()
    monkeypatch.setattr(lot, "dump", lambda: None)
    stale = _result(target, special=lot._data[target - timedelta(days=1)].special)  # type: ignore[attr-defined]
    first.answers[target] = second.answers[target] = stale

    sync.ensure_up_to_date(
        lottery=lot, fill_missing_days_back=9, polite_sleep_s=0.0,
        max_retries=3, retry_backoff_s=0.8, non_draw_days=set(),
    )
    assert lot.is_no_draw(target), "điều kiện tiền đề: trùng khít đã được nhận ra"
    assert first.calls.count(target) == 3
