import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const slugs = ['dau-duoi-loto', 'cap-lon-loto', 'lo-gan'];
// Ngày nghỉ và hai nháy cùng kỳ phân biệt khoảng theo kỳ với số lượt.
const draws = Array.from({length: 40}, (_, i) => {
  const number = [1, 5, 38].includes(i) ? '07' : [2, 10, 33].includes(i) ? '70'
    : [0, 39].includes(i) ? '00' : '99';
  return {
    d: new Date(Date.UTC(2026, 0, 1 + i + Math.floor(i / 5))).toISOString().slice(0, 10),
    s: `000${number}`, n: [...Array(2).fill(number), ...Array(25).fill('99')],
  };
});
const scaleDraws = draws.map((draw, i) => ({...draw,
  n: [...Array(2).fill([0, 10].includes(i) ? '07' : i === 27 ? '03' : '99'), ...Array(25).fill('99')],
}));
const build = `import json,sys
from pages.build_stat_pages import PAGES,render_page
fixtures=json.load(sys.stdin)
slugs={"dau-duoi-loto","cap-lon-loto","lo-gan"}
print(json.dumps({key:{p.slug:render_page(p,rows,generated="2026-10-25T00:00:00Z") for p in PAGES if p.slug in slugs} for key,rows in fixtures.items()}))`;
const pages = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(root), env: {...process.env, PYTHONPATH: 'src'},
  input: JSON.stringify({full: draws, scales: scaleDraws, empty: []}), encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
}));
const source = readFileSync(new URL('src/web/templates/stat_pages.js', root), 'utf8');

function setup(t, slug, fixture = 'full') {
  const errors = [];
  const html = process.env.APP_STAT_ENGINE
    ? pages[fixture][slug].replace(source, readFileSync(process.env.APP_STAT_ENGINE, 'utf8'))
    : pages[fixture][slug];
  const dom = new JSDOM(html, {
    url: `https://example.test/${slug}.html`, runScripts: 'dangerously', pretendToBeVisual: true,
    beforeParse(w) {
      w.addEventListener('error', event => errors.push(String(event.error)));
      w.ResizeObserver = class {observe() {}};
      w.HTMLElement.prototype.scrollIntoView = function () {};
      w.matchMedia = () => ({matches: false, addEventListener() {}});
    },
  });
  t.after(() => {dom.window.close(); assert.deepEqual(errors, []);});
  assert.deepEqual(errors, []);
  return dom;
}
function change(dom, id, value) {
  const input = dom.window.document.getElementById(id);
  input.value = value;
  input.dispatchEvent(new dom.window.Event('change', {bubbles: true}));
}
function rowFor(document, table, number, column = 0) {
  const row = [...document.querySelectorAll(`#${table} tbody tr`)]
    .find(row => row.cells[column]?.textContent.trim() === number);
  assert.ok(row, `Thiếu ${number} trong ${table}`);
  return row;
}
const values = row => [...row.cells].map(cell => cell.textContent.trim());
const viDate = iso => iso.split('-').reverse().join('-');
function metric(cell, name, value, unit) {
  assert.equal(cell.dataset.statMetric, name);
  assert.equal(cell.dataset.statValue, String(value));
  assert.match(cell.getAttribute('aria-label'), new RegExp(`${value} ${unit}`));
}

for (const slug of slugs) {
  test(`${slug}: vùng thao tác nhận đúng ba trang và bảng vẫn có bộ lọc, đánh dấu`, t => {
    const dom = setup(t, slug), d = dom.window.document;
    const shell = d.querySelector('.app-lotostats-shell[data-app-workspace-guide]');
    assert.ok(shell);
    assert.equal(shell.querySelectorAll('h1').length, 1);
    const nav = shell.querySelector('nav[aria-label="Thống kê LOTO"]');
    assert.deepEqual([...nav.querySelectorAll('a')].map(link => link.getAttribute('href')).sort(), slugs.map(name => `${name}.html`).sort());
    assert.equal(nav.querySelector('[aria-current="page"]').getAttribute('href'), `${slug}.html`);
    assert.ok(shell.querySelector('#sp-count'));
    assert.ok(shell.querySelector('#sp-clear-marks'));
    assert.equal(shell.querySelectorAll('.sp-chips [data-days]').length, 6);
    assert.equal(shell.querySelectorAll('.app-workspace-hero,.app-workspace-guide').length, 0);
  });
}

test('Đầu đuôi: bảng tổng giữ lượt, tỷ lệ và ba ma trận giữ đúng 20 kỳ mới nhất', t => {
  const dom = setup(t, 'dau-duoi-loto'), d = dom.window.document;
  for (const [id, at] of [['sp-head', 0], ['sp-tail', 1]]) {
    assert.equal(d.querySelectorAll(`#${id} tbody tr`).length, 10);
    const expected = Array(10).fill(0);
    draws.forEach(draw => draw.n.forEach(number => expected[Number(number[at])]++));
    for (let digit = 0; digit < 10; digit++) {
      const row = rowFor(d, id, String(digit));
      assert.deepEqual(values(row).slice(0, 3), [String(digit), String(expected[digit]), `${(100 * expected[digit] / 1080).toFixed(2)}%`]);
      assert.equal(row.cells[1].dataset.appHitCount, String(expected[digit]));
    }
  }
  for (const [id, count] of [
    ['sp-day-head', number => Number(number[0])],
    ['sp-day-tail', number => Number(number[1])],
    ['sp-day-sum', number => (Number(number[0]) + Number(number[1])) % 10],
  ]) {
    const rows = [...d.querySelectorAll(`#${id} tbody tr`)];
    assert.equal(rows.length, 20);
    rows.forEach((row, index) => {
      const draw = draws.at(-index - 1), expected = Array(10).fill(0);
      draw.n.forEach(number => expected[count(number)]++);
      assert.equal(row.cells[0].textContent, viDate(draw.d));
      assert.deepEqual([...row.cells].slice(1).map(cell => parseInt(cell.textContent, 10)), expected);
    });
  }
  const last = d.querySelector('#sp-day-head tbody tr').cells[1];
  last.click();
  const key = last.dataset.key;
  change(dom, 'sp-from', draws.at(-2).d);
  assert.equal(d.querySelectorAll('#sp-day-head tbody tr').length, 2);
  assert.ok(d.querySelector(`#sp-day-head [data-key="${key}"]`).classList.contains('marked'));
  assert.ok(d.querySelector('#app-head-tail-legend [data-app-hit-count]'));
  assert.ok(d.querySelector('#app-head-tail-day-legend [data-app-hit-count]'));
});

test('Cặp lộn: giữ thứ hạng, hai chiều, tổng lượt và danh tính có số không đứng đầu khi lọc', t => {
  const dom = setup(t, 'cap-lon-loto'), d = dom.window.document;
  assert.equal(d.querySelectorAll('#sp-grid tbody tr').length, 45);
  assert.equal(d.querySelectorAll('#sp-kep tbody tr').length, 10);
  const row = rowFor(d, 'sp-grid', '07 ↔ 70', 1);
  assert.deepEqual(values(row).slice(1), ['07 ↔ 70', '6', '6', '12', '0']);
  [6, 6, 12].forEach((value, i) => {
    metric(row.cells[i + 2], 'frequency', value, 'lượt');
    assert.equal(row.cells[i + 2].dataset.statLevel, '1');
  });
  assert.deepEqual(values(rowFor(d, 'sp-kep', '00')), ['00', '4']);
  const double = rowFor(d, 'sp-kep', '99');
  assert.deepEqual(values(double), ['99', '1064']);
  metric(double.cells[1], 'frequency', 1064, 'lượt');
  assert.equal(double.cells[1].dataset.statLevel, '3');
  assert.match(d.getElementById('app-loto-reverse-frequency-legend').textContent, /1064 lượt/);
  assert.equal(row.cells[0].dataset.statMetric, undefined);
  assert.equal(row.cells[5].dataset.statMetric, undefined);
  assert.match(row.cells[1].dataset.key, /\|n07-70$/);
  row.cells[1].click();
  const key = row.cells[1].dataset.key;
  change(dom, 'sp-from', draws[33].d);
  const filtered = rowFor(d, 'sp-grid', '07 ↔ 70', 1);
  assert.deepEqual(values(filtered).slice(1), ['07 ↔ 70', '2', '2', '4', '0']);
  metric(filtered.cells[4], 'frequency', 4, 'lượt');
  assert.match(d.getElementById('app-loto-reverse-frequency-legend').textContent, /183 lượt/);
  assert.doesNotMatch(d.getElementById('app-loto-reverse-frequency-legend').textContent, /1064 lượt/);
  assert.equal(filtered.cells[1].dataset.key, key);
  assert.ok(filtered.cells[1].classList.contains('marked'));
  d.getElementById('sp-clear-marks').click();
  assert.equal(d.querySelectorAll('.marked').length, 0);
});

test('Lô gan: trần màu khoảng hiện tại độc lập với trần chu kỳ và thiếu hai lần vẫn là chưa rõ', t => {
  const dom = setup(t, 'lo-gan', 'scales'), d = dom.window.document;
  const once = rowFor(d, 'sp-grid', '03');
  assert.deepEqual(values(once), ['03', viDate(draws[27].d), '12', '—', '1']);
  metric(once.cells[2], 'gap', 12, 'kỳ');
  assert.equal(once.cells[2].dataset.statLevel, '1');
  assert.equal(once.cells[3].dataset.statMetric, undefined);
  assert.equal(once.cells[3].dataset.statValue, undefined);
  assert.equal(once.cells[3].getAttribute('aria-label'), null);
  assert.equal(rowFor(d, 'sp-max-lo', '03').cells[1].dataset.statValue, undefined);
  assert.match(d.getElementById('app-loto-current-gap-legend').textContent, /40 kỳ/);
  assert.match(d.getElementById('app-loto-current-cycle-legend').textContent, /9 kỳ/);
});

test('Lô gan: màu tách số kỳ hiện tại, chu kỳ dài nhất và số kỳ có mặt', t => {
  const dom = setup(t, 'lo-gan'), d = dom.window.document;
  const row = rowFor(d, 'sp-grid', '07');
  // 07 về ở chỉ số 5 rồi 38: chỉ số 6..37 là đúng 32 kỳ trượt.
  assert.deepEqual(values(row), ['07', viDate(draws[38].d), '1', '32', '3']);
  metric(row.cells[2], 'gap', 1, 'kỳ');
  metric(row.cells[3], 'cycle', 32, 'kỳ');
  metric(row.cells[4], 'frequency', 3, 'kỳ');
  assert.equal(row.cells[2].dataset.statLevel, '1');
  assert.equal(row.cells[3].dataset.statLevel, '3');
  const absent = rowFor(d, 'sp-grid', '08');
  metric(absent.cells[2], 'gap', 40, 'kỳ');
  assert.equal(absent.cells[3].textContent, '—');
  assert.equal(absent.cells[3].dataset.statValue, undefined);
  const newest = rowFor(d, 'sp-grid', '00');
  metric(newest.cells[2], 'gap', 0, 'kỳ');
  assert.equal(newest.cells[2].dataset.statLevel, '0');
  const pair = rowFor(d, 'sp-pair-gan', '07 - 70');
  // Cặp ngắt gan ở chỉ số 10 và 33, còn đúng 22 kỳ trượt giữa chúng.
  assert.deepEqual(values(pair), ['07 - 70', viDate(draws[38].d), '1', '22', '6']);
  metric(pair.cells[2], 'gap', 1, 'kỳ');
  metric(pair.cells[3], 'cycle', 22, 'kỳ');
  metric(pair.cells[4], 'frequency', 6, 'kỳ');
  for (const id of ['app-loto-current-gap-legend', 'app-loto-current-cycle-legend',
    'app-loto-pair-gap-legend', 'app-loto-pair-cycle-legend', 'app-loto-history-cycle-legend']) {
    const legend = d.getElementById(id);
    assert.ok(legend, `Thiếu chú giải ${id}`);
    assert.match(legend.textContent, /kỳ/);
  }
  assert.equal(d.querySelectorAll('#sp-grid tbody tr').length, 100);
  assert.equal(d.querySelectorAll('#sp-pair-gan tbody tr').length, 50);
  assert.match(d.getElementById('app-loto-current-gap-legend').textContent, /40 kỳ/);
  assert.match(d.getElementById('app-loto-current-cycle-legend').textContent, /38 kỳ/);
  for (const id of ['sp-grid', 'sp-pair-gan']) {
    const gaps = [...d.querySelectorAll(`#${id} tbody tr`)].map(row => Number(row.cells[2].textContent));
    assert.deepEqual(gaps, gaps.toSorted((a, b) => b - a));
  }
});

test('Lô gan: lọc 30 kỳ làm mới chu kỳ trong dải, giữ nguyên hai nửa lịch sử', t => {
  const dom = setup(t, 'lo-gan'), d = dom.window.document;
  d.querySelector('.sp-chips [data-days="30"]').click();
  assert.match(d.getElementById('sp-count').textContent, /^30 kỳ/);
  const row = rowFor(d, 'sp-grid', '07');
  assert.deepEqual(values(row), ['07', viDate(draws[38].d), '1', '—', '1']);
  metric(row.cells[2], 'gap', 1, 'kỳ');
  assert.equal(row.cells[3].dataset.statValue, undefined);
  metric(row.cells[4], 'frequency', 1, 'kỳ');
  const pair = rowFor(d, 'sp-pair-gan', '07 - 70');
  assert.deepEqual(values(pair), ['07 - 70', viDate(draws[38].d), '1', '22', '3']);
  metric(pair.cells[3], 'cycle', 22, 'kỳ');
  const historical = rowFor(d, 'sp-max-lo', '07');
  assert.deepEqual(values(historical), ['07', '32 kỳ']);
  metric(historical.cells[1], 'cycle', 32, 'kỳ');
  assert.match(d.getElementById('app-loto-current-gap-legend').textContent, /30 kỳ/);
  assert.match(d.getElementById('app-loto-current-cycle-legend').textContent, /22 kỳ/);
  assert.doesNotMatch(d.getElementById('app-loto-current-cycle-legend').textContent, /38 kỳ/);
  assert.match(d.getElementById('app-loto-history-cycle-legend').textContent, /38 kỳ/);
  assert.equal(d.querySelectorAll('#sp-max-lo tbody tr').length, 50);
  assert.equal(d.querySelectorAll('#sp-max-hi tbody tr').length, 50);
  assert.deepEqual([...d.querySelectorAll('#sp-max-lo tbody tr')].map(row => row.cells[0].textContent),
    Array.from({length: 50}, (_, i) => String(i).padStart(2, '0')));
  assert.deepEqual([...d.querySelectorAll('#sp-max-hi tbody tr')].map(row => row.cells[0].textContent),
    Array.from({length: 50}, (_, i) => String(i + 50)));
});

test('Lô gan: dữ liệu trống giữ hợp đồng bảng và không tạo giá trị không hữu hạn', t => {
  const dom = setup(t, 'lo-gan', 'empty'), d = dom.window.document;
  assert.match(d.getElementById('sp-count').textContent, /^0 kỳ/);
  assert.equal(d.querySelectorAll('#sp-grid tbody tr').length, 100);
  assert.equal(d.querySelectorAll('#sp-pair-gan tbody tr').length, 50);
  for (const id of ['sp-grid', 'sp-max-lo', 'sp-max-hi', 'sp-pair-gan']) {
    assert.doesNotMatch(d.getElementById(id).textContent, /NaN|Infinity|undefined/);
    assert.equal(d.querySelectorAll(`#${id} [data-stat-value="NaN"]`).length, 0);
  }
});
