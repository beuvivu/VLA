"""Kiểm bố cục, tương tác, in của soi cầu/phôi và bốn trang đường cầu thật."""
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import threading

from playwright.sync_api import sync_playwright

from check_ui_browser import QuietHandler, contrast

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ui-browser-artifacts" / "bridge-workspace"


def geometry(page):
    state = page.evaluate("""() => {
      const main = document.querySelector('.ui-grid');
      const cards = [...main.children].filter(e => !e.hidden);
      const form = document.querySelector('#app-cau-form, #app-bridge-form, #app-phoi-form');
      const rect = form.getBoundingClientRect();
      return {overflow:document.documentElement.scrollWidth - innerWidth,
        widths:cards.map(c => c.getBoundingClientRect().width), gridWidth:main.clientWidth,
        padding:parseFloat(getComputedStyle(form).paddingLeft),
        fieldsFit:[...form.querySelectorAll('input,select,button')].every(e => {
          const r = e.getBoundingClientRect();
          return r.left >= rect.left && r.right <= rect.right + 1;
        })};
    }""")
    assert state["overflow"] <= 1 and state["fieldsFit"], state
    assert state["padding"] >= 16, state
    assert all(abs(w - state["gridWidth"]) <= 1 for w in state["widths"]), state
    return state


def check_grid(page):
    active = page.locator('.app-cau-tabs [aria-current="page"]')
    tab = active.evaluate("""e => ({left:e.getBoundingClientRect().left, right:e.getBoundingClientRect().right,
      navLeft:e.parentElement.getBoundingClientRect().left, navRight:e.parentElement.getBoundingClientRect().right})""")
    assert tab["left"] >= tab["navLeft"] and tab["right"] <= tab["navRight"], tab
    cells = page.locator("button.app-cau-cell")
    if cells.count() > 1:
        cells.nth(0).click()
        cells.nth(1).click()
        assert cells.nth(0).get_attribute("aria-pressed") == "false"
        assert cells.nth(1).get_attribute("aria-pressed") == "true"
        assert page.locator('.app-cau-cell[aria-pressed="true"]').count() == 1
        colors = cells.nth(1).evaluate("e => ({fg:getComputedStyle(e).color, bg:getComputedStyle(e).backgroundColor})")
        assert contrast(colors) >= 4.5, colors
        assert page.locator('.app-cau-bridge[aria-pressed="true"]').count() == 1
        assert page.locator('.app-cau-digit.is-src').count() > 0
        evidence_gap = page.evaluate("""() => document.querySelector('#app-cau-days').getBoundingClientRect().top
          - document.querySelector('#app-cau-detail').getBoundingClientRect().bottom""")
        assert 0 <= evidence_gap <= 200, {"evidence_gap": evidence_gap}
    wrap = page.locator(".app-cau-grid-wrap")
    wrap.evaluate("e => { e.scrollLeft = e.scrollWidth; }")
    state = wrap.evaluate("""e => ({right:e.getBoundingClientRect().right,
      last:e.querySelector('tbody tr:last-child td:last-child').getBoundingClientRect().right,
      first:e.querySelector('tbody th').getBoundingClientRect().left, left:e.getBoundingClientRect().left})""")
    assert state["last"] <= state["right"] + 1, state
    assert abs(state["first"] - state["left"]) <= 2, state
    wrap.evaluate("e => { e.scrollLeft = 0; }")


def check_sheet(page):
    form = page.locator("#app-phoi-form")
    for count in (5, 80):
        form.locator('[name="count"]').fill(str(count))
        assert page.locator(".app-phoi tbody tr").count() == count
        assert page.locator("#app-phoi-status").inner_text().startswith(f"{count} tuần")
    form.locator('[name="headsize"]').fill("35")
    form.locator('[name="tailsize"]').fill("35")
    page.locator("#app-phoi").evaluate("e => { e.scrollLeft = e.scrollWidth; }")
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    page.emulate_media(media="print")
    try:
        assert not form.is_visible()
        assert not page.locator(".app-analysis-header").is_visible()
        assert page.locator(".app-phoi tbody tr").count() == 80
        colors = page.locator(".app-phoi thead th").first.evaluate(
            "e => ({fg:getComputedStyle(e).color, bg:getComputedStyle(e).backgroundColor})")
        assert contrast(colors) >= 4.5, colors
    finally:
        page.emulate_media(media="screen")


def path_geometry(page):
    state = page.evaluate("""() => {
      const workspace = document.querySelector('.path-workspace');
      const overflow = document.documentElement.scrollWidth - innerWidth;
      if (!workspace) return {empty:true,overflow,
        rows:JSON.parse(document.querySelector('#path-data').textContent).rows.length};
      const box = selector => {
        const element = workspace.querySelector(selector), rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {top:rect.top,bottom:rect.bottom,height:rect.height,
          border:parseFloat(style.borderTopWidth),borderBottom:parseFloat(style.borderBottomWidth),
          paddingBottom:parseFloat(style.paddingBottom),marginTop:parseFloat(style.marginTop),
          marginBottom:parseFloat(style.marginBottom),
          contain:style.contain,maxHeight:style.maxHeight};
      };
      return {empty:false,overflow,width:innerWidth,list:box('.path-list'),
        detail:box('.path-detail'),scroll:box('.path-list>.path-table-scroll'),
        note:box('.path-list>.path-note'),detailEnd:box('.path-detail>:last-child'),
        hasTimeline:Boolean(workspace.querySelector('.path-timeline'))};
    }""")
    assert state["overflow"] <= 1, state
    if state["empty"]:
        assert state["rows"] == 0 and page.locator('.path-empty').is_visible(), state
        return state
    assert page.locator('.path-workspace').is_visible(), state
    left, right = state["list"], state["detail"]
    if state["width"] > 1150:
        assert left["border"] > 0 and right["border"] > 0, state
        assert abs(left["top"] - right["top"]) <= 1, state
        assert abs(left["bottom"] - right["bottom"]) <= 1, state
        assert abs(left["height"] - right["height"]) <= 1, state
        assert state["scroll"]["maxHeight"] == "none", state
        assert abs(state["scroll"]["bottom"] + state["note"]["marginTop"] - state["note"]["top"]) <= 1, state
        assert abs(state["note"]["bottom"] + left["paddingBottom"] + left["borderBottom"] - left["bottom"]) <= 1, state
        if state['hasTimeline']:
            end = state['detailEnd']
            assert abs(end['bottom'] + end['marginBottom'] + right['paddingBottom'] + right['borderBottom'] - right['bottom']) <= 1, state
    else:
        assert right["bottom"] <= left["top"], state
        assert state["scroll"]["contain"] == "none", state
    return state


def check_path_workspace(page):
    """Đo lại hai khung sau thao tác thật, không phụ thuộc dữ liệu mẫu Python."""
    initial = path_geometry(page)
    if initial["empty"]:
        return initial
    data = page.locator('#path-data').text_content()
    buttons = page.locator('[data-path-index]')
    chosen = buttons.nth(min(1, buttons.count() - 1))
    chosen.focus()
    chosen.press('Enter')
    assert page.locator('#path-detail-title').evaluate('e => e === document.activeElement')
    path_geometry(page)
    day_states = []
    for days in ('5', '10', 'all'):
        page.locator('#path-days-filter').select_option(days)
        expected = page.evaluate("""() => {
          const state = window.PathExplorer.state, row = state.data.rows[state.selected];
          const days = document.querySelector('#path-days-filter').value;
          return Number(Boolean(row.forecast)) + (days === 'all' ? row.cells.length : Math.min(Number(days),row.cells.length));
        }""")
        assert page.locator('.path-evidence').count() == expected
        measured = path_geometry(page)
        day_states.append({'days':days, 'cards':expected, 'height':measured['detail']['height']})
    if initial['width'] > 1150:
        for before, after in zip(day_states, day_states[1:], strict=False):
            if after['cards'] > before['cards']:
                assert after['height'] > before['height'], day_states
    numbers = page.evaluate("""() => {
      const values = new Set(window.PathExplorer.state.data.rows.map(row => row.next_num));
      return {present:[...values].find(value => /^\\d{2}$/.test(value)),
        missing:Array.from({length:100},(_,n) => String(n).padStart(2,'0')).find(value => !values.has(value))};
    }""")
    if numbers.get('present') is not None:
        page.locator('#path-number-filter').fill(numbers['present'])
        assert page.locator('[data-path-row]:not([hidden])').count() > 0
        path_geometry(page)
    # Nếu đủ cả 100 số thì giao diện không có bộ lọc số nào tạo danh sách rỗng.
    if numbers.get('missing') is not None:
        page.locator('#path-number-filter').fill(numbers['missing'])
        assert page.locator('[data-path-row]:not([hidden])').count() == 0
        assert page.locator('.path-evidence').count() == 0
        path_geometry(page)
    page.locator('#path-reset').click()
    assert page.locator('[data-path-row]:not([hidden])').count() == buttons.count()
    assert page.locator('#path-data').text_content() == data
    final = path_geometry(page)
    scroll = page.locator('.path-list>.path-table-scroll')
    scroll.evaluate('e => { e.scrollTop = e.scrollHeight; }')
    assert scroll.evaluate("e => e.querySelector('tbody tr:last-child').getBoundingClientRect().bottom <= e.getBoundingClientRect().bottom + 1")
    if final['width'] <= 1150:
        buttons.last.click()
        assert page.locator('#path-detail-title').evaluate('e => e === document.activeElement')
        assert page.locator('#path-detail-title').bounding_box()['y'] >= 0
        path_geometry(page)
    return {**initial, 'empty_filter_checked':numbers.get('missing') is not None}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "docs")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    names = sorted(p.name for p in (ROOT / "docs").glob("soi-cau-*.html")) + ["tao-phoi-tuan.html"]
    assert len(names) >= 9
    path_names = [f"soi-path-{mode}-{kind}.html" for mode in ('loto', 'de') for kind in ('active', 'stable')]
    assert all((ROOT / 'docs' / name).is_file() for name in path_names)
    results, failures = [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width in (360, 390, 820, 1440):
                context = browser.new_context(viewport={"width": width, "height": 1050},
                                              color_scheme="light", reduced_motion="reduce")
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                for name in names + path_names:
                    for dark in (False, True):
                        try:
                            errors.clear()
                            page.goto(f"http://127.0.0.1:{server.server_port}/{name}", wait_until="load")
                            page.locator("body[data-app-shell-ready]").wait_for()
                            if page.locator("html").evaluate("e => e.classList.contains('dark')") != dark:
                                page.locator("#app-theme").click()
                            if name in path_names:
                                state = check_path_workspace(page)
                            else:
                                state = geometry(page)
                                if page.locator("#app-cau-form").count():
                                    check_grid(page)
                                elif page.locator("#app-phoi-form").count():
                                    check_sheet(page)
                            page.evaluate("window.scrollTo(0,0)")
                            page.screenshot(path=str(OUT / f"{name[:-5]}-{width}-{'dark' if dark else 'light'}.png"))
                            assert not errors, errors
                            results.append({"page":name, "width":width, "dark":dark, **state})
                        except Exception as error:
                            failures.append({"page":name, "width":width, "dark":dark, "error":str(error)})
                context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    (OUT / "results.json").write_text(json.dumps({"checks":results, "failures":failures}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed":len(results), "failures":failures}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
