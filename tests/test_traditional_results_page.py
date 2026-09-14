"""Trang Sổ kết quả: dải dữ liệu, bộ lọc, tuỳ chọn hiển thị và xuất file.

Phép kiểm quan trọng nhất của tệp này là phép kiểm DẢI DỮ LIỆU. Lỗi "không
tra cứu được quá khứ" không nằm ở logic ngày tháng — logic ấy vốn đúng. Nó
nằm ở chỗ trang chỉ nhúng 500 kỳ gần nhất, nên mọi truy vấn trước ngày ấy
lọc đúng, trả về rỗng, và hiện "Chưa có kết quả trong khoảng đã chọn" — đọc
như thể hôm đó không quay.

Phần render (chân bảng, tràn ngang) được đo bằng trình duyệt thật trong
``scripts/check_traditional_results_page.py``; ở đây chỉ khoá lại các quy
tắc CSS mà phép đo ấy đã chứng minh là cần.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from bs4 import BeautifulSoup

from build_traditional_results import (
    PRIZE_SPEC,
    ROW_WIDTH,
    embedded_payload,
    encode_row,
    load_rows,
    render_page,
)
from ui_theme import nav_targets

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "src" / "templates" / "traditional_results.css").read_text(encoding="utf-8")
JS = (ROOT / "src" / "templates" / "traditional_results.js").read_text(encoding="utf-8")


def _javascript_without_comments() -> str:
    """Mã JS đã bỏ chú thích.

    Vì sao cần: phép kiểm "chuỗi X có trong tệp" rất dễ khớp vào một dòng CHÚ
    THÍCH thay vì mã thật. Đã xảy ra: bài kiểm thông báo "ngoài dải dữ liệu"
    khớp vào comment giải thích ngay phía trên, nên một đột biến xoá hẳn câu
    thông báo trong mã vẫn xanh.

    Chỉ bỏ chú thích NGUYÊN DÒNG, không đụng tới "//" giữa dòng. Bản đầu cắt
    cả giữa dòng và lập tức hỏng: mã xuất Excel chứa
    "http://schemas.openxmlformats.org/…" bên trong chuỗi, và phép cắt thô
    xén mất một nửa. Chú thích nguyên dòng là đủ cho mục đích ở đây.
    """
    lines = []
    for line in JS.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        lines.append(line)
    return "\n".join(lines)


JS_CODE = _javascript_without_comments()


@pytest.fixture(scope="module")
def csv_dates() -> list[str]:
    with (ROOT / "data" / "xsmb.csv").open(encoding="utf-8") as stream:
        return sorted(row["date"][:10] for row in csv.DictReader(stream))


# --- Nguyên nhân gốc: dải dữ liệu ------------------------------------------


def test_the_whole_history_is_embedded_not_just_a_recent_window(csv_dates) -> None:
    """ĐÂY là phép kiểm hồi quy cho lỗi tra cứu quá khứ.

    Bản trước dùng ``limit=500``, phủ 2025-04-29 → 2026-09-14. Mọi ngày trước
    2025-04-29 trả rỗng mà không nói vì sao.
    """
    rows = load_rows(ROOT)
    assert len(rows) == len(csv_dates)
    assert rows[0][:10] == csv_dates[-1]
    assert rows[-1][:10] == csv_dates[0], "kỳ cũ nhất của CSDL phải có trong trang"


def test_the_built_page_really_carries_every_draw(csv_dates) -> None:
    """Không chỉ kiểm hàm nạp mà kiểm TỆP ĐÃ DỰNG — đó mới là thứ người dùng mở."""
    html = (ROOT / "docs" / "so-ket-qua-truyen-thong.html").read_text(encoding="utf-8")
    blob = re.search(
        r'<script id="tr-embedded-data" type="application/json">(.*?)</script>',
        html, re.S,
    )
    assert blob is not None
    payload = json.loads(blob.group(1).replace("\\u003c", "<").replace("\\u003e", ">"))
    assert payload["total_draws"] == len(csv_dates)
    assert payload["earliest_draw_date"] == csv_dates[0]
    assert payload["latest_draw_date"] == csv_dates[-1]


def test_the_date_inputs_are_bounded_by_the_real_data_range(csv_dates) -> None:
    """Chặn trên/dưới của ô chọn ngày phải là dải THẬT.

    Không có chúng thì trình duyệt cho chọn năm 1999, và trang trả rỗng —
    người dùng không có cách nào biết dải hợp lệ là gì.
    """
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT), generated="x")), "html.parser")
    for field in ("tr-from", "tr-to"):
        node = soup.select_one(f"#{field}")
        assert node["min"] == csv_dates[0]
        assert node["max"] == csv_dates[-1]


def test_an_out_of_range_lookup_explains_itself_instead_of_looking_empty() -> None:
    """Kiểm trên MÃ đã bỏ chú thích, không phải trên toàn tệp.

    Bản đầu kiểm trên toàn tệp và khớp vào đúng dòng chú thích giải thích câu
    này — đột biến xoá câu thông báo thật vẫn xanh.
    """
    assert "ngoài dải dữ liệu" in JS_CODE
    assert "Sổ hiện có từ" in JS_CODE


# --- Mã hoá / giải mã -------------------------------------------------------


def test_the_python_and_javascript_prize_tables_are_identical() -> None:
    """Hai bảng lệch nhau thì trang vẫn dựng được nhưng cắt sai chuỗi.

    Hỏng kiểu ấy im lặng: số vẫn là số, chỉ là số rác.
    """
    block = re.search(r"const PRIZES = \[(.*?)\];", JS_CODE, re.S)
    assert block is not None
    found = re.findall(r'\["(\w+)", "([^"]+)", (\d+), (\d+)\]', block.group(1))
    assert [(c, n, int(k), int(w)) for c, n, k, w in found] == list(PRIZE_SPEC)
    assert "const DATE_WIDTH = 10;" in JS_CODE
    assert ROW_WIDTH == 117


def test_encoding_round_trips_against_the_csv(csv_dates) -> None:
    """Giải mã bằng ĐÚNG bảng độ rộng của bản JS, rồi so với CSV gốc."""
    with (ROOT / "data" / "xsmb.csv").open(encoding="utf-8") as stream:
        rows = {row["date"][:10]: row for row in csv.DictReader(stream)}
    for day in (csv_dates[0], csv_dates[len(csv_dates) // 2], csv_dates[-1]):
        encoded = encode_row(rows[day])
        assert encoded is not None and len(encoded) == ROW_WIDTH
        assert encoded[:10] == day
        cursor = 10
        for code, _, count, width in PRIZE_SPEC:
            for index in range(count):
                field = "special" if code == "special" else (
                    code if count == 1 else f"{code}_{index + 1}")
                assert encoded[cursor:cursor + width] == rows[day][field].strip().zfill(width)
                cursor += width
        assert cursor == ROW_WIDTH


@pytest.mark.parametrize("value", [None, "", "   "])
def test_incomplete_draw_is_not_fabricated_as_zero(value) -> None:
    with (ROOT / "data" / "xsmb.csv").open(encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))
    row["prize7_1"] = value
    assert encode_row(row) is None


# --- Bộ lọc và tuỳ chọn hiển thị -------------------------------------------


def test_the_period_presets_reach_far_beyond_the_old_hundred_day_ceiling() -> None:
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT, limit=5), generated="x")), "html.parser")
    values = [option["value"] for option in soup.select("#tr-period option")]
    assert values == ["10", "30", "60", "90", "100", "120", "200", "300",
                      "500", "1000", "all", "custom"]
    assert len(values) >= 11, "trang tham chiếu có 11 lựa chọn"


def test_the_page_offers_layout_and_visibility_controls() -> None:
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT, limit=5), generated="x")), "html.parser")
    layouts = [node["value"] for node in soup.select('input[name="tr-layout"]')]
    assert layouts == ["1", "2", "3", "4"]
    for toggle in ("tr-toggle-headtail", "tr-toggle-loto", "tr-toggle-tail"):
        assert soup.select_one(f"#{toggle}[type=checkbox]") is not None
    assert soup.select_one("#tr-print") is not None


def test_the_province_selector_is_gone() -> None:
    html = render_page(embedded_payload(load_rows(ROOT, limit=3), generated="x"))
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one("#tr-province") is None
    assert "Khu vực / Tỉnh thành" not in html


def test_no_brand_name_or_removed_wording_survives_on_the_page() -> None:
    """Chữ thương hiệu và ba câu đã yêu cầu gỡ không được còn ở đâu."""
    html = render_page(embedded_payload(load_rows(ROOT, limit=3), generated="x"))
    body = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    assert "VLA" not in body
    for phrase in (
        "ngày thiếu được API bù",
        "Worker chưa cấu hình",
        "Nguồn chuẩn",
        "Nguồn bù",
        "xskt.vn",
    ):
        assert phrase not in html, phrase


def test_the_information_boxes_use_the_requested_labels() -> None:
    html = render_page(embedded_payload(load_rows(ROOT, limit=3), generated="x"))
    assert "Sổ KQ XSMB" in html
    assert "Dữ liệu máy chủ" in html


# --- Giao diện: khoá lại các quy tắc phép đo đã chứng minh là cần ----------


def test_the_result_columns_reserve_space_below_the_last_row() -> None:
    """Lỗi chân bảng lấn lề.

    Đo trong Chromium: bản cũ để chân bảng cách cạnh dưới đúng 1 px. Đệm phải
    nằm trên hai CỘT chứ không trên ``.tr-day``, để đường kẻ dọc phân cách
    vẫn chạy hết chiều cao khung.
    """
    # Neo vào ĐẦU DÒNG. Bản đầu của phép kiểm này dùng regex không neo, nên
    # nó khớp nhầm quy tắc `.tr-results[...] .tr-prizes{padding-bottom:14px}`
    # ở media query hẹp — và một đột biến đưa quy tắc chính về 0 vẫn xanh.
    assert re.search(r"^\.tr-prizes\{[^}]*padding-bottom:14px", CSS, re.M)
    assert re.search(r"^\.tr-day-side\{[^}]*padding-bottom:14px", CSS, re.M)


def test_hiding_both_side_tables_still_leaves_a_footer_gap_on_narrow_screens() -> None:
    """Nhánh này là lỗi bản sửa ĐẦU TIÊN của tôi, và chỉ phép quét mới thấy.

    Ở ``max-width:900px`` cột giải được đặt ``padding-bottom:0`` vì cột phụ
    xếp xuống dưới và tự lo khoảng trống. Khi cả hai bảng phụ bị ẩn thì không
    còn gì nằm dưới, và chân bảng tụt về 2 px — đúng lỗi ban đầu, chỉ khác là
    nó chỉ xuất hiện ở một tổ hợp cụ thể.
    """
    narrow = re.search(r"@media \(max-width:900px\)\{(.*?)\n@media", CSS, re.S)
    assert narrow is not None
    assert '[data-headtail="off"][data-loto="off"] .tr-prizes{padding-bottom:14px' in narrow.group(1)


def test_a_broken_embedded_payload_refuses_to_render_anything() -> None:
    """Dữ liệu nhúng hỏng phải báo lỗi, không được dựng nửa vời.

    Không có chốt này thì một lần đổi lược đồ sẽ cho ra trang trống trơn mà
    không ai biết vì sao.
    """
    assert "embedded.schema_version !== 2 || ALL.length === 0" in JS_CODE
    assert "Dữ liệu nhúng không hợp lệ" in JS_CODE


def test_the_page_can_be_printed_without_the_controls() -> None:
    assert "@media print{" in CSS
    printing = CSS[CSS.index("@media print{"):]
    for hidden in (".tr-hero", ".tr-filter", ".tr-summary"):
        assert hidden in printing
    assert "break-inside:avoid" in printing


# --- Những thứ đã đúng từ trước, giữ nguyên chốt chặn ----------------------


def test_page_javascript_highlights_special_tail_and_builds_real_xlsx() -> None:
    assert '"tr-special-tail"' in JS_CODE
    assert "0x04034b50" in JS_CODE, "Excel phải là gói ZIP OOXML, không phải CSV đổi đuôi"
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in JS_CODE
    assert "replaceChildren" in JS_CODE
    assert ".innerHTML" not in JS, "không đưa dữ liệu vào innerHTML"


def test_the_page_makes_no_outbound_request() -> None:
    """Trang chạy hoàn toàn trên dữ liệu nhúng — không gọi mạng, không cần dịch vụ."""
    assert "fetch(" not in JS_CODE
    html = render_page(embedded_payload(load_rows(ROOT, limit=3), generated="x"))
    soup = BeautifulSoup(html, "html.parser")
    csp = soup.select_one('meta[http-equiv="Content-Security-Policy"]')["content"]
    assert "connect-src 'self'" in csp
    assert "workers.dev" not in csp


def test_generated_page_is_in_navigation_and_exists() -> None:
    assert "so-ket-qua-truyen-thong.html" in nav_targets()
    page = ROOT / "docs" / "so-ket-qua-truyen-thong.html"
    assert page.is_file() and page.stat().st_size > 100_000


def test_builder_output_is_deterministic_for_a_fixed_timestamp() -> None:
    payload = embedded_payload(load_rows(ROOT, limit=5), generated="2026-09-13T13:00:00Z")
    assert render_page(payload) == render_page(payload)


def test_large_selections_are_rendered_in_batches() -> None:
    """Chọn toàn bộ lịch sử không được treo trình duyệt.

    Đo trên Chromium máy bàn trước khi thêm phân trang:

        2 399 kỳ -> 545 060 nút DOM, 2 622 ms dựng

    Sau khi dựng theo lô 100 kỳ: 22 726 nút, 103 ms. Bộ lọc vẫn chọn TRỌN
    khoảng — ô "Số kỳ hiển thị" và các nút xuất file đều dùng trọn lựa chọn,
    chỉ phần dựng ra DOM là theo lô.
    """
    assert "const PAGE_SIZE = 100;" in JS_CODE
    assert "function appendPage(" in JS_CODE
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT, limit=5), generated="x")), "html.parser")
    assert soup.select_one("#tr-more-btn") is not None


def test_printing_renders_the_whole_selection_first() -> None:
    """Trình duyệt chỉ in thứ đã có trong DOM.

    Không dựng nốt trước khi in thì bản in chỉ có lô đầu tiên — và trên giấy
    thì không ai thấy được là đang thiếu.
    """
    assert "renderEverything()" in JS_CODE
    printing = JS_CODE[JS_CODE.index('getElementById("tr-print")'):]
    assert printing.index("renderEverything()") < printing.index("window.print()")


def test_exports_cover_the_whole_selection_not_just_what_is_rendered() -> None:
    """``exportRows`` phải duyệt ``current`` — danh sách đã chọn, không phải DOM."""
    block = JS_CODE[JS_CODE.index("function exportRows("):]
    block = block[:block.index("\n  }")]
    assert "for (const draw of current)" in block
    assert "querySelector" not in block
