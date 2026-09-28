"""Đo đủ dữ liệu, chiều cao, tiêu đề dính và cuộn ngang của năm bảng thống kê."""
from pathlib import Path


FREQUENCY_PAGES = ("tan-suat-loto.html", "tan-suat-cap-loto.html")
CALENDAR_PAGES = ("bang-dac-biet.html", "bang-dac-biet-thang.html", "bang-dac-biet-nam.html")


def select_days(page, days):
    """Chọn dải thật qua bộ lọc và phát sự kiện như thao tác người dùng."""
    page.evaluate("""days => {
      const from = document.getElementById('sp-from');
      const to = document.getElementById('sp-to');
      from.value = DRAWS.at(-days).d;
      to.value = DRAWS.at(-1).d;
      from.dispatchEvent(new Event('change', {bubbles:true}));
    }""", days)


def check_geometry(page, selector):
    """Đo DOM đã bố trí: không cắt hàng, không tràn trang, ghim đúng hai trục."""
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    table = page.locator(selector)
    state = table.evaluate("""table => {
      const wrap = table.parentElement;
      const last = table.tBodies[0].rows[table.tBodies[0].rows.length - 1];
      return {pageOverflow:document.documentElement.scrollWidth - innerWidth,
        tableHeight:table.offsetHeight, frameHeight:wrap.clientHeight,
        hiddenHeight:wrap.scrollHeight - wrap.clientHeight,
        lastInside:last.getBoundingClientRect().bottom <= wrap.getBoundingClientRect().bottom,
        minWidth:table.offsetWidth >= wrap.clientWidth - 2};
    }""")
    assert state["pageOverflow"] <= 1, state
    assert state["hiddenHeight"] <= 1 and state["lastInside"], state
    assert state["minWidth"], state
    # Cuộn trang thật; hàng tiêu đề phải nằm ngay dưới thanh ứng dụng.
    table.evaluate("""table => {
      window.scrollTo(0, table.getBoundingClientRect().top + scrollY + 100);
      table.parentElement.scrollLeft = Math.min(340, table.scrollWidth);
    }""")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    sticky = table.evaluate("""table => {
      const wrap = table.parentElement, head = table.tHead.rows[0].cells[0];
      const rowhead = Array.from(table.tBodies[0].rows).find(r => !r.classList.contains('sp-virtual-gap')).cells[0];
      const pan = wrap.parentElement.querySelector('.sp-table-pan');
      const top = document.querySelector('.app-header').getBoundingClientRect().bottom;
      const rect = table.getBoundingClientRect();
      const expected = Math.min(Math.max(rect.top,
        top + (pan && !pan.hidden ? pan.getBoundingClientRect().height : 0)),
        rect.bottom - head.getBoundingClientRect().height);
      return {headTop:head.getBoundingClientRect().top, expected,
        rowheadLeft:rowhead.getBoundingClientRect().left, frameLeft:wrap.getBoundingClientRect().left,
        rowhead:table.classList.contains('has-rowhead'), pan:pan?.scrollLeft,
        scroll:wrap.scrollLeft, border:getComputedStyle(head).borderBottomWidth};
    }""")
    assert abs(sticky["headTop"] - sticky["expected"]) <= 2, sticky
    if sticky["rowhead"]:
        assert abs(sticky["rowheadLeft"] - sticky["frameLeft"]) <= 2, sticky
    assert sticky["border"] == "1px", sticky
    if sticky["scroll"]:
        assert abs(sticky["pan"] - sticky["scroll"]) <= 1, sticky
    # Đi đến cột cuối bằng thanh cuộn ở đầu, kiểm tra đồng bộ ngược lại.
    table.evaluate("""table => {
      const pan = table.parentElement.parentElement.querySelector('.sp-table-pan');
      if (pan && !pan.hidden) pan.scrollLeft = pan.scrollWidth;
    }""")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    end = table.evaluate("""table => {
      const wrap = table.parentElement;
      const cells = Array.from(table.tHead.rows[0].cells).filter(c => !c.hidden);
      return {last:cells.at(-1).getBoundingClientRect().right,
        right:wrap.getBoundingClientRect().right, scroll:wrap.scrollLeft};
    }""")
    assert end["last"] <= end["right"] + 2, end
    return state


def check_full_history(page):
    """Cuộn tới ngày cũ nhất, quay lại và đổi chiều mà không dựng hàng trăm nghìn ô."""
    results = []
    for orientation in ("Xem theo chiều ngang", "Xem theo chiều dọc"):
        page.locator("#sp-orient").select_option(label=orientation)
        page.locator("#sp-sort").select_option('hit-desc')
        select_days(page, page.evaluate("DRAWS.length"))
        page.wait_for_function("document.querySelector('#sp-matrix-grid').hasAttribute('aria-rowcount')")
        for end in (False, True, False):
            page.evaluate("""({end, vertical}) => {
              const table = document.getElementById('sp-matrix-grid');
              if (vertical) window.scrollTo(0, table.getBoundingClientRect().top + scrollY +
                (end ? table.offsetHeight - 500 : -120));
              else table.parentElement.scrollLeft = end ? table.offsetWidth : 0;
            }""", {"end":end, "vertical":orientation.endswith("dọc")})
            page.wait_for_function("""end => {
              const date = end ? DRAWS[0].d : DRAWS.at(-1).d;
              return !!document.querySelector(`#sp-matrix-grid [data-key*="|d${date}"]`);
            }""", arg=end)
            state = page.evaluate("""() => {
              const table = document.getElementById('sp-matrix-grid');
              const cells = Array.from(table.querySelectorAll('td[data-key]'));
              const actual = cells.filter(c => /\\|d/.test(c.dataset.key) && /\\|[nc]/.test(c.dataset.key));
              const byDate = new Map(DRAWS.map(r => [r.d, r.n]));
              return {cells:cells.length, count:selected().length, width:table.offsetWidth,
                height:table.offsetHeight, rows:Number(table.getAttribute('aria-rowcount')),
                cols:Number(table.getAttribute('aria-colcount')),
                valid:actual.every(c => c.hasAttribute('aria-label')),
                incorrect:actual.filter(c => {
                  if (c.classList.contains('sp-pending')) return false;
                  const date = /\\|d(\\d{4}-\\d{2}-\\d{2})/.exec(c.dataset.key)[1];
                  const numbers = /\\|[nc]([\\d-]+)/.exec(c.dataset.key)[1].split('-');
                  const draw = byDate.get(date);
                  return !draw || draw.filter(n => numbers.includes(n)).length !== (parseInt(c.textContent, 10) || 0);
                }).length};
            }""")
            assert state["cells"] < 10000, state
            assert state["valid"] and not state["incorrect"], state
            assert max(state["rows"], state["cols"]) >= state["count"] + 1, state
            results.append({"days":"all", "orientation":orientation, "end":end, **state})
        # Mép trục số/cặp đã sort không được nhảy về vị trí gốc trong dữ liệu.
        boundary = page.evaluate("""vertical => {
          const rows = Array.from(document.querySelector('#sp-matrix-grid').tBodies[0].rows)
            .filter(r => !r.hidden && !r.classList.contains('sp-virtual-gap'));
          const row = vertical ? rows[0] : rows.at(-1);
          const cells = Array.from(row.cells).filter(c => !c.hidden && c.cellIndex > 0 && c.dataset.key);
          const cell = vertical ? cells.at(-1) : cells[0];
          cell.focus({preventScroll:true});
          return cell.dataset.key;
        }""", orientation.endswith("dọc"))
        page.keyboard.press('ArrowRight' if orientation.endswith('dọc') else 'ArrowDown')
        assert page.evaluate('document.activeElement?.dataset.key') == boundary
        # Phím mũi tên qua biên vùng dựng phải đi đúng một ngày và giữ danh tính ô.
        edge = page.evaluate("""vertical => {
          const table = document.getElementById('sp-matrix-grid');
          const rows = Array.from(table.tBodies[0].rows).filter(r => !r.hidden && !r.classList.contains('sp-virtual-gap'));
          const row = vertical ? rows.at(-1) : rows[0];
          const cells = Array.from(row.cells).filter(c => !c.hidden && c.cellIndex > 0 && c.dataset.key);
          const cell = vertical ? cells[0] : cells.at(-1);
          cell.focus({preventScroll:true});
          const date = /\\|d(\\d{4}-\\d{2}-\\d{2})/.exec(cell.dataset.key)[1];
          const previous = DRAWS[DRAWS.findIndex(r => r.d === date) - 1].d;
          return {expected:cell.dataset.key.replace(date, previous)};
        }""", orientation.endswith("dọc"))
        page.keyboard.press("ArrowDown" if orientation.endswith("dọc") else "ArrowRight")
        page.wait_for_function("key => document.activeElement?.dataset.key === key", arg=edge["expected"])
        # Dấu được lưu theo số/ngày, không theo vị trí ô trong vùng dựng.
        page.evaluate("document.activeElement.click()")
        marked = page.evaluate("document.activeElement.classList.contains('marked')")
        page.evaluate("""vertical => {
          const table = document.getElementById('sp-matrix-grid');
          if (vertical) window.scrollBy(0, 4000); else table.parentElement.scrollLeft += 4000;
        }""", orientation.endswith("dọc"))
        page.wait_for_function("key => !document.querySelector(`#sp-matrix-grid [data-key=\"${key}\"]`)", arg=edge["expected"])
        page.evaluate("""vertical => {
          const table = document.getElementById('sp-matrix-grid');
          if (vertical) window.scrollBy(0, -4000); else table.parentElement.scrollLeft -= 4000;
        }""", orientation.endswith("dọc"))
        page.wait_for_function("key => !!document.querySelector(`#sp-matrix-grid [data-key=\"${key}\"]`)", arg=edge["expected"])
        assert page.locator(f'#sp-matrix-grid [data-key="{edge["expected"]}"]').evaluate(
            "cell => cell.classList.contains('marked')") == marked
        # Đổi dải phải tháo vùng cuộn cũ; cuộn tiếp không được làm hiện lại lịch sử cũ.
        select_days(page, 10)
        page.wait_for_function("!document.querySelector('#sp-matrix-grid').hasAttribute('aria-rowcount')")
        page.evaluate("window.scrollBy(0, 200)")
        check_geometry(page, "#sp-matrix-grid")
    return results


def check_small_selection(page, pair_page):
    """Khung cũng phải co lại sau dải rỗng hoặc chỉ còn một cặp."""
    if pair_page:
        page.locator('#sp-orient').select_option(label='Xem theo chiều dọc')
        select_days(page, page.evaluate("DRAWS.length"))
        page.locator('details').filter(has=page.locator('#bf-pair-picker')).locator('summary').click()
        page.locator('[data-bf-pick="none"]').click()
        page.locator('[data-bf-pair]').first.click()
        page.wait_for_function("document.querySelectorAll('#sp-matrix-grid thead th:not([hidden])').length === 2")
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        size = page.locator('#sp-matrix-grid').evaluate("e => ({width:e.offsetWidth, frame:e.parentElement.clientWidth})")
        assert abs(size['width'] - size['frame']) <= 1, size
        page.locator('[data-bf-pick="all"]').click()
    page.evaluate("""() => {
      const from = document.getElementById('sp-from');
      document.getElementById('sp-to').value = DRAWS[0].d;
      from.value = DRAWS.at(-1).d;
      from.dispatchEvent(new Event('change', {bubbles:true}));
    }""")
    page.wait_for_function("document.querySelector('#sp-matrix-grid .sp-empty-row')")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    state = page.locator('#sp-matrix-grid').evaluate("""e => ({width:e.offsetWidth,
      frame:e.parentElement.clientWidth, hidden:e.parentElement.scrollHeight-e.parentElement.clientHeight})""")
    assert state['width'] <= state['frame'] + 1 and state['hidden'] <= 1, state
    select_days(page, 10)


def check_stat_tables(page, base, out: Path, width, dark):
    """Kiểm tra bộ lọc ngắn/dài và đổi trục trên dữ liệu đã xuất bản."""
    results = []
    for name in FREQUENCY_PAGES + CALENDAR_PAGES:
        errors = []
        def record_error(error, errors=errors):
            errors.append(str(error))
        page.on("pageerror", record_error)
        try:
            page.goto(f"{base}/{name}", wait_until="load")
            if page.locator("html").evaluate("e => e.classList.contains('dark')") != dark:
                page.locator("#app-theme").click()
            frequency = name in FREQUENCY_PAGES
            selector = "#sp-matrix-grid" if frequency else "#sp-grid"
            ranges = (10, 30, 100, 365) if page.locator("#sp-from").count() else (None,)
            for days in ranges:
                if days:
                    select_days(page, days)
                orientations = ("Xem theo chiều ngang", "Xem theo chiều dọc") if frequency else (None,)
                for orientation in orientations:
                    if orientation:
                        page.locator("#sp-orient").select_option(label=orientation)
                        counts = page.evaluate("""() => {
                          const expected = selected().map(r => r.d);
                          const dates = new Set(Array.from(document.querySelectorAll('#sp-matrix-grid [data-key]'),
                            c => /\\|d(\\d{4}-\\d{2}-\\d{2})/.exec(c.dataset.key)?.[1]).filter(Boolean));
                          return {expected:expected.length, missing:expected.filter(d => !dates.has(d)),
                            actual:dates.size, pending:pendingDay(selected()) ? 1 : 0};
                        }""")
                        assert not counts["missing"] and counts["actual"] == counts["expected"] + counts["pending"], counts
                    geometry = check_geometry(page, selector)
                    if name == "bang-dac-biet.html":
                        assert page.locator('#sp-grid .sp-de').count() == page.evaluate('selected().length')
                    results.append({"page":name, "width":width, "dark":dark, "days":days,
                                    "orientation":orientation, **geometry})
            page.screenshot(path=str(out / f"stat-{name}-{width}-{'dark' if dark else 'light'}.png"))
            if frequency and not dark:
                results.extend({"page":name, "width":width, "dark":dark, **state}
                               for state in check_full_history(page))
                check_small_selection(page, name == 'tan-suat-cap-loto.html')
            if name in ('bang-dac-biet-thang.html', 'bang-dac-biet-nam.html'):
                picker = page.locator('#sp-year' if name.endswith('thang.html') else '#sp-month')
                values = picker.locator('option').evaluate_all('nodes => nodes.map(n => n.value)')
                for value in (values[0], values[-1]):
                    picker.select_option(value)
                    check_geometry(page, selector)
                    expected = page.evaluate("""() => DRAWS.filter(r => document.getElementById('sp-year')
                      ? r.d.slice(0, 4) === document.getElementById('sp-year').value
                      : +r.d.slice(5, 7) === +document.getElementById('sp-month').value.replace('Tháng ', '')).length""")
                    assert page.locator('#sp-grid .sp-de').count() == expected
            assert not errors, errors
        except Exception:
            page.screenshot(path=str(out / f"stat-failure-{name}-{width}.png"))
            raise
        finally:
            page.remove_listener("pageerror", record_error)
    return results


if __name__ == "__main__":
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import json
    import threading
    from playwright.sync_api import sync_playwright

    root = Path(__file__).resolve().parents[1]
    out = root / "ui-browser-artifacts"
    out.mkdir(exist_ok=True)

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root / "docs")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width in (390, 1440):
                page = browser.new_page(viewport={"width":width, "height":950}, reduced_motion="reduce")
                for dark in (False, True):
                    results.extend(check_stat_tables(page, f"http://127.0.0.1:{server.server_port}", out, width, dark))
                    print(f"{width}px, {'tối' if dark else 'sáng'}: đã kiểm tra {len(results)} trạng thái", flush=True)
                page.close()
            browser.close()
    finally:
        server.shutdown()
        (out / "stat-tables-report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
