"""Kiểm thử hệ thống thiết kế dùng chung cho trang tĩnh.

Các trang được sinh ra phải tự chứa (CSP ``default-src 'self'``), có khung căn
giữa, bảng canh cột đúng loại dữ liệu và lưới không vượt quá 12 cột.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from ui_theme import (
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

ROOT = Path(__file__).resolve().parents[1]


def test_theme_stays_self_contained_without_external_assets() -> None:
    """Không tài nguyên nào được lấy từ tên miền khác.

    Điều cần canh là *nguồn gốc*, không phải sự có mặt của ``url()``. CSP đặt
    ``font-src 'self'`` nên một URL tương đối trỏ tới tệp cạnh biểu định kiểu
    hoàn toàn hợp lệ — và đó chính là cách phông Inter được phân phối. Phép
    kiểm cũ cấm mọi ``url()`` nên cũng cấm luôn cách làm đúng.
    """
    style = tailwind_style_tag()
    assert "https://" not in style
    assert "http://" not in style
    assert "//" not in style.replace("://", "")
    assert "@import" not in style
    for url in re.findall(r'url\("?([^")]+)"?\)', style):
        assert not url.startswith(("http", "//", "data:")), f"tài nguyên ngoài: {url}"


def test_theme_keeps_layout_and_component_primitives() -> None:
    for token in (
        ".vla-shell",
        ".vla-card",
        ".vla-table",
        ".vla-badge",
        ".vla-grid",
    ):
        assert token in TAILWIND_LITE_CSS, token
    # Container căn giữa và có padding tăng dần theo breakpoint.
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
    assert "vla-al" in cells[0]["class"]
    assert "vla-ac" in cells[1]["class"]
    assert "vla-ar" in cells[2]["class"]
    # Bảng luôn nằm trong vùng cuộn ngang riêng.
    assert soup.find("div", class_="vla-table-wrap") is not None


def test_render_table_infers_alignment_from_cell_values() -> None:
    """Fallback suy luận theo giá trị: số canh phải, chữ canh trái."""
    soup = BeautifulSoup(
        render_table(
            ["Nhãn", "Số", "Xác suất"], [["Lô tô", "83", "0.2491"]]
        ),
        "html.parser",
    )
    cells = soup.find_all("td")
    assert "vla-al" in cells[0]["class"]
    # Chuỗi chữ số vẫn là giá trị số nên được canh phải khi không khai báo align.
    assert "vla-ar" in cells[1]["class"]
    assert "vla-ar" in cells[2]["class"]


def test_explicit_align_overrides_numeric_inference_for_key_columns() -> None:
    """Cột khóa dạng số (ví dụ số lô tô) canh trái được khi khai báo rõ."""
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
    assert "vla-al" in cells[0]["class"]
    assert "vla-key" in cells[0]["class"]
    assert "vla-ar" in cells[1]["class"]


def test_render_table_escapes_untrusted_cell_content() -> None:
    out = render_table(["x"], [["<script>alert(1)</script>"]])
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_dataframe_table_reports_empty_frames_instead_of_raising() -> None:
    assert "vla-table-empty" in dataframe_table(pd.DataFrame())
    assert "vla-table-empty" in dataframe_table(None)


def test_dataframe_table_renders_every_row_and_column() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    soup = BeautifulSoup(dataframe_table(frame), "html.parser")
    assert len(soup.find_all("tr")) == 4  # 1 header + 3 dòng dữ liệu
    assert len(soup.find_all("th")) == 2


def test_card_span_is_clamped_into_the_twelve_column_grid() -> None:
    assert "vla-c8" in card("x", span=8)
    assert "vla-c12" in card("x", span=99)
    assert "vla-c1" in card("x", span=-3)


def test_page_header_and_nav_escape_input() -> None:
    assert "&lt;b&gt;" in page_header("<b>t</b>")
    assert "&lt;b&gt;" in nav_links([("a.html", "<b>x</b>")])
    assert 'aria-current="page"' in nav_links([("a.html", "x")], current="a.html")


def _grid_rows_do_not_overflow(page: Path) -> None:
    """Tổng span của các card trong một lưới không được vượt 12 cột."""
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    for grid in soup.find_all("div", class_="vla-grid"):
        used = 0
        for section in grid.find_all("section", class_="vla-card", recursive=False):
            spans = [
                int(m.group(1))
                for cls in section.get("class", [])
                if (m := re.fullmatch(r"vla-c(\d+)", cls))
            ]
            span = spans[0] if spans else 12
            used = span if used + span > 12 else used + span
            assert span <= 12, f"{page.name}: span {span} vượt 12 cột"


def test_generated_dashboard_pages_use_the_shared_shell_and_grid(tmp_path: Path) -> None:
    # Dựng vào thư mục tạm: chạy thẳng vào docs/ của kho khiến mỗi lần chạy
    # pytest là cây làm việc bẩn, và bẩn theo dạng "ngược pha" vì chuỗi builder
    # đầy đủ cho ra HTML khác với một builder chạy lẻ.
    subprocess.run(
        [sys.executable, "src/build_dashboard.py", "--docs-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
    )

    for name in ("dashboard.html", "model-quality.html"):
        page = tmp_path / name
        text = page.read_text(encoding="utf-8")
        assert "vla-shell" in text, name
        assert "https://" not in text, name
        # Không còn body margin cứng của bản cũ.
        assert "margin: 24px" not in text and "margin:24px" not in text, name
        _grid_rows_do_not_overflow(page)


def test_shell_open_offers_a_wide_variant() -> None:
    assert "vla-shell-wide" in shell_open(wide=True)
    assert "vla-shell-wide" not in shell_open()


# --- Hồi quy cho các lỗi bố cục/tương phản đã sửa -------------------------


def test_theme_does_not_force_heading_colour_globally() -> None:
    """Màu tiêu đề phải giới hạn trong khung của hệ thống này.

    Đặt màu ở cấp ``h1..h4`` toàn cục từng làm tiêu đề hero nền tối của trang
    landing trùng màu nền (tương phản ~1:1).
    """
    assert "h1,h2,h3,h4{font-weight:600" in TAILWIND_LITE_CSS
    assert ".vla-shell h1" in TAILWIND_LITE_CSS
    # Không còn quy tắc gán màu trực tiếp cho h1..h4 không phạm vi.
    assert "h1,h2,h3,h4{color:" not in TAILWIND_LITE_CSS


def test_path_ui_template_does_not_apply_light_classes_to_dark_page() -> None:
    """Trang soi cầu dùng nền tối; class chủ đề sáng làm chữ chìm vào nền."""
    template = (ROOT / "src/templates/path_ui_page.html.j2").read_text(
        encoding="utf-8"
    )
    assert "<body>" in template
    assert "bg-slate-50" not in template
    assert "text-slate-800" not in template


def test_statistics_matrix_fits_ten_tail_columns_in_a_half_width_card() -> None:
    """Ngưỡng cũ 660px rộng hơn card nên cột ĐUÔI 9 bị đẩy khỏi vùng nhìn."""
    source = (ROOT / "src/build_statistics_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "grid-template-columns: 40px repeat(10, minmax(38px, 1fr));" in source
    assert "min-width: 464px;" in source
    assert "min-width: 660px;" not in source


def test_statistics_section_nav_wraps_instead_of_hiding_links() -> None:
    """Cuộn ngang khiến các mục nav cuối bị ẩn khỏi tầm nhìn."""
    source = (ROOT / "src/build_statistics_dashboard.py").read_text(
        encoding="utf-8"
    )
    nav = source[source.index(".sticky-nav {{") : source.index(".sticky-nav a {{")]
    assert "flex-wrap: wrap;" in nav
    assert "overflow-x: auto;" not in nav


def test_landing_grid_items_can_shrink_below_their_content_width() -> None:
    """Grid item mặc định min-width:auto làm ma trận 430px đẩy tràn trang."""
    source = (ROOT / "src/build_landing_page.py").read_text(encoding="utf-8")
    assert ".result-combo > * {{ min-width: 0; }}" in source
    # Ma trận ngày phải nằm trong khung cuộn riêng.
    assert "<div class='matrix-wrap'><div class='tiny-matrix'>" in source
    # Ngưỡng cột cũ vượt bề rộng khả dụng của .main sau khi trừ sidebar.
    assert "minmax(760px, 1fr) minmax(360px, 440px)" not in source


def test_column_align_helpers_cover_expected_columns() -> None:
    """Bảng ghép chuỗi thủ công canh lề qua class theo vị trí cột."""
    for index in (1, 5, 10):
        assert f".vla-table.vla-r{index} td:nth-child({index})" in TAILWIND_LITE_CSS
        assert f".vla-table.vla-m{index} td:nth-child({index})" in TAILWIND_LITE_CSS
    # Cột số canh phải phải giữ trên một dòng.
    assert "text-align:right;white-space:nowrap" in TAILWIND_LITE_CSS


def test_published_path_pages_do_not_ship_light_theme_classes() -> None:
    """Kiểm chính file đã sinh, không chỉ template.

    Sửa template là chưa đủ: trang trong ``docs/`` mới là thứ GitHub Pages phục
    vụ. Lần trước template đã sửa nhưng HTML chưa sinh lại nên site vẫn chạy
    bản chữ tối trên nền tối.
    """
    pages = sorted((ROOT / "docs").glob("soi-path-*.html"))
    assert pages, "không tìm thấy trang soi cầu đã sinh"
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert '<body class="bg-slate-50' not in text, page.name
        assert "text-slate-800" not in text, page.name
        assert "<body>" in text, page.name


# --- Hệ thiết kế phải nằm ở LỚP DÙNG CHUNG, không ở một trang lẻ -----------
#
# Ba chủ thể tạo kiểu độc lập nhau cùng tồn tại trong kho:
#
#   src/ui_theme.py                  -> docs/assets/vla.css -> 28 trang
#   src/build_landing_page.py        -> :root riêng         -> trang chủ
#   src/build_statistics_dashboard.py-> CSS nội tuyến riêng  -> 1 trang
#
# Một lần đổi giao diện chỉ chạm vào chủ thể thứ ba đã xảy ra rồi: trang
# statistics đổi hẳn sang nền periwinkle, còn trang chủ — trang người dùng
# thực sự mở — giữ nguyên hero navy cũ. Nhìn từ phía người dùng thì đó là
# "không có gì thay đổi cả", và không một test nào đỏ.
#
# Hai phép kiểm dưới đây neo ba chủ thể vào cùng một mặt đất và cùng một dốc
# thương hiệu, nên lần sau sửa lệch một chủ thể sẽ đỏ ngay tại chỗ sửa.

#: Mặt đất của trang ở chế độ sáng. Mọi chủ thể tạo kiểu phải khai cùng giá trị.
PAGE_GROUND = ("#F2F4FF", "#E6EAFB")

#: Dốc thương hiệu dành riêng cho điều hướng và hành động chính.
BRAND_RAMP = ("#4F46E5", "#4C3BC4", "#5B2E9E")


def _light_root(css: str) -> str:
    """Khối ``:root`` đầu tiên — khối của chế độ sáng."""
    match = re.search(r":root\s*\{(.*?)\}", css, re.S)
    assert match is not None, "không tìm thấy khối :root"
    return match.group(1)


def test_every_style_owner_declares_the_same_page_ground() -> None:
    """Trang chủ, biểu định kiểu chung và trang thống kê đứng trên cùng nền.

    Đây là phép kiểm bắt được lỗi "đổi giao diện mà người dùng không thấy gì
    khác": nó so ba chủ thể với nhau chứ không so từng chủ thể với chính nó.
    """
    shared = _light_root(TAILWIND_LITE_CSS)
    assert f"--vla-bg:{PAGE_GROUND[0]}" in shared.replace(" ", "")
    assert f"--vla-bg-2:{PAGE_GROUND[1]}" in shared.replace(" ", "")

    landing = (ROOT / "src" / "build_landing_page.py").read_text(encoding="utf-8")
    landing_root = _light_root(landing)
    assert f"--bg:{PAGE_GROUND[0]}" in landing_root.replace(" ", "")
    assert f"--bg-2:{PAGE_GROUND[1]}" in landing_root.replace(" ", "")

    stats = (ROOT / "src" / "build_statistics_dashboard.py").read_text(encoding="utf-8")
    stats_root = _light_root(stats)
    assert f"--bg:{PAGE_GROUND[0]}" in stats_root.replace(" ", "")
    assert f"--bg-2:{PAGE_GROUND[1]}" in stats_root.replace(" ", "")


def test_brand_ramp_is_identical_wherever_it_is_declared() -> None:
    """Dốc thương hiệu chỉ có MỘT bộ chặng.

    Ba chặng này đã được dò tương phản trên toàn dải với chữ trắng
    (6,29 / 7,69 / 9,02 : 1). Khai một bộ chặng thứ hai ở nơi khác là mở lại
    khả năng một chặng chưa ai đo lọt vào trang.
    """
    for name in ("build_landing_page.py", "build_statistics_dashboard.py"):
        source = (ROOT / "src" / name).read_text(encoding="utf-8")
        ramps = re.findall(
            r"(?<!repeating-)linear-gradient\(135deg,\s*(#[0-9A-Fa-f]{6})[^)]*?(#[0-9A-Fa-f]{6})"
            r"[^)]*?(#[0-9A-Fa-f]{6})\s*100%\)",
            source,
        )
        assert ramps, f"{name}: không tìm thấy dốc thương hiệu"
        for ramp in ramps:
            assert tuple(c.upper() for c in ramp) == BRAND_RAMP, f"{name}: dốc lạ {ramp}"


def test_shared_stylesheet_reaches_the_page_the_user_actually_opens() -> None:
    """``index.html`` phải nạp biểu định kiểu chung.

    Trang chủ có ``:root`` riêng nên dễ tưởng nó tự lo hết phần tạo kiểu. Thực
    tế nó vẫn lấy phông, bảng, thẻ và nav từ ``vla.css``; mất liên kết đó thì
    trang vỡ mà các test dựng trang vẫn xanh.
    """
    index = ROOT / "docs" / "index.html"
    if not index.exists():  # kho mới sao chép, chưa dựng docs
        return
    assert "assets/vla.css" in index.read_text(encoding="utf-8")


def test_stat_page_surfaces_are_elevated_like_the_rest_of_the_system() -> None:
    """Các khối "thẻ" của nhóm trang thống kê phải có bóng nổi.

    ``stat_pages.css`` là chủ thể tạo kiểu THỨ TƯ của kho — nó cấp phát
    ``.sp-*`` cho 14 trang thống kê. Lần đổi giao diện trước bỏ sót nó, nên
    nhóm trang nhận được mặt đất mới mà thành phần bên trên vẫn phẳng lì.
    """
    css = (ROOT / "src" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    for block in (".sp-controls{", ".sp-scroll{", ".sp-kpi-card{", ".sp-cell{"):
        start = css.index(block)
        rule = css[start : css.index("}", start)]
        assert "box-shadow" in rule, f"{block} thiếu bóng nổi"


def test_stat_page_css_takes_every_colour_from_a_token() -> None:
    """Không hex cứng nào của bảng màu cũ còn sót ở chế độ sáng.

    Đây chính là lý do nhóm trang "trông y như cũ": các giá trị slate viết
    thẳng không đi qua token nên chúng không theo nền mới. Khối chế độ tối
    được miễn — ở đó hex là lựa chọn có chủ đích.
    """
    css = (ROOT / "src" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
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
    """Hộp trắng phải ôm lấy bảng.

    ``.sp-table`` cố ý dùng ``width:auto`` để cột không giãn ra cả gang tay,
    nhưng hộp chứa là ``display:block`` nên nó vẫn nở hết khung: trang Lô gan
    có bảng 5 cột rộng ~500px nằm giữa một mảng trắng rộng 1330px.
    """
    css = (ROOT / "src" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    start = css.index(".sp-scroll{")
    rule = css[start : css.index("}", start)]
    assert "width:fit-content" in rule
    assert "max-width:100%" in rule


# --- Kết quả rà soát giao diện: khoá từng mục lại ---------------------------
#
# Mỗi phép kiểm dưới đây tương ứng một mục ĐÃ TRƯỢT trong lần rà soát, kèm con
# số đo được lúc trượt. Ghi số vào đây để lần sau ai đọc cũng biết ngưỡng này
# từ đâu ra, thay vì tưởng là con số tuỳ ý.

STAT_CSS = "src/templates/stat_pages.css"


def _stat_css() -> str:
    return (ROOT / STAT_CSS).read_text(encoding="utf-8")


def test_empty_cell_sinks_with_solid_fill_and_visible_hatch() -> None:
    """Ô KHÔNG VỀ phải có nền đặc và vân đủ đậm để nhìn thấy.

    Trước: nền trong suốt, vân vẽ bằng --vla-border (#E7EAF6). Đo trên trang
    đã dựng, ô trống và ô có về cùng đứng trên nền trắng — 1,00:1 — nên mắt
    phải dò từng ô. Trên bảng 100x90 đó là mỏi mắt thật.
    """
    css = _stat_css()
    start = css.index("td.is-empty {")
    rule = css[start : css.index("}", start)]
    assert "background-color: #E2E8F0" in rule
    assert "rgba(100, 116, 139, .38)" in rule


def test_hit_cell_rises_with_fill_ring_and_shadow() -> None:
    """Ô CÓ VỀ phải nổi: nền riêng, viền trong, và bóng."""
    css = _stat_css()
    start = css.index("td.sp-hit {")
    rule = css[start : css.index("}", start)]
    assert "background-color: var(--vla-surface)" in rule
    assert "inset 0 0 0 1px" in rule


def test_every_nhay_tier_has_a_distinct_pair_that_passes_aa() -> None:
    """Năm cấp số nháy, mỗi cấp một cặp nền/chữ riêng, tất cả đạt AA."""
    css = _stat_css()
    expected = {
        "sp-n1": ("#FFFFFF", "#161C2D"),
        "sp-n2": ("#DBEAFE", "#1D4ED8"),
        "sp-n3": ("#D1FAE5", "#047857"),
        "sp-n4": ("#FFEDD5", "#9A3412"),
        "sp-n5": ("#5B21B6", "#FFFFFF"),
    }
    seen = set()
    for cls, (bg, fg) in expected.items():
        start = css.index(f"td.{cls} {{")
        rule = css[start : css.index("}", start)]
        assert bg in rule and fg in rule, f"{cls} sai cặp màu"
        assert contrast_ratio(fg, bg) >= WCAG_AA_NORMAL, f"{cls} trượt AA"
        seen.add(bg)
    assert len(seen) == 5, "hai cấp dùng chung một nền thì không còn phân cấp"


def test_nhay_legend_exists_because_the_ramp_has_no_perceptual_order() -> None:
    """Phải có chú giải.

    Xanh dương -> xanh lá -> cam không có trật tự tri giác: người đọc không
    tự suy ra 3 nháy nhiều hơn 2. Thiếu chú giải thì bảng màu chỉ là màu.
    """
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "renderNhayLegend" in js
    assert "sp-nhay-legend" in _stat_css()


def test_zebra_and_hover_never_repaint_a_data_coloured_cell() -> None:
    """Trợ giúp điều hướng không được đè lên nền đang mang dữ liệu.

    Sọc ngựa vằn và nền hover cùng vẽ ``background`` lên đúng ô mà cấp nháy
    đang dùng, và chúng cụ thể hơn nên chúng thắng: đo được ô "4 nháy" ở hàng
    chẵn mất sạch nền cam. Một nửa số hàng bị xoá thông tin.
    """
    css = _stat_css()
    for selector in ("tbody tr:nth-child(even) td", "tbody tr:hover td"):
        idx = css.index(selector)
        head = css[css.rindex("\n", 0, idx) : idx]
        assert ":not(.sp-nhay)" in head, f"{selector} chưa tránh bảng mã màu nháy"


def test_matrix_cells_have_a_fixed_size() -> None:
    """Ô ma trận không được co giãn theo nội dung.

    Đo được bề rộng chạy từ 26 tới 44px, nên lưới răng cưa và mắt không dóng
    thẳng theo cột được. 48px chứ không phải 40: nhãn ngày rộng nhất đo được
    34,6px + padding 8px, đặt 40 thì 52/90 tiêu đề bị cắt.
    """
    css = _stat_css()
    assert "table-layout: fixed" in css
    start = css.index(".sp-table.sp-dense td, .sp-table.sp-dense th {")
    rule = css[start : css.index("}", start)]
    assert "width: 48px" in rule and "height: 24px" in rule


def test_crosshair_covers_the_row_as_well_as_the_column() -> None:
    """Dóng chữ thập phải có đủ hai nửa.

    Nửa theo cột đã có từ trước; nửa theo hàng thì không — mà trên ma trận
    100 hàng thì dóng ngược lại mới là việc khó hơn.
    """
    css = _stat_css()
    assert "tbody tr.row-hint" in css
    assert "td.cell-hint" in css
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert 'classList.add("row-hint")' in js


def test_special_prize_is_red_in_both_themes() -> None:
    """Giải ĐẶC BIỆT luôn đỏ, đậm, có nền và viền đỏ nhạt — ở cả hai chế độ.

    Chế độ tối từng ghi đè về #e2e8f0, tức là mất hẳn màu đỏ. Giữ nguyên
    #BE123C ở nền tối thì chìm (2,49:1), nên dùng #FDA4AF trên #4C0519 (8,27:1).
    """
    css = _stat_css()
    start = css.index(".sp-de b {")
    rule = css[start : css.index("}", start)]
    assert "#BE123C" in rule and "#FFE4E6" in rule and "font-weight: 800" in rule
    assert contrast_ratio("#BE123C", "#FFE4E6") >= WCAG_AA_NORMAL

    dark = css[css.index("@media (prefers-color-scheme: dark)") :]
    assert "#FDA4AF" in dark, "chế độ tối đánh mất màu đỏ của giải đặc biệt"
    assert contrast_ratio("#FDA4AF", "#4C0519") >= WCAG_AA_NORMAL


def test_matrix_columns_always_have_a_ceiling_of_one_fr() -> None:
    """Cột ma trận không được đặt cứng.

    Một khai báo như ``repeat(10, 36px)`` có SÀN mà không có TRẦN: cột đứng
    yên ở 36px dù khung rộng bao nhiêu, và phần dôi ra thành mảng trắng bên
    phải. Đo ở khung 600px trước khi sửa: lưới rộng 546px, cột chiếm 444px —
    thừa 102px, đúng khoảng trắng người dùng nhìn thấy.

    ``minmax(<sàn>, 1fr)`` giữ nguyên hành vi cuộn khi khung chật (nhờ
    ``min-width`` trên chính lưới) và cho cột giãn lấp đầy khi khung rộng.
    """
    source = (ROOT / "src" / "build_landing_page.py").read_text(encoding="utf-8")
    tracks = re.findall(r"grid-template-columns:\s*\d+px\s+repeat\(10,\s*([^)]+)\)", source)
    assert tracks, "không tìm thấy khai báo cột ma trận nào"
    fixed = [t for t in tracks if "1fr" not in t]
    assert not fixed, f"cột ma trận đặt cứng, không giãn được: {fixed}"
