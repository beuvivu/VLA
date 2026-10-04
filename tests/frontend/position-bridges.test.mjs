import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM, VirtualConsole } from 'jsdom';

// Bản trình duyệt và bản Python của soi cầu vị trí PHẢI đếm ra cùng một con số:
// trang chủ in ô "đẹp nhất" từ Python, trang đường cầu tính lại bằng JS.
const build = `import json
import pandas as pd
import build_position_bridges as page
import position_bridges as pb
from shared_results import draw_from_row, render_result_board
raw = pd.read_csv("data/xsmb.csv", dtype=str)
raw = raw[raw["date"] <= "2026-09-28"]
dates, digits, values = pb.load_draws(raw.astype({c: int for c in pb.COLUMNS}))
rows = [{"k": k, "plus": k == 10, "n": 1000, "hits": 400, "rate": 0.4, "expected": 0.4, "z": 0.0, "days": 9} for k in range(11)]
report = {"source_date": dates[-1], "target_date": "2026-09-29", "window": pb.WINDOW,
          "draws": [{"date": d, "values": [str(int(v)).zfill(w) for v, w in zip(r, pb.WIDTHS)]}
                    for d, r in zip(dates[-pb.WINDOW:], values[-pb.WINDOW:])], "modes": {}}
for key, cfg in pb.MODES.items():
    found = pb.find_bridges(digits, values, nhay=cfg["nhay"], db=cfg["db"], lon=cfg["lon"], limit=cfg["limit"])
    report["modes"][key] = {**cfg, "summary": pb.summarize(found, cfg["limit"]), "best": pb.best(found),
                            "streaks": {"base_rate": 0.4, "rate_kep": 0.24, "rate_pair": 0.42, "draws": 4217, "rows": rows},
                            "consensus": {"limit": cfg["limit"], "rows": rows[:1] and [{**rows[0], "from": 1, "to": 1}]}}
combos = [dict(nhay=1, db=False, lon=True, limit=5), dict(nhay=2, db=False, lon=True, limit=3),
          dict(nhay=1, db=True, lon=True, limit=1), dict(nhay=1, db=False, lon=False, limit=5),
          dict(nhay=1, db=False, lon=True, limit=6, exact=True), dict(nhay=3, db=False, lon=True, limit=2),
          dict(nhay=1, db=True, lon=False, limit=1), dict(nhay=2, db=False, lon=False, limit=2)]
expected = [[[b["vt"], b["streak"], b["numbers"], b["shadow"]] for b in pb.find_bridges(digits, values, **c)] for c in combos]
row = raw.iloc[-1].to_dict()
print(json.dumps({"page": page.render(report), "combos": combos, "expected": expected,
                  "labels": [p["label"] for p in pb.positions()],
                  "landing": render_result_board(draw_from_row(row), extra=page.best_panel(report, dates[-1]))}))`;
const fixture = JSON.parse(execFileSync(process.env.APP_TEST_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(new URL('../../', import.meta.url)), env: { ...process.env, PYTHONPATH: 'src' },
  encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
}));

async function open(t, search = '') {
  // Bộ điều hướng của jsdom chưa có: lời gọi location.assign chỉ ghi "not implemented".
  const virtualConsole = new VirtualConsole();
  const dom = new JSDOM(fixture.page, {
    url: `https://example.test/soi-cau-vi-tri.html${search}`, runScripts: 'outside-only', virtualConsole,
  });
  t.after(() => dom.window.close());
  const source = readFileSync(new URL('../../src/templates/position_bridges.js', import.meta.url), 'utf8');
  const override = process.env.APP_POSITION_BRIDGES_SCRIPT
    ? readFileSync(process.env.APP_POSITION_BRIDGES_SCRIPT, 'utf8') : source;
  for (const script of dom.window.document.querySelectorAll('script:not([src])')) {
    if (script.type !== 'application/json' && script.textContent.includes('PositionBridges')) {
      dom.window.eval(script.textContent.replace(source, override));
    }
  }
  // Trang nạp script ở cuối thân nên dựng khi DOMContentLoaded; jsdom bắn sự
  // kiện ấy sau lượt đồng bộ hiện tại.
  if (dom.window.document.readyState === 'loading') {
    await new Promise((resolve) => dom.window.document.addEventListener('DOMContentLoaded', resolve));
  }
  return dom;
}

const texts = (nodes) => [...nodes].map((node) => node.textContent);

test('bộ máy trình duyệt ra đúng từng cầu như bản Python với tám bộ tham số', async t => {
  const dom = await open(t);
  const api = dom.window.PositionBridges;
  const report = JSON.parse(dom.window.document.getElementById('app-bridge-data').textContent);
  const prepared = api.prepare(report.draws);
  fixture.combos.forEach((combo, i) => {
    // Qua JSON: mảng dựng trong cửa sổ jsdom mang prototype của realm khác.
    const got = JSON.parse(JSON.stringify(api.findBridges(prepared, { exact: false, ...combo })
      .map((b) => [b.vt, b.streak, b.numbers, b.shadow])));
    assert.deepEqual(got, fixture.expected[i], JSON.stringify(combo));
  });
  assert.deepEqual(JSON.parse(JSON.stringify(api.POSITIONS.map((p) => p.label))), fixture.labels, 'hai bản đánh số vị trí khác nhau');
});

test('đường cầu 6x22 tô chữ số nguồn, tô số về theo cầu kỳ trước, mới nhất trước', async t => {
  const dom = await open(t, '?vt=6x22&limit=3&exactlimit=0&lon=1&nhay=2&db=0');
  const d = dom.window.document;
  assert.equal(d.querySelector('.app-bridge-path').hidden, false);
  assert.equal(d.querySelector('.app-bridge-path-head h2').textContent, 'Cầu LOTO 2 nháy tại vị trí 6x22');
  assert.equal(d.querySelector('.app-bridge-predict b').textContent, '68,86');
  assert.match(d.querySelector('.app-bridge-run').textContent, /Đã chạy 3 kỳ/);
  const days = d.querySelectorAll('.app-bridge-days .app-bridge-day');
  // Mặc định ít nhất 7 kỳ kết quả (8 bảng) để thấy cả những kỳ cầu trượt trước khi chạy.
  assert.equal(days.length, 8);
  assert.deepEqual(texts(d.querySelectorAll('.app-bridge-days h2')).map((s) => s.slice(-10)).slice(0, 4),
    ['28/09/2026', '27/09/2026', '26/09/2026', '25/09/2026']);
  assert.equal(d.querySelector('.app-bridge-day-button[aria-pressed="true"]').value, '7');
  assert.deepEqual(texts(days[0].querySelectorAll('.app-bridge-src')), ['6', '8']);
  assert.deepEqual(texts(days[0].querySelectorAll('.app-bridge-hit')), ['46', '46']);
  assert.deepEqual(texts(days[1].querySelectorAll('.app-bridge-hit')), ['45', '54']);
  assert.deepEqual(texts(d.querySelectorAll('.app-bridge-days .tr-badge')).slice(0, 4), ['Trúng', 'Trúng', 'Trúng', 'Trượt']);
  d.querySelector('.app-bridge-day-button[value="1"]').click();
  assert.equal(d.querySelectorAll('.app-bridge-days .app-bridge-day').length, 2);
  assert.equal(d.querySelector('.app-bridge-day-button[value="1"]').getAttribute('aria-pressed'), 'true');
});

test('không lộn thì chữ số thứ hai được đánh dấu riêng và thứ tự vị trí giữ nguyên', async t => {
  const dom = await open(t, '?vt=95x74&limit=5&exactlimit=0&lon=0&nhay=1&db=0');
  const d = dom.window.document;
  assert.equal(d.querySelector('.app-bridge-path-head h2').textContent, 'Cầu LOTO (không lộn) tại vị trí 95x74');
  assert.equal(d.querySelector('.app-bridge-predict b').textContent, '22');
  const first = d.querySelector('.app-bridge-days .app-bridge-day');
  assert.equal(first.querySelectorAll('.app-bridge-src--b').length, 1);
});

test('đường cầu Đặc Biệt chỉ tô hai số cuối của giải Đặc Biệt', async t => {
  const dom = await open(t, '?vt=18x36&limit=1&exactlimit=0&lon=1&nhay=1&db=1');
  const d = dom.window.document;
  assert.equal(d.querySelector('.app-bridge-path-head h2').textContent, 'Cầu Đặc Biệt tại vị trí 18x36');
  assert.equal(d.querySelector('.app-bridge-predict b').textContent, '44');
  // Mỗi số một phần tử: "67,76" viết liền bị đọc thành số thập phân.
  assert.deepEqual([...d.querySelectorAll('.app-bridge-predict .app-bridge-num')].map((n) => n.textContent), ['44', '99'], 'số bóng cũng là một phần tử số');
  assert.equal(d.querySelector('.app-bridge-predict .app-bridge-shadow').textContent, 'bóng 99');
  assert.match(d.querySelector('.app-bridge-run').textContent, /Đã chạy 2 kỳ/);
  const hits = [...d.querySelectorAll('.app-bridge-days .app-bridge-hit')];
  assert.equal(hits.length, 2);
  assert.ok(hits.every((node) => node.closest('.tr-prize-row').dataset.prize === 'special'));
  // Kéo dài 20 kỳ: số cầu báo có về ở giải khác cũng KHÔNG được tô — chỉ ĐB tính.
  const long = await open(t, '?vt=18x36&limit=1&exactlimit=0&lon=1&nhay=1&db=1&days=20');
  const cards = [...long.window.document.querySelectorAll('.app-bridge-days .app-bridge-day')];
  assert.equal(cards.length, 21);
  // Phải có kỳ mà số cầu báo về ở giải KHÁC — nếu không, phép kiểm dưới không đỏ được.
  const api = long.window.PositionBridges;
  const report = JSON.parse(long.window.document.getElementById('app-bridge-data').textContent);
  const days = api.pathOf(api.prepare(report.draws), 18, 36, { db: true, lon: true, nhay: 1 }).days.slice(-21);
  assert.ok(days.some((day) => day.prev && day.draw.two.slice(1).some((n) => day.prev.includes(n))));
  const allHits = [...long.window.document.querySelectorAll('.app-bridge-days .app-bridge-hit')];
  assert.ok(allHits.every((node) => node.closest('.tr-prize-row').dataset.prize === 'special'));
  const badges = texts(long.window.document.querySelectorAll('.app-bridge-days .tr-badge'));
  assert.equal(allHits.length, badges.filter((b) => b === 'Trúng').length, 'mỗi kỳ trúng đúng một ô ĐB');
});

test('danh sách mặc định là cầu LOTO từ 5 ngày, in đậm cầu dài hơn và thống kê cầu lặp', async t => {
  const dom = await open(t);
  const d = dom.window.document;
  assert.equal(d.querySelector('.app-bridge-path').hidden, true, 'không có vt thì không mở đường cầu');
  assert.equal(d.querySelectorAll('#app-bridge-list .app-bridge-links a').length, 43);
  assert.equal(d.querySelectorAll('#app-bridge-list .app-bridge-links .is-longer').length, 18);
  assert.deepEqual(texts(d.querySelectorAll('.app-bridge-repeats b')).slice(0, 3), ['38,83', '44', '27,72']);
  assert.equal(d.getElementById('app-bridge-form').elements.limit.value, '5');
  const href = d.querySelector('#app-bridge-list .app-bridge-links a').getAttribute('href');
  assert.match(href, /^\?vt=\d+x\d+&limit=5&exactlimit=0&lon=1&nhay=1&db=0$/);
});

test('bảng vị trí cầu: bấm vị trí in đậm thì các vị trí ghép cầu với nó hiện màu đỏ', async t => {
  const dom = await open(t, '?limit=3&nhay=2&lon=1&db=0');
  const d = dom.window.document;
  const cells = d.querySelectorAll('#app-bridge-matrix button.app-bridge-cell');
  assert.ok(cells.length > 0);
  const six = [...cells].find((node) => node.title.startsWith('Vị trí 6:'));
  six.click();
  assert.equal(six.getAttribute('aria-pressed'), 'true');
  const partners = [...d.querySelectorAll('#app-bridge-matrix .is-partner')].map((node) => node.title.split(':')[0]);
  assert.deepEqual(partners.sort(), ['Vị trí 22', 'Vị trí 76', 'Vị trí 84', 'Vị trí 89']);
  six.click();
  assert.equal(d.querySelectorAll('#app-bridge-matrix .is-partner').length, 0);
});

test('khi lộn, 22x6 và 6x22 là cùng một cầu', async t => {
  const dom = await open(t, '?vt=22x6&limit=3&exactlimit=0&lon=1&nhay=2&db=0');
  assert.equal(dom.window.document.querySelector('.app-bridge-path-head h2').textContent,
    'Cầu LOTO 2 nháy tại vị trí 6x22');
});

test('bấm Soi cầu không gửi biểu mẫu (CSP cấm) mà tự dựng truy vấn đã chuẩn hoá', async t => {
  const dom = await open(t);
  const d = dom.window.document;
  const form = d.getElementById('app-bridge-form');
  form.elements.limit.value = '3';
  form.elements.nhay.value = '2';
  d.querySelector('input[name="lon"][value="0"]').checked = true;
  const event = new dom.window.Event('submit', { cancelable: true });
  form.dispatchEvent(event);
  assert.equal(event.defaultPrevented, true, 'để trình duyệt tự gửi thì CSP form-action chặn đứng');
  const api = dom.window.PositionBridges;
  assert.equal(api.formQuery(form), '?limit=3&exactlimit=0&lon=0&nhay=2&db=0');
  form.elements.db.checked = true;
  form.elements.limit.value = '999';
  assert.equal(api.formQuery(form), '?limit=5&exactlimit=0&lon=0&nhay=1&db=1', 'ĐB bỏ số nháy; độ dài hỏng về mặc định');
});

test('tham số hỏng rơi về mặc định thay vì vẽ bậy', async t => {
  for (const search of ['?vt=999x3&limit=abc&nhay=9&lon=1', '?vt=7x7&limit=-3&nhay=0', '?limit=500&nhay=2.5']) {
    const dom = await open(t, search);
    const d = dom.window.document;
    assert.equal(d.querySelector('.app-bridge-path').hidden, true, search);
    assert.equal(d.getElementById('app-bridge-form').elements.limit.value, '5', search);
    assert.equal(d.getElementById('app-bridge-form').elements.nhay.value, search.includes('2.5') ? '2' : '1', search);
  }
});

test('ô cầu cạnh bảng LOTO của trang chủ sống sót khi bảng kết quả được dựng lại', t => {
  const dom = new JSDOM(fixture.landing, { url: 'https://example.test/', runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  for (const script of dom.window.document.querySelectorAll('script:not([src])')) {
    if (script.type !== 'application/json') dom.window.eval(script.textContent);
  }
  const d = dom.window.document;
  const extra = d.querySelector('.tr-day-grid > .tr-day-extra .app-bridge-best');
  assert.ok(extra, 'bộ dựng DOM làm rơi ô cầu');
  assert.equal(d.querySelectorAll('.tr-day-extra').length, 1);
  assert.equal(extra.querySelectorAll('.app-bridge-list a').length, 30);
  assert.ok(d.querySelector('.tr-day-grid > .tr-day-side + .tr-day-extra'), 'ô cầu đứng cạnh bảng LOTO');
});
