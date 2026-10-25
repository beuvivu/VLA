import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = new URL('../../', import.meta.url);
// Có ngày nghỉ, số lặp cùng kỳ, hai lần về liên tiếp và số chỉ về một lần.
const draws = [
  {d: '2026-09-01', s: '00000', n: ['00', '00', '12', ...Array(24).fill('99')]},
  {d: '2026-09-02', s: '00000', n: ['00', ...Array(26).fill('99')]},
  {d: '2026-09-05', s: '00021', n: ['21', ...Array(26).fill('99')]},
  {d: '2026-09-06', s: '00034', n: ['34', ...Array(26).fill('99')]},
  {d: '2026-09-07', s: '00012', n: ['12', ...Array(26).fill('99')]},
];
const build = `import json,sys
from pages.build_stat_pages import PAGES,render_page
rows=json.load(sys.stdin)
print(json.dumps({p.slug:render_page(p,rows,generated="2026-09-07T19:00:00Z") for p in PAGES if p.slug in {"lo-gan","tan-suat-loto","tan-suat-cap-loto"}}))`;
const pages = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(root), env: {...process.env, PYTHONPATH: 'src'}, input: JSON.stringify(draws), encoding: 'utf8',
}));
const source = readFileSync(new URL('src/web/templates/stat_pages.js', root), 'utf8');
function setup(t, slug, today = '2026-09-08') {
  const errors = [];
  const html = process.env.APP_STAT_ENGINE
    ? pages[slug].replace(source, readFileSync(process.env.APP_STAT_ENGINE, 'utf8')) : pages[slug];
  const dom = new JSDOM(html, {
    url: `https://example.test/${slug}.html`, runScripts: 'dangerously', pretendToBeVisual: true,
    beforeParse(w) {
      const RealDate = w.Date;
      w.Date = class extends RealDate {
        constructor(...args) { super(...(args.length ? args : [`${today}T04:00:00Z`])); }
        static now() { return RealDate.parse(`${today}T04:00:00Z`); }
      };
      w.addEventListener('error', event => errors.push(String(event.error)));
      w.ResizeObserver = class {observe() {}};
      w.matchMedia = () => ({matches: false, addEventListener() {}});
      w.HTMLElement.prototype.scrollIntoView = function () {};
      w.HTMLDialogElement.prototype.showModal = function () {this.open = true;};
      w.HTMLDialogElement.prototype.close = function () {this.open = false;};
    },
  });
  t.after(() => {dom.window.close(); assert.deepEqual(errors, []);});
  return dom;
}
function change(dom, id, value) {
  const field = dom.window.document.getElementById(id);
  field.value = value;
  field.dispatchEvent(new dom.window.Event('change', {bubbles: true}));
}
const pendingDates = d => [...new Set([...d.querySelectorAll('#sp-matrix-grid .sp-pending[data-key]')]
  .map(cell => /\|d([^|]+)/.exec(cell.dataset.key)?.[1]).filter(Boolean))];
function rowFor(d, table, number) {
  const row = [...d.querySelectorAll(`#${table} tbody tr`)].find(row => row.cells[0].textContent === number);
  assert.ok(row, `Thiếu ${number} trong ${table}`);
  return row;
}

for (const slug of ['tan-suat-loto', 'tan-suat-cap-loto']) {
  test(`${slug}: dải lịch sử không chèn kỳ chờ ngoài khoảng ngày đã chọn`, t => {
    const dom = setup(t, slug), d = dom.window.document;
    change(dom, 'sp-to', '2026-09-02');
    for (const direction of ['horizontal', 'vertical']) {
      d.querySelector(`[data-app-orientation="${direction}"]`).click();
      assert.deepEqual(pendingDates(d), []);
      const dates = [...new Set([...d.querySelectorAll('#sp-matrix-grid [data-key]')]
        .map(cell => /\|d([^|]+)/.exec(cell.dataset.key)?.[1]).filter(Boolean))];
      assert.deepEqual(dates, ['2026-09-02', '2026-09-01']);
    }
  });
  test(`${slug}: chỉ dải tới kỳ mới nhất mới có kỳ hôm nay đang chờ`, t => {
    const dom = setup(t, slug), d = dom.window.document;
    assert.deepEqual(pendingDates(d), ['2026-09-08']);
    change(dom, 'sp-to', '2026-09-06');
    assert.deepEqual(pendingDates(d), []);
    change(dom, 'sp-to', '2026-09-07');
    assert.deepEqual(pendingDates(d), ['2026-09-08']);
    change(dom, 'sp-weekday', '1'); // 08/09 là thứ Ba, không phải thứ Hai.
    assert.deepEqual(pendingDates(d), []);
  });
  test(`${slug}: hôm nay đã có kết quả thì không biến thành kỳ chờ khi lọc quá khứ`, t => {
    const dom = setup(t, slug, '2026-09-07'), d = dom.window.document;
    change(dom, 'sp-to', '2026-09-02');
    assert.deepEqual(pendingDates(d), []);
  });
}

test('Lô gan: cực đại đếm kỳ trượt, số về liên tiếp có gan bằng không và khớp popup', t => {
  const dom = setup(t, 'lo-gan'), d = dom.window.document;
  // 12 về ở chỉ số 0 và 4: ba kỳ 1,2,3 trượt; ngày nghỉ không là kỳ quay.
  assert.equal(rowFor(d, 'sp-grid', '12').cells[3].textContent, '3');
  assert.equal(rowFor(d, 'sp-max-lo', '12').cells[1].textContent, '3 kỳ');
  assert.equal(rowFor(d, 'sp-grid', '00').cells[3].textContent, '0');
  assert.equal(rowFor(d, 'sp-max-lo', '00').cells[1].textContent, '0 kỳ');
  assert.equal(rowFor(d, 'sp-grid', '34').cells[3].textContent, '—');
  assert.equal(rowFor(d, 'sp-max-lo', '34').cells[1].textContent, '—');
  assert.equal(dom.window.eval('ganCycles("12", "loto").max'), 3);
  assert.equal(dom.window.eval('ganCycles("00", "loto").max'), 0);
});

test('Cặp gan: một trong hai số về là ngắt gan, hai lần liên tiếp không là một kỳ trượt', t => {
  const dom = setup(t, 'lo-gan'), d = dom.window.document;
  // 12/21 có mặt ở chỉ số 0,2,4; mỗi khoảng chỉ có đúng một kỳ trượt.
  assert.equal(rowFor(d, 'sp-pair-gan', '12 - 21').cells[3].textContent, '1');
  assert.equal(rowFor(d, 'sp-pair-gan', '00 - 55').cells[3].textContent, '0');
  assert.equal(rowFor(d, 'sp-pair-gan', '34 - 43').cells[3].textContent, '—');
});

test('Gan bằng không đã được quan sát giữ số 0 và chú giải, khác dải chưa đủ hai lần', t => {
  const dom = setup(t, 'lo-gan'), d = dom.window.document;
  // Hai kỳ đầu liên tiếp có 00, còn 12 chỉ có mặt một lần.
  dom.window.__D_DRAWS__.splice(2);
  dom.window.eval('renderLoGan()');
  const zero = rowFor(d, 'sp-grid', '00').cells[3];
  assert.equal(zero.textContent, '0');
  assert.equal(zero.dataset.statValue, '0');
  assert.equal(rowFor(d, 'sp-grid', '12').cells[3].textContent, '—');
  for (const id of ['app-loto-current-cycle-legend', 'app-loto-pair-cycle-legend', 'app-loto-history-cycle-legend']) {
    assert.match(d.getElementById(id).textContent, /0 kỳ/);
    assert.doesNotMatch(d.getElementById(id).textContent, /Chưa đủ hai lần/);
  }
});
