from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

WEEKDAY_NAMES: Final[tuple[str, ...]] = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


@dataclass(frozen=True)
class ScheduleEra:

    start: date
    venues: tuple[str, ...]
    basis: str

    def __post_init__(self) -> None:
        if len(self.venues) != 7 or not all(isinstance(v, str) and v for v in self.venues):
            raise ValueError("một thời kỳ phải khai đủ 7 đài, từ thứ Hai tới Chủ Nhật")


ERAS: Final[tuple[ScheduleEra, ...]] = (
    ScheduleEra(
        start=date(2005, 9, 1),
        venues=("Hà Nội", "Quảng Ninh", "Bắc Ninh", "Hà Nội", "Hải Phòng", "Nam Định", "Thái Bình"),
        basis="Quay chung từ 01-09-2005 (Quyết định 2564/QĐ-BTC); lịch luân phiên đang ghi nhận.",
    ),
)


def _validate(eras: tuple[ScheduleEra, ...]) -> None:
    starts = [era.start for era in eras]
    if not eras or starts != sorted(starts) or len(set(starts)) != len(starts):
        raise ValueError("các thời kỳ phải có ngày bắt đầu tăng dần và không trùng")


_validate(ERAS)


def _as_date(value: date | str) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def era_for(value: date | str, eras: tuple[ScheduleEra, ...] = ERAS) -> ScheduleEra | None:
    day = _as_date(value)
    if day is None:
        return None
    current = None
    for era in eras:
        if era.start <= day:
            current = era
    return current


def venue_for(value: date | str, eras: tuple[ScheduleEra, ...] = ERAS) -> str:
    day = _as_date(value)
    era = era_for(day, eras) if day is not None else None
    return era.venues[day.weekday()] if era is not None and day is not None else ""


def venues_of(eras: tuple[ScheduleEra, ...] = ERAS) -> tuple[str, ...]:
    seen: list[str] = []
    for era in eras:
        for venue in era.venues:
            if venue not in seen:
                seen.append(venue)
    return tuple(seen)
