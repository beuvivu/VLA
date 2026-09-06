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


def test_pages_exist() -> None:
    assert len(PAGES) >= 14, "thiếu trang đã sinh; hãy chạy lại bộ dựng"


# --- Font ------------------------------------------------------------------


def test_shared_css_declares_aptos_first() -> None:
    match = re.search(r"--vla-font:([^;]+);", TAILWIND_LITE_CSS)
    assert match, "không tìm thấy token --vla-font"
    assert match.group(1).strip().startswith("Aptos")


def test_shared_css_has_a_real_fallback_chain() -> None:
    """Aptos chỉ có trên máy cài Microsoft 365; thiếu fallback là hỏng bố cục."""
    match = re.search(r"--vla-font:([^;]+);", TAILWIND_LITE_CSS)
    families = [f.strip().strip('"') for f in match.group(1).split(",")]
    assert "system-ui" in families
    assert families[-1] == "sans-serif"


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


def test_no_font_file_is_committed_to_docs() -> None:
    for suffix in ("*.woff", "*.woff2", "*.ttf", "*.otf"):
        assert not list(DOCS.rglob(suffix)), f"tệp font {suffix} không được phân phối lại"


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


def test_sidebar_state_persists_in_local_storage() -> None:
    for name in ("index.html", "dashboard.html"):
        text = (DOCS / name).read_text(encoding="utf-8")
        assert "vla-sidebar-collapsed" in text, name
        assert "localStorage" in text, name


def test_sidebar_toggle_is_reachable_by_keyboard_and_screen_readers() -> None:
    for name in ("index.html", "dashboard.html"):
        soup = _soup(DOCS / name)
        button = soup.find("button", id=re.compile("toggle"))
        assert button is not None, name
        assert button.get("aria-expanded") is not None, name
        # Nút chỉ có biểu tượng; thiếu nhãn ẩn thì chỉ nghe thấy "nút".
        assert button.find(class_=re.compile("sr-only")) is not None, name


# --- Điều hướng ------------------------------------------------------------


def test_navigation_covers_every_generated_page() -> None:
    """Hai trang cầu ổn định từng không được liên kết từ bất kỳ đâu."""
    missing = {p.name for p in PAGES} - nav_targets() - INDEX_ALIASES
    assert not missing, f"trang không có trong điều hướng: {sorted(missing)}"


def test_navigation_has_the_five_agreed_groups() -> None:
    assert [group for group, _ in SITE_NAV] == [
        "Trực tiếp",
        "Thống kê",
        "Cầu kèo",
        "Phỏng đoán",
        "Tool nâng cao",
    ]


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
    """Live → kết quả → chục×đơn vị + ma trận → mô phỏng → ngày mai → thống kê."""
    ids = [s.get("id") for s in _soup(DOCS / "index.html").find_all("section")]
    expected = [
        "live",
        "ket-qua",
        "chuc-don-vi",
        "ma-tran-ngay",
        "mo-phong",
        "ai-ml",
        "tan-suat-loto",
    ]
    positions = [ids.index(sid) for sid in expected]
    assert positions == sorted(positions), dict(zip(expected, positions, strict=True))


def test_side_by_side_blocks_use_a_stretching_grid() -> None:
    """align-items:start là nguyên nhân các khối cùng hàng cao thấp lệch nhau."""
    css = (DOCS / "index.html").read_text(encoding="utf-8")
    pair = re.search(r"\.pair-row\s*\{([^}]*)\}", css)
    assert pair and "stretch" in pair.group(1)
    inspector = re.search(r"\.inspector\s*\{([^}]*)\}", css)
    assert inspector and "stretch" in inspector.group(1)
    assert "align-items: start" not in inspector.group(1)


def test_evidence_block_is_a_three_column_grid() -> None:
    css = (DOCS / "index.html").read_text(encoding="utf-8")
    inspector = re.search(r"\.inspector\s*\{([^}]*)\}", css)
    assert "repeat(3," in inspector.group(1).replace(" ", "")


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
