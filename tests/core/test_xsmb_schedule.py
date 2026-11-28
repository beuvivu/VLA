from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from core import xsmb_schedule
from core.xsmb_schedule import ERAS, ScheduleEra, era_for, venue_for, venues_of

ROOT = Path(__file__).resolve().parents[2]


def test_the_current_rotation_matches_the_published_weekly_schedule() -> None:
    week = [venue_for(f"2026-09-{day}") for day in range(21, 28)]
    assert week == ["Hà Nội", "Quảng Ninh", "Bắc Ninh", "Hà Nội", "Hải Phòng", "Nam Định", "Thái Bình"]
    assert venue_for("2015-01-01") == "Hà Nội"


def test_a_new_era_relabels_only_the_draws_on_and_after_its_start() -> None:
    renamed = ScheduleEra(
        start=date(2027, 1, 2),
        venues=("Hà Nội", "Quảng Ninh", "Bắc Ninh", "Hà Nội", "Hải Phòng", "Ninh Bình", "Hưng Yên"),
        basis="giả định cho phép kiểm",
    )
    eras = (*ERAS, renamed)
    assert venue_for("2026-12-26", eras) == "Nam Định"
    assert venue_for("2027-01-02", eras) == "Ninh Bình"
    assert era_for("2027-01-02", eras) is renamed
    assert venues_of(eras)[-2:] == ("Ninh Bình", "Hưng Yên")


def test_unknown_or_too_early_dates_have_no_venue() -> None:
    assert venue_for("không phải ngày") == ""
    assert venue_for("2005-08-31") == ""
    assert era_for(date(2005, 8, 31)) is None


def test_eras_must_be_complete_and_ordered() -> None:
    with pytest.raises(ValueError):
        ScheduleEra(start=date(2027, 1, 1), venues=("Hà Nội",) * 6, basis="thiếu một ngày")
    later = ScheduleEra(start=date(2027, 1, 1), venues=ERAS[0].venues, basis="sau")
    with pytest.raises(ValueError):
        xsmb_schedule._validate((later, ERAS[0]))
    with pytest.raises(ValueError):
        xsmb_schedule._validate((ERAS[0], ERAS[0]))


def test_no_module_keeps_its_own_copy_of_the_rotation() -> None:
    pattern = re.compile(r"Quảng Ninh.{0,40}Bắc Ninh.{0,60}Hải Phòng")
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src").rglob("*.py")
        if path != ROOT / "src" / "core" / "xsmb_schedule.py" and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_the_copy_rule_itself_catches_a_copy(tmp_path: Path) -> None:
    sample = 'STATIONS = ("Hà Nội", "Quảng Ninh", "Bắc Ninh", "Hà Nội", "Hải Phòng", "Nam Định", "Thái Bình")'
    assert re.search(r"Quảng Ninh.{0,40}Bắc Ninh.{0,60}Hải Phòng", sample)
