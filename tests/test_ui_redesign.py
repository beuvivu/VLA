"""Kiểm thử đợt tái thiết kế giao diện.

Các test ở đây khóa lại những kết quả đã đo bằng trình duyệt thật, và khóa lại
ba lỗi đã sửa để chúng không quay lại một cách âm thầm.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from ui_theme import SITE_NAV, STYLESHEET_NAME, TAILWIND_LITE_CSS, nav_targets

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.glob("*.html"))

#: landing.html và landing_desktop.html là hai biến thể của index.html (cùng nội
#: dung, khác chế độ hiển thị), không phải đích điều hướng riêng.
INDEX_ALIASES = {"landing.html", "landing_desktop.html"}


def _soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def _css(path: Path) -> str:
    """CSS thực sự áp lên một trang, đã bỏ hết khoảng trắng.

    Trang landing nhúng thẳng CSS vào <style>; các trang dùng khung chung lại
    liên kết tới biểu định kiểu dùng chung. Đọc mỗi phần thân trang sẽ không
    thấy quy tắc nào của khung chung, nên khẳng định về CSS phải gộp cả hai
    nguồn — nếu không, test hoặc bỏ sót trang hoặc báo sai.

    Args:
        path: Đường dẫn tệp HTML trong ``docs/``.

    Returns:
        Chuỗi CSS đã nối và nén khoảng trắng.
    """
    text = path.read_text(encoding="utf-8")
    parts = [text]
    for link in _soup(path).find_all("link", rel="stylesheet"):
        href = link.get("href") or ""
        sheet = path.parent / href
        if sheet.exists() and sheet.suffix == ".css":
            parts.append(sheet.read_text(encoding="utf-8"))
    return "".join(parts).replace(" ", "").replace("\n", "")


#: Các trang thực sự gắn dock, xét theo lớp trong HTML.
DOCK_PAGES = [p for p in PAGES if "dock-inner" in p.read_text(encoding="utf-8")]

#: Các trang có khối điều hướng dự phòng ở chân trang.
FOOTER_PAGES = [p for p in PAGES if "nav-fallback" in p.read_text(encoding="utf-8")]


def test_pages_exist() -> None:
    assert len(PAGES) >= 14, "thiếu trang đã sinh; hãy chạy lại bộ dựng"


# --- Font ------------------------------------------------------------------


def test_shared_css_declares_self_hosted_inter_first() -> None:
    """Phông đầu chuỗi phải là phông ta THẬT SỰ phân phối được.

    Bản trước khai báo Aptos, nhưng CSP đặt ``font-src 'self'`` và kho không có
    tệp phông nào — nên trang chưa bao giờ hiển thị bằng Aptos trừ máy đã cài
    sẵn Microsoft 365. Aptos cũng không được phép phân phối lại nên không thể
    tự host hợp pháp.
    """
    match = re.search(r"--vla-font:([^;]+);", TAILWIND_LITE_CSS)
    assert match, "không tìm thấy token --vla-font"
    assert match.group(1).strip().startswith('"Inter var"')


def test_shared_css_has_a_real_fallback_chain() -> None:
    """Phông tải chậm hoặc hỏng thì vẫn phải có chuỗi dự phòng hợp lệ."""
    match = re.search(r"--vla-font:([^;]+);", TAILWIND_LITE_CSS)
    families = [f.strip().strip('"') for f in match.group(1).split(",")]
    assert "system-ui" in families
    assert families[-1] == "sans-serif"


def test_font_face_points_at_a_file_that_exists() -> None:
    """Khai báo @font-face trỏ tới tệp không tồn tại là một tham chiếu chết."""
    match = re.search(r'src:url\("([^"]+)"\)', TAILWIND_LITE_CSS)
    assert match, "không tìm thấy @font-face"
    assert (DOCS / "assets" / match.group(1)).exists()


def test_font_face_covers_the_whole_weight_range() -> None:
    """Bản variable phải khai báo đủ dải, nếu không trình duyệt tự làm đậm giả."""
    assert "font-weight:100 900" in TAILWIND_LITE_CSS


def test_font_display_swap_avoids_invisible_text() -> None:
    """Thiếu font-display:swap thì chữ vô hình trong lúc tải 172 KB phông."""
    assert "font-display:swap" in TAILWIND_LITE_CSS


def _effective_css(page: Path) -> str:
    """CSS thực sự áp lên trang: khối nội tuyến cộng biểu định kiểu đã liên kết.

    Sau khi tách CSS ra tệp rời, tìm chuỗi font trong HTML là kiểm sai chỗ —
    font nằm trong tệp được liên kết chứ không còn trong trang.
    """
    text = page.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "html.parser")
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href") or ""
        target = (page.parent / href).resolve()
        if target.exists():
            text += target.read_text(encoding="utf-8")
    return text


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_resolves_to_the_aptos_stack(page: Path) -> None:
    assert "Aptos" in _effective_css(page)


def test_no_page_loads_a_font_from_an_external_host() -> None:
    """CSP đặt font-src 'self', và giấy phép Aptos cấm phân phối lại tệp font.

    Nhúng tệp font sẽ vừa bị trình duyệt chặn im lặng, vừa đưa kho công khai
    này vào tình trạng vi phạm giấy phép của Microsoft.
    """
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in text, page.name
        assert "fonts.gstatic.com" not in text, page.name
        assert "@font-face" not in text, page.name


def test_only_the_licensed_font_is_distributed() -> None:
    """Chỉ được phân phối phông có giấy phép cho phép, và phải kèm giấy phép.

    Đảo ngược hẳn phép kiểm cũ ("không được có tệp phông nào"), vốn đúng khi
    phông duy nhất được nhắc tới là Aptos — thứ không được phép redistribute.
    Inter theo SIL OFL thì được, với điều kiện giữ nguyên văn bản giấy phép đi
    kèm; đó chính là điều kiện phép kiểm này canh.
    """
    fonts = [f for suffix in ("*.woff", "*.woff2", "*.ttf", "*.otf") for f in DOCS.rglob(suffix)]
    assert [f.name for f in fonts] == ["InterVariable.woff2"], (
        f"chỉ phân phối phông đã cấp phép, thấy: {[f.name for f in fonts]}"
    )
    assert (DOCS / "assets" / "Inter-LICENSE.txt").exists(), "thiếu giấy phép đi kèm phông"
    assert "SIL Open Font License" in (DOCS / "assets" / "Inter-LICENSE.txt").read_text(
        encoding="utf-8"
    )


# --- Biểu định kiểu dùng chung --------------------------------------------


def test_shared_stylesheet_is_written() -> None:
    assert (DOCS / STYLESHEET_NAME).exists()


def test_shared_stylesheet_matches_the_source() -> None:
    assert (DOCS / STYLESHEET_NAME).read_text(encoding="utf-8") == TAILWIND_LITE_CSS


def test_pages_link_the_shared_stylesheet_instead_of_inlining_it() -> None:
    """250 KB CSS nội tuyến lặp trên 14 trang không dùng lại được cache."""
    linked = 0
    for page in PAGES:
        hrefs = [link.get("href") for link in _soup(page).find_all("link", rel="stylesheet")]
        if STYLESHEET_NAME in hrefs:
            linked += 1
    assert linked >= 10, f"chỉ {linked}/{len(PAGES)} trang dùng biểu định kiểu chung"


# --- Chế độ tối ------------------------------------------------------------


def test_dark_theme_covers_all_three_viewer_states() -> None:
    """Mặc định "theo hệ điều hành" không gắn thuộc tính nào lên thẻ gốc."""
    assert "prefers-color-scheme:dark" in TAILWIND_LITE_CSS.replace(" ", "")
    assert 'data-vla-theme="dark"' in TAILWIND_LITE_CSS
    assert 'not([data-vla-theme="light"])' in TAILWIND_LITE_CSS.replace(" ", "")


# --- Sidebar thu gọn -------------------------------------------------------


def test_sidebar_is_gone_from_every_page() -> None:
    """Sidebar chiếm 292px trên màn 1680px — 17,4% chiều ngang cho 17 liên kết."""
    for page in PAGES:
        soup = _soup(page)
        assert not soup.select(".sidebar, .vla-side"), f"{page.name} vẫn còn sidebar"


def test_dock_replaces_it_on_the_main_pages() -> None:
    for page in DOCK_PAGES:
        soup = _soup(page)
        assert soup.select(".dock, .vla-dock"), f"{page.name} thiếu dock"


def test_dock_shows_one_button_per_navigation_group() -> None:
    """17 đích là quá nhiều cho một dock; gom theo 5 nhóm của SITE_NAV.

    Trang landing có thêm một nhóm "Trên trang" chứa neo cuộn nội bộ, nên số
    nút là 5 hoặc 6 — phép kiểm canh cận dưới và cận trên chứ không ghim cứng.
    """
    for page in DOCK_PAGES:
        soup = _soup(page)
        buttons = soup.select(".dock-btn, .vla-dock-btn")
        assert len(SITE_NAV) <= len(buttons) <= len(SITE_NAV) + 1, (
            f"{page.name}: {len(buttons)} nút / {len(SITE_NAV)} nhóm"
        )


def test_dock_popovers_reach_every_destination() -> None:
    """Mọi đích của SITE_NAV phải tới được; neo trong trang là phần thêm."""
    for page in DOCK_PAGES:
        soup = _soup(page)
        hrefs = {a.get("href") for a in soup.select(".dock-pop a, .vla-dock-pop a")}
        expected = {href for _, items in SITE_NAV for href, _, _ in items}
        assert expected <= hrefs, f"{page.name}: thiếu {sorted(expected - hrefs)}"


def test_landing_dock_keeps_in_page_anchors() -> None:
    """Bỏ sidebar cũng bỏ neo cuộn; trang này cao khoảng 12 000px."""
    hrefs = {a.get("href") for a in _soup(DOCS / "index.html").select(".dock-pop a")}
    anchors = {h for h in hrefs if h and h.startswith("#")}
    assert len(anchors) >= 10, f"chỉ còn {len(anchors)} neo trong trang"
    for required in ("#tong-quan", "#ket-qua", "#duong-cau", "#backtest"):
        assert required in anchors, required


def test_dock_popovers_open_on_focus_not_only_hover() -> None:
    """Chỉ mở bằng :hover thì người dùng bàn phím không tới được mục con."""
    css = (DOCS / "index.html").read_text(encoding="utf-8") + TAILWIND_LITE_CSS
    assert "focus-within" in css


def test_dock_magnification_uses_the_agreed_easing() -> None:
    """Đường cong đã đổi từ cubic-bezier(.25,1,.5,1) sang ease-in-out.

    Bản vẽ đầu dùng đường cong vọt-rồi-hãm cho cảm giác "nảy" kiểu macOS. Bản
    sửa lỗi yêu cầu ease-in-out: vào và ra đối xứng, không vọt quá, hợp với
    thanh dock đã thu gọn còn 54px nơi một cú nảy 4px trông như giật.
    """
    css = _css(DOCS / "index.html") + TAILWIND_LITE_CSS.replace(" ", "")
    assert "transition:transform.24sease-in-out" in css


def test_dock_motion_respects_reduced_motion_preference() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8") + TAILWIND_LITE_CSS
    assert "prefers-reduced-motion" in css


def test_no_page_is_a_navigation_dead_end() -> None:
    """Bốn trang soi cầu, research-lab và live từng không có <nav> nào."""
    for page in PAGES:
        assert _soup(page).select("nav a"), f"{page.name} không có liên kết điều hướng nào"


# --- Điều hướng ------------------------------------------------------------


def test_navigation_covers_every_generated_page() -> None:
    """Hai trang cầu ổn định từng không được liên kết từ bất kỳ đâu."""
    missing = {p.name for p in PAGES} - nav_targets() - INDEX_ALIASES
    assert not missing, f"trang không có trong điều hướng: {sorted(missing)}"


def test_navigation_groups_are_the_agreed_set() -> None:
    """Bảy nhóm. Hai nhóm "Bảng đặc biệt" và "Lô tô chi tiết" được thêm khi
    dựng mười trang thống kê riêng; trước đó chỉ có năm."""
    assert [group for group, _ in SITE_NAV] == [
        "Trực tiếp",
        "Thống kê",
        "Cầu kèo",
        "Phỏng đoán",
        "Bảng đặc biệt",
        "Lô tô chi tiết",
        "Tool nâng cao",
    ]


def test_every_navigation_group_has_entries() -> None:
    """Một nhóm rỗng vẫn hiện nút trên dock nhưng popover trống trơn."""
    for group, items in SITE_NAV:
        assert items, f"nhóm {group!r} không có mục nào"


def test_navigation_labels_are_unique_within_a_group() -> None:
    for group, items in SITE_NAV:
        labels = [label for _href, label, _icon in items]
        assert len(labels) == len(set(labels)), f"nhãn trùng trong nhóm {group!r}"


def test_landing_links_out_to_the_other_pages() -> None:
    soup = _soup(DOCS / "index.html")
    hrefs = {a.get("href", "") for a in soup.find_all("a")}
    for page in ("soi-path-de-stable.html", "soi-path-loto-stable.html", "live.html"):
        assert page in hrefs, page


def test_no_navigation_anchor_is_dead() -> None:
    soup = _soup(DOCS / "index.html")
    ids = {el.get("id") for el in soup.find_all(attrs={"id": True})}
    dead = [
        a.get("href")
        for a in soup.find_all("a")
        if (a.get("href") or "").startswith("#") and a["href"][1:] not in ids
    ]
    assert not dead, f"neo chết: {dead}"


# --- Lỗi 1: JSON thô trên dashboard ---------------------------------------


def test_dashboard_shows_tables_not_raw_json() -> None:
    """Bốn trong sáu card từng đổ thẳng JSON ra thẻ <pre>."""
    soup = _soup(DOCS / "dashboard.html")
    exposed = [p for p in soup.find_all("pre") if p.find_parent("details") is None]
    assert not exposed, f"{len(exposed)} khối JSON còn lộ ra ngoài"
    assert len(soup.find_all("table")) >= 6


def test_dashboard_keeps_raw_json_available_behind_a_disclosure() -> None:
    """Sửa cách trình bày không được làm mất khả năng kiểm chứng số liệu."""
    soup = _soup(DOCS / "dashboard.html")
    assert len(soup.find_all("details")) >= 4


def test_dashboard_labels_are_fully_vietnamese() -> None:
    """Nhãn hiển thị phải là tiếng Việt; JSON gốc giữ khóa gốc là có chủ đích.

    Trang cũ để lộ "w_cau" nằm ngay cạnh "Ngày neo" — nửa dịch nửa không. Khối
    JSON gập lại thì khác: nó tồn tại để kiểm chứng số liệu nên phải giữ đúng
    tên khóa của artifact.
    """
    soup = _soup(DOCS / "dashboard.html")
    for disclosure in soup.find_all("details"):
        disclosure.decompose()
    visible = soup.get_text(" ", strip=True)
    for raw_key in ("w_cau", "w_stat", "effective_weights", "component_availability"):
        assert raw_key not in visible, f"khóa chưa dịch còn hiện: {raw_key}"


# --- Lỗi 2: trạng thái rỗng -----------------------------------------------


PATH_PAGES: tuple[str, ...] = (
    "soi-path-loto-active.html",
    "soi-path-loto-stable.html",
    "soi-path-de-active.html",
    "soi-path-de-stable.html",
)


def _render_path_page(*, rows: list, empty_reason: dict | None = None) -> str:
    """Dựng trang đường cầu trực tiếp từ mẫu, không phụ thuộc dữ liệu của ngày.

    Cần thiết vì trang nào rỗng là *tính chất của dữ liệu hôm đó*, không phải
    của mã nguồn: hôm nay ĐB đang chạy có 4 đường cầu, hôm qua thì không. Kiểm
    trạng thái rỗng bằng cách chỉ đích danh một tệp sinh ra sẽ hỏng mỗi lần
    tình trạng dữ liệu đảo chiều — và nó đã hỏng đúng như vậy.
    """
    environment = Environment(loader=FileSystemLoader(str(ROOT / "src" / "templates")))
    return environment.get_template("path_ui_page.html.j2").render(
        title="Kiểm thử",
        mode="de",
        mode_label="Đặc Biệt",
        kind="active",
        kind_label="Đang chạy",
        other_link=None,
        other_kind_label="Ổn định",
        other_mode_label="Đặc Biệt",
        index_link=None,
        anchor_date="2026-09-02",
        display_days=10,
        days=[],
        rows=rows,
        picks=[],
        empty_reason=empty_reason or {},
    )


def test_empty_page_explains_itself_instead_of_blaming_the_data() -> None:
    """Trang rỗng phải nói rỗng là bình thường, không bảo người đọc chạy lại."""
    html = _render_path_page(
        rows=[],
        empty_reason={
            "threshold": 3,
            "is_de": True,
            "baseline_pct": 1.0,
            "chance_pct": 0.0001,
            "sibling_rows": 12,
            "sibling_link": "soi-path-de-stable.html",
            "sibling_label": "Cầu ĐB ổn định",
        },
    )
    empty = BeautifulSoup(html, "html.parser").find(class_="vla-empty")
    assert empty is not None, "thiếu trạng thái rỗng"
    text = empty.get_text(" ", strip=True).lower()
    assert "không phải lỗi dữ liệu" in text
    assert "chạy lại" not in text


def test_empty_state_points_to_where_the_data_actually_is() -> None:
    html = _render_path_page(
        rows=[],
        empty_reason={
            "threshold": 3,
            "is_de": True,
            "baseline_pct": 1.0,
            "chance_pct": 0.0001,
            "sibling_rows": 12,
            "sibling_link": "soi-path-de-stable.html",
            "sibling_label": "Cầu ĐB ổn định",
        },
    )
    empty = BeautifulSoup(html, "html.parser").find(class_="vla-empty")
    link = empty.find("a")
    assert link is not None and "stable" in link.get("href", "")


def _path_table_rows(soup: BeautifulSoup) -> int:
    """Số đường cầu trong bảng đường cầu, bỏ qua mọi bảng khác trên trang.

    Phải tìm đúng bảng: trang còn có bảng tham số và bảng chọn nhanh, nên
    ``soup.find("table")`` bắt nhầm và luôn báo là có dữ liệu.
    """
    for table in soup.find_all("table"):
        header = table.find("th")
        if header and "đường cầu" in header.get_text(strip=True).lower():
            body = table.find("tbody")
            return len(body.find_all("tr")) if body else 0
    return 0


def test_empty_state_appears_exactly_when_the_page_has_no_paths() -> None:
    """Hợp đồng trên các trang thật: không có đường cầu ⇔ có trạng thái rỗng.

    Kiểm hai chiều trên cả bốn trang thay vì chỉ định sẵn trang nào rỗng, nên
    phép kiểm đúng với mọi tình trạng dữ liệu.
    """
    for name in PATH_PAGES:
        soup = _soup(DOCS / name)
        has_empty_state = soup.find(class_="vla-empty") is not None
        path_count = _path_table_rows(soup)
        assert has_empty_state == (path_count == 0), (
            f"{name}: {path_count} đường cầu nhưng trạng thái rỗng={has_empty_state}"
        )


def test_a_page_with_paths_renders_no_empty_state() -> None:
    row = SimpleNamespace(
        path_id="G1P0-G2P1",
        lag=1,
        i=0,
        j=1,
        i_label="G1·0",
        j_label="G2·1",
        p_mean=0.2377,
        streak=3,
        cells=[SimpleNamespace(num=7, hit=True, hitde=False, tooltip="07")],
    )
    assert (
        BeautifulSoup(_render_path_page(rows=[row]), "html.parser").find(class_="vla-empty") is None
    )


# --- Bố cục ----------------------------------------------------------------


def test_landing_section_order_matches_the_agreed_flow() -> None:
    """Live → (kết quả | chục×đơn vị) → ma trận full → ngày mai → thống kê."""
    ids = [s.get("id") for s in _soup(DOCS / "index.html").find_all("section")]
    expected = [
        "live",
        "ket-qua",
        "chuc-don-vi",
        "ma-tran-ngay",
        "ai-ml",
        "tan-suat-loto",
    ]
    positions = [ids.index(sid) for sid in expected]
    assert positions == sorted(positions), dict(zip(expected, positions, strict=True))


def test_top_row_pairs_results_with_digit_spread_and_stretches() -> None:
    """Tầng 1: kết quả ~58% cạnh chục×đơn vị ~42%, cân bằng chiều cao."""
    css = (DOCS / "index.html").read_text(encoding="utf-8")
    top = re.search(r"\.matrix-top\s*\{([^}]*)\}", css)
    assert top, "thiếu lưới .matrix-top"
    body = top.group(1).replace(" ", "")
    assert "minmax(0,58fr)minmax(0,42fr)" in body
    assert "stretch" in body


def test_top_row_columns_cannot_be_pushed_open_by_wide_tables() -> None:
    """1fr mặc định là minmax(auto,1fr); bảng rộng sẽ phá vỡ tỉ lệ 58/42."""
    css = (DOCS / "index.html").read_text(encoding="utf-8")
    for name in ("matrix-top", "next-day", "inspector"):
        rule = re.search(rf"\.{name}\s*\{{([^}}]*)\}}", css)
        assert rule and "minmax(0," in rule.group(1).replace(" ", ""), name


def test_daily_matrix_spans_the_full_width() -> None:
    soup = _soup(DOCS / "index.html")
    matrix = soup.find(id="ma-tran-ngay")
    assert matrix is not None
    assert "matrix-full" in (matrix.get("class") or [])


def test_next_day_has_all_three_prediction_blocks() -> None:
    """Ba khối phải cùng có mặt. Bố cục ba-cột-một-hàng của bản trước đã bị
    thay bằng xếp dọc — xem test_next_day_cards_stack_vertically để biết lý
    do đo được."""
    children = _soup(DOCS / "index.html").select(".next-day > *")
    assert len(children) == 3, f"kỳ vọng 3 bảng, thấy {len(children)}"


def test_next_day_order_is_simulation_then_special_then_loto() -> None:
    soup = _soup(DOCS / "index.html")
    children = soup.select(".next-day > *")
    assert children[0].get("id") == "mo-phong"
    text = " ".join(c.get_text(" ", strip=True)[:80] for c in children[1:])
    assert text.index("Đặc biệt") < text.index("Lô tô")


def test_evidence_tables_are_merged_into_one_card() -> None:
    """Hai cột 445px làm cột "Tỷ lệ" bị cắt và bỏ trống ~45% chiều cao."""
    soup = _soup(DOCS / "index.html")
    merged = soup.select(".basis-merged")
    assert len(merged) == 1, "thiếu khối hợp nhất"
    sections = soup.select(".basis-merged > section")
    assert len(sections) == 2, f"khối hợp nhất phải có 2 phần, thấy {len(sections)}"


def test_merged_card_divider_sits_only_between_sections() -> None:
    """border-top cho mọi con sẽ vẽ một đường thừa trên phần đầu."""
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    assert ".basis-merged>section+section{border-top:" in css


def test_analysis_row_keeps_the_left_panel_independent() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8")
    rule = re.search(r"\.inspector\s*\{([^}]*)\}", css)
    assert "minmax(0,34fr)minmax(0,66fr)" in rule.group(1).replace(" ", "")


def test_wide_tables_scroll_inside_their_own_container() -> None:
    """Bảng kết quả rộng 520px từng đẩy cả trang tràn 187px ở màn 360px."""
    css = (DOCS / "index.html").read_text(encoding="utf-8")
    assert re.search(r"\.result-scroll\s*\{[^}]*overflow-x:\s*auto", css)
    assert _soup(DOCS / "index.html").find(class_="result-scroll") is not None


def test_shared_grids_never_let_a_child_force_the_page_wider() -> None:
    """minmax(0,1fr) là phần chống vỡ khung; thiếu nó cột phình theo nội dung."""
    for cls in (".vla-duo", ".vla-trio", ".vla-row"):
        block = re.search(re.escape(cls) + r"\s*\{([^}]*)\}", TAILWIND_LITE_CSS)
        assert block, cls
        assert "minmax(" in block.group(1), cls


# --- Khối quay trực tiếp ---------------------------------------------------


def test_live_block_sits_above_the_daily_result() -> None:
    ids = [s.get("id") for s in _soup(DOCS / "index.html").find_all("section")]
    assert ids.index("live") < ids.index("ket-qua")


def test_live_state_is_decided_on_the_viewer_clock_not_at_build_time() -> None:
    """Trang tĩnh dựng một lần rồi phục vụ cả ngày; trạng thái ghi cứng sẽ sai."""
    text = (DOCS / "index.html").read_text(encoding="utf-8")
    assert "Asia/Ho_Chi_Minh" in text
    assert "live-status" in text


# --- Trạng thái rỗng và đang tải dùng chung -------------------------------


def test_shared_css_provides_empty_and_loading_states() -> None:
    assert ".vla-empty" in TAILWIND_LITE_CSS
    assert ".vla-skeleton" in TAILWIND_LITE_CSS
    assert "prefers-reduced-motion" in TAILWIND_LITE_CSS


def test_predictions_output_is_still_valid_json() -> None:
    path = ROOT / "data/predictions_today.json"
    if not path.exists():
        pytest.skip("chưa sinh dự đoán")
    json.loads(path.read_text(encoding="utf-8"))


# --- Bảng chỉ số ------------------------------------------------------------


def test_metric_panel_has_six_cards() -> None:
    """Bốn thẻ để lại khoảng trống mất cân đối ở dải bên phải."""
    tiles = _soup(DOCS / "index.html").select(".metric-tile")
    assert len(tiles) == 6, f"kỳ vọng 6 thẻ chỉ số, thấy {len(tiles)}"


def test_metric_grid_reflows_without_per_breakpoint_rules() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    assert "grid-template-columns:repeat(auto-fit,minmax(190px,1fr))" in css


def test_long_metric_values_do_not_wrap() -> None:
    """Ngày "2026-09-06" ở cỡ 42px xuống hai dòng thành "2026-09-" / "06"."""
    soup = _soup(DOCS / "index.html")
    long_tiles = [t for t in soup.select(".metric-tile") if t.get("data-long") == "true"]
    assert long_tiles, "không thẻ nào được đánh dấu giá trị dài"
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    assert '.metric-tile[data-long="true"]strong{font-size:' in css


def test_empty_simulation_block_leaves_no_gap() -> None:
    """Bảng mô phỏng do build_fun_prediction.py chèn vào SAU khi trang được
    dựng; nếu bước đó trượt thì section rỗng vẫn chiếm một hàng của lưới và để
    lại khoảng trống. Với lưới một cột thì chỉ cần ẩn nó — quy tắc :has thu
    lưới còn hai cột của bản ba cột không còn nghĩa nữa."""
    css = _css(DOCS / "index.html")
    assert ".next-day>section:empty{display:none" in css


# --- Sáu lỗi bố cục đã báo -------------------------------------------------
#
# Mỗi test dưới đây khoá một số đo đã kiểm bằng Chromium, không phải một ý
# thích: số đo "trước" ghi trong docstring là giá trị thật đo được lúc lỗi còn.


def test_main_container_is_centred() -> None:
    """Trước: mép trái 0px, mép phải 140px ở màn 1920px — lệch hẳn một phía."""
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    rule = re.search(r"\.main\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc .main"
    body = rule.group(1)
    assert "margin:0auto" in body
    assert "max-width:1600px" in body


def test_main_max_width_is_declared_once_and_the_same_everywhere() -> None:
    """Ba nơi khai báo .main từng lệch nhau (1600/1780/1600) nên màn rộng chạy
    quá khung thiết kế 1440-1600px."""
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    widths = set(re.findall(r"\.main\{[^}]*?max-width:([^;}]+)", css))
    widths |= set(re.findall(r"\.desktop-view\.main\{[^}]*?max-width:([^;}]+)", css))
    for w in widths:
        assert "1600px" in w, f"còn một khai báo max-width khác: {w}"


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_dock_bar_fits_the_agreed_height(page: Path) -> None:
    """Trước: 108-114px. Nhãn cố định dưới icon là thứ đội chiều cao lên.

    54px = icon 40 + đệm 6*2 + viền 1*2, nằm trong khoảng 48-56px của bản vẽ.
    """
    css = _css(page)
    assert re.search(r"dock-ic\{[^}]*width:40px;height:40px", css), page.name
    assert re.search(r"dock-inner\{[^}]*padding:6px10px", css), page.name


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_dock_label_is_a_tooltip_not_a_fixed_row(page: Path) -> None:
    """Nhãn phải ra khỏi luồng, nếu không nó cộng thẳng vào chiều cao thanh."""
    css = _css(page)
    assert re.search(r"dock-name\{[^}]*position:absolute", css), page.name


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_dock_uses_glassmorphism_at_thirty_percent(page: Path) -> None:
    """Trước: nền đục 84% + blur 20px — không nhìn thấy gì phía sau."""
    css = _css(page)
    rule = re.search(r"dock-inner\{([^}]*)\}", css)
    assert rule, page.name
    body = rule.group(1)
    assert "blur(12px)" in body, page.name
    assert re.search(r"rgba\(15,23,42,\.?3\d*\)|srgb[^;]*30%|30%,transparent", body), page.name


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_dock_opaque_fallback_when_backdrop_filter_is_missing(page: Path) -> None:
    """Nền 30% mà không có blur thì chữ nằm trên nội dung trang, đọc không nổi."""
    css = _css(page)
    assert "@supportsnot(backdrop-filter" in css, page.name


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_submenu_has_a_hover_bridge_over_the_gap(page: Path) -> None:
    """Trước: khe hở 10px giữa đáy popover và đỉnh nút làm menu tắt giữa đường.

    Cầu ::after cao 18px phủ kín khe đó, nên :hover của nhóm không bao giờ đứt.
    """
    css = _css(page)
    assert re.search(r"dock-pop::after\{[^}]*top:100%", css), page.name
    assert re.search(r"dock-pop::after\{[^}]*height:18px", css), page.name


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_submenu_closes_slower_than_it_opens(page: Path) -> None:
    """Nửa sau của hover intent: mở ngay, đóng trễ, để con trỏ kịp băng qua."""
    css = _css(page)
    rule = re.search(r"dock-pop\{([^}]*)\}", css)
    assert rule, page.name
    assert re.search(r"visibility:?[^;]*\.4\ds|visibility0slinear\.4\ds", rule.group(1).replace(" ", "")), page.name


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_icon_magnification_stays_in_the_agreed_range(page: Path) -> None:
    """Bản vẽ yêu cầu 1.15-1.2x, ease-in-out."""
    css = _css(page)
    scales = [float(s) for s in re.findall(r"dock-ic\{?[^}]*?\}?[^{]*?transform:scale\(([\d.]+)\)", css)]
    scales += [float(s) for s in re.findall(r"transform:scale\(([\d.]+)\)", css)]
    hits = [s for s in scales if 1.10 <= s <= 1.25]
    assert hits, f"{page.name}: không thấy hệ số phóng nào trong khoảng"
    assert all(1.15 <= s <= 1.20 for s in hits), f"{page.name}: {hits}"
    assert re.search(r"dock-ic\{[^}]*transition:transform[^;]*ease-in-out", css), page.name


def test_evidence_columns_are_balanced_by_a_sticky_panel() -> None:
    """Cân bằng bằng cách GIỮ khung trái trong tầm mắt, không nhồi khối phải.

    Bản trước khoá chiều cao khối phải bằng khung trái (absolute inset:0). Nó
    chữa được độ lệch 497px nhưng ép hai bảng cần 874px và 1082px vào 511px
    mỗi bảng. sticky đòi ô lưới không bị kéo giãn, nên align-self:start là bắt
    buộc — align-items:stretch của .inspector sẽ vô hiệu hoá sticky nếu thiếu.
    """
    css = _css(DOCS / "index.html")
    rule = re.search(r"\.inspector>\.inspect-panel\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc sticky cho khung căn cứ"
    body = rule.group(1)
    assert "position:sticky" in body
    assert "align-self:start" in body, "thiếu align-self:start thì sticky không có tác dụng"


def test_evidence_card_no_longer_locks_its_height() -> None:
    """Thủ thuật absolute inset:0 phải đi hẳn, không chỉ bị ghi đè ở đâu đó."""
    css = _css(DOCS / "index.html")
    assert not re.search(r"\.basis-cell>\.basis-merged\{[^}]*position:absolute", css)


def test_evidence_tables_have_exactly_one_scroll_container() -> None:
    """Đây là lỗi thật đã thấy trên màn hình: HAI thanh cuộn lồng nhau.

    section cuộn (511px chứa 695px) trong khi .table-wrap bên trong cũng cuộn
    (520px chứa 874px). Cuộn một cái thì không biết cái nào chạy, và .table-wrap
    cao 520px nằm trong section cao 511px nên hàng cuối bị cắt ngang.
    """
    css = _css(DOCS / "index.html")
    rule = re.search(r"\.basis-merged>section\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc cho section trong thẻ gộp"
    assert "overflow:auto" not in rule.group(1), (
        "section không được cuộn: .table-wrap bên trong đã là thanh cuộn rồi"
    )
    assert re.search(r"\.basis-merged\.table-wrap\{[^}]*max-height:none", css), (
        "bảng chỉ có 10 hàng nên để cao tự nhiên, không cần trần chiều cao"
    )


def test_path_tables_give_the_text_columns_room() -> None:
    """Hàng cao 83px ở bảng trên và 104px ở bảng dưới vì hai cột chữ bị bóp
    xuống ~90px và xuống 3-4 dòng."""
    css = _css(DOCS / "index.html")
    assert re.search(r"\.basis-merged\.col-path_line\{[^}]*min-width:190px", css)
    assert re.search(r"\.basis-merged\.col-reason\{[^}]*min-width:170px", css)


def test_only_data_cells_get_nowrap_not_headers() -> None:
    """Cho cả <th> nowrap thì tiêu đề dài tự đặt sàn bề rộng cho cột, đẩy bảng
    lên 1051px trong khung 927px và sinh cuộn ngang. Đo được khi thử."""
    # _css() bỏ hết khoảng trắng, nên bắt vào bộ chọn CUỐI của mỗi danh sách —
    # nó nằm ngay sát dấu ngoặc mở.
    css = _css(DOCS / "index.html")
    th_rule = re.search(r"th\.col-rule_score\{([^}]*)\}", css)
    td_rule = re.search(r"td\.col-rule_score\{([^}]*)\}", css)
    assert td_rule and "white-space:nowrap" in td_rule.group(1), "ô dữ liệu số phải nowrap"
    assert th_rule and "white-space:nowrap" not in th_rule.group(1), (
        "tiêu đề KHÔNG được nowrap — nó đặt sàn bề rộng cho cột một chữ số"
    )


def test_hits_and_trials_are_merged_into_one_column() -> None:
    """Hai cột riêng tốn 158px để hiện "3" và "379"; bề rộng do tiêu đề "Số lần
    trúng" đặt sàn chứ không phải do dữ liệu."""
    soup = _soup(DOCS / "index.html")
    merged = soup.find(class_="basis-merged")
    assert merged is not None
    headers = [th.get_text(strip=True) for th in merged.select("thead th")]
    assert "Trúng/Mẫu" in headers
    assert "Số lần trúng" not in headers and "Cỡ mẫu" not in headers


def test_probability_column_is_not_eight_decimal_places() -> None:
    """p_mean từng in nguyên "0.02544529" — rộng vô ích và không ai đọc tới số
    thứ tám."""
    soup = _soup(DOCS / "index.html")
    merged = soup.find(class_="basis-merged")
    values = [td.get_text(strip=True) for td in merged.select("td.col-p_mean")]
    assert values, "không tìm thấy ô tỷ lệ nào"
    for v in values:
        assert v.endswith("%"), f"tỷ lệ phải ở dạng phần trăm, thấy {v!r}"
        assert len(v) <= 7, f"tỷ lệ quá dài: {v!r}"


def test_table_cells_carry_their_column_name() -> None:
    """Lớp theo tên cột thay cho nth-child: chỉ số cột đổi theo mỗi lời gọi
    _render_table nên quy tắc nth-child sẽ trượt sang cột khác lúc nào không
    hay."""
    merged = _soup(DOCS / "index.html").find(class_="basis-merged")
    for col in ("number_str", "path_line", "reason", "rule_score"):
        assert merged.select(f"th.col-{col}"), f"thiếu lớp trên tiêu đề {col}"
        assert merged.select(f"td.col-{col}"), f"thiếu lớp trên ô dữ liệu {col}"


def test_evidence_card_markup_has_the_wrapper_cell() -> None:
    cell = _soup(DOCS / "index.html").find(class_="basis-cell")
    assert cell is not None, "thiếu ô bọc .basis-cell"
    assert cell.find(class_="basis-merged") is not None


@pytest.mark.parametrize("page", FOOTER_PAGES, ids=lambda p: p.name)
def test_footer_links_spread_across_the_full_width(page: Path) -> None:
    """Trước: năm hàng rộng 1684px nhưng chữ dồn hết sang mép trái.

    Lưới cột chứ không phải space-between trên từng <ul>: nhóm chỉ 2-4 mục thì
    space-between đẩy chúng dính hai mép và chừa khoảng trống lớn ở giữa.
    """
    css = _css(page)
    rule = re.search(r"nav-fallback\{([^}]*)\}", css)
    assert rule, page.name
    body = rule.group(1)
    assert "display:grid" in body, page.name
    assert "repeat(auto-fit,minmax(min(180px,100%),1fr))" in body, page.name


@pytest.mark.parametrize("page", FOOTER_PAGES, ids=lambda p: p.name)
def test_each_footer_group_is_one_grid_cell(page: Path) -> None:
    """Không bọc <section> thì <h2> và <ul> thành hai ô lưới rời nhau: tiêu đề
    một cột, danh sách cột kế bên."""
    nav = _soup(page).find(class_=re.compile(r"nav-fallback"))
    assert nav is not None, page.name
    children = [c for c in nav.find_all(recursive=False)]
    assert children, page.name
    assert all(c.name == "section" for c in children), (
        f"{page.name}: con trực tiếp phải là <section>, thấy "
        f"{sorted({c.name for c in children})}"
    )
    for sec in children:
        assert sec.find("h2") is not None and sec.find("ul") is not None, page.name


def test_site_nav_stores_plain_text_not_pre_escaped_html() -> None:
    """Nguồn dữ liệu giữ ký tự thật; thoát HTML là việc của nơi kết xuất.

    Lưu sẵn "&amp;" trong SITE_NAV làm nơi nào thoát thêm một lần nữa thì hiện
    ra "&amp;" trên màn hình — và lỗi chỉ xuất hiện ở vài trang, tuỳ nơi đó có
    thoát hay không.
    """
    for group, items in SITE_NAV:
        assert "&amp;" not in group, group
        for _href, label, _icon in items:
            assert "&amp;" not in label, label


@pytest.mark.parametrize("page", PAGES)
def test_no_page_shows_a_raw_html_entity(page: Path) -> None:
    """"&amp;amp;" trong nguồn nghĩa là người đọc thấy "&amp;" trên màn hình."""
    text = page.read_text(encoding="utf-8")
    assert "&amp;amp;" not in text, page.name
    assert "&amp;lt;" not in text, page.name


# --- Khu dự đoán ngày mai: xếp dọc ----------------------------------------


def test_next_day_cards_stack_vertically() -> None:
    """Bản ba cột cho mỗi thẻ 485px ở 1920px và 435px ở 1440px.

    Bảng mô phỏng bên trong cần tối thiểu 520px cho khung giải, nên nó bị ép
    còn 131px và 81px — đo được tràn 389px và 439px, đúng thanh cuộn ngang
    nhìn thấy dưới bảng.
    """
    css = _css(DOCS / "index.html")
    rule = re.search(r"\.next-day\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc .next-day"
    body = rule.group(1)
    assert "grid-template-columns:minmax(0,1fr)" in body, (
        "khu này phải xếp dọc một cột"
    )
    assert "repeat(3," not in body and "repeat(2," not in body


def test_next_day_order_is_simulation_then_special_then_loto_stacked() -> None:
    """Thứ tự dọc: mô phỏng -> Đặc biệt -> Lô tô."""
    grid = _soup(DOCS / "index.html").find(class_="next-day")
    assert grid is not None
    kids = [k for k in grid.find_all(recursive=False)]
    assert kids[0].get("id") == "mo-phong"
    titles = [k.get_text(" ", strip=True)[:60] for k in kids[1:]]
    assert any("Đặc biệt ngày mai" in t for t in titles[:1]), titles
    assert any("Lô tô ngày mai" in t for t in titles[1:2]), titles


def test_bar_chart_uses_columns_instead_of_one_long_bar() -> None:
    """Thẻ chiếm trọn 1504px sau khi xếp dọc; một thanh dài ~1400px không cho
    biết thêm gì mà nhãn với trị số bị đẩy ra hai mép xa nhau."""
    css = _css(DOCS / "index.html")
    rule = re.search(r"\.bar-list\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc .bar-list"
    body = rule.group(1)
    assert "repeat(auto-fit,minmax(min(100%,560px),1fr))" in body
    assert "max-width" not in body, (
        "giới hạn bề rộng sẽ bỏ trống nửa thẻ; phải chia cột"
    )


def test_simulation_board_keeps_its_minimum_width_in_three_columns() -> None:
    """Khung giải cần 520px. Ở 1280px cột đầu chỉ còn 474px — đo được tràn
    46px — nên ngưỡng chia ba cột phải là 1400px, không phải 1100px.

    Kiểm ở NGUỒN chứ không ở docs/index.html: nhiều builder cùng ghi tệp đó và
    khối <style> này chỉ có mặt khi build_fun_prediction chạy sau cùng, nên
    khẳng định trên tệp đã dựng sẽ đỏ hay xanh tuỳ thứ tự test — một phép kiểm
    như vậy không nói lên điều gì về mã.
    """
    css = (ROOT / "src" / "build_fun_prediction.py").read_text(encoding="utf-8")
    css = css.replace(" ", "").replace("\n", "")
    assert "@media(min-width:1400px)" in css
    block = re.search(r"@media\(min-width:1400px\)\{(.*?\.fun-prob-panels\{[^}]*\})", css)
    assert block, "không tìm thấy khối ba cột cho bảng mô phỏng"
    assert "minmax(520px" in block.group(1)
    assert "display:contents" in block.group(1)


# --- Màn hình tần suất cặp lô tô -------------------------------------------


def test_pair_frequency_screen_exists() -> None:
    """src/pair_stats.py tính bảng này hàng ngày vào
    data/pairs/top_unordered_pairs_top300.csv nhưng trước đây không trang nào
    hiển thị nó."""
    soup = _soup(DOCS / "index.html")
    section = soup.find(id="tan-suat-cap")
    assert section is not None, "thiếu khu tần suất cặp lô tô"
    assert section.find("table") is not None


def test_pair_table_shows_the_expected_count_beside_the_observed() -> None:
    """Chỉ hiện số lần cùng về là gây hiểu sai: người đọc không có gì để so."""
    section = _soup(DOCS / "index.html").find(id="tan-suat-cap")
    headers = [th.get_text(strip=True) for th in section.select("thead th")]
    assert "Kỳ vọng" in headers
    assert "So kỳ vọng" in headers


def test_pair_table_carries_the_chance_maximum_warning() -> None:
    """Với 4950 cặp, cặp dẫn đầu cao hơn kỳ vọng là chuyện đương nhiên. Ở 393
    kỳ, cực đại do ngẫu nhiên trung bình là 39.9 còn quan sát thật là 41 —
    nằm gọn trong khoảng ngẫu nhiên. Thiếu ghi chú này thì bảng chế ra một
    tín hiệu không tồn tại.

    Mốc được đọc theo số kỳ mà trang tự khai, không so với hằng số: sau mỗi
    lần bổ sung lịch sử con số phải đổi theo.
    """
    from build_landing_page import pair_chance_maximum

    section = _soup(DOCS / "index.html").find(id="tan-suat-cap")
    note = section.find(class_="pair-note")
    assert note is not None, "thiếu ghi chú mốc ngẫu nhiên"
    text = re.sub(r"\s+", " ", note.get_text(" ", strip=True))
    assert "4 950" in text

    n_draws = int(re.search(r"dài đúng ([\d]+) kỳ", text).group(1))
    expected, (low, high) = pair_chance_maximum(n_draws)
    assert f"{expected:.1f}" in text, (
        f"ghi chú phải nêu cực đại ngẫu nhiên {expected:.1f} cho {n_draws} kỳ"
    )
    assert f"{low}–{high}" in text


def test_pair_chance_maximum_scales_with_history_length() -> None:
    """Mốc cực đại ngẫu nhiên KHÔNG được đóng cứng.

    Trước đây nó là hằng số 39.8 đo trên 393 kỳ. Khi backfill nâng kho lên
    ~2200 kỳ, số lần đồng xuất hiện kỳ vọng tăng tuyến tính theo N nên mốc
    thật thành 161.8; giữ 39.8 thì mọi cặp đều vượt mốc và bảng tuyên bố
    "bất thường" cho dữ liệu hoàn toàn ngẫu nhiên.
    """
    from build_landing_page import pair_chance_maximum

    short_max, short_band = pair_chance_maximum(393)
    long_max, long_band = pair_chance_maximum(2200)

    assert short_max == pytest.approx(39.9, abs=0.2)
    assert long_max == pytest.approx(161.8, abs=0.5)
    assert long_max > 4 * short_max, "mốc phải tăng theo độ dài lịch sử"

    for chance_max, (low, high) in ((short_max, short_band), (long_max, long_band)):
        assert low < chance_max < high

    assert pair_chance_maximum(0) == (0.0, (0, 0))


def test_pair_chance_maximum_stays_above_the_per_pair_expectation() -> None:
    """Cực đại của 4950 cặp phải cao hơn hẳn kỳ vọng của MỘT cặp — đó chính
    là lý do bảng cần cột so sánh. Nếu hai con số xấp xỉ nhau thì phép hiệu
    chỉnh so sánh bội đã hỏng."""
    from build_landing_page import PAIR_COOCCURRENCE_RATE, pair_chance_maximum

    for n_draws in (393, 1200, 2200):
        chance_max, _ = pair_chance_maximum(n_draws)
        per_pair = PAIR_COOCCURRENCE_RATE * n_draws
        assert chance_max > 1.3 * per_pair, (
            f"{n_draws} kỳ: cực đại {chance_max:.1f} không tách khỏi kỳ vọng "
            f"{per_pair:.1f}"
        )


def test_pair_cooccurrence_rate_uses_inclusion_exclusion() -> None:
    """P(hai số cùng về) KHÔNG phải bình phương của tỉ lệ đơn: hai biến cố
    không độc lập vì cùng rút từ 27 ô giải."""
    from build_landing_page import PAIR_COOCCURRENCE_RATE

    single = 1.0 - 0.99**27
    exact = 1.0 - 2.0 * (0.99**27) + (0.98**27)
    assert PAIR_COOCCURRENCE_RATE == pytest.approx(exact, abs=1e-12)
    assert PAIR_COOCCURRENCE_RATE != pytest.approx(single**2, abs=1e-6), (
        "dùng bình phương là bỏ qua tính không độc lập"
    )
    assert PAIR_COOCCURRENCE_RATE == pytest.approx(0.0549, abs=5e-4)
