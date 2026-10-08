"""Kiểm tra Vietlott thật: font/theme, responsive và bộ số nháp trên Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ui-browser-artifacts'
PAGES = ('vietlott.html', 'vietlott-lotto-535.html', 'vietlott-mega-645.html',
         'vietlott-power-655.html', 'vietlott-max-3d.html', 'vietlott-max-3d-pro.html',
         'vietlott-keno.html', 'vietlott-bingo18.html')


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    OUT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT / 'docs')))
    Thread(target=server.serve_forever, daemon=True).start()
    checks = []
    options = {}
    if os.environ.get('UI_CHROMIUM_EXECUTABLE'):
        options['executable_path'] = os.environ['UI_CHROMIUM_EXECUTABLE']
    if os.environ.get('UI_CHROMIUM_ARGS_FILE'):
        options['args'] = json.loads(Path(os.environ['UI_CHROMIUM_ARGS_FILE']).read_text())
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**options)
            context = browser.new_context(reduced_motion='reduce', accept_downloads=True)
            for width in (320, 390, 768, 1440):
                for theme in ('light', 'dark'):
                    context.clear_cookies()
                    for name in PAGES:
                        page = context.new_page()
                        page.set_viewport_size({'width': width, 'height': 900})
                        page.emulate_media(color_scheme=theme)
                        errors = []
                        page.on('pageerror', lambda error, found=errors: found.append(str(error)))
                        page.goto(f'http://127.0.0.1:{server.server_port}/{name}', wait_until='networkidle')
                        page.evaluate('localStorage.removeItem("app-theme")')
                        page.reload(wait_until='networkidle')
                        page.evaluate('document.fonts.ready')
                        assert page.evaluate('document.documentElement.classList.contains("dark")') == (theme == 'dark')
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (name, width, theme)
                        assert 'Inter var' in page.locator('.vl-hero h1').evaluate('el => getComputedStyle(el).fontFamily')
                        assert page.evaluate('(font) => document.fonts.check(font)', '750 16px "Inter var"')
                        assert 'Instrument Sans' in page.locator('.app-header').evaluate('el => getComputedStyle(el).fontFamily')
                        for button in page.locator('.vl-button, .vl-pick, .vl-product').all():
                            if button.is_visible():
                                assert button.bounding_box()['height'] >= 44, (name, width)
                        if name in ('vietlott-mega-645.html', 'vietlott-power-655.html'):
                            board = page.locator('[data-vl-picks]')
                            for number in range(1, 7):
                                board.locator(f'[data-vl-number="{number}"]').click()
                            expect(board.locator('[aria-pressed="true"]')).to_have_count(6)
                            board.locator('[data-vl-number="7"]').click(force=True)
                            expect(board.locator('[aria-pressed="true"]')).to_have_count(6)
                            review = board.locator('[data-vl-review]')
                            review.click()
                            expect(board.locator('dialog')).to_be_visible()
                            expect(board.locator('[data-vl-preview]')).to_have_text('01 · 02 · 03 · 04 · 05 · 06')
                            with page.expect_download() as download:
                                board.locator('[data-vl-download]').click()
                            assert download.value.suggested_filename.endswith('-bo-so-nhap.txt')
                            text = Path(download.value.path()).read_text(encoding='utf-8')
                            assert 'BỘ SỐ NHÁP' in text and '01 02 03 04 05 06' in text
                            page.keyboard.press('Escape')
                            expect(board.locator('dialog')).not_to_be_visible()
                            expect(review).to_be_focused()
                            page.locator('#app-theme').click()
                            expect(board.locator('[aria-pressed="true"]')).to_have_count(6)
                            assert page.evaluate('document.documentElement.classList.contains("dark")') == (theme == 'light')
                            page.locator('#app-theme').click()
                            board.locator('[data-vl-clear]').click()
                            expect(review).to_be_disabled()
                            board.locator('[data-vl-random]').click()
                            expect(board.locator('[aria-pressed="true"]')).to_have_count(6)
                            board.locator('[data-vl-clear]').click()
                            board.locator('[data-vl-number="1"]').focus()
                            page.keyboard.press('ArrowRight')
                            expect(board.locator('[data-vl-number="2"]')).to_be_focused()
                            page.keyboard.press('Space')
                            expect(board.locator('[data-vl-number="2"]')).to_have_attribute('aria-pressed', 'true')
                        if name == 'vietlott.html' or (width in (390, 1440) and name == 'vietlott-mega-645.html'):
                            page.evaluate('scrollTo({top:0,behavior:"instant"})')
                            page.wait_for_function('scrollY === 0')
                            page.screenshot(path=str(OUT / f'{name[:-5]}-{width}-{theme}.png'))
                        assert not errors, (name, errors)
                        checks.append({'page': name, 'width': width, 'theme': theme, 'ok': True})
                        page.close()
            browser.close()
    finally:
        server.shutdown()
    (OUT / 'vietlott-ui.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(f'{len(checks)} trạng thái Vietlott: font/theme, responsive và bộ số nháp đạt')


if __name__ == '__main__':
    main()
