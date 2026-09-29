"""Bảy kiểu cầu vị trí: đếm đúng từng ô như trang tham chiếu thứ hai, luật từng
kiểu đúng trên dữ liệu dựng sẵn, và trang xuất bản mang đủ dữ liệu cho bộ máy JS.

Số đối chiếu nằm trong ``tests/fixtures/bridge_reference_2026-09-28.json`` — đọc
từ trang ấy (dữ liệu đến 28-09-2026) qua workflow ``inspect-reference-bridge.yml``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from bs4 import BeautifulSoup

import bridge_rules as br
import build_bridge_pages as pages
from position_bridges import COLUMNS

ROOT = Path(__file__).resolve().parents[1]
REF = json.loads((ROOT / "tests" / "fixtures" / "bridge_reference_2026-09-28.json").read_text(encoding="utf-8"))
SUNDAY = 6


@pytest.fixture(scope="module")
def history():
    raw = pd.read_csv(ROOT / "data" / "xsmb.csv", dtype={"date": str})
    dates, digits, values = br.load_draws(raw[raw["date"] <= REF["source_date"]])
    assert dates[-1] == REF["source_date"]
    return dates, digits, values


@pytest.mark.parametrize(("page", "kind", "count", "weekday"), [
    ("loto", "loto", 3, None),
    ("hai-nhay", "hai-nhay", 2, None),
    ("bach-thu", "bach-thu", 3, None),
    ("dac-biet", "dac-biet", 2, None),
    ("bo-so", "bo-so", 2, None),
    ("dac-biet-theo-thu-chu-nhat", "dac-biet", 3, SUNDAY),
    ("loto-theo-thu-tat-ca", "loto", 3, None),
])
def test_every_cell_matches_the_reference_page(history, page, kind, count, weekday) -> None:
    """Từng ô của bảng đầu 0–9, tổng số cầu và cầu dài nhất — không xấp xỉ."""
    dates, digits, values = br.weekday_subset(*history, weekday)
    found = br.find(kind, digits, values, count=count)
    tally = br.tally(found["bridges"], kind)
    expected = REF["pages"][page]
    assert tally["counts"] == expected["counts"]
    assert tally["total"] == expected["total"]
    assert found["longest"] == expected["longest"]


def test_special_prize_pairs_rank_like_the_reference(history) -> None:
    found = br.find("dac-biet", history[1], history[2], count=2)
    groups = [[g["key"], g["bridges"]] for g in br.tally(found["bridges"], "dac-biet")["groups"]]
    assert groups[:13] == REF["dac_biet_pairs_top"]


def test_the_set_bridges_are_exactly_the_32_decoded_position_pairs(history) -> None:
    """Các cặp vị trí này dựng lại từ lớp đánh dấu chữ số của trang tham chiếu —
    chúng ghim chính LUẬT bộ số chứ không chỉ con số tổng."""
    found = br.find("bo-so", history[1], history[2], count=2)
    assert sorted(b["vt"] for b in found["bridges"]) == sorted(REF["bo_so_positions"])


def test_a_set_is_both_digits_and_their_shadows_both_ways() -> None:
    assert br.bo_members(3) == ["03", "08", "30", "35", "53", "58", "80", "85"]
    assert br.bo_members(0) == ["00", "05", "50", "55"]
    assert br.BO_ID[85] == br.BO_ID[30] == 3


def _draws(rows: list[dict[int, int]]) -> tuple[np.ndarray, np.ndarray]:
    """Các kỳ dựng sẵn: ĐB = 99999, mọi giải khác 0, trừ chỉ số được đặt."""
    values = np.zeros((len(rows), 27), dtype=np.int64)
    values[:, 0] = 99999
    for t, row in enumerate(rows):
        for index, value in row.items():
            values[t, index] = value
    frame = pd.DataFrame(values, columns=COLUMNS)
    frame.insert(0, "date", [f"2026-01-{i + 1:02d}" for i in range(len(rows))])
    _, digits, values = br.load_draws(frame)
    return digits, values


def _step(kind: str, rows: list[dict[int, int]], **kw) -> bool:
    """Cặp vị trí 5×6 (hai chữ số đầu của G1) qua một bước."""
    digits, values = _draws(rows)
    pa, pb = br.pair_index(True)
    p = int(np.flatnonzero((pa == 5) & (pb == 6))[0])
    return bool(br.step_matrix(kind, digits, values, **kw)[0, p])


@pytest.mark.parametrize(("kind", "next_draw", "expected"), [
    ("loto", {23: 54}, True),            # chỉ số lộn về vẫn là trúng
    ("bach-thu", {23: 54}, False),       # bạch thủ không tính số lộn
    ("bach-thu", {23: 45}, True),
    ("hai-nhay", {23: 45, 24: 45}, True),   # 45 về hai nháy
    ("hai-nhay", {23: 45, 24: 54}, True),   # cả hai chiều cùng về
    ("hai-nhay", {23: 54, 24: 54}, False),  # số lộn về hai nháy KHÔNG tính (đúng như trang tham chiếu)
    ("hai-nhay", {23: 45}, False),
])
def test_each_loto_kind_has_its_own_hit_rule(kind, next_draw, expected) -> None:
    assert _step(kind, [{1: 45000}, next_draw]) is expected


@pytest.mark.parametrize(("special", "both", "expected"), [
    (12340, False, True),    # hàng chục ĐB = 4
    (12305, False, True),    # hàng đơn vị ĐB = 5
    (12367, False, False),
    (12354, True, True),     # cả hai chữ số, lộn
    (12345, True, True),
    (12340, True, False),    # một chữ số không đủ khi đòi cả hai
])
def test_the_special_prize_rule_reads_only_its_last_two_digits(special, both, expected) -> None:
    rows = [{1: 45000}, {0: special, 23: 45, 24: 54}]
    assert _step("dac-biet", rows, both=both) is expected


def test_a_set_bridge_runs_while_the_number_stays_in_its_set() -> None:
    assert _step("bo-so", [{1: 45000}, {1: 90000}]) is True     # 45 → 90: cùng bộ 04
    assert _step("bo-so", [{1: 45000}, {1: 46000}]) is False
    digits, values = _draws([{1: 45000}, {0: 12390}])
    pa, pb = br.pair_index(True)
    p = int(np.flatnonzero((pa == 5) & (pb == 6))[0])
    assert br.outcome_matrix("bo-so", digits, values)[0, p], "ĐB 90 rơi vào bộ của 45"


def test_weekday_pages_only_use_draws_of_that_weekday(history) -> None:
    dates, _, _ = br.weekday_subset(*history, SUNDAY)
    assert dates and all(pd.Timestamp(d).weekday() == SUNDAY for d in dates)
    assert dates[-1] == "2026-09-27"


def test_the_backtest_can_see_a_planted_signal() -> None:
    """Chép y nguyên kỳ trước ở 50% số kỳ: cầu vừa trúng dễ trúng tiếp thật."""
    rng = np.random.default_rng(3)
    values = np.column_stack([rng.integers(0, 10 ** w, size=300) for w in br.WIDTHS])
    copy = np.random.default_rng(4).random(300) < 0.5
    for t in range(1, 300):
        if copy[t]:
            values[t] = values[t - 1]
    frame = pd.DataFrame(values, columns=COLUMNS)
    frame.insert(0, "date", pd.date_range("2020-01-01", periods=300).strftime("%Y-%m-%d"))
    _, digits, values = br.load_draws(frame)
    rows = br.backtest("bach-thu", [(digits, values)])["rows"]
    assert rows[3]["rate"] > rows[3]["expected"] + 0.05 and rows[3]["z"] > 4


def _report(history) -> dict:
    dates, digits, values = history
    stub = {"base_rate": 0.4, "rate_kep": 0.2, "rate_pair": 0.4, "draws": 4217,
            "rows": [{"k": k, "plus": k == 10, "n": 1000, "hits": 400, "rate": 0.4, "expected": 0.4,
                      "z": 0.0, "days": 9} for k in range(11)]}
    report = {"source_date": dates[-1], "target_date": "2026-09-29", "window": br.WINDOW,
              "draws": ["".join([d, *(str(int(v)).zfill(w) for v, w in zip(row, br.WIDTHS, strict=True))])
                        for d, row in zip(dates[-br.EMBED:], values[-br.EMBED:], strict=True)],
              "rules": {}}
    for key, cfg in br.RULES.items():
        weekday = 1 if cfg["weekday"] else None
        _, dg, vl = br.weekday_subset(dates, digits, values, weekday)
        found = br.find(cfg["kind"], dg, vl, count=cfg["count"])
        report["rules"][key] = {**cfg, "default_weekday": weekday, "longest": found["longest"],
                                **br.tally(found["bridges"], cfg["kind"]), "backtest": stub}
    return report


def test_each_page_embeds_its_rule_and_shows_the_counts_before_javascript(history) -> None:
    report = _report(history)
    soup = BeautifulSoup(pages.render("bo-so", report), "html.parser")
    payload = json.loads(soup.select_one("#app-cau-data").string)
    assert payload["rule"]["kind"] == "bo-so" and payload["rule"]["count"] == 2
    assert len(payload["draws"]) == br.EMBED and payload["draws"][-1].startswith("2026-09-28")
    cells = {c.select_one("b").get_text(): c.select_one("span").get_text() for c in soup.select("#app-cau-grid .app-cau-cell")}
    assert cells["85"] == "3 cầu" and len(cells) == 21
    assert soup.select_one('.app-cau-tabs a[aria-current="page"]')["href"] == "soi-cau-dac-biet-bo-so.html"
    assert len(soup.select(".app-cau-tabs a")) == len(br.RULES)
    assert "vla" not in str(soup).lower()


def test_the_weekday_pages_offer_every_weekday_and_the_special_page_the_both_digits_switch(history) -> None:
    report = _report(history)
    theo_thu = BeautifulSoup(pages.render("dac-biet-theo-thu", report), "html.parser")
    assert [o.get_text() for o in theo_thu.select("select[name=thu] option")] == list(pages.WEEKDAYS)
    assert theo_thu.select_one("input[name=both]")
    assert not BeautifulSoup(pages.render("loto", report), "html.parser").select_one("input[name=both]")


def test_the_weekly_sheet_embeds_date_and_special_prize_only(history) -> None:
    report = _report(history)
    specials = pages.specials_from(report)
    assert specials[-1] == ["2026-09-28", "77115"]
    soup = BeautifulSoup(pages.render_tool(specials), "html.parser")
    data = json.loads(soup.select_one("#app-phoi-data").string)
    assert data["specials"][-1] == ["2026-09-28", "77115"]
    assert soup.select_one("input[name=count]")["max"] == "80"


def test_the_backtest_verdict_is_read_from_the_numbers(history) -> None:
    report = _report(history)
    data = report["rules"]["loto"]
    assert "Không hàng nào" in pages.backtest_card(br.RULES["loto"], data)
    data["backtest"] = {**data["backtest"], "rows": [dict(r) for r in data["backtest"]["rows"]]}
    data["backtest"]["rows"][4]["z"] = 3.5
    assert "1 trên 11 hàng đủ mẫu" in pages.backtest_card(br.RULES["loto"], data)
