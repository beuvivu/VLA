"""Đo đủ dữ liệu, chiều cao, tiêu đề dính và cuộn ngang của năm bảng thống kê."""
from pathlib import Path

from playwright.sync_api import expect


FREQUENCY_PAGES = ("tan-suat-loto.html", "tan-suat-cap-loto.html")
CALENDAR_PAGES = ("bang-dac-biet.html", "bang-dac-biet-thang.html", "bang-dac-biet-nam.html")
PRESET_PAGES = ("cau-dac-biet-theo-bo-so.html", "chu-ky-dac-biet.html",
                "lo-gan.html", "giai-db-ngay-mai.html")


def check_tomorrow_panels(page, width):
    """Hai khung cân nhau; mọi LOTO phải thuộc đúng ngày nằm cạnh giải."""
    state = page.evaluate("""() => {
      const left = document.querySelector('.app-tomorrow-history');
      const right = document.querySelector('.app-tomorrow-stat');
      const scroll = left.querySelector('.sp-scroll');
      const box = e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom}};
      const rightStyle=getComputedStyle(right),end=right.lastElementChild;
      const rightContentBottom=box(end).bottom+parseFloat(getComputedStyle(end).marginBottom)
        +parseFloat(rightStyle.paddingBottom)+parseFloat(rightStyle.borderBottomWidth);
      const errors=[];
      const byDate=new Map(DRAWS.map(r=>[r.d,r]));
      const rows=[...document.querySelectorAll('#sp-grid tbody tr[data-trigger-date]')];
      for (const row of rows) {
        const day=row.dataset.triggerDate;
        const next=new Date(day+'T00:00:00Z'); next.setUTCDate(next.getUTCDate()+1);
        for (const [kind,date] of [['trigger',day],['next',next.toISOString().slice(0,10)]]) {
          const field=row.querySelector(`[data-${kind}-loto]`), draw=byDate.get(date);
          if (!field || field.dataset.lotoDate!==date) {errors.push({day,kind,date,error:'sai ngày LOTO'});continue;}
          const actual=[...field.querySelectorAll('[data-loto-number]')].map(e=>[e.dataset.lotoNumber,+e.dataset.lotoCount]);
          const counts=new Map();
          for (const n of draw?.n||[]) counts.set(n,(counts.get(n)||0)+1);
          const expected=[...counts].sort((a,b)=>a[0].localeCompare(b[0]));
          if (JSON.stringify(actual)!==JSON.stringify(expected)) errors.push({day,kind,error:'sai số hoặc nháy'});
        }
      }
      scroll.scrollTop=scroll.scrollHeight; scroll.scrollLeft=scroll.scrollWidth;
      const lastRow=document.querySelector('#sp-grid tbody tr:last-child');
      const lastColumn=document.querySelector('#sp-grid thead th:last-child');
      const result={left:box(left),right:box(right),rightContentBottom,scroll:box(scroll),errors,rows:rows.length,
        clippedSpecials:[...document.querySelectorAll('[data-trigger-special],[data-next-special]')].filter(e=>{
          const r=e.getBoundingClientRect(),cell=e.closest('td').getBoundingClientRect();
          return r.left<cell.left-.5 || r.right>cell.right+.5;
        }).map(e=>e.textContent),
        columns:[...document.querySelectorAll('#sp-grid thead th')].map(e=>getComputedStyle(e).display),
        lastRow:box(lastRow),lastColumn:box(lastColumn),pageOverflow:document.documentElement.scrollWidth-innerWidth};
      scroll.scrollTop=0;scroll.scrollLeft=0;
      return result;
    }""")
    assert not state["errors"], state
    assert not state["clippedSpecials"], state
    assert state["pageOverflow"] <= 1, state
    assert len(state["columns"]) == 5 and "none" not in state["columns"], state
    assert state["lastColumn"]["x"] + state["lastColumn"]["w"] <= state["scroll"]["x"] + state["scroll"]["w"] + 1, state
    assert state["lastRow"]["bottom"] <= state["scroll"]["bottom"] + 1, state
    left, right = state["left"], state["right"]
    if width > 1050:
        assert abs(left["y"] - right["y"]) <= 1, state
        assert abs(left["bottom"] - right["bottom"]) <= 1, state
        assert abs(left["w"] - right["w"]) <= 1, state
        assert abs(state["scroll"]["bottom"] - left["bottom"]) <= 2, state
        assert abs(state["rightContentBottom"] - right["bottom"]) <= 1, state
    else:
        assert right["y"] >= left["bottom"] - 1, state
    return {"equal_panels": "passed", "loto_dates": "passed", "rows": state["rows"]}


def check_preset_ranges(page, base, out: Path, width, dark):
    """Bấm các mốc thật, đối chiếu số kỳ và số lần về với dữ liệu gốc."""
    results = []
    for name in PRESET_PAGES:
        errors = []
        def record_error(error, errors=errors):
            errors.append(str(error))
        page.on("pageerror", record_error)
        try:
            page.goto(f"{base}/{name}", wait_until="load")
            if page.locator("html").evaluate("e => e.classList.contains('dark')") != dark:
                page.locator("#app-theme").click()
            for days in (30, 60, 90, 180, 365, 30, 0):
                page.locator(f'.sp-chips .sp-chip[data-days="{days}"]').click()
                state = page.evaluate("""({days, name}) => {
                  const expected = days ? DRAWS.slice(-days) : DRAWS;
                  const actual = selected();
                  const count = document.getElementById('sp-count').textContent;
                  const rows = Array.from(document.querySelectorAll('#sp-grid tbody tr'));
                  const stats = rows.filter(row => row.cells.length === 5);
                  const hits = stats.reduce((n, row) => n + Number(row.cells[4].textContent), 0);
                  const wantHits = name === 'lo-gan.html'
                    ? expected.reduce((n, draw) => n + new Set(draw.n).size, 0) : expected.length;
                  return {expected:expected.length, actual:actual.length,
                    sameDates:JSON.stringify(actual.map(r => r.d)) === JSON.stringify(expected.map(r => r.d)),
                    count, first:expected[0]?.d, last:expected.at(-1)?.d, hits, wantHits,
                    active:document.querySelector('.sp-chips .on')?.dataset.days};
                }""", {"days": days, "name": name})
                assert state["actual"] == state["expected"] and state["sameDates"], state
                assert state["active"] == str(days), state
                assert state["count"].startswith(f'{state["expected"]} kỳ · '), state
                if state["first"]:
                    assert state["first"] in state["count"] and state["last"] in state["count"], state
                if name != "giai-db-ngay-mai.html":
                    assert state["hits"] == state["wantHits"], state
                else:
                    check_tomorrow_panels(page, width)
                page.locator("#sp-clear-marks").click()
                assert page.locator("#sp-count").inner_text() == state["count"]
                results.append({"page": name, "width": width, "dark": dark,
                                "days": days, "preset_range": "passed", "draws": state["actual"]})
            assert not errors, errors
            if name == "giai-db-ngay-mai.html":
                page.locator('.sp-chip[data-days="30"]').click()
                empty_number = page.evaluate("""() => {
                  const seen=new Set(selected().map(r=>r.s.slice(-2)));
                  return Array.from({length:100},(_,i)=>String(i).padStart(2,'0')).find(n=>!seen.has(n));
                }""")
                selected_number = page.locator('#sp-tomorrow-number').input_value()
                page.locator('#sp-tomorrow-number').select_option(empty_number)
                empty_state = check_tomorrow_panels(page, width)
                assert empty_state["rows"] == 0, empty_state
                page.locator('#sp-tomorrow-number').select_option(selected_number)
                page.locator('.sp-chip[data-days="0"]').click()
                check_tomorrow_panels(page, width)
                results.append({"page": name, "width": width, "dark": dark,
                                "empty_tomorrow_panels": "passed"})
                if width == 1440:
                    viewport = page.viewport_size
                    page.set_viewport_size({"width": 1100, "height": viewport["height"]})
                    try:
                        check_tomorrow_panels(page, 1100)
                        results.append({"page": name, "width": 1100, "dark": dark,
                                        "narrow_tomorrow_panels": "passed"})
                    finally:
                        page.set_viewport_size(viewport)
            page.screenshot(path=str(out / f"preset-{name}-{width}-{'dark' if dark else 'light'}.png"))
        finally:
            page.remove_listener("pageerror", record_error)
    return results


def select_days(page, days):
    """Chọn dải thật qua bộ lọc và phát sự kiện như thao tác người dùng."""
    page.evaluate("""days => {
      const from = document.getElementById('sp-from');
      const to = document.getElementById('sp-to');
      from.value = DRAWS.at(-days).d;
      to.value = DRAWS.at(-1).d;
      from.dispatchEvent(new Event('change', {bubbles:true}));
    }""", days)


def choose_orientation(page, orientation):
    """Hai nút công khai giữ bộ chọn nội bộ cho hợp đồng dữ liệu cũ."""
    value = "vertical" if orientation.endswith("dọc") else "horizontal"
    page.locator(f'[data-app-orientation="{value}"]').click()


def check_vertical_matrix(page):
    """Chiều dọc hoán đổi trục; số lượt, đồ thị và danh tính ô không thay đổi."""
    state = page.evaluate("""() => {
      const table = document.getElementById('sp-matrix-grid');
      const counts = countLoto(selected());
      const head = Array.from(table.tHead.rows[0].cells);
      const charts = Array.from(table.querySelectorAll('thead .app-frequency-spark'));
      const cells = Array.from(table.querySelectorAll('tbody td[data-key]')).filter(c => c.cellIndex > 0);
      return {pageOverflow:document.documentElement.scrollWidth-innerWidth,
        tableHidden:table.parentElement.hidden, first:head[0].textContent,
        columns:head.filter(c => !c.hidden).length - 1, charts:charts.length,
        scaleCount:new Set(charts.map(chart => chart.dataset.scale)).size,
        incorrect:charts.filter(chart => Number(chart.dataset.total) !==
          counts[Number(chart.parentElement.dataset.appNumber)]).length,
        wrongAxis:cells.filter(c => !c.dataset.key.startsWith(head[c.cellIndex].dataset.key + '|d') ||
          !c.dataset.key.endsWith(c.parentElement.cells[0].dataset.key.slice(1))).length};
    }""")
    assert state['pageOverflow'] <= 1 and not state['tableHidden'], state
    assert state['first'] == 'Ngày' and state['charts'] > 0, state
    assert not state['incorrect'] and not state['wrongAxis'] and state['scaleCount'] == 1, state
    check_geometry(page, '#sp-matrix-grid')
    return state


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
        choose_orientation(page, orientation)
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
        choose_orientation(page, 'Xem theo chiều dọc')
        select_days(page, page.evaluate("DRAWS.length"))
        page.locator('details').filter(has=page.locator('#bf-pair-picker')).locator('summary').click()
        page.locator('[data-bf-pick="none"]').click()
        page.locator('[data-bf-pair]').first.click()
        page.wait_for_function("document.querySelectorAll('#sp-matrix-grid thead .app-frequency-spark').length === 2")
        state = check_vertical_matrix(page)
        assert state['charts'] == 2 and state['columns'] == 1, state
        page.locator('[data-bf-pick="all"]').click()
    page.evaluate("""() => {
      const from = document.getElementById('sp-from');
      document.getElementById('sp-to').value = DRAWS[0].d;
      from.value = DRAWS.at(-1).d;
      from.dispatchEvent(new Event('change', {bubbles:true}));
    }""")
    choose_orientation(page, 'Xem theo chiều ngang')
    page.wait_for_function("document.querySelector('#sp-matrix-grid .sp-empty-row')")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    state = page.locator('#sp-matrix-grid').evaluate("""e => ({width:e.offsetWidth,
      frame:e.parentElement.clientWidth, hidden:e.parentElement.scrollHeight-e.parentElement.clientHeight})""")
    assert state['width'] <= state['frame'] + 1 and state['hidden'] <= 1, state
    select_days(page, 10)


def check_gan_keyboard(page):
    """Popup thật giữ Tab bên trong, đóng trả focus và đổi mode không mất focus."""
    trigger = page.locator('#sp-gan-pick')
    trigger.focus()
    trigger.select_option('12')
    modal = page.locator('#sp-gan-modal')
    expect(modal).to_have_attribute('open', '')
    expect(modal.locator('[data-close]')).to_be_focused()
    expect(modal).to_have_accessible_name('Chu kỳ gan · số 12')
    for key in ('Shift+Tab', *('Tab',) * 8):
        page.keyboard.press(key)
        assert modal.evaluate('e => e.contains(document.activeElement)'), key
    page.keyboard.press('Escape')
    expect(modal).to_be_hidden()
    expect(trigger).to_be_focused()

    trigger.select_option('12')
    mode = modal.locator('[data-gmode="de"]')
    mode.focus()
    page.keyboard.press('Enter')
    expect(modal.locator('[data-gmode="de"]')).to_be_focused()
    expect(modal.locator('[data-gmode="de"]')).to_have_class('sp-btn on')
    if page.locator('#sp-picker').count():
        modal.locator('[data-gfilter="12"]').click()
        keys = page.locator('#sp-matrix-grid [data-key*="|n"]').evaluate_all(
            'nodes => [...new Set(nodes.map(e => /\\|n(\\d{2})/.exec(e.dataset.key)[1]))]')
        assert keys == ['12'], keys
    else:
        modal.locator('[data-close]').click()
    expect(modal).to_be_hidden()
    expect(trigger).to_be_focused()


def check_detail_tables(page, base, out: Path, width, dark):
    """Giữ cỡ số khi chọn, đủ ma trận Đầu–Đuôi và phân cấp bảng chi tiết."""
    results = []

    def select_without_resize(value):
        size = value.evaluate("e => getComputedStyle(e).fontSize")
        value.click()
        assert value.evaluate("e => getComputedStyle(e).fontSize") == size, size
        value.click()

    for name in ("cap-lon-loto.html", "cau-giai-dac-biet.html", "giai-dac-biet-theo-tong.html"):
        page.goto(f"{base}/{name}", wait_until="load")
        if page.locator("html").evaluate("e => e.classList.contains('dark')") != dark:
            page.locator("#app-theme").click()
        page.evaluate("async () => {await document.fonts.ready; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))}")
        page.locator("#sp-clear-marks").click()
        if name == "cau-giai-dac-biet.html":
            grid = page.locator("#sp-grid")
            expect(grid.locator("tbody tr")).to_have_count(10)
            expect(grid.locator("tbody td")).to_have_count(110)
            state = grid.evaluate("""e => ({view:e.parentElement.clientHeight, full:e.parentElement.scrollHeight,
              last:e.tBodies[0].rows[9].getBoundingClientRect().bottom,
              bottom:e.parentElement.getBoundingClientRect().bottom})""")
            assert state["full"] <= state["view"] + 1 and state["last"] <= state["bottom"] + 1, state
            values = [grid.locator("tbody td:not(:first-child) b").first,
                      page.locator("#sp-lon tbody td:nth-child(2)").first]
            if grid.locator(".sp-none").count():
                values.append(grid.locator(".sp-none").first)
            for value in values:
                assert float(value.evaluate("e => getComputedStyle(e).fontSize").removesuffix("px")) >= 24
                select_without_resize(value)
        elif name == "cap-lon-loto.html":
            cards = page.locator(".app-reverse-card").evaluate_all("nodes => nodes.map(e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})")
            assert len(cards) == 2, cards
            a, b = cards
            if width >= 1024:
                assert abs(a["y"] - b["y"]) <= 1 and b["x"] > a["x"] + a["w"], cards
            else:
                assert b["y"] >= a["y"] + a["h"], cards
            for primary, auxiliary in (("#sp-grid tbody td:nth-child(2)", "#sp-grid tbody td:nth-child(3)"),
                                       ("#sp-kep tbody td:first-child", "#sp-kep tbody td:nth-child(2)")):
                sizes = [float(page.locator(selector).first.evaluate("e => getComputedStyle(e).fontSize").removesuffix("px"))
                         for selector in (primary, auxiliary)]
                assert sizes[0] > sizes[1], sizes
                select_without_resize(page.locator(primary).first)
        else:
            cards = page.locator(".app-specialstats-pair > .app-specialstats-panel").evaluate_all(
                "nodes => nodes.map(e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})")
            assert len(cards) == 2, cards
            a, b = cards
            # Hai panel mới có chú giải riêng nên hàng dữ liệu đầu không cùng
            # cao độ. Đo đỉnh panel và đúng ngưỡng xếp chồng của lớp riêng.
            if width > 1100:
                assert abs(a["y"] - b["y"]) <= 1 and b["x"] > a["x"] + a["w"], cards
            else:
                assert b["y"] >= a["y"] + a["h"], cards
            for selector in ("#sp-grid tbody td:first-child", "#sp-parity tbody td:first-child",
                             "#sp-trans tbody td:first-child", "#sp-trans tbody td:nth-child(2)"):
                select_without_resize(page.locator(selector).first)
            for table_id, expected in (("sp-grid", [.2, .32, .24, .24]),
                                       ("sp-parity", [.2, .2, .3, .3]),
                                       ("sp-trans", [.18, .18, .14, .18, .16, .16])):
                state = page.locator("#" + table_id).evaluate("""e => ({
                  widths:Array.from(e.tBodies[0].rows[0].cells,c => c.getBoundingClientRect().width/e.getBoundingClientRect().width),
                  sizes:Array.from(e.tBodies[0].rows[0].cells,c => parseFloat(getComputedStyle(c).fontSize)),
                  clipped:Array.from(e.querySelectorAll('tbody td')).filter(c => c.scrollWidth>c.clientWidth+1).map(c => c.textContent)
                })""")
                assert all(abs(a - b) < .015 for a, b in zip(state["widths"], expected, strict=True)), state
                assert state["sizes"][0] > max(state["sizes"][2:]) and not state["clipped"], state
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.screenshot(path=str(out / f"detail-{name}-{width}-{'dark' if dark else 'light'}.png"))
        results.append({"page": name, "width": width, "dark": dark, "detail_layout": "passed"})
    return results


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
                        choose_orientation(page, orientation)
                        counts = page.evaluate("""() => {
                          const expected = selected().map(r => r.d);
                          const dates = new Set(Array.from(document.querySelectorAll('#sp-matrix-grid [data-key]'),
                            c => /\\|d(\\d{4}-\\d{2}-\\d{2})/.exec(c.dataset.key)?.[1]).filter(Boolean));
                          return {expected:expected.length, missing:expected.filter(d => !dates.has(d)),
                            actual:dates.size, pending:pendingDay(selected()) ? 1 : 0};
                        }""")
                        assert not counts["missing"] and counts["actual"] == counts["expected"] + counts["pending"], counts
                    geometry = check_vertical_matrix(page) if frequency and orientation.endswith('dọc') else check_geometry(page, selector)
                    if name == "bang-dac-biet.html":
                        assert page.locator('#sp-grid .sp-de').count() == page.evaluate('selected().length')
                    results.append({"page":name, "width":width, "dark":dark, "days":days,
                                    "orientation":orientation, **geometry})
            page.screenshot(path=str(out / f"stat-{name}-{width}-{'dark' if dark else 'light'}.png"))
            if frequency and not dark:
                results.extend({"page":name, "width":width, "dark":dark, **state}
                               for state in check_full_history(page))
                check_small_selection(page, name == 'tan-suat-cap-loto.html')
            if frequency:
                check_gan_keyboard(page)
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
    results.extend(check_detail_tables(page, base, out, width, dark))
    results.extend(check_preset_ranges(page, base, out, width, dark))
    return results


if __name__ == "__main__":
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import json
    import threading
    from playwright.sync_api import sync_playwright

    root = Path(__file__).resolve().parents[2]
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
