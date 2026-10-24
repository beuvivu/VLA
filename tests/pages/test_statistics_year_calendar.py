"""Lịch năm giữ ngày thật, số gốc và trạng thái thiếu kết quả."""

import pandas as pd
from bs4 import BeautifulSoup

from pages import build_statistics_dashboard as dashboard


def _calendar(raw: pd.DataFrame) -> BeautifulSoup:
    assert hasattr(dashboard, "_board_year_table"), "Thiếu lịch Đặc Biệt theo năm"
    return BeautifulSoup(dashboard._board_year_table(raw), "html.parser")


def _history() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2023-02-28", "2024-02-29", "2024-01-01", "2024-01-01", "2026-01-01", "bad"],
        "special": ["00001", "04789", "11111", "00000", "", "99999"],
    })


def test_year_selector_comes_from_all_valid_history_years() -> None:
    page = _calendar(_history())
    assert [o["value"] for o in page.select("[data-app-year-select] option")] == ["2026", "2024", "2023"]
    assert page.select_one("[data-app-year-select] option[selected]")["value"] == "2026"
    assert len(page.select('[data-app-year="2024"] thead th')) == 13
    assert len(page.select('[data-app-year="2024"] tbody tr')) == 31


def test_year_calendar_distinguishes_leap_day_missing_and_impossible_dates() -> None:
    page = _calendar(_history())
    leap = page.select_one('[data-app-date="2024-02-29"]')
    assert leap.get_text() == "04789"
    assert leap["data-app-result"] == "04789"
    assert page.select_one('[data-app-date="2023-02-29"]') is None
    assert page.select_one('[data-app-year="2023"] [data-app-day="29"] td:nth-of-type(2)').get_text() == "Không có ngày"
    missing = page.select_one('[data-app-date="2024-02-28"]')
    assert missing.get_text() == "Chưa có KQ"
    assert "data-app-result" not in missing.attrs
    assert page.select_one('[data-app-date="2024-01-01"]').get_text() == "00000"


def test_year_with_dates_but_no_draw_stays_selectable_and_reports_zero() -> None:
    page = _calendar(_history())
    panel = page.select_one('[data-app-year="2026"]')
    assert panel["data-app-draw-count"] == "0"
    assert len(panel.select("[data-app-date]")) == 365
    assert "0 ngày có kết quả" in panel.get_text()


def test_empty_history_explains_why_no_year_is_selectable() -> None:
    page = _calendar(pd.DataFrame())
    assert page.select_one("select") is None
    assert "Chưa có lịch sử" in page.get_text()


def test_year_filter_has_accessible_status_and_sticky_scroll_region() -> None:
    page = _calendar(_history())
    search = page.select_one('input[type="search"]')
    assert search["aria-label"] == "Lọc số Đặc Biệt trong năm đã chọn"
    assert page.select_one('[data-app-year-status][role="status"]') is not None
    region = page.select_one(".app-year-scroll")
    assert region["tabindex"] == "0" and "cuộn ngang" in region["aria-label"]
    assert page.select("[title]") == []


def test_year_calendar_offers_all_months_and_a_readable_single_month_view() -> None:
    page = _calendar(_history())
    assert [o["value"] for o in page.select("[data-app-month-select] option")] == ["", *[f"{month:02d}" for month in range(1, 13)]]
    assert page.select_one('[data-app-year="2024"]')["data-app-latest-month"] == "02"
    assert len(page.select('[data-app-year="2024"] [data-app-month="02"]')) == 32
