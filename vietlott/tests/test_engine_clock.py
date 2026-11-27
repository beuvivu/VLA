from __future__ import annotations

import time
from datetime import date, datetime, timezone

import pytest

from vietlott_engine.core.products import ProductCode
from vietlott_engine.crawler.schemas import MirrorRecord
from vietlott_engine.crawler.sources.nhanaz import NhanAZArchive


def test_monthly_archive_files_follow_the_vietnam_calendar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VQE_FORECAST_NOW", "2025-01-01T06:30:00+07:00")
    archive = NhanAZArchive(base_url="https://archive.example")
    assert archive._months(ProductCode.BINGO18, date(2024, 12, 15)) == ["2024-12", "2025-01"]


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="cần đổi múi giờ của tiến trình (Unix)")
def test_an_epoch_date_from_the_mirror_is_read_in_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    millis = int(datetime(2026, 11, 4, tzinfo=timezone.utc).timestamp() * 1000)
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        row = MirrorRecord.model_validate({"date": millis, "id": 944, "result": [1, 2, 3, 4, 5, 6]})
        assert row.date == date(2026, 11, 4)
        assert MirrorRecord.model_validate({"date": str(millis), "id": 944, "result": [1, 2, 3, 4, 5, 6]}).date == date(2026, 11, 4)
    finally:
        monkeypatch.undo()
        time.tzset()
