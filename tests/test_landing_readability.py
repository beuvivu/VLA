"""Hợp đồng đọc số liệu của trang chủ theo yêu cầu ngày 26-09-2026."""

from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from build_landing_page import _render_group_bars, _render_html, _render_pair_frequency, _render_table


ROOT = Path(__file__).resolve().parents[1]


def test_calendar_immediately_follows_daily_matrix_then_predictions() -> None:
    soup = BeautifulSoup(_render_html(ROOT, generated_at="2026-09-26"), "html.parser")
    matrix = soup.find(id="ma-tran-ngay")
    assert matrix.find_next_sibling("section").get("id") == "db-tuan-thang"
    assert soup.find(id="db-tuan-thang").find_next_sibling("section").get("id") == "ai-ml"


def test_pair_frequency_headers_share_numeric_columns_with_data(tmp_path: Path) -> None:
    pairs = tmp_path / "data/pairs"
    pairs.mkdir(parents=True)
    pd.DataFrame([{"pair": "12-68", "count": 293}]).to_csv(
        pairs / "top_unordered_pairs_top300.csv", index=False
    )
    pd.DataFrame({"date": ["2026-09-26"]}).to_csv(tmp_path / "data/xsmb.csv", index=False)
    soup = BeautifulSoup(_render_pair_frequency(tmp_path), "html.parser")
    table = soup.find("table")
    assert "pair-frequency-table" in table.get("class", [])
    assert len(table.select("colgroup col")) == 4
    for header, cell in zip(table.select("thead th"), table.select("tbody tr:first-child td"), strict=True):
        assert header.get("scope") == "col"
        assert header.get("class") == cell.get("class")
    assert all("numeric" in th.get("class", []) for th in table.select("thead th")[1:])


def test_table_rounds_display_precision_without_mutating_statistics() -> None:
    frame = pd.DataFrame([{"pair": "46-64", "avg_per_draw": 24 / 26, "mean_gap": 5 / 3,
                           "val_brier": 0.0123456789, "val_logloss": 0.987654321}])
    original = frame.copy(deep=True)
    soup = BeautifulSoup(_render_table(title="Chi tiết", subtitle="", df=frame,
                                      columns=list(frame.columns)), "html.parser")
    assert soup.select_one("td.col-avg_per_draw").get_text() == "0.92"
    assert soup.select_one("td.col-mean_gap").get_text() == "1.67"
    assert soup.select_one("td.col-val_brier").get_text() == "0.0123"
    assert soup.select_one("td.col-val_logloss").get_text() == "0.988"
    pd.testing.assert_frame_equal(frame, original)


def test_group_charts_show_every_digit_exact_counts_shares_and_coverage(tmp_path: Path) -> None:
    advanced = tmp_path / "data/advanced"
    advanced.mkdir(parents=True)
    rows = []
    for group, values in {"head": {0: 1, 1: 3}, "tail": {7: 4}, "total": {7: 1, 8: 3}}.items():
        rows.extend({"period_kind": "month", "period_key": "2026-09", "group_type": group,
                     "group_value": digit, "freq": freq} for digit, freq in values.items())
    pd.DataFrame(rows).to_csv(advanced / "head_tail_total_loto_current.csv", index=False)
    pd.DataFrame({"date": ["2026-08-31", "2026-09-02", "2026-09-26"]}).to_csv(
        tmp_path / "data/xsmb.csv", index=False
    )
    soup = BeautifulSoup(_render_group_bars(tmp_path, "month"), "html.parser")
    assert "Tháng 09/2026" in soup.get_text(" ", strip=True)
    assert "02/09/2026–26/09/2026" in soup.get_text(" ", strip=True)
    assert "2 kỳ quay có dữ liệu" in soup.get_text(" ", strip=True)
    assert "6 + 8 = 14" in soup.get_text(" ", strip=True)
    cards = soup.select(".group-chart")
    assert len(cards) == 3
    for card in cards:
        bars = card.select(".group-bar-row")
        assert [row["data-group-value"] for row in bars] == [str(i) for i in range(10)]
        assert sum(int(row["data-frequency"]) for row in bars) == 4
        assert all("lượt" in row.get_text() and "%" in row.get_text() for row in bars)
        zero_rows = [row for row in bars if row["data-frequency"] == "0"]
        assert zero_rows
        assert all("width:0.0%" in row.select_one(".bar-fill")["style"] for row in zero_rows)
    assert "25.0%" in cards[0].get_text()
    assert "75.0%" in cards[0].get_text()


def test_path_tables_have_one_outer_card_and_inset_contents() -> None:
    soup = BeautifulSoup(_render_html(ROOT, generated_at="2026-09-26"), "html.parser")
    sections = soup.select(".basis-merged > section")
    assert len(sections) == 2
    for section in sections:
        assert section.select_one(".table-card") is not None
        assert section.select(".card") == []
        assert len(section.select(".table-wrap")) == 1
        assert len(section.select("thead th")) == 9
