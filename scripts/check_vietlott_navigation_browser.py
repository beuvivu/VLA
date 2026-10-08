"""Kiểm tra điều hướng Vietlott thật trên Chromium, desktop/mobile và hai theme."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ui-browser-artifacts'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    OUT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT / 'docs')))
    Thread(target=server.serve_forever, daemon=True).start()
    checks = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width in (320, 390, 768, 1440):
                for theme in ('light', 'dark'):
                    context = browser.new_context(viewport={'width': width, 'height': 900}, color_scheme=theme,
                                                  reduced_motion='reduce', has_touch=width < 1200)
                    for name in ('index.html', 'dashboard.html', 'vietlott.html'):
                        page = context.new_page()
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{server.server_port}/{name}', wait_until='networkidle')
                        before = page.locator('#app-main').bounding_box()
                        if width < 1200:
                            page.locator('#app-toggle').click()
                        ticket = page.locator('.app-rail-btn[data-app-module="vietlott"]')
                        # Trang Vietlott có thể đã mở đúng nhóm trên mobile.
                        if page.locator('#app-panel').get_attribute('aria-hidden') == 'true' or ticket.get_attribute('aria-selected') != 'true':
                            ticket.click()
                        expect(ticket).to_have_attribute('aria-selected', 'true')
                        expect(page.locator('#app-panel')).to_have_attribute('aria-hidden', 'false')
                        links = page.locator('.app-panel-group[data-app-module="vietlott"] .app-nav-item')
                        assert links.count() == 18
                        for link in links.all():
                            link.scroll_into_view_if_needed()
                            assert link.evaluate('el => {const r=el.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return el===hit || el.contains(hit)}')
                        after = page.locator('#app-main').bounding_box()
                        assert before['x'] == after['x'] and before['width'] == after['width']
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                        if name == 'vietlott.html':
                            page.locator('#app-panel').evaluate('el => el.scrollTop')
                            links.first.scroll_into_view_if_needed()
                            page.screenshot(path=str(OUT / f'vietlott-nav-{width}-{theme}.png'))
                            target = page.locator('.app-nav-item[href="vietlott.html#vl-pairs"]')
                            target.click()
                            expect(target).to_have_attribute('aria-current', 'page')
                            expect(page.locator('#app-panel')).to_have_attribute('aria-hidden', 'true')
                            assert page.locator('#vl-pairs').is_visible()
                            assert page.locator('#app-main').evaluate('el => !el.inert')
                        else:
                            page.keyboard.press('Escape')
                            expect(page.locator('#app-panel')).to_have_attribute('aria-hidden', 'true')
                        assert not errors, errors
                        checks.append({'page': name, 'width': width, 'theme': theme, 'ok': True})
                        page.close()
                    context.close()
            # Pointer thực, có animation: hover không lưu trạng thái; click ghim.
            context = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = context.new_page()
            page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
            ticket = page.locator('.app-rail-btn[data-app-module="vietlott"]')
            ticket.hover()
            expect(page.locator('#app-panel')).to_have_attribute('aria-hidden', 'false')
            assert page.evaluate('localStorage.getItem("app-panel-open")') == '0'
            ticket.click()
            page.mouse.move(1000, 500)
            page.wait_for_timeout(300)
            expect(page.locator('#app-panel')).to_have_attribute('aria-hidden', 'false')
            ticket.click()
            expect(page.locator('#app-panel')).to_have_attribute('aria-hidden', 'true')
            context.close()
            browser.close()
    finally:
        server.shutdown()
    (OUT / 'vietlott-navigation.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(f'{len(checks)} trạng thái Vietlott + hover/click: đạt')


if __name__ == '__main__':
    main()
