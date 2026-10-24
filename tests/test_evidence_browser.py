"""Số bị gấp hoặc lọc ẩn không được chọn bằng bàn phím trong Chromium thật."""

import os
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="cần playwright để đo trong trình duyệt")
CHROMIUM = os.environ.get(
    "VN_LOTTERY_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
)
if not Path(CHROMIUM).exists():
    pytest.skip(f"không có Chromium tại {CHROMIUM}", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(os.environ.get("APP_EVIDENCE_SCRIPT", ROOT / "src/web/assets/app-evidence.js"))


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        instance = pw.chromium.launch(executable_path=CHROMIUM)
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    yield page
    page.close()


@pytest.mark.parametrize("hidden", [
    '<details><summary>Chi tiết</summary><span>42</span></details>',
    '<div style="display:none"><span>42</span></div>',
])
def test_keyboard_skips_collapsed_and_css_hidden_values(page, hidden):
    page.set_content(f'<main id="app-main"><section id="values">{hidden}<span>45</span></section></main>')
    page.add_script_tag(content=SCRIPT.read_text(encoding="utf-8"))
    page.keyboard.press("Tab")
    page.locator("#values").focus()
    assert page.locator(".app-evidence-active").text_content() == "45"


def test_expanding_details_keeps_one_keyboard_region(page):
    page.set_content('<main id="app-main"><details><summary>Chi tiết</summary>'
                     '<section id="values"><span>42</span><span>43</span></section></details></main>')
    page.add_script_tag(content=SCRIPT.read_text(encoding="utf-8"))
    page.locator('details').evaluate('e => {e.open = true;}')
    page.keyboard.press('Tab')
    page.locator('#values').focus()
    assert page.locator('.app-evidence-active').text_content() == '42'
    page.keyboard.press('ArrowRight')
    assert page.locator('.app-evidence-active').text_content() == '43'
    assert page.locator('#values [tabindex]').count() == 0


@pytest.mark.parametrize("hiding", ["hidden", "display"])
@pytest.mark.parametrize("key", ["Enter", "ArrowRight"])
def test_keyboard_revalidates_the_active_value_after_filtering(page, hiding, key):
    page.set_content('<main id="app-main"><table id="values"><tbody>'
                     '<tr><td>1</td><td>11</td></tr><tr><td>2</td><td>22</td></tr>'
                     '</tbody></table></main>')
    page.add_script_tag(content=SCRIPT.read_text(encoding="utf-8"))
    page.keyboard.press("Tab")
    page.locator("#values").focus()
    assert page.locator(".app-evidence-active").text_content() == "1"
    page.locator("#values tr").first.evaluate(
        '(row, hiding) => {if (hiding === "hidden") row.hidden = true; else row.style.display = "none";}', hiding
    )
    page.keyboard.press(key)
    if key == "Enter":
        assert page.locator("#app-evidence-drawer .app-evidence-value").text_content() == "2"
    else:
        assert page.locator(".app-evidence-active").text_content() == "2"
