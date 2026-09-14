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
#: CSS đã bỏ chú thích.
#:
#: Cùng lý do với ``JS_CODE``: phép kiểm "chuỗi X không có trong tệp" sẽ
#: khớp vào một dòng CHÚ THÍCH giải thích chính chuỗi ấy. Đã xảy ra hai
#: lần trong tệp này — lần này là chú thích nhắc tới ``minmax(64px,1fr)``
#: để giải thích vì sao nó bị bỏ.
CSS_CODE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
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


def test_one_padding_rule_now_gives_every_side_the_same_gap() -> None:
    """Chân bảng lấn lề — và hai bản vá trước đó của chính tôi.

    Bản gốc: cột giải không có đệm nào, chân bảng cách cạnh dưới đúng 1 px
    (đo trong Chromium), trong khi cột phải có 14 px — hai bên lệch hẳn.

    Bản vá thứ nhất: đặt ``padding-bottom`` riêng trên từng cột. Đỡ được chỗ
    dính, nhưng hai bên vẫn lệch (31 px so với 15 px) vì cột thấp hơn nhận
    thêm phần dư khi bị kéo giãn.

    Bản vá thứ hai: ở ``max-width:900px`` cột giải được đặt ``padding-bottom:0``
    vì cột phụ xếp xuống dưới — nhưng khi ẩn cả hai bảng phụ thì không còn gì
    nằm dưới, và chân tụt về 2 px.

    Nay chỉ còn MỘT quy tắc: đệm bốn phía trên ``.tr-day-grid``. Không có
    nhánh riêng nào để bỏ sót.
    """
    grid = re.search(r"^\.tr-day-grid\{([^}]*)\}", CSS_CODE, re.M)
    assert grid is not None
    assert "padding:14px" in grid.group(1)
    assert "padding-bottom" not in CSS_CODE, (
        "không còn nhánh đệm riêng — đó là cách hai bản vá trước bỏ sót một tổ hợp"
    )


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


# --- Bố cục nhiều cột: lỗi vỡ chữ số --------------------------------------


def test_the_number_grid_has_no_pixel_floor_that_can_overflow() -> None:
    """ĐÂY là dòng sửa lỗi vỡ 3/4 cột.

    `minmax(64px,1fr)` là một sàn CỨNG: sáu số giải ba cần 6×64 = 384px, còn
    thẻ ở bố cục 4 cột chỉ rộng 331px. Lưới tràn, và `.tr-day{overflow:hidden}`
    CẮT phần thừa thay vì làm trang cuộn — nên phép kiểm "trang có cuộn ngang
    không" của tôi vẫn xanh trong khi giao diện đã vỡ. Đo ở cấp phần tử:

        bố cục 1   tràn   0px   0 ô bị cắt
        bố cục 2   tràn   0px   0 ô bị cắt
        bố cục 3   tràn  56px   6 ô bị cắt
        bố cục 4   tràn 172px   6 ô bị cắt
    """
    grid = re.search(r"^\.tr-number-grid\{([^}]*)\}", CSS_CODE, re.M)
    assert grid is not None
    assert "minmax(0,1fr)" in grid.group(1), "sàn pixel làm lưới tràn ở 3/4 cột"
    assert "minmax(64px" not in CSS_CODE


@pytest.mark.parametrize("layout", ["2", "3", "4"])
def test_each_column_layout_sets_its_own_cell_metrics(layout: str) -> None:
    """Cỡ chữ và đệm ô phải co theo bố cục, không dùng chung một giá trị."""
    block = re.search(rf'\.tr-results\[data-layout="{layout}"\]\{{([^}}]*)\}}', CSS)
    assert block is not None, f"bố cục {layout} không có bộ biến riêng"
    body = block.group(1)
    for token in ("--tr-label-w", "--tr-num-fs", "--tr-num-h", "--tr-sp-fs"):
        assert token in body, f"bố cục {layout} thiếu {token}"


def test_narrower_layouts_use_smaller_type_than_wider_ones() -> None:
    """Thứ tự phải đơn điệu: càng nhiều cột thì chữ càng nhỏ.

    Không có chốt này thì một lần chỉnh tay có thể đặt bố cục 4 cột chữ to hơn
    bố cục 3 cột, và lỗi vỡ quay lại y như cũ.
    """
    sizes = {}
    for layout in ("2", "3", "4"):
        block = re.search(rf'\.tr-results\[data-layout="{layout}"\]\{{([^}}]*)\}}', CSS)
        found = re.search(r"--tr-num-fs:([\d.]+)px", block.group(1))
        assert found is not None, f"bố cục {layout} phải đặt cỡ chữ bằng px"
        sizes[layout] = float(found.group(1))
    assert sizes["2"] > sizes["3"] > sizes["4"], sizes


# --- Đường kẻ và khoảng cách bảng trong / khung ngoài ----------------------


def test_the_inner_table_is_a_bordered_block_inset_from_the_card() -> None:
    """Một thay đổi cấu trúc giải quyết cùng lúc ba khiếu nại.

    Bảng giải nay có viền riêng và thụt vào nhờ đệm của `.tr-day-grid`:

    * cạnh phải bảng trong không còn dính khung ngoài;
    * giải 7 có đường kẻ đóng bảng (chính là cạnh dưới của viền ấy);
    * ở bố cục 2/3/4 cột, bảng vẫn có ranh giới rõ dù đường kẻ dọc phân cách
      giữa hai cột đã không còn.
    """
    prizes = re.search(r"^\.tr-prizes\{([^}]*)\}", CSS, re.M)
    assert prizes is not None
    assert "border:1px solid" in prizes.group(1)
    assert "border-radius" in prizes.group(1)
    grid = re.search(r"^\.tr-day-grid\{([^}]*)\}", CSS, re.M)
    assert grid is not None
    assert "padding:14px" in grid.group(1), "đệm bốn phía giữ bảng trong khỏi cạnh khung"
    assert "gap:14px" in grid.group(1)


def test_the_last_prize_row_does_not_double_up_the_closing_line() -> None:
    """Viền của `.tr-prizes` đã vẽ cạnh dưới; hàng cuối kẻ thêm sẽ thành hai nét."""
    assert re.search(r"^\.tr-prize-row:last-child\{border-bottom:0\}", CSS, re.M)


# --- Đánh dấu số ------------------------------------------------------------


def test_marking_uses_one_delegated_listener_not_one_per_cell() -> None:
    """Vùng kết quả có hàng chục nghìn ô và được dựng lại mỗi lần đổi bộ lọc.

    Gắn sự kiện từng ô nghĩa là bằng đó lượt đăng ký mỗi lần dựng.
    """
    assert 'resultsNode.addEventListener("click"' in JS_CODE
    assert 'closest(".tr-number, .tr-mini")' in JS_CODE
    body = JS_CODE[JS_CODE.index("function renderPrizes("):]
    body = body[:body.index("\n  }")]
    assert "addEventListener" not in body, "không gắn sự kiện lên từng ô"


def test_marking_is_keyed_by_value_so_the_same_number_lights_up_everywhere() -> None:
    """Bấm con 27 ở một kỳ thì con 27 ở mọi kỳ đang xem cùng sáng.

    Đó chính là việc người soi cầu muốn làm — dò một số qua nhiều ngày. Lưu
    theo phần tử thì dựng lại danh sách là mất dấu.
    """
    assert "const marked = new Set();" in JS_CODE
    assert "text.slice(-2)" in JS_CODE
    assert "marked.has(key)" in JS_CODE and "marked.delete(key)" in JS_CODE


def test_marks_survive_a_rerender() -> None:
    """`appendPage` phải sơn lại dấu, nếu không thì "xem thêm" ra các thẻ trắng."""
    body = JS_CODE[JS_CODE.index("function appendPage("):]
    body = body[:body.index("\n  }")]
    assert "paintMarks()" in body


def test_marked_cells_are_outlined_not_bordered() -> None:
    """`border` làm ô rộng thêm và đẩy cả lưới lệch; `outline` vẽ đè, không chiếm chỗ."""
    rule = re.search(r"\.tr-number\[data-marked\][^{]*\{([^}]*)\}", CSS)
    assert rule is not None
    assert "outline:" in rule.group(1)
    assert re.search(r"(^|;)border:", rule.group(1)) is None


def test_there_is_a_way_to_clear_every_mark_at_once() -> None:
    """Đánh dấu lan sang mọi kỳ đang xem, nên bỏ từng ô là không khả thi.

    Nút phải ẩn khi chưa đánh dấu gì và hiện kèm SỐ LƯỢNG khi đã có — người
    xem cần biết mình đang giữ bao nhiêu dấu mà không phải cuộn đi tìm.
    """
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT, limit=3), generated="x")), "html.parser")
    button = soup.select_one("#tr-mark-clear")
    assert button is not None
    assert button.has_attr("hidden")
    assert "clearButton.hidden = marked.size === 0" in JS_CODE
    assert "marked.clear()" in JS_CODE


def test_number_cells_are_reachable_by_keyboard() -> None:
    assert "number.tabIndex = 0;" in JS_CODE
    assert 'resultsNode.addEventListener("keydown"' in JS_CODE
    assert 'setAttribute("role", "button")' in JS_CODE
