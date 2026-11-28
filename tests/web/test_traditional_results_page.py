from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from bs4 import BeautifulSoup

from pages.build_traditional_results import (
    PRIZE_SPEC,
    ROW_WIDTH,
    embedded_payload,
    encode_row,
    load_rows,
    render_page,
)
from web.ui_theme import nav_targets

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "src" / "web" / "templates" / "traditional_results.css").read_text(encoding="utf-8")
CSS_CODE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
JS = "\n".join(
    (ROOT / "src" / "web" / "templates" / name).read_text(encoding="utf-8")
    for name in ("shared_results.js", "traditional_results.js")
)


def _javascript_without_comments() -> str:
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


def test_the_whole_history_is_embedded_not_just_a_recent_window(csv_dates) -> None:
    rows = load_rows(ROOT)
    assert len(rows) == len(csv_dates)
    assert rows[0][:10] == csv_dates[-1]
    assert rows[-1][:10] == csv_dates[0], "kỳ cũ nhất của CSDL phải có trong trang"


def test_the_built_page_really_carries_every_draw(csv_dates) -> None:
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
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT), generated="x")), "html.parser")
    for field in ("tr-from", "tr-to"):
        node = soup.select_one(f"#{field}")
        assert node["min"] == csv_dates[0]
        assert node["max"] == csv_dates[-1]


def test_an_out_of_range_lookup_explains_itself_instead_of_looking_empty() -> None:
    assert "ngoài dải dữ liệu" in JS_CODE
    assert "Sổ hiện có từ" in JS_CODE


def test_the_python_and_javascript_prize_tables_are_identical() -> None:
    block = re.search(r"const PRIZES = \[(.*?)\];", JS_CODE, re.S)
    assert block is not None
    found = re.findall(r'\["(\w+)", "([^"]+)", (\d+), (\d+)\]', block.group(1))
    assert [(c, n, int(k), int(w)) for c, n, k, w in found] == list(PRIZE_SPEC)
    assert "const DATE_WIDTH = 10;" in JS_CODE
    assert ROW_WIDTH == 117


def test_encoding_round_trips_against_the_csv(csv_dates) -> None:
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
    assert "SỔ KẾT QUẢ XSMB" in html
    assert "Dữ liệu máy chủ" in html


def test_one_padding_rule_now_gives_every_side_the_same_gap() -> None:
    grid = re.search(r"^\.tr-day-grid\{([^}]*)\}", CSS_CODE, re.M)
    assert grid is not None
    assert "padding:14px" in grid.group(1)
    assert "padding-bottom" not in CSS_CODE, (
        "không còn nhánh đệm riêng — đó là cách hai bản vá trước bỏ sót một tổ hợp"
    )


def test_a_broken_embedded_payload_refuses_to_render_anything() -> None:
    assert "embedded.schema_version !== 2 || ALL.length === 0" in JS_CODE
    assert "Dữ liệu nhúng không hợp lệ" in JS_CODE


def test_the_hidden_attribute_is_made_to_actually_hide() -> None:
    assert "[hidden]{display:none!important}" in CSS_CODE


def test_every_element_that_sets_a_display_and_uses_hidden_is_covered() -> None:
    html = render_page(embedded_payload(load_rows(ROOT, limit=3), generated="x"))
    soup = BeautifulSoup(html, "html.parser")
    hidden_ids = {node.get("id") for node in soup.select("[hidden]") if node.get("id")}
    assert hidden_ids, "trang phải có ít nhất một phần tử dùng `hidden`"
    rule = re.search(r"\[hidden\]\{([^}]*)\}", CSS_CODE)
    assert rule is not None
    assert "display:none!important" in rule.group(1)


def test_the_filter_row_does_not_break_when_the_date_box_hides() -> None:
    rule = re.search(r"^\.tr-form\{([^}]*)\}", CSS_CODE, re.M)
    assert rule is not None
    assert "display:flex" in rule.group(1)
    assert "flex-wrap:wrap" in rule.group(1)
    assert "grid-template-columns" not in rule.group(1)


def test_the_empty_panel_packs_its_two_lines_together() -> None:
    rule = re.search(r"^\.tr-empty\{([^}]*)\}", CSS_CODE, re.M)
    assert rule is not None
    assert "align-content:center" in rule.group(1)
    assert "place-items:center" not in rule.group(1)


def test_the_page_can_be_printed_without_the_controls() -> None:
    assert "@media print{" in CSS
    printing = CSS[CSS.index("@media print{"):]
    for hidden in (".tr-hero", ".tr-filter", ".tr-summary"):
        assert hidden in printing
    assert "break-inside:avoid" in printing


def test_page_javascript_highlights_special_tail_and_builds_real_xlsx() -> None:
    assert '"tr-special-tail"' in JS_CODE
    assert "0x04034b50" in JS_CODE, "Excel phải là gói ZIP OOXML, không phải CSV đổi đuôi"
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in JS_CODE
    assert "replaceChildren" in JS_CODE
    assert ".innerHTML" not in JS, "không đưa dữ liệu vào innerHTML"


def test_the_page_makes_no_outbound_request() -> None:
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
    assert "const PAGE_SIZE = 100;" in JS_CODE
    assert "function appendPage(" in JS_CODE
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT, limit=5), generated="x")), "html.parser")
    assert soup.select_one("#tr-more-btn") is not None


def test_printing_renders_the_whole_selection_first() -> None:
    assert "renderEverything()" in JS_CODE
    printing = JS_CODE[JS_CODE.index('getElementById("tr-print")'):]
    assert printing.index("renderEverything()") < printing.index("window.print()")


def test_exports_cover_the_whole_selection_not_just_what_is_rendered() -> None:
    block = JS_CODE[JS_CODE.index("function exportRows("):]
    block = block[:block.index("\n  }")]
    assert "for (const draw of current)" in block
    assert "querySelector" not in block


def test_the_number_grid_has_no_pixel_floor_that_can_overflow() -> None:
    grid = re.search(r"^\.tr-number-grid\{([^}]*)\}", CSS_CODE, re.M)
    assert grid is not None
    assert "minmax(0,1fr)" in grid.group(1), "sàn pixel làm lưới tràn ở 3/4 cột"
    assert "minmax(64px" not in CSS_CODE


@pytest.mark.parametrize("layout", ["2", "3", "4"])
def test_each_column_layout_sets_its_own_cell_metrics(layout: str) -> None:
    block = re.search(rf'\.tr-results\[data-layout="{layout}"\]\{{([^}}]*)\}}', CSS)
    assert block is not None, f"bố cục {layout} không có bộ biến riêng"
    body = block.group(1)
    for token in ("--tr-label-w", "--tr-num-fs", "--tr-num-h", "--tr-sp-fs"):
        assert token in body, f"bố cục {layout} thiếu {token}"


def test_narrower_layouts_use_smaller_type_than_wider_ones() -> None:
    sizes = {}
    for layout in ("2", "3", "4"):
        block = re.search(rf'\.tr-results\[data-layout="{layout}"\]\{{([^}}]*)\}}', CSS)
        found = re.search(r"--tr-num-fs:([\d.]+)px", block.group(1))
        assert found is not None, f"bố cục {layout} phải đặt cỡ chữ bằng px"
        sizes[layout] = float(found.group(1))
    assert sizes["2"] > sizes["3"] > sizes["4"], sizes


def test_the_inner_table_is_a_bordered_block_inset_from_the_card() -> None:
    prizes = re.search(r"^\.tr-prizes\{([^}]*)\}", CSS, re.M)
    assert prizes is not None
    assert "border:1px solid" in prizes.group(1)
    assert "border-radius" in prizes.group(1)
    grid = re.search(r"^\.tr-day-grid\{([^}]*)\}", CSS, re.M)
    assert grid is not None
    assert "padding:14px" in grid.group(1), "đệm bốn phía giữ bảng trong khỏi cạnh khung"
    assert "gap:14px" in grid.group(1)


def test_the_last_prize_row_does_not_double_up_the_closing_line() -> None:
    assert re.search(r"^\.tr-prize-row:last-child\{border-bottom:0\}", CSS, re.M)


def test_marking_uses_one_delegated_listener_not_one_per_cell() -> None:
    assert 'resultsNode.addEventListener("click"' in JS_CODE
    assert 'closest(".tr-number, .tr-mini")' in JS_CODE
    body = JS_CODE[JS_CODE.index("function renderPrizes("):]
    body = body[:body.index("\n  }")]
    assert "addEventListener" not in body, "không gắn sự kiện lên từng ô"


def test_marking_keeps_two_separate_stores_not_one() -> None:
    assert "const markedCells = new Map();" in JS_CODE
    assert "const markedValues = new Set();" in JS_CODE
    assert "markedCells.has(markCell(node))" in JS_CODE
    assert "markedValues.has(value)" in JS_CODE


def test_the_default_mode_marks_exactly_the_cell_that_was_clicked() -> None:
    body = JS_CODE[JS_CODE.index("function toggleMark("):]
    body = body[:body.index("\n  }")]
    assert re.search(r"else if \(pairMode\.checked && value !== null\) \{[^}]*markedValues\.add\(value\)", body)
    assert "markedCells.set(cell, value)" in body


def test_clicking_a_lit_cell_turns_it_off_whatever_lit_it() -> None:
    body = JS_CODE[JS_CODE.index("function toggleMark("):]
    body = body[:body.index("\n  }")]
    order = [
        body.index("markedValues.delete(value)"),
        body.index("markedCells.delete(cell)"),
        body.index("markedValues.add(value)"),
        body.index("markedCells.set(cell, value)"),
    ]
    assert order == sorted(order), "nhánh bật đang đứng trước nhánh tắt"


def test_a_mini_cell_carries_the_whole_two_digit_pair() -> None:
    assert "const pair = `${headDigit}${tail}`;" in JS_CODE
    assert "mini.dataset.value = pair;" in JS_CODE
    assert "if (node.dataset.value) return node.dataset.value;" in JS_CODE


def test_switching_mode_does_not_erase_existing_marks() -> None:
    assert 'pairMode.addEventListener("change", () => paintMarks());' in JS_CODE


def test_marks_survive_a_rerender() -> None:
    body = JS_CODE[JS_CODE.index("function appendPage("):]
    body = body[:body.index("\n  }")]
    assert "paintMarks()" in body
    assert "number.dataset.cell = `${draw.date}|${prize.code}|${index}`;" in JS_CODE
    assert "mini.dataset.cell = `${draw.date}|d${headDigit}|${index}`;" in JS_CODE


def test_marked_cells_are_outlined_not_bordered() -> None:
    rule = re.search(r"\.tr-number\[data-marked\][^{]*\{([^}]*)\}", CSS)
    assert rule is not None
    assert "outline:" in rule.group(1)
    assert re.search(r"(^|;)border:", rule.group(1)) is None


def test_there_is_a_way_to_clear_every_mark_at_once() -> None:
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT, limit=3), generated="x")), "html.parser")
    button = soup.select_one("#tr-mark-clear")
    assert button is not None
    assert button.has_attr("hidden")
    assert "clearButton.hidden = total === 0" in JS_CODE
    assert "const total = markedCells.size + markedValues.size;" in JS_CODE
    assert "markedCells.clear()" in JS_CODE
    assert "markedValues.clear()" in JS_CODE


def test_the_loto_table_keeps_only_the_head_side() -> None:
    assert '["Đầu", "LOTO"]' in JS_CODE
    assert "Đuôi tương ứng" not in JS_CODE
    assert "Đầu tương ứng" not in JS_CODE
    rule = re.search(r"\.tr-head-tail table\{([^}]*)\}", CSS_CODE)
    assert rule is not None
    assert "width:100%" in rule.group(1)
    assert "table-layout:fixed" in rule.group(1), (
        "không cố định bố cục thì cột đuôi co lại theo nội dung ở hàng ít số"
    )


def test_the_head_digit_uses_the_special_prize_colour() -> None:
    rule = re.search(r"^\.tr-digit\{([^}]*)\}", CSS_CODE, re.M)
    assert rule is not None
    assert "color:var(--ui-bad)" in rule.group(1)
    special = re.search(
        r'\.tr-prize-row\[data-prize="special"\] \.tr-prize-label\{([^}]*)\}', CSS_CODE)
    assert special is not None
    assert "color:var(--ui-bad)" in special.group(1)


def test_the_pair_mode_checkbox_exists_and_starts_unchecked() -> None:
    soup = BeautifulSoup(render_page(embedded_payload(load_rows(ROOT, limit=3), generated="x")), "html.parser")
    box = soup.select_one("#tr-pair-mode[type=checkbox]")
    assert box is not None
    assert not box.has_attr("checked"), "chế độ cặp không được bật sẵn"


def test_number_cells_are_reachable_by_keyboard() -> None:
    assert "number.tabIndex = 0;" in JS_CODE
    assert 'resultsNode.addEventListener("keydown"' in JS_CODE
    assert 'setAttribute("role", "button")' in JS_CODE


def test_the_weekday_filter_offers_all_seven_days_plus_an_off_switch() -> None:
    payload = embedded_payload(load_rows(ROOT, limit=5), generated="2026-01-01T00:00:00+07:00")
    soup = BeautifulSoup(render_page(payload), "html.parser")
    select = soup.select_one("#tr-weekday")
    assert select is not None, "phải có ô chọn thứ trong tuần"
    values = [option["value"] for option in select.select("option")]
    assert values[0] == "all", values
    assert sorted(values[1:]) == [str(day) for day in range(7)], values
    labels = [option.get_text(strip=True) for option in select.select("option")]
    assert labels[1] == "Thứ hai" and labels[-1] == "Chủ nhật", labels


def test_the_weekday_is_computed_without_the_viewer_timezone() -> None:
    body = JS_CODE[JS_CODE.index("function weekdayOf"):]
    body = body[: body.index("\n  }") + 4]
    assert "Date.UTC(" in body and "getUTCDay()" in body, body
    assert "getDay(" not in body.replace("getUTCDay(", ""), body


def test_the_weekday_filter_narrows_the_range_rather_than_replacing_it() -> None:
    body = JS_CODE[JS_CODE.index("function selectRows"):]
    body = body[: body.index("\n  }") + 4]
    assert "selectRange()" in body, body
    assert "weekdayOf(draw.date) === want" in body, body


def test_a_weekday_filter_that_finds_nothing_says_so_in_its_own_words() -> None:
    body = JS_CODE[JS_CODE.index("function emptyMessage"):]
    body = body[: body.index("\n  }") + 4]
    assert "weekdayLabel()" in body, body
    assert body.index('weekday.value !== "all"') < body.index('period.value !== "custom"'), body


def test_the_status_line_says_how_many_draws_the_weekday_filter_started_from() -> None:
    body = JS_CODE[JS_CODE.index("function statusLine"):]
    body = body[: body.index("\n  }") + 4]
    assert "weekdayLabel()" in body and "selectRange()" in body, body


def test_a_loto_cell_shows_the_whole_pair_not_just_the_tail_digit() -> None:
    body = JS_CODE[JS_CODE.index("function renderDigitList"):]
    body = body[: body.index("\n  }") + 4]
    assert 'el("span", "tr-mini", pair)' in body, body
    assert "const pair = `${headDigit}${tail}`;" in body, body


def test_the_loto_type_scales_with_the_column_not_the_viewport() -> None:
    block = CSS_CODE[CSS_CODE.index("@supports (container-type:inline-size)"):]
    block = block[: block.index("\n}") + 2]
    assert "cqw" in block, block
    assert "vw" not in block.replace("cqw", ""), block
    assert "container-type:inline-size" in CSS_CODE.replace("@supports (container-type:inline-size)", "")


def test_browsers_without_container_queries_still_get_a_size() -> None:
    guarded = CSS_CODE[CSS_CODE.index("@supports (container-type:inline-size)"):]
    base = CSS_CODE[: CSS_CODE.index("@supports (container-type:inline-size)")]
    for token in ("--tr-mini-fs", "--tr-digit-fs", "--tr-digit-w", "--tr-mini-w", "--tr-mini-h"):
        assert token in base, f"{token} phải có giá trị nền ngoài @supports"
        assert token in guarded, f"{token} phải được đè bên trong @supports"


@pytest.mark.parametrize("layout", ["1", "2", "3", "4"])
def test_no_layout_falls_back_to_unreadably_small_loto_type(layout: str) -> None:
    if layout == "1":
        block = CSS_CODE[CSS_CODE.index(".tr-results{display:grid"):]
    else:
        block = CSS_CODE[CSS_CODE.index(f'.tr-results[data-layout="{layout}"]{{'):]
    block = block[: block.index("}")]
    found = re.search(r"--tr-mini-fs:([\d.]+)px", block)
    assert found is not None, block
    assert float(found.group(1)) >= 11.0, (layout, found.group(1))


def test_the_head_column_keeps_the_special_prize_red() -> None:
    rule = re.search(r"^\.tr-digit\{[^}]*\}", CSS_CODE, flags=re.M)
    assert rule is not None, "không thấy quy tắc .tr-digit"
    assert "color:var(--ui-bad)" in rule.group(0), rule.group(0)
    special = re.search(
        r"^\.tr-prize-row\[data-prize=\"special\"\] \.tr-prize-label\{[^}]*\}",
        CSS_CODE, flags=re.M)
    assert special is not None and "color:var(--ui-bad)" in special.group(0), special
