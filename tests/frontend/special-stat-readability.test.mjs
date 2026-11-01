import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const draws = [
  ['2026-10-01', '00107'], ['2026-10-02', '00007'], ['2026-10-03', '00030'],
  ['2026-10-05', '00007'], ['2026-10-06', '00000'], ['2026-10-07', '00012'], ['2026-10-08', '00021'],
].map(([d, s]) => ({d, s, n: Array(27).fill(s.slice(-2))}));
const build = `import json,sys
from pages.build_stat_pages import PAGES,render_page
draws=json.load(sys.stdin)
slugs={"cau-giai-dac-biet","giai-dac-biet-theo-tong","cau-dac-biet-theo-bo-so","chu-ky-dac-biet"}
print(json.dumps({p.slug:render_page(p,draws,generated="2026-10-25T00:00:00Z") for p in PAGES if p.slug in slugs}))`;
const pages = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(root), env: {...process.env, PYTHONPATH: 'src'},
  input: JSON.stringify(draws), encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
}));

function setup(t, slug) {
  const errors = [];
  const dom = new JSDOM(pages[slug], {
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
const rowFor = (document, table, number, column = 0) => [...document.querySelectorAll(`#${table} tbody tr`)]
  .find(row => row.cells[column]?.textContent.trim() === number);

test('Tần suất Đặc Biệt: màu và chú giải dùng số lượt thật, đổi theo dải lọc', t => {
  const dom = setup(t, 'cau-giai-dac-biet'), d = dom.window.document;
  const seven = () => d.querySelector('#sp-grid tbody tr').cells[8];
  assert.equal(seven().dataset.statValue, '3');
  assert.equal(seven().dataset.statMetric, 'frequency');
  assert.equal(seven().dataset.statLevel, '3');
  assert.equal(seven().textContent, '073 lần');
  const zero = d.querySelector('#sp-grid tbody tr').cells[2];
  assert.equal(zero.dataset.statValue, '0');
  assert.equal(zero.dataset.statLevel, '0');
  assert.match(zero.getAttribute('aria-label'), /01.*0 lần/);
  assert.match(d.getElementById('app-special-frequency-legend').textContent, /3 lần/);
  const originalKey = seven().dataset.key;
  seven().click();
  change(dom, 'sp-from', '2026-10-05');
  assert.equal(seven().dataset.statValue, '1');
  assert.equal(seven().dataset.key, originalKey);
  assert.ok(seven().classList.contains('marked'));
  const legend = d.getElementById('app-special-frequency-legend').textContent;
  assert.match(legend, /1 lần/);
  assert.doesNotMatch(legend, /3 lần/);
  const reverseLegend = d.getElementById('app-special-reverse-legend');
  assert.ok(reverseLegend);
  assert.match(reverseLegend.textContent, /2 lần/);
  assert.doesNotMatch(legend, /2 lần/);
  assert.equal(d.querySelectorAll('#sp-recent .sp-draw').length, 3);
  assert.match(d.getElementById('sp-recent').textContent, /08-10-2026/);
});

for (const slug of ['cau-dac-biet-theo-bo-so', 'chu-ky-dac-biet']) {
  test(`${slug}: màu khoảng cách dùng số kỳ chưa về, không dùng chu kỳ cực đại`, t => {
    const dom = setup(t, slug), d = dom.window.document;
    const numberColumn = slug === 'chu-ky-dac-biet' ? 1 : 0;
    const row = rowFor(d, 'sp-grid', '07', numberColumn);
    assert.ok(row);
    assert.equal(d.querySelectorAll('#sp-grid tbody tr').length, 100);
    assert.equal(row.cells[2].textContent, '3');
    assert.equal(row.cells[3].textContent, '2');
    assert.equal(row.cells[4].textContent, '3');
    assert.equal(row.cells[2].dataset.statValue, '3');
    assert.equal(row.cells[2].dataset.statMetric, 'gap');
    const absent = rowFor(d, 'sp-grid', '99', numberColumn);
    assert.equal(absent.cells[2].dataset.statValue, '7');
    assert.equal(absent.cells[2].dataset.statLevel, '3');
    assert.match(d.getElementById('app-special-gap-legend').textContent, /kỳ/);
    d.querySelector('.sp-chips [data-days="30"]').click();
    assert.equal(rowFor(d, 'sp-grid', '07', numberColumn).cells[2].dataset.statValue, '3');
  });
}

test('Theo tổng: phân biệt lượt, kỳ chưa về và chẵn/lẻ mà giữ đúng mẫu liền ngày', t => {
  const dom = setup(t, 'giai-dac-biet-theo-tong'), d = dom.window.document;
  const seven = rowFor(d, 'sp-grid', '7');
  assert.equal(seven.cells[2].dataset.statValue, '3');
  assert.equal(seven.cells[2].dataset.statMetric, 'gap');
  assert.equal(seven.cells[3].dataset.statValue, '3');
  assert.equal(seven.cells[3].dataset.statMetric, 'frequency');
  const totalLegend = d.getElementById('app-special-total-frequency-legend');
  assert.ok(totalLegend);
  assert.match(totalLegend.textContent, /3 lần/);
  assert.doesNotMatch(d.getElementById('app-special-transition-legend').textContent, /3 lần/);
  const parity = rowFor(d, 'sp-parity', '7');
  assert.deepEqual([...parity.cells].map(cell => cell.textContent), ['7', '3', '33,33 %', '66,67 %']);
  assert.equal(parity.cells[2].dataset.statParity, 'even');
  assert.equal(parity.cells[3].dataset.statParity, 'odd');
  const transition = [...d.querySelectorAll('#sp-trans tbody tr')]
    .find(row => row.cells[0].textContent === '3' && row.cells[1].textContent === '7');
  assert.equal(transition.cells[2].textContent, '0');
  assert.equal(transition.cells[3].textContent, '1');
  change(dom, 'sp-from', '2026-11-01');
  for (const id of ['sp-grid', 'sp-parity', 'sp-trans']) {
    assert.equal(d.querySelectorAll(`#${id} tbody .sp-empty-row`).length, 1);
    assert.equal(d.querySelectorAll(`#${id} [data-stat-value]`).length, 0);
  }
});
