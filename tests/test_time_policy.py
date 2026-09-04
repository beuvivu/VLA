from __future__ import annotations

from datetime import UTC, datetime

import pytest

from time_policy import (
    DEFAULT_DRAW_CUTOFF,
    iso_local,
    iso_utc,
    latest_complete_draw_date,
    utc_cron_for_vietnam,
    vietnam_date,
)


def test_vietnam_clock_is_the_single_cron_and_date_authority() -> None:
    assert utc_cron_for_vietnam(18, 0) == "0 11 * * *"
    assert utc_cron_for_vietnam(18, 35) == "35 11 * * *"
    assert utc_cron_for_vietnam(7, 15) == "15 0 * * *"
    utc = datetime(2026, 9, 3, 17, 0, tzinfo=UTC)
    assert vietnam_date(utc).isoformat() == "2026-09-04"


def test_latest_completed_draw_respects_utc7_cutoff() -> None:
    before = datetime(2026, 9, 3, 11, 34, 59, tzinfo=UTC)
    at_cutoff = datetime(2026, 9, 3, 11, 35, tzinfo=UTC)
    assert latest_complete_draw_date(now=before) == datetime(2026, 9, 2).date()
    assert latest_complete_draw_date(now=at_cutoff) == datetime(2026, 9, 3).date()
    assert DEFAULT_DRAW_CUTOFF.hour == 18 and DEFAULT_DRAW_CUTOFF.minute == 35


def test_timestamp_rendering_is_explicit_and_stable() -> None:
    instant = datetime(2026, 9, 3, 11, 0, tzinfo=UTC)
    assert iso_local(instant) == "2026-09-03T18:00:00+07:00"
    assert iso_utc(instant) == "2026-09-03T11:00:00Z"


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError):
        vietnam_date(datetime(2026, 9, 3, 11, 0))
