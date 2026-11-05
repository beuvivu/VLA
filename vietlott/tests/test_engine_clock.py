"""Ngày của engine theo giờ Việt Nam (hay UTC của dữ liệu), không theo múi giờ của máy chạy (05-11-2026).

Runner GitHub chạy UTC, máy người dùng có thể ở bất kỳ đâu. Hai chỗ từng hỏi đồng hồ của máy:

* kho cộng đồng liệt kê tệp Keno/Bingo18 theo THÁNG tới «hôm nay»: 06:00–07:00 sáng ngày 1 giờ VN (kỳ
  đầu tháng đã quay) UTC còn ở tháng trước, nên tệp tháng mới bị bỏ sót;
* bản sao đôi khi ghi ngày bằng mili-giây epoch (nửa đêm UTC, như ``pandas.to_json``): đọc theo múi giờ
  máy thì phía tây Greenwich ra ngày hôm trước.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone

import pytest

from vietlott_engine.core.products import ProductCode
from vietlott_engine.crawler.schemas import MirrorRecord
from vietlott_engine.crawler.sources.nhanaz import NhanAZArchive


def test_monthly_archive_files_follow_the_vietnam_calendar(monkeypatch: pytest.MonkeyPatch) -> None:
    # 06:30 ngày 01-01-2025 giờ VN = 23:30 ngày 31-12-2024 UTC: kỳ Bingo18 đầu năm đã quay.
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
