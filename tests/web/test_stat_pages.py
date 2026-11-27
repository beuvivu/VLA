from __future__ import annotations

import itertools

import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from pages.build_stat_pages import (
    CHANCE_NOTES,
    LOTO_BASELINE,
    PAGES,
    PAIR_BASELINE,
    PRIZE_WIDTH,
    load_draws,
    render_page,
)

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


@pytest.fixture(scope="module")
def draws():
    return load_draws(ROOT)


def _soup(slug: str) -> BeautifulSoup:
    return BeautifulSoup((DOCS / f"{slug}.html").read_text(encoding="utf-8"), "html.parser")


def test_every_draw_has_exactly_27_numbers(draws) -> None:
    assert draws, "không nạp được kỳ nào"
    for row in draws:
        assert len(row["n"]) == 27, f"kỳ {row['d']} có {len(row['n'])} ô"


def test_numbers_keep_their_leading_zero(draws) -> None:
    for row in draws:
        for value in row["n"]:
            assert len(value) == 2 and value.isdigit(), f"{row['d']}: {value!r}"


def test_special_is_five_digits(draws) -> None:
    for row in draws:
        assert len(row["s"]) == 5 and row["s"].isdigit(), f"{row['d']}: {row['s']!r}"


def test_draws_are_sorted_by_date(draws) -> None:
    dates = [row["d"] for row in draws]
    assert dates == sorted(dates)


def test_prize_widths_sum_to_the_107_digit_board() -> None:
    counts = {"special": 1, "prize1": 1, "prize2": 2, "prize3": 6,
              "prize4": 4, "prize5": 6, "prize6": 3, "prize7": 4}
    assert sum(counts.values()) == 27
    assert sum(PRIZE_WIDTH[k] * n for k, n in counts.items()) == 107


def test_loto_baseline_is_the_known_constant() -> None:
    assert LOTO_BASELINE == pytest.approx(0.2377, abs=5e-4)


def test_pair_baseline_uses_inclusion_exclusion() -> None:
    assert PAIR_BASELINE == pytest.approx(0.0549, abs=5e-4)
    assert PAIR_BASELINE != pytest.approx(LOTO_BASELINE**2, abs=1e-6)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.slug)
def test_page_file_exists(page) -> None:
    assert (DOCS / f"{page.slug}.html").exists()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.slug)
def test_page_has_its_title_and_controls(page) -> None:
    soup = _soup(page.slug)
    assert soup.find("h1") is not None
    assert page.title in soup.find("h1").get_text()
    assert soup.select(".sp-controls"), "thiếu thanh điều khiển bộ lọc"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.slug)
def test_page_embeds_the_history(page) -> None:
    text = (DOCS / f"{page.slug}.html").read_text(encoding="utf-8")
    assert "__D_DRAWS__" in text, "trang phải nhúng lịch sử để lọc phía trình duyệt"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.slug)
def test_render_function_is_declared_not_a_const(page) -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert re.search(rf"^function {re.escape(page.render)}\s*\(", js, re.M), (
        f"{page.render} phải khai bằng `function`, không phải `const`"
    )


def test_no_render_function_is_declared_with_const() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert not re.search(r"^const render\w+\s*=", js, re.M)


def test_page_slugs_are_unique() -> None:
    slugs = [p.slug for p in PAGES]
    assert len(slugs) == len(set(slugs))


def test_all_ten_requested_pages_are_built() -> None:
    expected = {
        "bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam",
        "tan-suat-loto", "tan-suat-cap-loto", "cap-lon-loto", "dau-duoi-loto",
        "cau-giai-dac-biet", "giai-dac-biet-theo-tong",
        "chu-ky-dac-biet", "cau-dac-biet-theo-bo-so", "giai-db-ngay-mai",
        "thong-ke-tong-hop", "lo-gan",
    }
    assert {p.slug for p in PAGES} == expected


def test_pair_chance_note_scales_with_the_embedded_history() -> None:
    from pages.build_stat_pages import chance_note_context

    short = chance_note_context(393)
    long = chance_note_context(2200)

    assert short["chance_max"] == "39,9"
    assert long["chance_max"] == "161,8"
    assert short["pair_expected"] == "21,6"
    assert long["pair_expected"] == "120,7"


def test_pair_chance_grid_matches_the_exact_formula() -> None:
    from pages.build_stat_pages import PAIR_CHANCE_GRID_POINTS, pair_chance_grid
    from core.xsmb_domain import pair_chance_maximum

    grid = pair_chance_grid()
    assert [row[0] for row in grid] == list(PAIR_CHANCE_GRID_POINTS)

    for n, mean, low, high in grid:
        exact_mean, (exact_low, exact_high) = pair_chance_maximum(int(n))
        assert mean == pytest.approx(exact_mean, abs=0.005)
        assert (low, high) == (exact_low, exact_high)

    counts = [row[0] for row in grid]
    means = [row[1] for row in grid]
    assert counts == sorted(counts), "lưới phải tăng dần để nội suy được"
    assert means == sorted(means), "cực đại phải tăng theo số kỳ"


def test_pair_chance_grid_interpolates_within_one_percent() -> None:
    from pages.build_stat_pages import pair_chance_grid
    from core.xsmb_domain import pair_chance_maximum

    grid = pair_chance_grid()

    def interpolate(n: int) -> float:
        if n <= grid[0][0]:
            return grid[0][1]
        if n >= grid[-1][0]:
            return grid[-1][1]
        for (a_n, a_m, _, _), (b_n, b_m, _, _) in itertools.pairwise(grid):
            if a_n <= n <= b_n:
                t = (n - a_n) / (b_n - a_n)
                return a_m + t * (b_m - a_m)
        raise AssertionError("ngoài lưới")

    worst = max(
        abs(interpolate(n) - pair_chance_maximum(n)[0]) / pair_chance_maximum(n)[0]
        for n in range(10, 7300, 37)
    )
    assert worst < 0.01, f"sai số nội suy {worst:.2%} vượt 1%"


def test_pair_page_recomputes_the_chance_note_for_the_filtered_range() -> None:
    html = (DOCS / "tan-suat-cap-loto.html").read_text(encoding="utf-8")
    assert "__D_PAIR_CHANCE__" in html, "trang phải nhúng lưới tra cho trình duyệt"

    note = _soup("tan-suat-cap-loto").select_one("#sp-chance")
    assert note is not None, "ghi chú thiếu chỗ để JavaScript viết lại"

    js = (
        Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "stat_pages.js"
    ).read_text(encoding="utf-8")
    body = js[js.index("function renderPairFrequency()") :]
    body = body[: body.index("\nfunction ", 1)]
    assert "updateChanceNote(" in body, (
        "renderPairFrequency phải cập nhật ghi chú, nếu không nó đứng yên khi lọc"
    )


def test_chance_notes_are_format_safe() -> None:
    from pages.build_stat_pages import chance_note_context

    context = chance_note_context(393)
    for note in CHANCE_NOTES.values():
        note.format(**context)


def test_baselines_come_from_the_single_source_of_truth() -> None:
    from core.xsmb_domain import LOTO_BASELINE_RATE, PAIR_COOCCURRENCE_RATE

    assert LOTO_BASELINE is LOTO_BASELINE_RATE
    assert PAIR_BASELINE is PAIR_COOCCURRENCE_RATE


@pytest.mark.parametrize("slug", sorted(CHANCE_NOTES))
def test_ranking_pages_carry_a_chance_note(slug) -> None:
    note = _soup(slug).select_one(".sp-note")
    assert note is not None, f"{slug} thiếu ghi chú mốc ngẫu nhiên"
    assert len(note.get_text(strip=True)) > 60


def test_prediction_page_states_it_is_not_calibrated() -> None:
    text = " ".join(note.get_text(" ", strip=True)
                    for note in _soup("giai-db-ngay-mai").select(".sp-note"))
    assert "không phải xác suất đã hiệu chuẩn" in text


def test_render_page_is_deterministic_apart_from_the_timestamp(draws) -> None:
    a = render_page(PAGES[0], draws, generated="2026-01-01T00:00:00Z")
    b = render_page(PAGES[0], draws, generated="2026-01-01T00:00:00Z")
    assert a == b


def test_embedded_payload_is_valid_json(draws) -> None:
    html = render_page(PAGES[0], draws[:5], generated="2026-01-01T00:00:00Z")
    match = re.search(r"__D_DRAWS__=(\[.*?\]);", html, re.S)
    assert match, "không tìm thấy khối dữ liệu nhúng"
    payload = json.loads(match.group(1).replace("\\u0026", "&"))
    assert len(payload) == 5
    assert set(payload[0]) == {"d", "s", "n"}


@pytest.mark.parametrize(
    "slug", ["bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam"]
)
def test_special_tables_render_all_five_digits(slug) -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function specialFull(" in js

    body = js[js.index("function specialFull(") :]
    body = body[: body.index("\n}") + 2]
    assert "padStart(5" in body, "phải bù 0 cho giải mất số 0 đứng đầu"
    assert "slice(0, 3)" in body and "slice(3)" in body, (
        "phải hiện ba số đầu cùng hai số cuối, không chỉ hai số cuối"
    )
    page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
    assert "sp-de" in page, f"{slug} chưa dùng lớp hiển thị giải đủ 5 số"

    render = next(page.render for page in PAGES if page.slug == slug)

    def body_of(name: str) -> str:
        chunk = js[js.index(f"function {name}(") :]
        return chunk[: chunk.index("\nfunction ", 1)]

    reached = set()
    frontier = [render]
    while frontier:
        name = frontier.pop()
        if name in reached:
            continue
        reached.add(name)
        body = body_of(name)
        assert ".slice(-2)" not in body, f"{name} còn cắt hai số cuối khi hiển thị"
        for helper in ("specialCell", "specialFull", "weekGrid", "monthGrid"):
            if f"{helper}(" in body:
                frontier.append(helper)

    assert "specialFull" in reached, (
        f"{render} không dẫn tới specialFull qua bất kỳ đường nào; giải bị cắt"
    )


def test_counting_uses_last_two_digits_but_display_does_not() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function lastTwo(" in js
    assert "r.s.slice(-2)" not in js, (
        "còn chỗ cắt thẳng chuỗi giải; dùng lastTwo() để đếm hoặc "
        "specialFull() để hiện"
    )


def test_reverse_pairs_are_true_reversals_not_kep_bong() -> None:
    pairs = []
    for a in range(100):
        b = (a % 10) * 10 + a // 10
        if a < b:
            pairs.append((a, b))

    assert len(pairs) == 45
    assert not any(a % 11 == 0 or b % 11 == 0 for a, b in pairs), (
        "số kép không được xuất hiện trong cặp lộn"
    )

    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function reversePairs(" in js
    assert "function doubleNumbers(" in js
    assert "sp-kep" in js, "số kép phải liệt kê riêng, không trộn vào cặp lộn"


def test_reverse_pair_page_exists_separately() -> None:
    assert "cap-lon-loto" in {p.slug for p in PAGES}
    from web.ui_theme import SITE_NAV

    links = [item[0] for group in SITE_NAV for item in group[1]]
    assert "cap-lon-loto.html" in links, "trang mới phải vào được từ điều hướng"


def test_cells_can_be_marked_for_comparison() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function bindMarking(" in js
    assert '"data-key": key' in js, "ô phải có khoá ổn định để nhớ được"
    assert "localStorage" in js

    assert "try {" in js and "catch" in js, (
        "cửa sổ ẩn danh ném lỗi ngay ở lệnh đọc localStorage; không bọc thì "
        "trang trắng"
    )
    css = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    assert "td.marked" in css


@pytest.mark.parametrize("slug", sorted(p.slug for p in PAGES))
def test_every_page_can_clear_its_marks(slug) -> None:
    page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
    assert 'id="sp-clear-marks"' in page, f"{slug} thiếu nút xoá đánh dấu"
    assert 'id="sp-mark-count"' in page, f"{slug} thiếu số đếm ô đã đánh dấu"


def test_bo_lookup_comes_from_the_domain_helper() -> None:
    from pages.build_stat_pages import bo_lookup
    from core.number_reference import bo_family_id

    table = bo_lookup()
    assert len(table) == 100
    for n in range(100):
        assert table[n] == bo_family_id(f"{n:02d}")

    for two, expected in (("68", "13"), ("48", "34"), ("21", "12"), ("77", "22")):
        assert table[int(two)] == expected

    assert len(set(table)) == 15, "bộ số có đúng 15 họ"


def test_special_cell_carries_all_six_reference_fields() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function specialCell(" in js

    body = js[js.index("function specialCell(") :]
    body = body[: body.index("\n}") + 2]

    assert "(dau + duoi) % 10" in body, "Tổng = (Đầu + Đuôi) mod 10"
    assert 'duoi % 2 === 0 ? "C" : "L"' in body, "Chẵn/Lẻ xét theo Đuôi, không phải Đầu"
    assert "BO_LOOKUP[" in body, "Bộ phải tra bảng dựng sẵn"

    fields = js[js.index("const DE_FIELDS") :]
    fields = fields[: fields.index("];") + 2]
    for key in ("ngay", "tong", "dau", "duoi", "chanle", "bo"):
        assert f'key: "{key}"' in fields, f"thiếu trường {key}"


@pytest.mark.parametrize(
    "slug", ["bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam"]
)
def test_special_pages_can_toggle_each_field(slug) -> None:
    page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
    assert 'id="sp-fields-toggle"' in page, f"{slug} thiếu hộp bật/tắt trường"

    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function bindFieldToggles(" in js
    assert "__D_BO__" in page, f"{slug} chưa nhúng bảng tra bộ số"


def test_matrix_note_does_not_shadow_the_chance_note() -> None:
    for slug in ("tan-suat-loto", "tan-suat-cap-loto"):
        page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
        assert 'class="sp-matrix-note"' in page
        assert 'class="sp-note" id="sp-matrix-note"' not in page

        note = _soup(slug).select_one(".sp-note")
        assert note is not None and len(note.get_text(strip=True)) > 60, (
            f"{slug}: ghi chú mốc ngẫu nhiên bị che"
        )


def test_responsive_layout_is_published_on_the_detailed_table_pages() -> None:
    targets = {"tan-suat-loto", "tan-suat-cap-loto", "bang-dac-biet",
               "bang-dac-biet-thang", "bang-dac-biet-nam", "thong-ke-tong-hop"}
    for page in PAGES:
        html = (DOCS / f"{page.slug}.html").read_text(encoding="utf-8")
        assert ("installStatTableLayout();" in html) == (page.slug in targets)


def test_parity_field_covers_both_digits() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    body = js[js.index("function specialCell(") :]
    body = body[: body.index("\n}") + 2]
    assert 'dau % 2 === 0 ? "C" : "L"' in body, "thiếu chẵn/lẻ của Đầu"
    assert 'duoi % 2 === 0 ? "C" : "L"' in body, "thiếu chẵn/lẻ của Đuôi"


def test_transition_table_ranks_by_standardised_deviation() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    body = js[js.index("function renderSpecialByTong(") :]

    assert "Math.sqrt(P0 * (1 - P0) / n)" in body, "thiếu sai số chuẩn"
    assert "Math.abs(y[5]) - Math.abs(x[5])" in body, (
        "phải xếp theo độ lệch chuẩn hoá, không theo tỉ lệ thô"
    )
    assert "Trên tổng số kỳ" in body, "phải hiện mẫu nền, nếu không tỉ lệ vô nghĩa"


def test_transition_table_skips_non_consecutive_draws() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    body = js[js.index("function renderSpecialByTong(") :]
    assert "gap !== 1" in body, "phải bỏ qua ranh giới ngày nghỉ quay"


def test_tong_page_states_the_chance_level() -> None:
    text = _soup("giai-dac-biet-theo-tong").select_one(".sp-note").get_text(" ", strip=True)
    assert "10 %" in text
    assert "lệch chuẩn hoá" in text.lower()
    assert "không phải xác suất đã hiệu chuẩn" in text


def test_empty_cells_are_marked_so_they_read_as_gaps() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "is-empty" in js, "ô rỗng phải được gắn lớp riêng"

    css = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    assert "td.is-empty" in css
    empty = re.search(r"\.sp-table td\.is-empty\s*\{([^}]+)\}", css).group(1)
    hit = re.search(r"\.sp-table td\.sp-hit\s*\{([^}]+)\}", css).group(1)
    assert "box-shadow: none" in empty
    assert "inset" in hit


def test_grid_lines_run_both_ways() -> None:
    css = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    block = css[css.index(".sp-table.sp-grid-lines th,") :]
    block = block[: block.index("}") + 1]
    assert "border-right" in block, "thiếu đường dọc"
    assert "border-bottom" in block, "thiếu đường ngang"


def test_row_head_styling_is_opt_out_for_calendar_tables() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "has-rowhead" in js
    assert "rowHead: false" in js, "lịch tuần phải tắt cột nhãn"

    css = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    assert ".sp-table.sp-grid-lines.has-rowhead td:first-child" in css, (
        "kiểu cột nhãn phải gắn với has-rowhead, không áp cho mọi bảng"
    )


def test_week_grid_marks_all_weekdays_as_data_cells() -> None:
    body = _js_function("table")
    assert "const isDataCell = opts.rowHead === false || i > 0;" in body
    assert "if (!blank && isDataCell) {" in body


def test_weekly_detail_layout_does_not_single_out_first_weekday() -> None:
    css = (ROOT / "src" / "web" / "templates" / "stat_detail_pages.css").read_text(encoding="utf-8")
    assert ".sp-page-bang-dac-biet #sp-grid th,.sp-page-bang-dac-biet #sp-grid td{text-align:center" in css
    assert ".sp-page-bang-dac-biet #sp-grid td:first-child{text-align:left}" not in css


@pytest.mark.parametrize(
    "slug", ["bang-dac-biet", "bang-dac-biet-nam", "tan-suat-loto", "giai-dac-biet-theo-tong"]
)
def test_tables_use_the_grid_style(slug) -> None:
    page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
    assert "sp-grid-lines" in page, f"{slug} chưa dùng kiểu bảng lưới"


def test_column_hint_uses_one_delegated_handler() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    body = js[js.index("function bindColumnHint(") :]
    body = body[: body.index("\nfunction ", 1)]
    assert 'document.addEventListener("mouseover"' in body
    assert "querySelectorAll" in body
    assert ".forEach(" not in body.split("addEventListener")[0], (
        "không được gắn trình xử lý cho từng ô"
    )


def _legend_body() -> str:
    return _js_function("renderLegend")


def test_every_field_in_a_cell_is_named_and_explained() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    block = js[js.index("const DE_FIELDS = [") :]
    block = block[: block.index("\n];")]
    for key in ("ngay", "tong", "dau", "duoi", "chanle", "bo"):
        assert f'key: "{key}"' in block, f"thiếu trường {key}"
    assert block.count("hint:") == 6, "mỗi trường phải có một câu giải thích"


def test_legend_states_the_two_rules_a_reader_cannot_guess() -> None:
    body = _legend_body()
    assert "mod 10" in body, "phải nêu công thức Tổng"
    assert "bóng dương" in body, "phải nêu cách gom Bộ"
    assert "0↔5" in body, "phải liệt kê cặp bóng để tự kiểm được"


def test_legend_example_comes_from_real_data_not_a_made_up_cell() -> None:
    body = _legend_body()
    assert "DRAWS[DRAWS.length - 1]" in body, "phải lấy kỳ mới nhất"
    assert "specialFull(" in body, "ô mẫu phải dựng bằng đúng hàm dựng ô thật"


def test_legend_lists_the_whole_bo_family_so_the_example_always_teaches() -> None:
    body = _legend_body()
    assert "BO_LOOKUP[n] === bo" in body, "phải quét bảng tra ra cả họ"
    assert "family.join(" in body, "phải in danh sách ra chú giải"


def test_legend_does_not_keep_a_second_copy_of_the_field_names() -> None:
    body = _legend_body()
    assert "DE_FIELDS.map(" in body, "chú giải phải sinh từ DE_FIELDS"

    builder = (ROOT / "src" / "pages" / "build_stat_pages.py").read_text(encoding="utf-8")
    block = builder[builder.index("FIELD_TOGGLE = (") :]
    block = block[: block.index("\n)")]
    assert 'id="sp-legend"' in block, "trang phải có chỗ để đặt chú giải"
    assert 'id="sp-legend"></div>' in block, "khối chú giải phải rỗng trong HTML"
    for label in ("Ngày", "Tổng", "Đầu", "Đuôi", "Chẵn lẻ", "Bộ"):
        assert label not in block, f"nhãn {label} bị chép sang Python"


@pytest.mark.parametrize("slug", ["bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam"])
def test_special_pages_carry_the_legend(slug) -> None:
    page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
    assert 'id="sp-legend"' in page, f"{slug} chưa có chú giải ô"
    assert ".sp-lg-hint" in page, f"{slug} chưa có kiểu cho chú giải"


def test_hints_are_not_hidden_behind_hover_only() -> None:
    body = _legend_body()
    assert "sp-lg-hint" in body, "lời giải thích phải được in ra thành thẻ"

    css = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    block = css[css.index(".sp-lg-hint {") :]
    block = block[: block.index("}") + 1]
    assert "display: block" in block, "chú giải phải luôn hiện"


def _js_function(name: str) -> str:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    body = js[js.index(f"function {name}(") :]
    end = body.find("\nfunction ", 1)
    return body if end < 0 else body[:end]


def test_pair_gan_counts_either_number_not_both() -> None:
    assert "&& !seen.has(pair[1])" in _js_function("pairGaps"), (
        "phải là 'không con nào về' mới bỏ qua; dùng || là hoá thành 'cả hai'"
    )


def test_gan_compares_numbers_with_numbers() -> None:
    for name in ("lotoGaps", "pairGaps"):
        assert "parseInt(x, 10)" in _js_function(name), (
            f"{name} phải quy chuỗi về số trước khi so"
        )


def test_gan_counts_a_draw_once_even_if_the_number_repeats() -> None:
    assert "new Set(" in _js_function("lotoGaps"), "phải khử trùng trong cùng một kỳ"


def test_lo_gan_page_has_all_four_reference_tables() -> None:
    page = (DOCS / "lo-gan.html").read_text(encoding="utf-8")
    for table_id in ("sp-grid", "sp-max-lo", "sp-max-hi", "sp-pair-gan"):
        assert f'id="{table_id}"' in page, f"thiếu bảng {table_id}"


def test_lo_gan_page_says_gan_is_counted_in_draws_not_calendar_days() -> None:
    page = (DOCS / "lo-gan.html").read_text(encoding="utf-8")
    assert "kỳ quay" in page and "ngày lịch" in page, (
        "trang phải nói rõ gan đếm theo kỳ"
    )
    assert "lịch sử" in page, "phải nói gan cực đại phụ thuộc độ dài lịch sử"


def test_head_tail_page_has_the_three_per_day_matrices() -> None:
    page = (DOCS / "dau-duoi-loto.html").read_text(encoding="utf-8")
    for table_id in ("sp-day-head", "sp-day-tail", "sp-day-sum"):
        assert f'id="{table_id}"' in page, f"thiếu ma trận {table_id}"


def test_empty_range_clears_the_tables_instead_of_keeping_stale_numbers() -> None:
    body = _js_function("table")
    assert "sp-empty-row" in body, "table() phải dựng dòng báo dải rỗng"
    assert "rows.length ?" in body, "phải rẽ nhánh theo số hàng"

    tong = _js_function("renderSpecialByTong")
    assert "if (!rows.length) {" in tong, "không được return trắng"
    branch = tong[tong.index("if (!rows.length) {") :]
    branch = branch[: branch.index("return;")]
    for table_id in ("sp-grid", "sp-trans", "sp-parity"):
        assert f'table($("{table_id}")' in branch, f"nhánh rỗng phải dựng lại {table_id}"


def test_notes_only_name_columns_the_tables_actually_render() -> None:
    builder = (ROOT / "src" / "pages" / "build_stat_pages.py").read_text(encoding="utf-8")
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")

    assert "So mức ngẫu nhiên" not in builder, (
        "không cột nào mang tên này; ghi chú phải nói theo cột thật"
    )
    for column in ("Tỉ lệ", "Lệch chuẩn hoá"):
        assert column in builder, f"ghi chú không còn nhắc {column}?"
        assert f'"{column}"' in js, f"bảng không dựng cột {column}"


def test_cycle_page_explains_it_counts_draws_not_calendar_days() -> None:
    notes = " ".join(note.get_text(" ", strip=True)
                     for note in _soup("chu-ky-dac-biet").select(".sp-note"))
    assert "kỳ quay trong dải đã chọn" in notes
    assert "những ngày nghỉ quay không được tính thêm" in notes


def test_clear_marks_button_is_not_a_range_filter_chip() -> None:
    source = (ROOT / "src" / "pages" / "build_stat_pages.py").read_text(encoding="utf-8")
    marker = 'id="sp-clear-marks"'
    line = next(ln for ln in source.splitlines() if marker in ln)
    assert 'class="sp-btn"' in line
    assert "sp-chip" not in line


def test_range_handler_only_binds_buttons_inside_the_filter_group() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert 'querySelectorAll(".sp-chip")' not in js
    assert 'querySelectorAll(".sp-chips .sp-chip")' in js


def test_default_range_chip_matches_the_javascript_default() -> None:
    from pages.build_stat_pages import DEFAULT_RANGE_DRAWS

    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert f"DRAWS.length - {DEFAULT_RANGE_DRAWS}" in js


def test_preset_pages_highlight_all_history_not_ninety_draws() -> None:
    from pages.build_stat_pages import _range_controls

    preset = _range_controls(mode="preset")
    assert '<button class="sp-chip on" data-days="0">Tất cả</button>' in preset
    assert 'class="sp-chip on" data-days="90"' not in preset

    day = _range_controls(mode="day")
    assert '<button class="sp-chip on" data-days="90">90 kỳ</button>' in day
    assert 'class="sp-chip on" data-days="0"' not in day


SPECIAL_SLUGS = ("bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam")

JS_SOURCE = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")


def _render_body(function_name: str) -> str:
    start = JS_SOURCE.index(f"function {function_name}()")
    following = JS_SOURCE.find("\nfunction ", start + 1)
    return JS_SOURCE[start : following if following != -1 else len(JS_SOURCE)]


def _primary_table_axes(function_name: str) -> list[str]:
    body = _render_body(function_name)
    axes = []
    for match in re.finditer(r'table\(\$\("sp-grid"\),\s*([A-Za-z_$][\w$]*|\[[^\]]*\][^,;]*)', body):
        head = match.group(1).strip()
        if re.fullmatch(r"[a-z_$][\w$]*", head):
            local = re.search(rf"const\s+{re.escape(head)}\s*=\s*([^;]+);", body, re.S)
            if local:
                head = local.group(1)
        axes.append(re.sub(r"\s+", " ", head).strip())
    return axes


def test_the_three_special_pages_do_not_render_the_same_primary_table() -> None:
    by_page = {
        slug: _primary_table_axes(page.render)
        for slug, page in ((p.slug, p) for p in PAGES)
        if slug in SPECIAL_SLUGS
    }
    assert set(by_page) == set(SPECIAL_SLUGS), by_page

    seen: dict[str, str] = {}
    for slug, axes in by_page.items():
        assert axes, f"{slug}: không dựng bảng chính nào"
        for axis in axes:
            if axis in seen and seen[axis] != slug:
                pytest.fail(f"{slug} trải đúng cùng trục với {seen[axis]}: {axis}")
            seen.setdefault(axis, slug)


def test_each_special_page_title_matches_the_axis_it_actually_shows() -> None:
    expected = {
        "bang-dac-biet": ("tuần", ("weekGrid", "WEEKDAYS")),
        "bang-dac-biet-thang": ("tháng", ("monthGrid", "sp-year")),
        "bang-dac-biet-nam": ("năm", ("byYear", "sp-month")),
    }
    for page in PAGES:
        if page.slug not in expected:
            continue
        word, markers = expected[page.slug]
        assert page.title.lower().endswith(word), f"{page.slug}: {page.title!r}"
        body = _render_body(page.render)
        for marker in markers:
            assert marker in body, f"{page.slug} thiếu {marker!r} trong {page.render}"


def test_each_special_page_has_exactly_the_one_picker_its_axis_needs() -> None:
    month_page = next(p for p in PAGES if p.slug == "bang-dac-biet-thang")
    assert 'id="sp-year"' in month_page.controls, "cột là tháng nên phải chọn NĂM"
    assert 'id="sp-month"' not in month_page.controls
    assert "sp-multiyear" not in month_page.body, "không còn bảng phụ"

    year_page = next(p for p in PAGES if p.slug == "bang-dac-biet-nam")
    assert 'id="sp-month"' in year_page.controls, "hàng là năm nên phải chọn THÁNG"
    assert 'id="sp-year"' not in year_page.controls
    assert 'id="sp-mode"' not in year_page.controls, "bỏ bộ chọn Kiểu để không trùng trang tuần"
