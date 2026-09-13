from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from monitor_health import expected_latest_draw_date


def test_expected_latest_draw_is_yesterday_before_cutoff() -> None:
    now = datetime(2026, 8, 31, 5, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    assert expected_latest_draw_date(now=now, cutoff=dtime(18, 35)).isoformat() == "2026-08-30"


def test_expected_latest_draw_is_today_after_cutoff() -> None:
    now = datetime(2026, 8, 31, 18, 40, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    assert expected_latest_draw_date(now=now, cutoff=dtime(18, 35)).isoformat() == "2026-08-31"
