from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from web.ui_theme import (
    ALIGN_CENTER,
    WCAG_AA_NORMAL,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    TAILWIND_LITE_CSS,
    card,
    contrast_ratio,
    dataframe_table,
    nav_links,
    page_header,
    render_table,
    shell_open,
    tailwind_style_tag,
)

from pages import build_landing_page as blp

ROOT = Path(__file__).resolve().parents[2]


def test_theme_stays_self_contained_without_external_assets() -> None:
    style = tailwind_style_tag()
    assert "https://" not in style
    assert "http://" not in style
    assert "//" not in style.replace("://", "")
    assert "@import" not in style
    for url in re.findall(r'url\("?([^")]+)"?\)', style):
        assert not url.startswith(("http", "//", "data:")), f"tài nguyên ngoài: {url}"


def test_theme_keeps_layout_and_component_primitives() -> None:
    for token in (
        ".ui-shell",
        ".ui-card",
        ".ui-table",
        ".ui-badge",
        ".ui-grid",
    ):
        assert token in TAILWIND_LITE_CSS, token
    assert "margin-inline:auto" in TAILWIND_LITE_CSS
    assert "min-width:640px" in TAILWIND_LITE_CSS
    assert "min-width:1024px" in TAILWIND_LITE_CSS


def test_render_table_aligns_columns_by_declared_type() -> None:
    html_out = render_table(
        ["Nhãn", "Trạng thái", "Giá trị"],
        [["a", "ok", "1.5"]],
        align=[ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT],
    )
    soup = BeautifulSoup(html_out, "html.parser")
    cells = soup.find_all("td")
    assert "ui-al" in cells[0]["class"]
    assert "ui-ac" in cells[1]["class"]
    assert "ui-ar" in cells[2]["class"]
    assert soup.find("div", class_="ui-table-wrap") is not None


def test_render_table_infers_alignment_from_cell_values() -> None:
    soup = BeautifulSoup(
        render_table(
            ["Nhãn", "Số", "Xác suất"], [["LOTO", "83", "0.2491"]]
        ),
        "html.parser",
    )
    cells = soup.find_all("td")
    assert "ui-al" in cells[0]["class"]
    assert "ui-ar" in cells[1]["class"]
    assert "ui-ar" in cells[2]["class"]


def test_explicit_align_overrides_numeric_inference_for_key_columns() -> None:
    soup = BeautifulSoup(
        render_table(
            ["Số", "Xác suất"],
            [["83", "0.2491"]],
            align=[ALIGN_LEFT, ALIGN_RIGHT],
            key_column=0,
        ),
        "html.parser",
    )
    cells = soup.find_all("td")
    assert "ui-al" in cells[0]["class"]
    assert "ui-key" in cells[0]["class"]
    assert "ui-ar" in cells[1]["class"]


def test_render_table_escapes_untrusted_cell_content() -> None:
    out = render_table(["x"], [["<script>alert(1)</script>"]])
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_dataframe_table_reports_empty_frames_instead_of_raising() -> None:
    assert "ui-table-empty" in dataframe_table(pd.DataFrame())
    assert "ui-table-empty" in dataframe_table(None)


def test_dataframe_table_renders_every_row_and_column() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    soup = BeautifulSoup(dataframe_table(frame), "html.parser")
    assert len(soup.find_all("tr")) == 4
    assert len(soup.find_all("th")) == 2


def test_card_span_is_clamped_into_the_twelve_column_grid() -> None:
    assert "ui-c8" in card("x", span=8)
    assert "ui-c12" in card("x", span=99)
    assert "ui-c1" in card("x", span=-3)


def test_page_header_and_nav_escape_input() -> None:
    assert "&lt;b&gt;" in page_header("<b>t</b>")
    assert "&lt;b&gt;" in nav_links([("a.html", "<b>x</b>")])
    assert 'aria-current="page"' in nav_links([("a.html", "x")], current="a.html")


def _grid_rows_do_not_overflow(page: Path) -> None:
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    for grid in soup.find_all("div", class_="ui-grid"):
        used = 0
        for section in grid.find_all("section", class_="ui-card", recursive=False):
            spans = [
                int(m.group(1))
                for cls in section.get("class", [])
                if (m := re.fullmatch(r"ui-c(\d+)", cls))
            ]
            span = spans[0] if spans else 12
            used = span if used + span > 12 else used + span
            assert span <= 12, f"{page.name}: span {span} vượt 12 cột"


def _selector_targets_body(selector: str) -> bool:
    return any(re.match(r"body(?=$|[.#:\[])", part, re.I) for part in _selector_subjects(selector))


def _selector_subjects(selector: str) -> list[str]:
    subjects = []
    compound = ""
    last = ""
    depth = 0
    quote = ""
    escaped = False
    for char in selector.strip():
        if escaped:
            compound += char
            escaped = False
        elif char == "\\":
            compound += char
            escaped = True
        elif quote:
            compound += char
            if char == quote:
                quote = ""
        elif char in "\"'":
            compound += char
            quote = char
        elif char in "([":
            compound += char
            depth += 1
        elif char in ")]":
            compound += char
            depth -= 1
        elif depth == 0 and char == ",":
            subjects.append(compound or last)
            compound = last = ""
        elif depth == 0 and (char.isspace() or char in ">+~"):
            if compound:
                last = compound
                compound = ""
        else:
            compound += char
    subjects.append(compound or last)
    return subjects


def _assert_no_legacy_body_margin(css: str) -> None:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules = [rule.rpartition("{") for rule in css.split("}")]
    body_rules = [declarations for selector, _, declarations in rules
                  if _selector_targets_body(selector)]
    assert not any(re.search(r"\bmargin\s*:\s*24px\b", rule) for rule in body_rules)


@pytest.mark.parametrize("css", [
    "body {margin:24px}",
    "body.app-workspace {margin: 24px 0}",
    "html > body.dark { margin : 24px!important; }",
    "body:is(.light,.dark) {margin:24px}",
    'body[data-note="a b"] {margin:24px}',
    ".card, body.dark {margin:24px}",
    "body.dark, .card {margin:24px}",
    "@media(prefers-color-scheme:dark){@supports(display:grid){html body.dark{margin:24px}}}",
])
def test_body_margin_guard_rejects_actual_body_targets(css: str) -> None:
    with pytest.raises(AssertionError):
        _assert_no_legacy_body_margin(css)


@pytest.mark.parametrize("css", [
    "body.app-workspace .sp-duo{margin:24px}",
    "body.dark > .card {margin:24px}",
    "body .card, html body.dark .sp-duo {margin:24px}",
    "@media(prefers-color-scheme:dark){@supports(display:grid){body.dark .card{margin:24px}}}",
    ".nobody {margin:24px}",
    '.card[data-note="body"] {margin:24px}',
    ".card:has(body) {margin:24px}",
    "body {margin:0;padding:24px} body .card {margin:24px}",
])
def test_body_margin_guard_allows_descendant_spacing(css: str) -> None:
    _assert_no_legacy_body_margin(css)


def test_generated_dashboard_pages_use_the_shared_shell_and_grid(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "src/pages/build_dashboard.py", "--docs-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, "src/pages/build_model_quality.py", "--docs-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
    )

    for name in ("dashboard.html", "model-quality.html"):
        page = tmp_path / name
        text = page.read_text(encoding="utf-8")
        assert "ui-shell" in text, name
        assert "https://" not in text, name
        css = "\n".join(style.get_text() for style in BeautifulSoup(text, "html.parser").find_all("style"))
        _assert_no_legacy_body_margin(css)
        _grid_rows_do_not_overflow(page)


def test_shell_open_offers_a_wide_variant() -> None:
    assert "ui-shell-wide" in shell_open(wide=True)
    assert "ui-shell-wide" not in shell_open()


def test_theme_does_not_force_heading_colour_globally() -> None:
    assert "h1,h2,h3,h4{font-weight:600" in TAILWIND_LITE_CSS
    assert ".ui-shell h1" in TAILWIND_LITE_CSS
    assert "h1,h2,h3,h4{color:" not in TAILWIND_LITE_CSS


def test_path_ui_template_does_not_apply_light_classes_to_dark_page() -> None:
    template = (ROOT / "src/web/templates/path_ui_page.html.j2").read_text(
        encoding="utf-8"
    )
    assert '<body class="ui-app path-page">' in template
    assert "bg-slate-50" not in template
    assert "text-slate-800" not in template


def test_statistics_matrix_fits_ten_tail_columns_in_a_half_width_card() -> None:
    source = (ROOT / "src/pages/build_statistics_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "grid-template-columns: 40px repeat(10, minmax(38px, 1fr));" in source
    assert "min-width: 464px;" in source
    assert "min-width: 660px;" not in source


def test_statistics_section_nav_wraps_instead_of_hiding_links() -> None:
    from pages import build_statistics_dashboard as bsd

    source = bsd._DASHBOARD_CSS
    nav = source[source.index(".sticky-nav {") : source.index(".sticky-nav a {")]
    assert "flex-wrap: wrap;" in nav
    assert "overflow-x: auto;" not in nav


def test_landing_grid_items_can_shrink_below_their_content_width() -> None:
    source = (ROOT / "src/pages/build_landing_page.py").read_text(encoding="utf-8")
    assert ".result-combo > * { min-width: 0; }" in blp._LANDING_CSS
    assert "<div class='matrix-wrap'><div class='tiny-matrix'>" in source
    assert "minmax(760px, 1fr) minmax(360px, 440px)" not in source


def test_column_align_helpers_cover_expected_columns() -> None:
    for index in (1, 5, 10):
        assert f".ui-table.ui-r{index} td:nth-child({index})" in TAILWIND_LITE_CSS
        assert f".ui-table.ui-m{index} td:nth-child({index})" in TAILWIND_LITE_CSS
    assert "text-align:right;white-space:nowrap" in TAILWIND_LITE_CSS


def test_published_path_pages_do_not_ship_light_theme_classes() -> None:
    pages = sorted((ROOT / "docs").glob("soi-path-*.html"))
    assert pages, "không tìm thấy trang soi cầu đã sinh"
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert '<body class="bg-slate-50' not in text, page.name
        assert "text-slate-800" not in text, page.name
        body = BeautifulSoup(text, "html.parser").body
        assert {"ui-app", "path-page"} <= set(body.get("class", [])), page.name


PAGE_GROUND = ("#f0f4fd", "#eaedff")

BRAND_RAMP = ("#2946F3", "#4A44EA", "#724ADE")


def _light_root(css: str) -> str:
    match = re.search(r":root\s*\{(.*?)\}", css, re.S)
    assert match is not None, "không tìm thấy khối :root"
    return match.group(1)


def test_every_style_owner_declares_the_same_page_ground() -> None:
    shared = _light_root(TAILWIND_LITE_CSS)
    assert f"--ui-bg:{PAGE_GROUND[0]}" in shared.replace(" ", "")
    assert f"--ui-bg-2:{PAGE_GROUND[1]}" in shared.replace(" ", "")

    landing = (ROOT / "src" / "pages" / "build_landing_page.py").read_text(encoding="utf-8")
    landing_root = _light_root(landing)
    assert "--bg:var(--ui-bg)" in landing_root.replace(" ", "")
    assert "--bg-2:var(--ui-bg-2)" in landing_root.replace(" ", "")

    stats = (ROOT / "src" / "pages" / "build_statistics_dashboard.py").read_text(encoding="utf-8")
    stats_root = _light_root(stats)
    assert "--bg:var(--ui-bg)" in stats_root.replace(" ", "")
    assert "--bg-2:var(--ui-bg-2)" in stats_root.replace(" ", "")


def test_brand_ramp_is_identical_wherever_it_is_declared() -> None:
    for name in ("build_landing_page.py", "build_statistics_dashboard.py"):
        source = (ROOT / "src" / "pages" / name).read_text(encoding="utf-8")
        ramps = re.findall(
            r"(?<!repeating-)linear-gradient\(135deg,\s*(#[0-9A-Fa-f]{6})[^)]*?(#[0-9A-Fa-f]{6})"
            r"[^)]*?(#[0-9A-Fa-f]{6})\s*100%\)",
            source,
        )
        assert ramps, f"{name}: không tìm thấy dốc thương hiệu"
        for ramp in ramps:
            assert tuple(c.upper() for c in ramp) == BRAND_RAMP, f"{name}: dốc lạ {ramp}"


def test_shared_stylesheet_reaches_the_page_the_user_actually_opens() -> None:
    index = ROOT / "docs" / "index.html"
    if not index.exists():
        return
    assert "assets/ui.css" in index.read_text(encoding="utf-8")


def test_stat_page_surfaces_are_elevated_like_the_rest_of_the_system() -> None:
    css = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    for block in (".sp-controls{", ".sp-scroll{", ".sp-kpi-card{", ".sp-cell{"):
        start = css.index(block)
        rule = css[start : css.index("}", start)]
        assert "box-shadow" in rule, f"{block} thiếu bóng nổi"


def test_stat_page_css_takes_every_colour_from_a_token() -> None:
    css = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    light, depth = [], 0
    for line in css.splitlines():
        if "prefers-color-scheme: dark" in line:
            depth = 1
            continue
        if depth:
            depth += line.count("{") - line.count("}")
            depth = max(depth, 0)
            continue
        light.append(line)

    stale = {"#94a3b8", "#64748b", "#cbd5e1", "#334155", "#475569", "#f1f5f9", "#e2e8f0"}
    found = sorted({c for c in stale if c in "\n".join(light)})
    assert not found, f"còn hex của bảng màu cũ ở chế độ sáng: {found}"


def test_scroll_box_hugs_its_table_instead_of_stretching() -> None:
    css = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    start = css.index(".sp-scroll{")
    rule = css[start : css.index("}", start)]
    assert "width:fit-content" in rule
    assert "max-width:100%" in rule


from theme_palette_helpers import theme_tokens, resolve_theme_colors

STAT_CSS = "src/web/templates/stat_pages.css"


def _stat_css() -> str:
    return (ROOT / STAT_CSS).read_text(encoding="utf-8")


def test_empty_cell_sinks_by_tone_and_elevation_not_by_hatching() -> None:
    css = _stat_css()
    start = css.index("td.is-empty {")
    rule = css[start : css.index("}", start)]
    assert "background-image: none" in rule, rule
    assert "gradient" not in rule, rule
    assert "box-shadow: none" in rule, rule
    assert "var(--ui-empty-bg)" in rule
    found = re.search(r"background-color:\s*(#[0-9A-Fa-f]{6})", resolve_theme_colors(rule, True))
    assert found, rule
    red, green, blue = (int(found.group(1)[i:i + 2], 16) for i in (1, 3, 5))
    assert 0.2126 * red + 0.7152 * green + 0.0722 * blue < 40, found.group(1)


def test_hit_cell_rises_with_fill_ring_and_shadow() -> None:
    css = _stat_css()
    start = css.index("td.sp-hit {")
    rule = css[start : css.index("}", start)]
    assert "background-color: var(--ui-surface)" in rule
    assert "inset 0 0 0 1px" in rule


def test_every_nhay_tier_has_a_distinct_pair_that_passes_aa() -> None:
    source = _stat_css()
    for dark in (False, True):
        css = resolve_theme_colors(source, dark)
        seen = set()
        for tier in range(1, 6):
            assert f"var(--ui-n{tier}-bg)" in source
            start = css.index(f"td.sp-n{tier} {{")
            rule = css[start : css.index("}", start)]
            bg = re.search(r"background-color:\s*(#[0-9A-Fa-f]{6})", rule).group(1)
            fg = re.search(r"(?<!-)color:\s*(#[0-9A-Fa-f]{6})", rule).group(1)
            assert contrast_ratio(fg, bg) >= WCAG_AA_NORMAL, (dark, tier)
            seen.add(bg)
        assert len(seen) == 5, "hai cấp dùng chung nền thì không còn phân cấp"


def test_nhay_legend_exists_because_the_ramp_has_no_perceptual_order() -> None:
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "renderNhayLegend" in js
    assert "sp-nhay-legend" in _stat_css()


def test_zebra_and_hover_never_repaint_a_data_coloured_cell() -> None:
    css = _stat_css()
    for selector in ("tbody tr:nth-child(even) td", "tbody tr:hover td"):
        idx = css.index(selector)
        head = css[css.rindex("\n", 0, idx) : idx]
        assert ":not(.sp-nhay)" in head, f"{selector} chưa tránh bảng mã màu nháy"


def test_matrix_cells_have_a_fixed_size() -> None:
    css = _stat_css()
    assert "table-layout: fixed" in css
    start = css.index(".sp-table.sp-dense td, .sp-table.sp-dense th {")
    rule = css[start : css.index("}", start)]
    assert "width: 48px" in rule and "height: 24px" in rule


def test_crosshair_covers_the_row_as_well_as_the_column() -> None:
    css = _stat_css()
    assert "tbody tr.row-hint" in css
    assert "td.cell-hint" in css
    js = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert 'classList.add("row-hint")' in js


def test_special_prize_is_red_in_both_themes() -> None:
    css = _stat_css()
    start = css.index(".sp-de b {")
    rule = css[start : css.index("}", start)]
    assert "var(--ui-special-ink)" in rule and "var(--ui-special-bg)" in rule
    assert "font-weight: 800" in rule
    for dark in (False, True):
        values = theme_tokens(dark)
        fg, bg = values["--ui-special-ink"], values["--ui-special-bg"]
        assert int(fg[1:3], 16) > int(fg[3:5], 16), (dark, fg)
        assert contrast_ratio(fg, bg) >= WCAG_AA_NORMAL


def test_matrix_columns_always_have_a_ceiling_of_one_fr() -> None:
    source = (ROOT / "src" / "pages" / "build_landing_page.py").read_text(encoding="utf-8")
    tracks = re.findall(r"grid-template-columns:\s*\d+px\s+repeat\(10,\s*([^)]+)\)", source)
    assert tracks, "không tìm thấy khai báo cột ma trận nào"
    fixed = [t for t in tracks if "1fr" not in t]
    assert not fixed, f"cột ma trận đặt cứng, không giãn được: {fixed}"


BRAND_HUE = 243.0

BRAND_HUE_GUARD = 40.0


def _hsv(hex6: str) -> tuple[float, float, float]:
    import colorsys

    r, g, b = (int(hex6[i : i + 2], 16) for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)


def test_landing_data_marks_never_borrow_the_brand_hue() -> None:
    html_text = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    offenders: list[str] = []
    checked = 0
    for match in re.finditer(r"background:\s*#([0-9a-fA-F]{6})", html_text):
        hue, sat, val = _hsv(match.group(1).lower())
        if sat < 0.35 or val < 0.25:
            continue
        checked += 1
        delta = abs(hue * 360 - BRAND_HUE)
        delta = min(delta, 360 - delta)
        if delta < BRAND_HUE_GUARD:
            offenders.append(f"#{match.group(1)} lệch {delta:.0f}°")

    assert checked > 100, f"chỉ kiểm được {checked} dấu hiệu — bộ lọc hỏng"
    assert not offenders, f"dấu hiệu dữ liệu mang sắc thương hiệu: {sorted(set(offenders))}"


def test_one_measure_uses_one_hue_across_its_time_windows() -> None:
    source = (ROOT / "src" / "pages" / "build_landing_page.py").read_text(encoding="utf-8")

    groups = {
        "tần suất LOTO": [
            "Tần suất 00–99 trong ngày kết quả mới nhất.",
            "Cộng dồn LOTO trong tuần hiện tại.",
            "Cộng dồn LOTO trong tháng hiện tại.",
            "Cộng dồn LOTO trong năm hiện tại.",
        ],
        "tần suất Đặc Biệt": [
            "Tần suất 2 số cuối giải Đặc Biệt trong tháng.",
            "Tần suất 2 số cuối giải Đặc Biệt trong năm.",
        ],
    }
    for name, subtitles in groups.items():
        seen = set()
        for sub in subtitles:
            start = source.index(sub)
            pal = re.search(r'palette="([a-z]+)"', source[start:])
            assert pal, f"{name}: không tìm thấy palette sau {sub!r}"
            seen.add(pal.group(1))
        assert len(seen) == 1, f"{name} dùng {len(seen)} sắc cho một phép đo: {sorted(seen)}"


def test_design_system_doc_only_cites_tests_that_exist() -> None:
    doc = ROOT / "documentation" / "architecture" / "ui-design-system.md"
    assert doc.exists(), "thiếu tài liệu hệ thiết kế"

    cited = set(re.findall(r"test_[a-z0-9_]+", doc.read_text(encoding="utf-8")))
    assert len(cited) >= 15, f"tài liệu chỉ dẫn {len(cited)} phép kiểm — có vẻ đã bị cắt"

    defined = set()
    test_files = sorted((ROOT / "tests").rglob("test_*.py"))
    assert len(test_files) > 100, len(test_files)
    for path in test_files:
        defined |= set(re.findall(r"^def (test_[a-z0-9_]+)", path.read_text(encoding="utf-8"), re.M))

    missing = sorted(cited - defined - {"test_design_system_doc_only_cites_tests_that_exist"})
    assert not missing, f"tài liệu dẫn phép kiểm không tồn tại: {missing}"
