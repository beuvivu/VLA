"""Lịch Đặc Biệt phải dùng kết quả gốc và giữ nguyên năm chữ số."""

from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

import build_statistics_dashboard as dashboard


def test_dashboard_calendar_reads_full_prizes_instead_of_statistical_tails(
    tmp_path: Path, monkeypatch,
) -> None:
    """Hai nguồn khác nhau phải hiện kết quả thật, kể cả giá trị 00001."""
    advanced = tmp_path / "data" / "advanced"
    advanced.mkdir(parents=True)
    (tmp_path / "data" / "xsmb.csv").write_text(
        "date,special\n2025-12-29,1\n2026-01-01,04789\n", encoding="utf-8",
    )
    (advanced / "special_week_board.csv").write_text(
        "week_key,T2,T3,T4,T5,T6,T7,CN\n2026-W01,01,,,89,,,\n", encoding="utf-8",
    )
    (advanced / "special_month_board.csv").write_text(
        "month_key,01,29\n2025-12,,01\n2026-01,89,\n", encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    dashboard.main()
    page = BeautifulSoup((tmp_path / "docs" / "statistics.html").read_text(), "html.parser")
    tables = page.select("#bang-db .table-card table")
    week, month = tables[:2]
    assert [cell.get_text() for cell in week.select('td[data-col="T2"]')] == ["00001"]
    assert [cell.get_text() for cell in week.select('td[data-col="T5"]')] == ["04789"]
    assert [cell.get_text() for cell in week.select('td[data-col="T3"]')] == [""]
    assert [cell.get_text() for cell in month.select('td[data-col="01"]')] == ["", "04789"]
    assert [cell.get_text() for cell in month.select('td[data-col="29"]')] == ["00001", ""]
    assert (advanced / "special_week_board.csv").read_text().splitlines()[1].startswith("2026-W01,01,")


def test_result_calendar_formatting_preserves_five_digits_and_empty_days() -> None:
    """Số nhỏ vẫn đủ năm chữ số; không biến ô trống thành kết quả 00000."""
    week = BeautifulSoup(dashboard._board_week_table(pd.DataFrame({
        "week_key": ["2026-W01"], "T2": ["00001"], "T3": ["00000"],
        "T4": [""], "T5": ["04789"], "T6": [""], "T7": [""], "CN": ["12345"],
    })), "html.parser")
    assert [cell.get_text() for cell in week.select("tbody td")][1:] == [
        "00001", "00000", "", "04789", "", "", "12345",
    ]
    month = BeautifulSoup(dashboard._board_month_table(pd.DataFrame({
        "month_key": ["2026-02"], "01": ["00001"], "28": ["99999"], "29": [""],
    })), "html.parser")
    assert month.select_one('td[data-col="01"]').get_text() == "00001"
    assert month.select_one('td[data-col="29"]').get_text() == ""


def test_full_result_boards_use_iso_weeks_and_calendar_days() -> None:
    """Đổi năm ISO, tháng nhuận và hàng lỗi không được làm lệch ngày kết quả."""
    week, month = dashboard._full_special_boards(pd.DataFrame({
        "date": ["2026-01-01", "2025-12-29", "2024-02-29", "bad", "2026-01-02", "2026-01-03"],
        "special": ["04789", "1", "00000", "12345", "", "broken"],
    }))
    assert list(week.columns) == ["week_key", *dashboard.WEEKDAY_COLS]
    assert list(month.columns) == ["month_key", *[f"{day:02d}" for day in range(1, 32)]]
    latest = week.set_index("week_key").loc["2026-W01"]
    assert latest["T2"] == "00001" and latest["T5"] == "04789"
    assert latest["T6"] == "" and latest["T7"] == ""
    assert month.set_index("month_key").loc["2024-02", "29"] == "00000"
    assert len(week) == 2 and len(month) == 3
