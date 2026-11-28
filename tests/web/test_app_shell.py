from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "src"))

PAGES = sorted(DOCS.glob("*.html"))

def test_the_published_tree_holds_at_least_one_page() -> None:
    assert PAGES, "docs/ không có trang nào — các phép kiểm dưới sẽ quét tập rỗng"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_published_page_carries_the_shell(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    for dau in ('class="app-rail"', 'class="app-panel"', 'class="app-header"',
                'class="app-main"', 'id="app-toggle"'):
        assert dau in text, f"{page.name} thiếu {dau}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_published_page_carries_the_shell_twice(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    for dau in ('class="app-rail"', 'class="app-panel"', 'class="app-header"',
                'class="app-main"', 'id="app-toggle"'):
        assert text.count(dau) == 1, (
            f"{page.name} có {text.count(dau)} lần {dau}, phải đúng 1"
        )


@pytest.mark.parametrize("query", ["?rev=0123456789abcdef", "?rev=old&amp;mode=fast#tail"])
def test_wrapping_a_versioned_page_keeps_one_shell(query: str) -> None:
    from web.app_shell import wrap_page

    original = '<html><head></head><body><p id="business">07</p></body></html>'
    once = wrap_page(original, "index.html")
    versioned = once.replace('src="assets/app-shell.js"', f'src="assets/app-shell.js{query}"')
    repaired = wrap_page(versioned, "index.html")
    assert repaired == once
    assert repaired.count('class="app-main"') == 1
    assert '<p id="business">07</p>' in repaired


def test_wrapping_a_page_twice_gives_the_same_page() -> None:
    from web.app_shell import wrap_page

    goc = "<html><head></head><body><p>Nội dung thật</p></body></html>"
    mot = wrap_page(goc, "index.html")
    assert mot.count('class="app-rail"') == 1
    assert "<p>Nội dung thật</p>" in mot

    assert wrap_page(mot, "index.html") == mot

    from web.app_shell import header_html, panel_html, rail_html

    than = mot.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    long_nhau = (
        rail_html("index.html")
        + panel_html("index.html")
        + '<div class="app-scrim" id="app-scrim" hidden></div>'
        + header_html("index.html")
        + '<main class="app-main" id="app-main">'
        + than
        + "</main>"
        + '<script src="assets/app-shell.js" defer></script>'
    )
    assert long_nhau.count('class="app-rail"') == 2, "mẫu dựng sẵn phải thật sự hỏng"

    sua = wrap_page("<html><head></head><body>" + long_nhau + "</body></html>", "index.html")
    assert sua.count('class="app-rail"') == 1, "trang bọc chồng phải được bóc về một lớp"
    assert "<p>Nội dung thật</p>" in sua, "bóc khung không được đánh rơi nội dung"

    mat_script = long_nhau.replace(
        '<script src="assets/app-shell.js" defer></script>', "", 1
    )
    sua2 = wrap_page("<html><head></head><body>" + mat_script + "</body></html>", "index.html")
    assert sua2.count('class="app-rail"') == 1, "thiếu thẻ kịch bản vẫn phải bóc được"
    assert "<p>Nội dung thật</p>" in sua2


def _dock_script() -> str:
    return (Path(__file__).resolve().parents[1] / "fixtures" / "legacy_ui_dock_script.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("so_lop", [2, 8, 11, 12])
def test_a_page_nested_the_way_the_pipeline_nested_live_is_repaired(so_lop: int) -> None:
    import re

    from web.app_shell import header_html, panel_html, rail_html, wrap_page

    goc = "<html><head></head><body><p>Nội dung thật</p></body></html>"
    than = wrap_page(goc, "live.html").split("<body>", 1)[1].rsplit("</body>", 1)[0]
    for _ in range(so_lop - 1):
        than = (
            rail_html("live.html")
            + panel_html("live.html")
            + '<div class="app-scrim" id="app-scrim" hidden></div>'
            + header_html("live.html")
            + '<main class="app-main" id="app-main">'
            + re.sub(r"<(/?)main\b", r"<\1div", than)
            + _dock_script()
            + "</main>"
            + '<script src="assets/app-shell.js" defer></script>'
        )
    hong = "<html><head></head><body>" + than + "</body></html>"
    assert hong.count('class="app-rail"') == so_lop, "mẫu dựng sẵn phải thật sự hỏng"

    sua = wrap_page(hong, "live.html")

    assert sua.count('class="app-rail"') == 1
    assert sua.count('id="app-main"') == 1
    assert _dock_script() not in sua, "kịch bản dock mồ côi phải được gỡ"
    assert sua == wrap_page(goc, "live.html"), "sửa xong phải đúng từng byte bản bọc một lớp"


def test_refreshing_the_live_page_again_and_again_keeps_one_shell(tmp_path: Path) -> None:
    from web.ui_theme import refresh_live_page

    trang = tmp_path / "live.html"
    trang.write_text(
        "<!doctype html><html><head><style>body{margin:0}</style></head>"
        "<body><p>Nội dung thật</p></body></html>",
        encoding="utf-8",
    )
    refresh_live_page(tmp_path)
    lan_dau = trang.read_text(encoding="utf-8")
    for _ in range(4):
        refresh_live_page(tmp_path)

    sau = trang.read_text(encoding="utf-8")
    assert sau.count('class="app-rail"') == 1
    assert _dock_script() not in sau
    assert sau == lan_dau, "chạy lại phải cho ra đúng tệp ấy"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_published_page_carries_the_retired_dock_script(page: Path) -> None:
    assert _dock_script() not in page.read_text(encoding="utf-8")


def test_the_rail_has_one_button_per_navigation_group() -> None:
    from web.ui_theme import SITE_NAV

    text = (DOCS / "statistics.html").read_text(encoding="utf-8")
    assert text.count('class="app-rail-btn"') == len(SITE_NAV)


def test_every_navigation_target_is_a_real_page() -> None:
    from web.ui_theme import SITE_NAV

    thieu = [
        href
        for _, muc in SITE_NAV
        for href, _, _ in muc
        if not (DOCS / href.split("#", 1)[0]).is_file()
    ]
    assert not thieu, f"điều hướng trỏ tới trang không có: {thieu}"


@pytest.fixture()
def trinh_duyet():
    if os.environ.get("UI_BROWSER_REQUIRED") == "1":
        import playwright.sync_api as playwright
    else:
        playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pw:
        options = {"args": ["--no-sandbox"]}
        if os.environ.get("UI_CHROMIUM_EXECUTABLE"):
            options["executable_path"] = os.environ["UI_CHROMIUM_EXECUTABLE"]
        if os.environ.get("UI_CHROMIUM_ARGS_FILE"):
            options["args"] = json.loads(Path(os.environ["UI_CHROMIUM_ARGS_FILE"]).read_text())
        try:
            b = pw.chromium.launch(**options)
        except playwright.Error:
            if os.environ.get("UI_BROWSER_REQUIRED") == "1" or options.get("executable_path"):
                raise
            pytest.skip("chưa cài Chromium; browser CI phải cài và chạy phép kiểm này")
        yield b
        b.close()


def _mo(trinh_duyet, w: int, h: int, cam_ung: bool = False):
    return trinh_duyet.new_page(
        viewport={"width": w, "height": h},
        has_touch=cam_ung,
        is_mobile=cam_ung,
    )


def test_the_detail_panel_overlays_the_content_instead_of_pushing_it(trinh_duyet) -> None:
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    truoc = pg.evaluate("() => getComputedStyle(document.querySelector('.app-main')).marginLeft")
    pg.click("#app-toggle")
    pg.wait_for_timeout(500)
    sau = pg.evaluate("() => getComputedStyle(document.querySelector('.app-main')).marginLeft")
    mo = pg.evaluate("() => document.body.classList.contains('app-panel-open')")
    pg.close()
    assert mo, "bấm nút mà dải chi tiết không mở"
    assert truoc == sau, f"nội dung bị đẩy: {truoc} -> {sau}"


def test_the_toggle_stays_clickable_while_the_panel_is_open(trinh_duyet) -> None:
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    pg.click("#app-toggle")
    pg.wait_for_timeout(500)
    tren_cung = pg.evaluate(
        """() => {
          const t = document.getElementById('app-toggle');
          const r = t.getBoundingClientRect();
          const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return t === el || t.contains(el);
        }"""
    )
    pg.click("#app-toggle")
    pg.wait_for_timeout(400)
    dong = pg.evaluate("() => !document.body.classList.contains('app-panel-open')")
    pg.close()
    assert tren_cung, "nút thu/mở bị dải chi tiết che"
    assert dong, "bấm lần hai không đóng được"


def test_touch_can_reach_every_navigation_link_on_a_phone(trinh_duyet) -> None:
    from web.ui_theme import SITE_NAV

    pg = _mo(trinh_duyet, 390, 844, cam_ung=True)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    pg.tap("#app-toggle")
    pg.wait_for_timeout(600)
    so_nhom = pg.locator(".app-rail-btn").count()
    ket_qua = []
    for i in range(so_nhom):
        pg.locator(".app-rail-btn").nth(i).tap()
        pg.wait_for_timeout(400)
        links = pg.locator(".app-panel-group:not([hidden]) .app-nav-item")
        hong = []
        panel = pg.locator(".app-panel").bounding_box()
        pg.mouse.move(panel["x"] + panel["width"] / 2, panel["y"] + panel["height"] / 2)
        pg.mouse.wheel(0, -10_000)
        pg.wait_for_timeout(100)
        for link in links.all():
            for _ in range(20):
                reached = link.evaluate("""a => {
                const r = a.getBoundingClientRect();
                const el = r.width >= 4 && r.height >= 4
                  ? document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) : null;
                return !!(el && (a === el || a.contains(el)));
                }""")
                if reached:
                    break
                pg.mouse.wheel(0, 160)
                pg.wait_for_timeout(50)
            if not reached:
                hong.append(link.get_attribute("href"))
        ket_qua.append({"tong": links.count(), "hong": hong})
    pg.close()
    assert so_nhom == len(SITE_NAV), f"chỉ {so_nhom} nút nhóm trên dải biểu tượng"
    tong = sum(do["tong"] for do in ket_qua)
    hong = [href for do in ket_qua for href in do["hong"]]
    can = sum(len(items) for _, items in SITE_NAV)
    assert tong == can, f"chỉ thấy {tong}/{can} liên kết khi đi qua mọi nhóm — menu chưa mở?"
    assert not hong, f"{len(hong)}/{tong} liên kết không chạm được: {hong}"


def test_page_widgets_never_cover_links_in_the_open_menu(trinh_duyet) -> None:
    pg = _mo(trinh_duyet, 1440, 844)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.locator("#app-tab-5").click()
    links = pg.locator("#app-panel-5 .app-nav-item")
    assert links.count() == 13
    covered = []
    for link in links.all():
        link.scroll_into_view_if_needed()
        if not link.evaluate("""a => {
            const r = a.getBoundingClientRect();
            const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return e && (e === a || a.contains(e));
        }"""):
            covered.append(link.get_attribute("href"))
    pg.close()
    assert not covered, f"nội dung trang che mục menu: {covered}"


def test_no_floating_element_covers_the_navigation_controls(trinh_duyet) -> None:
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    che = pg.evaluate(
        """() => {
          const diem = [];
          const h = document.querySelector('.app-header').getBoundingClientRect();
          diem.push([h.left + 40, h.top + h.height / 2]);
          const r = document.querySelector('.app-rail').getBoundingClientRect();
          diem.push([r.left + r.width / 2, r.top + 150]);
          const xau = [];
          for (const [x, y] of diem) {
            const el = document.elementFromPoint(x, y);
            if (!el) { xau.push('không có phần tử'); continue; }
            if (!el.closest('.app-header, .app-rail, .app-panel')) {
              xau.push(el.tagName + '.' + (el.className || '').toString().slice(0, 40));
            }
          }
          return xau;
        }"""
    )
    pg.close()
    assert not che, f"phần tử nổi che điều hướng: {che}"


def test_the_theme_button_changes_resolved_theme_and_remembers(trinh_duyet) -> None:
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    thay = []
    for _ in range(4):
        thay.append(pg.evaluate("() => document.documentElement.classList.contains('dark')"))
        pg.click("#app-theme")
        pg.wait_for_timeout(250)
    luu = pg.evaluate("() => localStorage.getItem('app-theme')")
    pg.close()
    assert all(left != right for left, right in zip(thay, thay[1:], strict=False)), thay
    assert luu in {"light", "dark"}, f"không ghi nhớ lựa chọn: {luu!r}"


def test_the_search_only_offers_pages_that_exist(trinh_duyet) -> None:
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    pg.click("#app-toggle")
    pg.wait_for_timeout(400)
    pg.click("#app-search-open")
    pg.fill("#app-global-search-input", "tần suất")
    pg.wait_for_timeout(400)
    href = pg.evaluate(
        """() => [...document.querySelectorAll('.app-global-result')]
               .filter(a => a.offsetParent !== null)
               .map(a => a.getAttribute('href'))"""
    )
    trong = pg.evaluate("""() => { document.getElementById('app-global-search-input').value='zzzz';
        document.getElementById('app-global-search-input').dispatchEvent(new Event('input'));
        return document.getElementById('app-global-search-empty').hidden; }""")
    pg.close()
    assert href, "tìm 'tần suất' không ra kết quả nào"
    thieu = [h for h in href if not (DOCS / h.split("#", 1)[0]).is_file()]
    assert not thieu, f"kết quả tìm trỏ tới trang không có: {thieu}"
    assert trong is False, "không khớp gì mà vẫn không báo cho người dùng"
