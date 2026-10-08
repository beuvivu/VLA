"""Kiểm tra bản HTML đã xuất bản bằng Chromium, lưu ảnh để duyệt trực quan."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import threading

from playwright.sync_api import expect, sync_playwright
from check_landing_readability_browser import check_landing

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ui-browser-artifacts"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def contrast(colors):
    """Độ tương phản từ màu đã phân giải trong Chromium, không chép token."""
    def luminance(color):
        rgb = [float(n.strip()) / 255 for n in color.split("(")[1].split(")")[0].split(",")[:3]]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722), strict=True))
    light, dark = sorted((luminance(colors["fg"]), luminance(colors["bg"])), reverse=True)
    return (light + .05) / (dark + .05)


def check_evidence(page, name, width, dark):
    """Mọi trang: một con số mở được nguồn & bằng chứng.

    Ưu tiên con số chưa có chức năng nhấp (nhấp thường mở ngăn kéo). Trang mà
    mọi con số đều đã có chức năng (ô đánh dấu của trang thống kê) thì dùng
    Alt + nhấp — đúng lối mà tooltip của những ô ấy chỉ dẫn. Rê chuột chỉ đo
    ở bản rộng, nền sáng; chữ của giá trị phải đạt AA trên nền ngăn kéo ở cả
    hai chế độ màu; Escape đóng ngăn kéo.
    """
    found = page.evaluate_handle("""() => {
      const root = document.getElementById('app-main');
      const inView = e => { const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.bottom > 90 && r.top < innerHeight - 20 &&
          r.left > 0 && r.right < innerWidth; };
      const busy = e => !!e.closest('a[href],button,label,summary,[onclick],[data-key],.tr-number,.tr-mini,[role=button]');
      let fallback = null;
      for (const e of root.querySelectorAll('td, th, span, strong, b, em, p, li, div, dd, small, text')) {
        const hit = window.appEvidence && window.appEvidence.find(e);
        if (hit !== e) continue;
        if (!busy(hit)) { hit.scrollIntoView({block: 'center'}); if (inView(hit)) return {el: hit, alt: false}; }
        else if (!fallback) fallback = hit;
      }
      if (fallback) { fallback.scrollIntoView({block: 'center'}); return {el: fallback, alt: true}; }
      return null;
    }""")
    alt = found.evaluate("r => r && r.alt")
    target = found.evaluate_handle("r => r && r.el").as_element()
    assert target is not None, f"{name}: không tìm thấy con số nào nhận được bằng chứng"
    if width > 640 and not dark:
        # Trang trước có thể để con trỏ nằm sẵn đúng chỗ (hai trang ML cùng bố
        # cục): không di chuột thì trình duyệt không phát mouseover.
        page.mouse.move(1, 1)
        target.hover()
        tip = page.locator("#app-evidence-tip")
        expect(tip).to_be_visible()
        text = tip.text_content()
        assert "Nguồn" in text and "bằng chứng suy luận" in text, text
        assert ("Alt + nhấp" in text) == bool(alt), text
    target.click(modifiers=["Alt"] if alt else [])
    drawer = page.locator("#app-evidence-drawer")
    expect(drawer).to_be_visible()
    assert drawer.locator(".app-evidence-sources li").count() >= 1
    assert drawer.locator(".app-evidence-steps li").count() >= 1
    colors = drawer.locator(".app-evidence-value").evaluate(
        "e => ({fg:getComputedStyle(e).color,bg:getComputedStyle(e.closest('dialog')).backgroundColor})")
    assert contrast(colors) >= 4.5, colors
    box = drawer.bounding_box()
    assert box["x"] >= -1 and box["x"] + box["width"] <= width + 1, box
    page.keyboard.press("Escape")
    expect(drawer).not_to_be_visible()
    if width > 640 and not dark:
        # Bàn phím: vùng chứa số nhận tiêu điểm, mũi tên chọn số, Enter mở.
        # Trang tự dựng lại (live) có thể đã thay phần tử: lấy vùng còn gắn trên trang.
        page.wait_for_function("document.querySelector('#app-main [data-evidence-region]')")
        region = target.evaluate_handle(
            "e => (e.isConnected && e.closest('[data-evidence-region]')) || "
            "document.querySelector('#app-main [data-evidence-region]')").as_element()
        assert region is not None, f"{name}: con số không thuộc vùng bàn phím nào"
        page.keyboard.press("Shift")
        region.focus()
        expect(page.locator(".app-evidence-active")).to_have_count(1)
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter")
        expect(drawer).to_be_visible()
        page.keyboard.press("Escape")
        expect(drawer).not_to_be_visible()
        assert region.evaluate("e => document.activeElement === e"), f"{name}: tiêu điểm không về vùng"
    return ("alt:" if alt else "") + target.evaluate("e => e.textContent.trim().slice(0, 24)")


def check_evidence_keeps_existing_clicks(page):
    """Ô đã có chức năng nhấp (đánh dấu) giữ nguyên; Alt + nhấp mới mở bằng chứng."""
    cell = page.locator("#sp-matrix-grid td.cell[data-key]").filter(has_text="1").first
    cell.scroll_into_view_if_needed()
    before = cell.evaluate("e => e.classList.contains('marked')")
    cell.click()
    assert cell.evaluate("e => e.classList.contains('marked')") != before
    assert not page.locator("#app-evidence-drawer").is_visible()
    marked = cell.evaluate("e => e.classList.contains('marked')")
    cell.click(modifiers=["Alt"])
    expect(page.locator("#app-evidence-drawer")).to_be_visible()
    assert cell.evaluate("e => e.classList.contains('marked')") == marked
    page.keyboard.press("Escape")
    cell.click()


def main():
    OUT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "docs")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    results, failures = [], []
    pages = sorted(p.name for p in (ROOT / "docs").glob("*.html") if 'id="app-main"' in p.read_text())
    assert len(pages) >= 29, "Không được kiểm tra trên tập trang rỗng/thiếu"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width in (390, 1440):
                context = browser.new_context(viewport={"width": width, "height": 950}, color_scheme="light", reduced_motion="reduce")
                page = context.new_page()
                # A fixed draw fixture makes the LIVE forecast/date contract deterministic.
                live_fixture = {
                    "draw_date": "2026-09-26", "status": "complete_verified",
                    "verified_complete": True, "progress_percent": 100,
                    "verification_percent": 100, "checked_at_local": "2026-09-26T18:35:00+07:00",
                    "prizes": {key: ["0" * digits] * count for key, count, digits in [
                        ("special", 1, 5), ("prize1", 1, 5), ("prize2", 2, 5),
                        ("prize3", 6, 5), ("prize4", 4, 4), ("prize5", 6, 4),
                        ("prize6", 3, 3), ("prize7", 4, 2),
                    ]}, "conflicts": [],
                }
                page.route("**/live.json*", lambda route, _request, live_fixture=live_fixture: route.fulfill(
                    content_type="application/json", body=json.dumps(live_fixture)))
                def forecast_route(route):
                    # Kỳ 26-09 đã quay xong, nên khối dự đoán phải nhắm kỳ kế tiếp.
                    if not route.request.url.endswith("_2026-09-27.csv"):
                        route.fulfill(status=404, body="")
                        return
                    route.fulfill(content_type="text/csv", body=(
                        "predict_for_date,rank,number,cau_score,prob\n"
                        "2026-09-27,1,05,70.1,0.01\n2026-09-27,2,42,65.3,0.01\n"))
                # Trang trực tiếp đọc bản chụp 10 số đầu bảng Cầu Kèo theo ngày quay.
                page.route("**/ai_ml/daily/cau_keo_*_top10_*.csv", forecast_route)
                errors = []
                page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                for name in pages:
                    errors.clear()
                    try:
                        page.goto(f"{base}/{name}", wait_until="load")
                        page.locator("body[data-app-shell-ready]").wait_for()
                        for dark in (False, True):
                            if page.locator("html").evaluate("e => e.classList.contains('dark')") != dark:
                                page.locator("#app-theme").click()
                            state = page.evaluate("""() => {
                              const root = document.documentElement;
                              const header = getComputedStyle(document.querySelector('.app-header'));
                              return {dark:root.classList.contains('dark'), surface:header.backgroundColor,
                                overflow:root.scrollWidth-root.clientWidth,
                                shells:document.querySelectorAll('#app-main').length};
                            }""")
                            assert state["dark"] == dark and state["shells"] == 1, state
                            if name != "landing_desktop.html":
                                assert state["overflow"] <= 1, state
                            rgb = [int(n.strip()) for n in state["surface"].split("(")[1].split(")")[0].split(",")[:3]]
                            assert (max(rgb) < 100) if dark else (min(rgb) > 200), state
                            page.keyboard.press("Control+k")
                            search = page.locator("#app-global-search-input")
                            search.fill("tan suat")
                            assert page.locator(".app-global-result:visible").count() >= 2
                            search.fill("khongcochucnang987")
                            assert page.locator("#app-global-search-empty").is_visible()
                            search.press("Escape")
                            assert not page.locator("#app-global-search").is_visible()
                            if name in ("tan-suat-loto.html", "tan-suat-cap-loto.html"):
                                if name == "tan-suat-cap-loto.html":
                                    picker = page.locator("details").filter(has=page.locator("#bf-pair-picker"))
                                    if picker.get_attribute("open") is None:
                                        picker.locator("summary").click()
                                    assert page.locator(".bf-pair-grid button").count() == 50
                                    button = page.locator(".bf-pair-grid button").first
                                    button.click()
                                    expect(button).to_have_attribute("aria-pressed", "false")
                                    button.click()
                                    expect(button).to_have_attribute("aria-pressed", "true")
                                    colors = button.evaluate("e => ({fg:getComputedStyle(e).color,bg:getComputedStyle(e).backgroundColor})")
                                    assert contrast(colors) >= 4.5, colors
                                    picker.locator("summary").click()
                                cell = page.locator("#sp-matrix-grid td.sp-n2").first
                                assert cell.count(), "Thiếu ô 2 nháy để đo màu dữ liệu"
                                colors = cell.evaluate("e => ({fg:getComputedStyle(e).color,bg:getComputedStyle(e).backgroundColor})")
                                assert contrast(colors) >= 4.5, colors
                            assert page.locator("#app-sidebar-filter").count() == 0
                            assert page.locator(".app-calendar-link").get_attribute("href") == "index.html#db-tuan-thang"
                            if name == "live.html":
                                expect(page.locator(".live-prediction-list li")).to_have_count(4)
                                expect(page.locator("#live-prediction-date")).to_have_attribute("datetime", "2026-09-27")
                                assert page.locator(".live-actions a").evaluate_all(
                                    "nodes => nodes.map(n => n.getAttribute('href'))"
                                ) == ["index.html", "so-ket-qua-truyen-thong.html", "statistics.html"]
                                assert page.locator('[data-prediction-mode="de"] .live-prediction-number').all_text_contents() == ["05", "42"]
                                assert page.locator("#sources").count() == 0
                            if name == "index.html":
                                assert page.locator(".app-hero-shortcut").evaluate_all(
                                    "nodes => nodes.map(n => n.getAttribute('href'))"
                                ) == ["statistics.html", "so-ket-qua-truyen-thong.html"]
                            state["evidence"] = check_evidence(page, name, width, dark)
                            if name == "tan-suat-loto.html" and not dark:
                                check_evidence_keeps_existing_clicks(page)
                            if name in ("index.html", "statistics.html", "tan-suat-cap-loto.html", "live.html"):
                                page.screenshot(path=str(OUT / f"{name}-{width}-{'dark' if dark else 'light'}.png"))
                            if name == "index.html":
                                state["landing"] = check_landing(page, OUT, width, dark)
                            results.append({"page": name, "width": width, **state})
                        assert not errors, errors
                    except Exception as error:
                        failures.append({"page": name, "width": width, "error": str(error)})
                        page.screenshot(path=str(OUT / f"failure-{name}-{width}.png"))
                # Đóng modal phải trả focus về mục menu đã mở nó.
                page.goto(base + "/tan-suat-cap-loto.html", wait_until="load")
                # Reference header controls must work at both widths, with visible menus.
                page.locator('#app-profile-toggle').click()
                expect(page.locator('#app-profile-menu')).to_be_visible()
                page.locator('#app-notifications-toggle').click()
                expect(page.locator('#app-profile-menu')).not_to_be_visible()
                notifications = page.locator('#app-notifications-menu')
                expect(notifications).to_be_visible()
                menu_box = notifications.bounding_box()
                assert menu_box['x'] >= 0 and menu_box['x'] + menu_box['width'] <= width
                notifications.locator('a').first.focus()
                page.keyboard.press('Escape')
                expect(page.locator('#app-notifications-toggle')).to_be_focused()
                expect(notifications).not_to_be_visible()
                page.locator('#app-profile-toggle').press('ArrowDown')
                expect(page.locator('#app-profile-menu a').first).to_be_focused()
                page.keyboard.press('Escape')
                expect(page.locator('#app-profile-toggle')).to_be_focused()
                assert page.locator('.app-rail svg').count() == 10
                assert page.locator('.app-rail-divider').count() == 3
                page.locator("#app-toggle").click()
                sidebar = page.locator(".app-panel-group:not([hidden]) .app-nav-item").first
                sidebar.focus()
                sidebar.press("Control+k")
                page.locator("#app-global-search-input").fill("nghien cuu")
                assert page.locator(".app-global-result:visible").count() >= 1
                page.locator("#app-global-search-input").press("Escape")
                expect(sidebar).to_be_focused()
                sidebar.press("Escape")
                sidebar.press("Escape")
                assert not page.locator("#app-main").evaluate("e => e.inert")
                expect(page.locator("#app-toggle")).to_be_focused()
                if width == 390:
                    # Mô phỏng người dùng đóng nền phủ khi đang chọn mục menu.
                    page.locator("#app-toggle").click()
                    sidebar.focus()
                    page.locator("#app-scrim").click(position={"x": 370, "y": 500})
                    expect(page.locator("#app-toggle")).to_be_focused()
                    assert page.locator("#app-panel").evaluate("e => e.inert")
                    assert not page.locator("#app-main").evaluate("e => e.inert")
                context.close()
            browser.close()
    finally:
        server.shutdown()
        (OUT / "report.json").write_text(json.dumps({"checks": results, "failures": failures}, ensure_ascii=False, indent=2))
    print(f"{len(results)} trạng thái trang đã đo; {len(failures)} lỗi", flush=True)
    assert not failures, failures


if __name__ == "__main__":
    main()
