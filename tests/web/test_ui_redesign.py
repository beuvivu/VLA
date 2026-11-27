from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from web.page_output import strip_css
from web.ui_theme import SITE_NAV, STYLESHEET_NAME, TAILWIND_LITE_CSS, nav_targets

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.glob("*.html"))

INDEX_ALIASES = {"landing.html", "landing_desktop.html"}


_SCRIPT_BODY = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)


def _soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def _css(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = _SCRIPT_BODY.sub("", text)
    parts = [text]
    for link in _soup(path).find_all("link", rel="stylesheet"):
        href = link.get("href") or ""
        sheet = path.parent / urlsplit(href).path
        if sheet.exists() and sheet.suffix == ".css":
            parts.append(sheet.read_text(encoding="utf-8"))
    return "".join(parts).replace(" ", "").replace("\n", "")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_pins_the_measured_shell_geometry(page: Path) -> None:
    hrefs = [urlsplit(link.get("href", "")).path for link in _soup(page).select("link[rel=stylesheet]")]
    assert "assets/app-shell.css" in hrefs, page.name
    gon = (ROOT / "src/web/templates/app_shell.css").read_text(encoding="utf-8").replace(" ", "")
    for khoa, gia_tri in (
        ("--app-rail-w:", "80px"),
        ("--app-panel-w:", "240px"),
        ("--app-header-h:", "80px"),
        ("--app-shell-radius:", "8px"),
    ):
        assert khoa + gia_tri in gon, f"{khoa} lệch khỏi số đo {gia_tri}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_the_css_under_test_carries_no_script_body(page: Path) -> None:
    assert "<script" not in _css(page), f"{page.name}: thân script lọt vào chuỗi CSS"


def test_no_regex_here_nests_unbounded_lazy_quantifiers() -> None:
    hazard = re.compile(r"\[\^.\]\*\?\\?.\?\[\^.\]\*\?")
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    patterns: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name) and func.value.id == "re"):
            continue
        for argument in node.args[:1]:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                patterns.append(argument.value)
    assert patterns, "không tìm thấy biểu thức nào — phép soi đã hỏng"
    risky = [pattern for pattern in patterns if hazard.search(pattern)]
    assert not risky, f"biểu thức có nguy cơ quay lui bình phương: {risky}"


def test_pages_exist() -> None:
    assert len(PAGES) >= 14, "thiếu trang đã sinh; hãy chạy lại bộ dựng"


def test_shared_css_declares_self_hosted_inter_first() -> None:
    match = re.search(r"--ui-font:([^;]+);", TAILWIND_LITE_CSS)
    assert match, "không tìm thấy token --ui-font"
    assert match.group(1).strip().startswith('"Inter var"')


def test_shared_css_has_a_real_fallback_chain() -> None:
    match = re.search(r"--ui-font:([^;]+);", TAILWIND_LITE_CSS)
    families = [f.strip().strip('"') for f in match.group(1).split(",")]
    assert "system-ui" in families
    assert families[-1] == "sans-serif"


def test_font_face_points_at_a_file_that_exists() -> None:
    match = re.search(r'src:url\("([^"]+)"\)', TAILWIND_LITE_CSS)
    assert match, "không tìm thấy @font-face"
    assert (DOCS / "assets" / match.group(1)).exists()


def test_font_face_covers_the_whole_weight_range() -> None:
    assert "font-weight:100 900" in TAILWIND_LITE_CSS


def test_font_display_swap_avoids_invisible_text() -> None:
    assert "font-display:swap" in TAILWIND_LITE_CSS


def _effective_css(page: Path) -> str:
    text = page.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "html.parser")
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href") or ""
        target = (page.parent / urlsplit(href).path).resolve()
        if target.exists():
            text += target.read_text(encoding="utf-8")
    return text


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_resolves_to_the_self_hosted_font_stack(page: Path) -> None:
    css = _effective_css(page).replace(" ", "")
    assert '--ui-font:"Intervar"' in css, page.name
    assert "InterVariable.woff2" in css, page.name


def test_no_page_loads_a_font_from_an_external_host() -> None:
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in text, page.name
        assert "fonts.gstatic.com" not in text, page.name
        assert "@font-face" not in text, page.name


def test_only_the_licensed_font_is_distributed() -> None:
    import hashlib
    import json

    licensed = {
        "InterVariable.woff2": "Inter-LICENSE.txt",
        **{f"InstrumentSans-{weight}.woff2": "InstrumentSans-OFL.txt"
           for weight in (400, 600, 700)},
    }
    fonts = [f for suffix in ("*.woff", "*.woff2", "*.ttf", "*.otf") for f in DOCS.rglob(suffix)]
    assert sorted(f.relative_to(DOCS).as_posix() for f in fonts) == sorted(
        f"assets/{name}" for name in licensed
    ), (
        f"chỉ phân phối phông đã cấp phép, thấy: {[f.name for f in fonts]}"
    )
    for license_name in set(licensed.values()):
        license_text = (DOCS / "assets" / license_name).read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in license_text
        assert "Copyright" in license_text
    source = ROOT / "src" / "web" / "assets" / "nexlink"
    manifest = json.loads((source / "provenance.json").read_text())["font"]
    assert manifest["family"] == "Instrument Sans"
    assert set(manifest["sha256"]) == {f"InstrumentSans-{w}.woff2" for w in (400, 600, 700)}
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((DOCS / "assets" / name).read_bytes()).hexdigest() == digest
        assert (DOCS / "assets" / name).read_bytes() == (source / name).read_bytes()
    assert (DOCS / "assets" / "InstrumentSans-OFL.txt").read_bytes() == (source / "InstrumentSans-OFL.txt").read_bytes()


def test_shared_stylesheet_is_written() -> None:
    assert (DOCS / STYLESHEET_NAME).exists()


def test_shared_stylesheet_matches_the_source() -> None:
    shipped = (DOCS / STYLESHEET_NAME).read_text(encoding="utf-8")
    assert shipped == strip_css(TAILWIND_LITE_CSS)
    assert "/*" not in shipped


def test_pages_link_the_shared_stylesheet_instead_of_inlining_it() -> None:
    linked = 0
    for page in PAGES:
        hrefs = [urlsplit(link.get("href", "")).path for link in _soup(page).find_all("link", rel="stylesheet")]
        if STYLESHEET_NAME in hrefs:
            linked += 1
    assert linked >= 10, f"chỉ {linked}/{len(PAGES)} trang dùng biểu định kiểu chung"


def test_dark_theme_covers_all_three_viewer_states() -> None:
    assert "prefers-color-scheme:dark" in TAILWIND_LITE_CSS.replace(" ", "")
    assert 'data-ui-theme="dark"' in TAILWIND_LITE_CSS
    assert 'not([data-ui-theme="light"])' in TAILWIND_LITE_CSS.replace(" ", "")


def test_sidebar_is_gone_from_every_page() -> None:
    for page in PAGES:
        soup = _soup(page)
        assert not soup.select(".sidebar, .ui-side"), f"{page.name} vẫn còn sidebar"


def test_landing_shell_keeps_in_page_anchors() -> None:
    hrefs = {a.get("href") for a in _soup(DOCS / "index.html").select(".app-page-sections a")}
    anchors = {h for h in hrefs if h and h.startswith("#")}
    assert len(anchors) >= 10, f"chỉ còn {len(anchors)} neo trong trang"
    for required in ("#tong-quan", "#ket-qua", "#duong-cau", "#backtest"):
        assert required in anchors, required


def test_no_page_is_a_navigation_dead_end() -> None:
    for page in PAGES:
        assert _soup(page).select("nav a"), f"{page.name} không có liên kết điều hướng nào"


def test_navigation_covers_every_generated_page() -> None:
    missing = {p.name for p in PAGES} - nav_targets() - INDEX_ALIASES
    assert not missing, f"trang không có trong điều hướng: {sorted(missing)}"


def test_navigation_groups_are_the_agreed_set() -> None:
    assert [group for group, _ in SITE_NAV] == [
        "Kết quả",
        "Vietlott",
        "Thống kê",
        "Thống kê LOTO",
        "Thống kê Đặc Biệt",
        "Soi cầu",
        "Dự báo",
        "Nghiên cứu & công cụ",
    ]


def test_every_navigation_group_has_entries() -> None:
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


def test_dashboard_shows_tables_not_raw_json() -> None:
    soup = _soup(DOCS / "dashboard.html")
    exposed = [p for p in soup.find_all("pre") if p.find_parent("details") is None]
    assert not exposed, f"{len(exposed)} khối JSON còn lộ ra ngoài"
    assert len(soup.find_all("table")) >= 6


def test_dashboard_keeps_raw_json_available_behind_a_disclosure() -> None:
    soup = _soup(DOCS / "dashboard.html")
    assert len(soup.find_all("details")) >= 4


def test_dashboard_labels_are_fully_vietnamese() -> None:
    soup = _soup(DOCS / "dashboard.html")
    for disclosure in soup.find_all("details"):
        disclosure.decompose()
    visible = soup.get_text(" ", strip=True)
    for raw_key in ("w_cau", "w_stat", "effective_weights", "component_availability"):
        assert raw_key not in visible, f"khóa chưa dịch còn hiện: {raw_key}"


PATH_PAGES: tuple[str, ...] = (
    "soi-path-loto-active.html",
    "soi-path-loto-stable.html",
    "soi-path-de-active.html",
    "soi-path-de-stable.html",
)


def _render_path_page(*, rows: list, empty_reason: dict | None = None) -> str:
    environment = Environment(loader=FileSystemLoader(str(ROOT / "src" / "web" / "templates")))
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
    html = _render_path_page(
        rows=[],
        empty_reason={
            "threshold": 3,
            "is_de": True,
            "baseline_pct": 1.0,
            "chance_pct": 0.0001,
            "sibling_rows": 12,
            "sibling_link": "soi-path-de-stable.html",
            "sibling_label": "Cầu Đặc Biệt ổn định",
        },
    )
    empty = BeautifulSoup(html, "html.parser").find(class_="ui-empty")
    assert empty is not None, "thiếu trạng thái rỗng"
    text = empty.get_text(" ", strip=True).lower()
    assert "chưa có đường cầu nối đủ 3 kỳ liên tiếp" in text
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
            "sibling_label": "Cầu Đặc Biệt ổn định",
        },
    )
    empty = BeautifulSoup(html, "html.parser").find(class_="ui-empty")
    link = empty.find("a")
    assert link is not None and "stable" in link.get("href", "")


def _path_table_rows(soup: BeautifulSoup) -> int:
    for table in soup.find_all("table"):
        header = table.find("th")
        if header and "đường cầu" in header.get_text(strip=True).lower():
            body = table.find("tbody")
            return len(body.find_all("tr")) if body else 0
    return 0


def test_empty_state_appears_exactly_when_the_page_has_no_paths() -> None:
    for name in PATH_PAGES:
        soup = _soup(DOCS / name)
        has_empty_state = soup.find(class_="ui-empty") is not None
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
        BeautifulSoup(_render_path_page(rows=[row]), "html.parser").find(class_="ui-empty") is None
    )


def test_landing_section_order_matches_the_agreed_flow() -> None:
    ids = [s.get("id") for s in _soup(DOCS / "index.html").find_all("section")]
    expected = [
        "live",
        "ket-qua",
        "ma-tran-ngay",
        "db-tuan-thang",
        "ai-ml",
        "tan-suat-loto",
    ]
    positions = [ids.index(sid) for sid in expected]
    assert positions == sorted(positions), dict(zip(expected, positions, strict=True))


def test_daily_results_use_the_ledger_card_without_the_extra_loto_strip() -> None:
    soup = _soup(DOCS / "index.html")
    card = soup.select_one("#ket-qua .tr-day")
    assert card is not None
    assert not soup.select(".matrix-top")
    assert len(card.select(".tr-prizes .tr-number")) == 27
    assert card.select_one(".tr-head-tail table") is not None
    assert len(card.select(".tr-head-tail tbody tr")) == 10
    assert not card.select(".tr-loto,.app-prize-table,.app-head-tail-table")


def test_top_row_columns_cannot_be_pushed_open_by_wide_tables() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8") + (DOCS / "assets/ui.css").read_text(encoding="utf-8")
    for name in ("app-result-layout", "next-day", "inspector"):
        rule = re.search(rf"\.{name}\s*\{{([^}}]*)\}}", css)
        assert rule, name
        cols = re.search(r"grid-template-columns:([^;]*)", rule.group(1))
        assert cols, f"{name}: không khai grid-template-columns"
        tracks = cols.group(1).replace(" ", "")
        assert "minmax(" in tracks, f"{name}: rãnh thiếu sàn tường minh ({tracks})"
        assert not re.search(r"(^|\))[0-9.]+fr", tracks), f"{name}: còn rãnh fr trần ({tracks})"


def test_daily_matrix_spans_the_full_width() -> None:
    soup = _soup(DOCS / "index.html")
    matrix = soup.find(id="ma-tran-ngay")
    assert matrix is not None
    assert "matrix-full" in (matrix.get("class") or [])


def test_next_day_has_all_three_prediction_blocks() -> None:
    children = _soup(DOCS / "index.html").select(".next-day > *")
    assert len(children) == 3, f"kỳ vọng 3 bảng, thấy {len(children)}"


def test_next_day_order_is_simulation_then_special_then_loto() -> None:
    soup = _soup(DOCS / "index.html")
    children = soup.select(".next-day > *")
    assert children[0].get("id") == "mo-phong"
    text = " ".join(c.get_text(" ", strip=True)[:80] for c in children[1:])
    assert text.index("Đặc Biệt") < text.index("LOTO")


def test_evidence_tables_are_merged_into_one_card() -> None:
    soup = _soup(DOCS / "index.html")
    merged = soup.select(".basis-merged")
    assert len(merged) == 1, "thiếu khối hợp nhất"
    sections = soup.select(".basis-merged > section")
    assert len(sections) == 2, f"khối hợp nhất phải có 2 phần, thấy {len(sections)}"


def test_merged_card_divider_sits_only_between_sections() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    assert ".basis-merged>section+section{border-left:" in css
    assert "border-top:1pxsolidvar(--line)" in css


def test_analysis_row_keeps_the_left_panel_independent() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8")
    rule = re.search(r"\.inspector\s*\{([^}]*)\}", css)
    assert rule, "thiếu lưới .inspector"
    assert "minmax(0,1fr)" in rule.group(1).replace(" ", "")

    basis = re.search(r"\.basis-merged\s*\{([^}]*)\}", css)
    assert basis, "thiếu lưới .basis-merged"
    assert "minmax(0,1fr)minmax(0,1fr)" in basis.group(1).replace(" ", "")


def test_wide_tables_scroll_inside_their_own_container() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8")
    assert re.search(r"\.table-wrap\s*\{[^}]*overflow:\s*auto", css)
    assert _soup(DOCS / "index.html").find(class_="table-wrap") is not None
    assert "grid-template-columns:repeat(var(--count),minmax(0,1fr))" in _css(DOCS / "index.html")


def test_shared_grids_never_let_a_child_force_the_page_wider() -> None:
    for cls in (".ui-duo", ".ui-trio", ".ui-row"):
        block = re.search(re.escape(cls) + r"\s*\{([^}]*)\}", TAILWIND_LITE_CSS)
        assert block, cls
        assert "minmax(" in block.group(1), cls


def test_live_block_sits_above_the_daily_result() -> None:
    ids = [s.get("id") for s in _soup(DOCS / "index.html").find_all("section")]
    assert ids.index("live") < ids.index("ket-qua")


def test_live_state_is_decided_on_the_viewer_clock_not_at_build_time() -> None:
    text = (DOCS / "index.html").read_text(encoding="utf-8")
    assert "Asia/Ho_Chi_Minh" in text
    assert "live-status" in text


def test_shared_css_provides_empty_and_loading_states() -> None:
    assert ".ui-empty" in TAILWIND_LITE_CSS
    assert ".ui-skeleton" in TAILWIND_LITE_CSS
    assert "prefers-reduced-motion" in TAILWIND_LITE_CSS


def test_predictions_output_is_still_valid_json() -> None:
    path = ROOT / "data/predictions_today.json"
    if not path.exists():
        pytest.skip("chưa sinh dự đoán")
    json.loads(path.read_text(encoding="utf-8"))


def test_metric_panel_has_six_cards() -> None:
    tiles = _soup(DOCS / "index.html").select(".metric-tile")
    assert len(tiles) == 6, f"kỳ vọng 6 thẻ chỉ số, thấy {len(tiles)}"


def test_metric_grid_reflows_without_per_breakpoint_rules() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    assert "grid-template-columns:repeat(auto-fit,minmax(190px,1fr))" in css


def test_long_metric_values_do_not_wrap() -> None:
    soup = _soup(DOCS / "index.html")
    long_tiles = [t for t in soup.select(".metric-tile") if t.get("data-long") == "true"]
    assert long_tiles, "không thẻ nào được đánh dấu giá trị dài"
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    assert '.metric-tile[data-long="true"]strong{font-size:' in css


def test_empty_simulation_block_leaves_no_gap() -> None:
    css = _css(DOCS / "index.html")
    assert ".next-day>section:empty{display:none" in css


def test_main_container_is_centred() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    rule = re.search(r"\.main\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc .main"
    body = rule.group(1)
    assert "margin:0auto" in body
    assert "max-width:1600px" in body


def test_main_max_width_is_declared_once_and_the_same_everywhere() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8").replace(" ", "")
    widths = set(re.findall(r"\.main\{[^}]*?max-width:([^;}]+)", css))
    widths |= set(re.findall(r"\.desktop-view\.main\{[^}]*?max-width:([^;}]+)", css))
    for w in widths:
        assert "1600px" in w, f"còn một khai báo max-width khác: {w}"


def test_evidence_columns_are_balanced_by_a_sticky_panel() -> None:
    css = _css(DOCS / "index.html")
    rule = re.search(r"\.inspector>\.inspect-panel\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc cho khung căn cứ"
    body = rule.group(1)
    assert "position:sticky" not in body
    assert "align-self:start" in body


def test_evidence_card_no_longer_locks_its_height() -> None:
    css = _css(DOCS / "index.html")
    assert not re.search(r"\.basis-cell>\.basis-merged\{[^}]*position:absolute", css)


def test_evidence_tables_have_exactly_one_scroll_container() -> None:
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
    css = _css(DOCS / "index.html")
    assert re.search(r"\.basis-merged\.col-path_line\{[^}]*min-width:190px", css)
    assert re.search(r"\.basis-merged\.col-reason\{[^}]*min-width:170px", css)


def test_only_data_cells_get_nowrap_not_headers() -> None:
    css = _css(DOCS / "index.html")
    th_rule = re.search(r"th\.col-rule_score\{([^}]*)\}", css)
    td_rule = re.search(r"td\.col-rule_score\{([^}]*)\}", css)
    assert td_rule and "white-space:nowrap" in td_rule.group(1), "ô dữ liệu số phải nowrap"
    assert th_rule and "white-space:nowrap" not in th_rule.group(1), (
        "tiêu đề KHÔNG được nowrap — nó đặt sàn bề rộng cho cột một chữ số"
    )


def test_hits_and_trials_are_merged_into_one_column() -> None:
    soup = _soup(DOCS / "index.html")
    merged = soup.find(class_="basis-merged")
    assert merged is not None
    headers = [th.get_text(strip=True) for th in merged.select("thead th")]
    assert "Trúng/Mẫu" in headers
    assert "Số lần trúng" not in headers and "Cỡ mẫu" not in headers


def test_probability_column_is_not_eight_decimal_places() -> None:
    soup = _soup(DOCS / "index.html")
    merged = soup.find(class_="basis-merged")
    values = [td.get_text(strip=True) for td in merged.select("td.col-p_mean")]
    assert values, "không tìm thấy ô tỷ lệ nào"
    for v in values:
        assert v.endswith("%"), f"tỷ lệ phải ở dạng phần trăm, thấy {v!r}"
        assert len(v) <= 7, f"tỷ lệ quá dài: {v!r}"


def test_table_cells_carry_their_column_name() -> None:
    merged = _soup(DOCS / "index.html").find(class_="basis-merged")
    for col in ("number_str", "path_line", "reason", "rule_score"):
        assert merged.select(f"th.col-{col}"), f"thiếu lớp trên tiêu đề {col}"
        assert merged.select(f"td.col-{col}"), f"thiếu lớp trên ô dữ liệu {col}"


def test_evidence_card_markup_has_the_wrapper_cell() -> None:
    cell = _soup(DOCS / "index.html").find(class_="basis-cell")
    assert cell is not None, "thiếu ô bọc .basis-cell"
    assert cell.find(class_="basis-merged") is not None


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_page_ships_a_footer_navigation_block(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    assert "nav-fallback" not in text, (
        f"{page.name} vẫn còn khối điều hướng chân trang"
    )


def test_site_nav_stores_plain_text_not_pre_escaped_html() -> None:
    for group, items in SITE_NAV:
        assert "&amp;" not in group, group
        for _href, label, _icon in items:
            assert "&amp;" not in label, label


@pytest.mark.parametrize("page", PAGES)
def test_no_page_shows_a_raw_html_entity(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    assert "&amp;amp;" not in text, page.name
    assert "&amp;lt;" not in text, page.name


def test_next_day_cards_prioritize_simulation_with_internal_scroll() -> None:
    css = _css(DOCS / "index.html")
    rule = re.search(r"\.next-day\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc .next-day"
    body = rule.group(1)
    assert "grid-template-columns:minmax(400px,2fr)repeat(2,minmax(280px,1fr))" in body
    assert "overflow-x:auto" in body and "align-items:stretch" in body


def test_next_day_order_is_simulation_then_special_then_loto_stacked() -> None:
    grid = _soup(DOCS / "index.html").find(class_="next-day")
    assert grid is not None
    kids = [k for k in grid.find_all(recursive=False)]
    assert kids[0].get("id") == "mo-phong"
    titles = [k.get_text(" ", strip=True)[:60] for k in kids[1:]]
    assert any("Đặc Biệt ngày mai" in t for t in titles[:1]), titles
    assert any("LOTO ngày mai" in t for t in titles[1:2]), titles


def test_bar_chart_uses_columns_instead_of_one_long_bar() -> None:
    css = _css(DOCS / "index.html")
    rule = re.search(r"\.bar-list\{([^}]*)\}", css)
    assert rule, "không tìm thấy quy tắc .bar-list"
    body = rule.group(1)
    assert "repeat(auto-fit,minmax(min(100%,560px),1fr))" in body
    assert "max-width" not in body, (
        "giới hạn bề rộng sẽ bỏ trống nửa thẻ; phải chia cột"
    )


def test_simulation_uses_the_same_compact_prize_grid() -> None:
    soup = _soup(DOCS / "index.html")
    board = soup.select_one(".fun-result-table.app-prize-table")
    assert board is not None
    assert len(board.select(".app-prize-number")) == 27
    assert len(board.select("tr[data-prize]")) == 8
    src = (ROOT / "src" / "pages" / "build_fun_prediction.py").read_text(encoding="utf-8")
    assert "minmax(0, 1.5fr) minmax(300px, 1fr)" in src
    assert "min-width: 520px" not in src
    assert src.index("Đặc Biệt ngày mai") < src.index("LOTO ngày mai")


def test_pair_frequency_screen_exists() -> None:
    soup = _soup(DOCS / "index.html")
    section = soup.find(id="tan-suat-cap")
    assert section is not None, "thiếu khu tần suất cặp LOTO"
    assert section.find("table") is not None


def test_pair_table_shows_the_expected_count_beside_the_observed() -> None:
    section = _soup(DOCS / "index.html").find(id="tan-suat-cap")
    headers = [th.get_text(strip=True) for th in section.select("thead th")]
    assert "Kỳ vọng" in headers
    assert "So kỳ vọng" in headers


def test_pair_table_carries_the_chance_maximum_warning() -> None:
    from pages.build_landing_page import pair_chance_maximum

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
    from pages.build_landing_page import pair_chance_maximum

    short_max, short_band = pair_chance_maximum(393)
    long_max, long_band = pair_chance_maximum(2200)

    assert short_max == pytest.approx(39.9, abs=0.2)
    assert long_max == pytest.approx(161.8, abs=0.5)
    assert long_max > 4 * short_max, "mốc phải tăng theo độ dài lịch sử"

    for chance_max, (low, high) in ((short_max, short_band), (long_max, long_band)):
        assert low < chance_max < high

    assert pair_chance_maximum(0) == (0.0, (0, 0))


def test_pair_chance_maximum_stays_above_the_per_pair_expectation() -> None:
    from pages.build_landing_page import PAIR_COOCCURRENCE_RATE, pair_chance_maximum

    for n_draws in (393, 1200, 2200):
        chance_max, _ = pair_chance_maximum(n_draws)
        per_pair = PAIR_COOCCURRENCE_RATE * n_draws
        assert chance_max > 1.3 * per_pair, (
            f"{n_draws} kỳ: cực đại {chance_max:.1f} không tách khỏi kỳ vọng "
            f"{per_pair:.1f}"
        )


def test_pair_cooccurrence_rate_uses_inclusion_exclusion() -> None:
    from pages.build_landing_page import PAIR_COOCCURRENCE_RATE

    single = 1.0 - 0.99**27
    exact = 1.0 - 2.0 * (0.99**27) + (0.98**27)
    assert PAIR_COOCCURRENCE_RATE == pytest.approx(exact, abs=1e-12)
    assert PAIR_COOCCURRENCE_RATE != pytest.approx(single**2, abs=1e-6), (
        "dùng bình phương là bỏ qua tính không độc lập"
    )
    assert PAIR_COOCCURRENCE_RATE == pytest.approx(0.0549, abs=5e-4)


def test_desktop_view_never_overrides_a_layout_the_base_sheet_defines() -> None:
    css = _css(ROOT / "src" / "pages" / "build_landing_page.py")
    overrides = re.findall(
        r"body\.desktop-view\s*([^{]+)\{([^}]*grid-template-columns[^}]*)\}", css
    )
    for selector, body in overrides:
        target = selector.strip().lstrip(".")
        if target not in {"inspector", "matrix-top", "basis-merged", "next-day", "fun-pred-grid"}:
            continue
        tracks = re.search(r"grid-template-columns:([^;!]*)", body)
        assert tracks, f"{selector}: không đọc được rãnh"
        assert tracks.group(1).count("minmax") <= 1, (
            f"body.desktop-view {selector} dựng lại bố cục nhiều cột; "
            "lớp nền đã lo phần này và !important ở đây sẽ lật ngược nó"
        )


def test_desktop_page_differs_from_the_default_one_only_by_its_body_class() -> None:
    docs = ROOT / "docs"
    default, desktop = docs / "index.html", docs / "landing_desktop.html"
    if not (default.exists() and desktop.exists()):
        return
    marker = ' class="desktop-view"'
    body = desktop.read_text(encoding="utf-8")
    assert marker in body, "trang máy tính thiếu lớp desktop-view"

    def than(html: str) -> str:
        dau = html.find('<main class="app-main"')
        if dau == -1:
            return html
        dau = html.index(">", dau) + 1
        return html[dau : html.rindex("</main>")]

    stripped = than(body.replace(marker, "", 1))
    expected = than(default.read_text(encoding="utf-8"))
    if stripped == expected:
        return

    import hashlib

    first = next(
        (i for i, (x, y) in enumerate(zip(stripped, expected, strict=False)) if x != y),
        min(len(stripped), len(expected)),
    )
    raise AssertionError(
        "hai trang khác nhau nhiều hơn một lớp trên thẻ body — chúng đã có bố cục "
        "riêng, và phép kiểm ghi đè desktop-view không phủ được nữa.\n"
        f"  digest index           : {hashlib.sha256(expected.encode()).hexdigest()[:16]}\n"
        f"  digest landing_desktop : {hashlib.sha256(stripped.encode()).hexdigest()[:16]}\n"
        f"  lệch từ ký tự {first}\n"
        f"  index           : {expected[first - 40:first + 60]!r}\n"
        f"  landing_desktop : {stripped[first - 40:first + 60]!r}"
    )
