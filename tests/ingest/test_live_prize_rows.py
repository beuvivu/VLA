from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.sources import EXPECTED_COUNTS, PRIZE_ORDER, extract_partial_prize_map

PAGES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "prize_pages.json").read_text(encoding="utf-8")
)
FULL = {
    "special": ["38287"], "prize1": ["32680"], "prize2": ["12824", "56761"],
    "prize3": ["18337", "43868", "08556", "15458", "12206", "70045"],
    "prize4": ["1882", "0875", "9096", "8272"],
    "prize5": ["5888", "6187", "9926", "3016", "8724", "7781"],
    "prize6": ["957", "840", "830"], "prize7": ["49", "86", "38", "75"],
}


@pytest.mark.parametrize("page", ["thuc_xoso_live_du_giai", "thuc_minhngoc_du_giai"])
def test_a_complete_board_in_the_real_layouts_is_read_whole(page: str) -> None:
    assert extract_partial_prize_map(PAGES[page]) == FULL


def test_an_undrawn_prize_7_does_not_take_numbers_from_the_loto_table() -> None:
    parsed = extract_partial_prize_map(PAGES["thuc_xoso_live_g7_chua_quay"])
    assert parsed["prize7"] == []
    assert {k: v for k, v in parsed.items() if k != "prize7"} == {k: FULL[k] for k in PRIZE_ORDER if k != "prize7"}


def test_a_prize_7_being_drawn_keeps_the_numbers_already_out() -> None:
    assert extract_partial_prize_map(PAGES["thuc_g7_dang_quay"])["prize7"] == ["49", "86"]


@pytest.mark.parametrize("page", ["thuc_nhan_rong_roi_lien_ket_ngay", "thuc_o_chon_thang"])
def test_a_page_before_the_draw_yields_no_numbers_at_all(page: str) -> None:
    assert extract_partial_prize_map(PAGES[page]) == {k: [] for k in PRIZE_ORDER}


def test_two_adjacent_prize_7_labels_read_the_row_after_the_second() -> None:
    parsed = extract_partial_prize_map(PAGES["thuc_hai_nhan_giai_bay"])
    assert parsed["prize7"] == ["49", "86", "38", "75"]
    assert parsed["prize6"] == ["957", "840", "830"]


def test_a_row_never_takes_more_values_than_the_prize_has() -> None:
    page = "<div>ĐB</div><div>38287</div><div>7</div>" + "".join(f"<div>{n}</div>" for n in range(10, 20))
    assert len(extract_partial_prize_map(page)["prize7"]) == EXPECTED_COUNTS["prize7"]
