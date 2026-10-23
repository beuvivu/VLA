"""Hàng giải chỉ đọc số của chính nó — không vớ số của phần trang phía sau.

Lỗi "trùng lặp giải 7" của trang live: giải 7 là nhãn CUỐI của bảng, nên khối số của
nó từng kéo tới nhãn kế tiếp ở tận bảng lô tô hay ô chọn tháng. Khi giải 7 chưa quay,
bộ bóc vớ số hai chữ số ở đó. Đo trên trang thật lúc 00:02 ngày 13-10-2026 (kỳ chưa
quay), qua ``.github/workflows/diagnose-live-sources.yml``:

* ``xoso.com.vn`` trang theo ngày: giải 7 = ``["10", "11", "12"]`` — ô chọn tháng;
* ``xosodaiphat.com``: giải 7 = ``["12", "10", "14", "10"]`` — liên kết
  "XSMB 12/10/2026", "XSMB 14/10/2026", có cả số lặp.

Các mẫu ``thuc_*`` trong ``tests/fixtures/prize_pages.json`` dựng lại đúng bố cục ấy;
``test_worker_parser_parity.py`` buộc bản JS ra cùng kết quả trên chúng.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.sources import EXPECTED_COUNTS, PRIZE_ORDER, extract_partial_prize_map

PAGES = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "prize_pages.json").read_text(encoding="utf-8")
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
    """Sau nhãn "7" là bảng lô tô, có cả "06", "16", "24"… — đúng là số trùng với giải khác."""
    parsed = extract_partial_prize_map(PAGES["thuc_xoso_live_g7_chua_quay"])
    assert parsed["prize7"] == []
    assert {k: v for k, v in parsed.items() if k != "prize7"} == {k: FULL[k] for k in PRIZE_ORDER if k != "prize7"}


def test_a_prize_7_being_drawn_keeps_the_numbers_already_out() -> None:
    """Hai số đã về, hai ô còn ký hiệu chờ, rồi tới danh sách lô tô: chỉ lấy hai số đầu."""
    assert extract_partial_prize_map(PAGES["thuc_g7_dang_quay"])["prize7"] == ["49", "86"]


@pytest.mark.parametrize("page", ["thuc_nhan_rong_roi_lien_ket_ngay", "thuc_o_chon_thang"])
def test_a_page_before_the_draw_yields_no_numbers_at_all(page: str) -> None:
    """Ngày tháng và ô chọn tháng không phải số giải: kỳ chưa quay thì bảng phải rỗng."""
    assert extract_partial_prize_map(PAGES[page]) == {k: [] for k in PRIZE_ORDER}


def test_two_adjacent_prize_7_labels_read_the_row_after_the_second() -> None:
    parsed = extract_partial_prize_map(PAGES["thuc_hai_nhan_giai_bay"])
    assert parsed["prize7"] == ["49", "86", "38", "75"]
    assert parsed["prize6"] == ["957", "840", "830"]


def test_a_row_never_takes_more_values_than_the_prize_has() -> None:
    page = "<div>ĐB</div><div>38287</div><div>7</div>" + "".join(f"<div>{n}</div>" for n in range(10, 20))
    assert len(extract_partial_prize_map(page)["prize7"]) == EXPECTED_COUNTS["prize7"]
