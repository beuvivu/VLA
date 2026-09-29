import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM, VirtualConsole } from 'jsdom';

// Bảy trang cầu vị trí và công cụ phôi tuần. Bộ máy JS phải đếm ra đúng từng ô
// như `bridge_rules.py` — với tham số mặc định lẫn tham số người xem chọn.
const build = `import json, sys
sys.path.insert(0, "tests")
import pandas as pd
import bridge_rules as br
import build_bridge_pages as pages
raw = pd.read_csv("data/xsmb.csv", dtype={"date": str})
dates, digits, values = br.load_draws(raw[raw["date"] <= "2026-09-28"])
stub = {"base_rate": 0.4, "rate_kep": 0.2, "rate_pair": 0.4, "draws": 4217,
        "rows": [{"k": k, "plus": k == 10, "n": 1000, "hits": 400, "rate": 0.4, "expected": 0.4, "z": 0.0, "days": 9} for k in range(11)]}
report = {"source_date": dates[-1], "target_date": "2026-09-29", "window": br.WINDOW,
          "draws": ["".join([d, *(str(int(v)).zfill(w) for v, w in zip(row, br.WIDTHS))]) for d, row in zip(dates[-br.EMBED:], values[-br.EMBED:])],
          "rules": {}}
cases = []
for key, cfg in br.RULES.items():
    weekday = 1 if cfg["weekday"] else None
    _, dg, vl = br.weekday_subset(dates, digits, values, weekday)
    found = br.find(cfg["kind"], dg, vl, count=cfg["count"])
    report["rules"][key] = {**cfg, "default_weekday": weekday, "longest": found["longest"], **br.tally(found["bridges"], cfg["kind"]), "backtest": stub}
    if cfg["kind"] == "dac-biet":
        report["rules"][key]["backtest_both"] = {**stub, "rows": [{**r, "rate": 0.0123, "expected": 0.0199} for r in stub["rows"]]}
def expect(kind, count, both=False, weekday=None, end=None):
    ds, dg, vl = br.weekday_subset(dates, digits, values, weekday)
    if end:
        keep = [i for i, d in enumerate(ds) if d <= end]
        dg, vl = dg[keep], vl[keep]
    found = br.find(kind, dg, vl, count=count, both=both)
    return {"counts": br.tally(found["bridges"], kind)["counts"], "longest": found["longest"],
            "vts": [b["vt"] for b in found["bridges"]]}
for key, kind, count, both, wd, end in [("loto", "loto", 3, False, None, None), ("loto", "loto", 5, False, None, None),
        ("hai-nhay", "hai-nhay", 2, False, None, None), ("bach-thu", "bach-thu", 3, False, None, None),
        ("dac-biet", "dac-biet", 2, False, None, None), ("dac-biet", "dac-biet", 1, True, None, None),
        ("bo-so", "bo-so", 2, False, None, None), ("bo-so", "bo-so", 1, False, None, "2026-09-20"),
        ("dac-biet-theo-thu", "dac-biet", 3, False, 6, None), ("loto-theo-thu", "loto", 2, False, 4, None)]:
    cases.append({"key": key, "kind": kind, "count": count, "both": both, "weekday": wd, "end": end, **expect(kind, count, both, wd, end)})
print(json.dumps({"pages": {k: pages.render(k, report) for k in br.RULES}, "cases": cases,
                  "tool": pages.render_tool(pages.specials_from(report))}))`;
const fixture = JSON.parse(execFileSync(process.env.APP_TEST_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(new URL('../../', import.meta.url)), env: { ...process.env, PYTHONPATH: 'src' },
  encoding: 'utf8', maxBuffer: 256 * 1024 * 1024,
}));

const SOURCE = {
  pages: readFileSync(new URL('../../src/templates/bridge_pages.js', import.meta.url), 'utf8'),
  tool: readFileSync(new URL('../../src/templates/weekly_sheet.js', import.meta.url), 'utf8'),
};

async function open(t, html, search = '', marker = 'BridgePages') {
  const virtualConsole = new VirtualConsole();
  const dom = new JSDOM(html, { url: `https://example.test/page.html${search}`, runScripts: 'outside-only', virtualConsole });
  t.after(() => dom.window.close());
  for (const script of dom.window.document.querySelectorAll('script:not([src])')) {
    if (script.type !== 'application/json' && script.textContent.includes(marker)) dom.window.eval(script.textContent);
  }
  if (dom.window.document.readyState === 'loading') {
    await new Promise((resolve) => dom.window.document.addEventListener('DOMContentLoaded', resolve));
  }
  return dom;
}

const plain = (value) => JSON.parse(JSON.stringify(value));
const search = (c) => {
  const q = new URLSearchParams({ count: String(c.count) });
  if (c.both) q.set('both', '1');
  if (c.weekday !== null) q.set('thu', String(c.weekday));
  if (c.end) q.set('ngay', c.end);
  return `?${q}`;
};

test('bộ máy trình duyệt ra đúng từng ô, cầu dài nhất và cặp vị trí như bản Python', async t => {
  for (const c of fixture.cases) {
    const dom = await open(t, fixture.pages[c.key], search(c));
    const { result } = dom.window.BridgePages.state;
    assert.deepEqual(plain(result.counts), c.counts, JSON.stringify({ ...c, counts: undefined, vts: undefined }));
    assert.equal(result.longest, c.longest, c.key);
    assert.deepEqual(plain(result.bridges.map((b) => b.vt)), c.vts, c.key);
  }
});

test('bảng đầu 0–9 hiện đúng số cầu từng ô và tóm tắt đúng tổng', async t => {
  const dom = await open(t, fixture.pages['bo-so']);
  const d = dom.window.document;
  const cells = Object.fromEntries([...d.querySelectorAll('button.app-cau-cell')]
    .map((b) => [b.querySelector('b').textContent, b.querySelector('span').textContent]));
  assert.equal(Object.keys(cells).length, 21);
  assert.equal(cells['85'], '3 cầu');
  assert.match(d.getElementById('app-cau-summary').textContent, /32 cầu.*Cầu dài nhất: 3 ngày/);
  assert.equal(d.querySelectorAll('#app-cau-days .app-cau-day').length, 3, 'count + 1 kỳ');
  assert.deepEqual([...d.querySelectorAll('.app-cau-groups b')].slice(0, 1).map((n) => n.textContent), ['Bộ 03']);
});

test('bấm một ô: chọn cầu, tô đúng hai vị trí nguồn trên mọi kỳ và đánh dấu kỳ trúng', async t => {
  const dom = await open(t, fixture.pages['dac-biet']);
  const d = dom.window.document;
  d.querySelector('button.app-cau-cell[data-number="00"]').click();
  assert.equal(d.querySelector('.app-cau-detail h3').textContent, 'Số 00: 2 cầu');
  const pressed = d.querySelector('.app-cau-bridge[aria-pressed="true"]');
  const [a, b] = pressed.textContent.split(' ')[0].split('x').map(Number);
  for (const card of d.querySelectorAll('#app-cau-days .app-cau-day')) {
    const src = [...card.querySelectorAll('.app-cau-digit.is-src')].map((n) => Number(n.dataset.pos)).sort((u, v) => u - v);
    assert.deepEqual(src, [a, b]);
  }
  const first = d.querySelector('#app-cau-days .app-cau-day');
  assert.equal(first.querySelector('.tr-number[data-value="0"]').classList.contains('is-hit'), true, 'cầu 2 ngày trúng ở kỳ cuối');
  assert.match(first.querySelector('.app-cau-facts').textContent, /Trúng theo cầu kỳ trước/);
  d.querySelectorAll('.app-cau-bridge')[1].click();
  assert.equal(d.querySelectorAll('.app-cau-bridge[aria-pressed="true"]').length, 1);
});

test('rê chuột lên ô tô mọi vị trí của các cầu báo số ấy', async t => {
  const dom = await open(t, fixture.pages.loto);
  const d = dom.window.document;
  const cell = d.querySelector('button.app-cau-cell[data-number="09"]');
  cell.dispatchEvent(new dom.window.Event('mouseenter'));
  const { result } = dom.window.BridgePages.state;
  const positions = new Set(result.bridges.filter((x) => x.number === '09').flatMap((x) => [x.a, x.b]));
  const marked = new Set([...d.querySelectorAll('#app-cau-days .app-cau-day:first-child .app-cau-digit.is-cau')].map((n) => Number(n.dataset.pos)));
  assert.deepEqual([...marked].sort((u, v) => u - v), [...positions].sort((u, v) => u - v));
  cell.dispatchEvent(new dom.window.Event('mouseleave'));
  assert.equal(d.querySelectorAll('.app-cau-digit.is-cau').length, 0);
});

test('biểu mẫu không tự gửi (CSP cấm) mà dựng truy vấn đã chuẩn hoá', async t => {
  const dom = await open(t, fixture.pages['dac-biet-theo-thu']);
  const d = dom.window.document;
  const form = d.getElementById('app-cau-form');
  assert.equal(form.elements.thu.value, '1', 'mặc định cùng thứ với kỳ tới');
  assert.equal(form.elements.ngay.options[0].value, '2026-09-22', 'biên ngày chỉ gồm kỳ cùng thứ');
  form.elements.count.value = '4';
  form.elements.thu.value = '6';
  form.elements.both.checked = true;
  const event = new dom.window.Event('submit', { cancelable: true });
  form.dispatchEvent(event);
  assert.equal(event.defaultPrevented, true);
  const api = dom.window.BridgePages;
  assert.equal(api.formQuery(form), '?count=4&both=1&thu=6&ngay=2026-09-22');
  form.elements.count.value = '-2';
  assert.match(api.formQuery(form), /^\?count=3&/, 'số ngày hỏng về mặc định của trang');
});

test('phôi tuần: đúng số tuần, cột Thứ Hai → Chủ Nhật, cỡ chữ và màu theo lựa chọn', async t => {
  const dom = await open(t, fixture.tool, '', 'WeeklySheet');
  const d = dom.window.document;
  const rows = d.querySelectorAll('.app-phoi tbody tr');
  assert.equal(rows.length, 50);
  assert.deepEqual([...d.querySelectorAll('.app-phoi thead th')].map((n) => n.textContent),
    ['No', 'Thứ hai', 'Thứ ba', 'Thứ tư', 'Thứ năm', 'Thứ sáu', 'Thứ bảy', 'Chủ nhật']);
  const last = rows[rows.length - 1];
  assert.equal(last.querySelector('th').textContent, '1', 'tuần mới nhất ở cuối, đánh số 1');
  assert.equal(last.cells[1].textContent, '77115', '28-09-2026 là Thứ Hai');
  assert.equal(last.cells[2].textContent, '', 'kỳ chưa quay để trống');
  const form = d.getElementById('app-phoi-form');
  form.elements.count.value = '7';
  form.elements.headsize.value = '99';
  form.elements.tailcolour.value = '#0000ff';
  form.dispatchEvent(new dom.window.Event('input'));
  assert.equal(d.querySelectorAll('.app-phoi tbody tr').length, 7);
  const head = d.querySelector('.app-phoi-head');
  assert.equal(head.style.fontSize, '35px', 'cỡ chữ bị kẹp trong 15–35');
  assert.equal(d.querySelector('.app-phoi-tail').style.color, 'rgb(0, 0, 255)');
  form.elements.count.value = '2';
  form.dispatchEvent(new dom.window.Event('input'));
  assert.equal(d.querySelectorAll('.app-phoi tbody tr').length, 5, 'tối thiểu 5 tuần');
});

test('trang bộ số chỉ tô giải Đặc Biệt khi nó rơi vào bộ mà cầu kỳ trước báo', async t => {
  const dom = await open(t, fixture.pages['bo-so']);
  const d = dom.window.document;
  const api = dom.window.BridgePages;
  const { series } = api.state;
  let checked = 0;
  for (const cell of d.querySelectorAll('button.app-cau-cell')) {
    cell.click();
    for (const button of d.querySelectorAll('.app-cau-bridge')) {
      button.click();
      const [a, b] = button.textContent.split(' ')[0].split('x').map(Number);
      for (const card of d.querySelectorAll('#app-cau-days .app-cau-day')) {
        const index = series.findIndex((x) => x.date === card.dataset.date);
        if (index < 1) continue;
        const prev = series[index - 1];
        const draw = series[index];
        const expected = api.BO_ID[10 * prev.digits[a] + prev.digits[b]] === api.BO_ID[draw.two[0]];
        assert.equal(card.querySelector('.tr-number[data-value="0"]').classList.contains('is-hit'), expected);
        checked += 1;
      }
    }
  }
  assert.ok(checked >= 60, 'phải thật sự soi đủ các cặp kỳ');
});

test('biên ngày sớm nhất chọn được vẫn được tôn trọng; biên quá sớm bị từ chối có báo, không âm thầm đổi', async t => {
  const first = await open(t, fixture.pages['loto-theo-thu'], '?thu=4');
  const options = [...first.window.document.getElementById('app-cau-form').elements.ngay.options].map((o) => o.value);
  assert.equal(options.length, 60, 'đủ 60 biên ngày cùng thứ');
  const earliest = options[options.length - 1];
  const dom = await open(t, fixture.pages['loto-theo-thu'], `?thu=4&count=59&ngay=${earliest}`);
  const { series, params } = dom.window.BridgePages.state;
  assert.equal(series[series.length - 1].date, earliest);
  assert.equal(params.rejected, undefined);
  const tooEarly = await open(t, fixture.pages['loto-theo-thu'], '?thu=4&ngay=2000-01-06');
  const d = tooEarly.window.document;
  assert.match(d.querySelector('.app-cau-notice').textContent, /06\/01\/2000 không còn đủ 60 kỳ/);
});

test('"cả hai chữ số" dùng kiểm lịch sử của chính luật ấy', async t => {
  const one = await open(t, fixture.pages['dac-biet']);
  one.window.document.querySelector('button.app-cau-cell').click();
  assert.match(one.window.document.querySelector('.app-cau-honest').textContent, /40,0%/);
  const both = await open(t, fixture.pages['dac-biet'], '?count=1&both=1');
  both.window.document.querySelector('button.app-cau-cell').click();
  assert.match(both.window.document.querySelector('.app-cau-honest').textContent, /1,2% số lần.*2,0%/);
});

test('phôi 80 tuần có đủ 80 hàng', async t => {
  const dom = await open(t, fixture.tool, '', 'WeeklySheet');
  const form = dom.window.document.getElementById('app-phoi-form');
  form.elements.count.value = '80';
  form.dispatchEvent(new dom.window.Event('input'));
  assert.equal(dom.window.document.querySelectorAll('.app-phoi tbody tr').length, 80);
});
