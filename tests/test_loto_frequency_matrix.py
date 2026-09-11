"""Production loader tests; optional real-browser tests with VLA_BROWSER_TESTS=1.

Browser checks use Python Playwright and an installed Chromium browser, never
add a JavaScript runtime or framework to the generated site.
"""
from collections import Counter
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from build_stat_pages import PAGES, load_draws, render_page
from xsmb_domain import FIELD_WIDTHS

ROOT = Path(__file__).resolve().parents[1]
PAGE = next(p for p in PAGES if p.slug == "tan-suat-loto")


def test_loader_preserves_occurrences_and_special(tmp_path):
    endings = ["06", "01"] + ["02"]*2 + ["03"]*3 + ["04"]*4 + ["05"]*6 + ["06"]*2 + ["99"]*8
    row = {field: str(int(value)) for (field, _), value in zip(FIELD_WIDTHS, endings)}
    row["date"] = "2026-09-01"
    (tmp_path / "data").mkdir()
    pd.DataFrame([row]).to_csv(tmp_path / "data/xsmb.csv", index=False)
    draw, = load_draws(tmp_path)
    assert draw["s"] == "00006"
    counts = Counter(draw["n"])
    assert [counts[f"{n:02}"] for n in range(7)] == [0, 1, 2, 3, 4, 6, 3]
    assert sum(counts.values()) == 27


@pytest.mark.parametrize("special", ["", None, "bad", "123456", "-1", "1.5"])
def test_incomplete_special_excluded(tmp_path, special):
    row = {field: "1" for field, _ in FIELD_WIDTHS}
    row.update(date="2026-09-01", special=special)
    (tmp_path / "data").mkdir()
    pd.DataFrame([row]).to_csv(tmp_path / "data/xsmb.csv", index=False)
    assert load_draws(tmp_path) == []


def test_real_three_recent_draws():
    raw = pd.read_csv(ROOT / "data/xsmb.csv", dtype=str).tail(3)
    draws = {d["d"]: d for d in load_draws(ROOT)}
    for _, row in raw.iterrows():
        expected = Counter(f"{int(row[field]) % 100:02}" for field, _ in FIELD_WIDTHS)
        assert Counter(draws[row["date"]]["n"]) == expected
        assert draws[row["date"]]["s"][-2:] == f"{int(row['special']) % 100:02}"


def test_generator_component_is_scoped():
    draws = load_draws(ROOT)
    html = render_page(PAGE, draws, generated="test")
    for marker in ("loto-frequency-matrix", "lfm-legend", "data-lfm-theme", "lfm-special", "data-hit-count", "data-is-special"):
        assert marker in html
    import re
    embedded = json.loads(re.search(r"window.__VLA_DRAWS__=(.*?);", html).group(1))
    assert embedded == draws
    other = render_page(PAGES[0], draws, generated="test")
    assert "lfmInit" not in other


@pytest.fixture(scope="module")
def browser():
    if os.environ.get("VLA_BROWSER_TESTS") != "1":
        pytest.skip("Set VLA_BROWSER_TESTS=1 for installed Playwright/Chromium")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        args = {"headless": True}
        if os.environ.get("VLA_BROWSER_PATH"):
            args["executable_path"] = os.environ["VLA_BROWSER_PATH"]
        instance = pw.chromium.launch(**args)
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto((ROOT / "docs/tan-suat-loto.html").as_uri())
    yield page
    page.close()


def test_browser_states(page):
    result = page.evaluate("""() => {
      const d=lfmDraw({d:'2026-09-01',s:'00006',n:['01','02','02',...Array(3).fill('03'),...Array(4).fill('04'),...Array(6).fill('05'),'06','06']});
      return {counts:d.counts.slice(0,7), special:d.special,
        states:[0,1,2,3,4,5,6].map(n=>lfmState(n,false)),
        specials:[1,2,6].map(n=>lfmState(n,true)),
        zero:lfmDraw({s:'00004',n:['04']}).special,
        bad:[null,'bad','',undefined].map(s=>lfmDraw({s,n:[]}).special)};
    }""")
    assert result == {"counts": [0,1,2,3,4,6,2], "special":"06",
        "states":["miss","hit1","hit2","hit3","hit4","hit5","hit5"],
        "specials":["special"]*3, "zero":"04", "bad":[None]*4}
    assert page.locator('.lfm-cell').count() > 0
    special = page.locator('[data-is-special="true"]').first
    assert special.locator('.lfm-special').count() == 1
    assert special.locator('.lfm-card').evaluate('(el)=>getComputedStyle(el).color') == 'rgb(220, 38, 38)'


@pytest.mark.parametrize("width", [320,360,390,430,768,1280])
def test_browser_geometry_and_sticky(page, width):
    page.set_viewport_size({"width":width,"height":900})
    result = page.locator('.lfm-scroll').evaluate("""el => {
      el.scrollLeft=200; el.scrollTop=300;
      const rect=el.getBoundingClientRect(), table=el.querySelector('table');
      const corner=table.tHead.rows[0].cells[0].getBoundingClientRect();
      const left=table.tBodies[0].rows[8].cells[0].getBoundingClientRect();
      return {scroll:el.scrollWidth>el.clientWidth,width:table.tBodies[0].rows[0].cells[1].getBoundingClientRect().width,
        cornerX:corner.x-rect.x,cornerY:corner.y-rect.y,left:left.x-rect.x,
        overflow:document.documentElement.scrollWidth>innerWidth};
    }""")
    assert result['scroll'] and result['width'] == 62
    assert abs(result['cornerX']-1) < 2 and abs(result['cornerY']-1) < 2
    assert abs(result['left']-1) < 2
    assert not result['overflow']


def test_browser_crosshair_theme_marks(page):
    cell = page.locator('.lfm-cell').first
    cell.click()
    assert 'lfm-active' in cell.get_attribute('class')
    page.locator('#lfm-mark').click()
    assert 'marked' in cell.get_attribute('class')
    page.locator('[data-lfm-theme="dark"]').click()
    page.reload()
    assert page.locator('html').get_attribute('data-theme') == 'dark'
    assert 'marked' in page.locator('.lfm-cell').first.get_attribute('class')
    page.locator('.lfm-cell').first.focus()
    page.keyboard.press('ArrowRight')
    assert page.locator(':focus').get_attribute('data-column') == '1'
    page.keyboard.press('Escape')
    assert page.locator('.lfm-active').count() == 0


def test_browser_touch_and_storage_denied(browser):
    context = browser.new_context(viewport={"width":390,"height":844}, has_touch=True, is_mobile=True)
    context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})")
    page = context.new_page()
    page.goto((ROOT / 'docs/tan-suat-loto.html').as_uri())
    cell = page.locator('.lfm-cell').first
    cell.tap()
    assert page.locator('.lfm-active').count() == 1
    cell.tap()
    assert page.locator('.lfm-active').count() == 0
    page.locator('[data-lfm-theme="dark"]').tap()
    assert page.locator('html').get_attribute('data-theme') == 'dark'
    assert page.locator('.lfm-scroll').evaluate('(e)=>getComputedStyle(e).touchAction') == 'pan-x pan-y'
    context.close()


def test_browser_visual_capture(page):
    out = ROOT / 'logs/lfm-visual'
    out.mkdir(parents=True, exist_ok=True)
    for theme in ('light','dark'):
        page.locator(f'[data-lfm-theme="{theme}"]').click()
        page.locator('.loto-frequency-matrix').screenshot(path=str(out / f'phase-a-{theme}.png'))
