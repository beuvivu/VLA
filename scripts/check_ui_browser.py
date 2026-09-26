"""Kiểm tra bản HTML đã xuất bản bằng Chromium, lưu ảnh để duyệt trực quan."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import threading

from playwright.sync_api import expect, sync_playwright

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
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted((luminance(colors["fg"]), luminance(colors["bg"])), reverse=True)
    return (light + .05) / (dark + .05)


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
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
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
                            if name in ("index.html", "statistics.html", "tan-suat-cap-loto.html"):
                                page.screenshot(path=str(OUT / f"{name}-{width}-{'dark' if dark else 'light'}.png"))
                            results.append({"page": name, "width": width, **state})
                        assert not errors, errors
                    except Exception as error:
                        failures.append({"page": name, "width": width, "error": str(error)})
                        page.screenshot(path=str(OUT / f"failure-{name}-{width}.png"))
                # Hai truy vấn tồn tại cùng lúc, đóng modal phải trả về bộ lọc.
                page.goto(base + "/tan-suat-cap-loto.html", wait_until="load")
                page.locator("#app-toggle").click()
                sidebar = page.locator("#app-sidebar-filter")
                sidebar.fill("cap")
                sidebar.press("Control+k")
                page.locator("#app-global-search-input").fill("nghien cuu")
                assert sidebar.input_value() == "cap"
                assert page.locator(".app-global-result:visible").count() >= 1
                page.locator("#app-global-search-input").press("Escape")
                expect(sidebar).to_be_focused()
                assert sidebar.input_value() == "cap"
                sidebar.press("Escape")
                sidebar.press("Escape")
                assert not page.locator("#app-main").evaluate("e => e.inert")
                expect(page.locator("#app-toggle")).to_be_focused()
                if width == 390:
                    # Mô phỏng người dùng đóng nền phủ khi đang nhập bộ lọc.
                    page.locator("#app-toggle").click()
                    sidebar.fill("cap")
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
