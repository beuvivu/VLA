import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const draws = [
  { d: '2026-09-01', s: '00012', n: ['12', '12', '21', ...Array(24).fill('00')] },
  { d: '2026-09-02', s: '00034', n: ['34', '34', '34', '43', '43', ...Array(22).fill('55')] },
  { d: '2026-09-03', s: '00001', n: [...Array(10).fill('01'), ...Array(10).fill('10'), ...Array(7).fill('55')] },
];
const build = `import json, sys
from pathlib import Path
from tempfile import TemporaryDirectory
from build_stat_pages import PAGES, render_page
from page_output import _attach_evidence
draws = json.load(sys.stdin)
with TemporaryDirectory() as directory:
 print(json.dumps({page.slug: _attach_evidence(Path(directory) / (page.slug + ".html"), render_page(page, draws, generated="2026-09-03T19:00:00Z"))
                  for page in PAGES if page.slug in {"tan-suat-loto", "tan-suat-cap-loto", "thong-ke-tong-hop"}}))`;
const pages = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(root), env: { ...process.env, PYTHONPATH: 'src' }, input: JSON.stringify(draws), encoding: 'utf8',
}));

function setup(t, slug, { evidence = false, query = '' } = {}) {
  let html = pages[slug];
  for (const [override, name] of [
    [process.env.APP_FREQUENCY_PRESENTATION, 'frequency_bento.js'],
    [process.env.APP_STAT_ENGINE, 'stat_pages.js'],
  ]) {
    if (override) html = html.replace(readFileSync(new URL(`src/templates/${name}`, root), 'utf8'), readFileSync(override, 'utf8'));
  }
  const dom = new JSDOM(html, {
    url: `https://example.test/${slug}.html${query}`, runScripts: 'dangerously', pretendToBeVisual: true,
    beforeParse(window) {
      window.ResizeObserver = class { observe() {} };
      window.HTMLElement.prototype.scrollIntoView = function () {};
      window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
      window.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new window.Event('close')); };
    },
  });
  t.after(() => dom.window.close());
  if (evidence) dom.window.eval(readFileSync(new URL('src/assets/app-evidence.js', root), 'utf8'));
  return dom;
}

function change(dom, id, value) {
  const field = dom.window.document.getElementById(id);
  field.value = value;
  field.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
}
const totals = (dom, selector) => [...dom.window.document.querySelectorAll(`${selector} .sp-cell`)]
  .map(cell => [cell.querySelector('b').textContent, Number(cell.querySelector('i').textContent)]);
const distribution = (dom, id) => [...dom.window.document.querySelectorAll(`#${id} tbody tr`)]
  .filter(row => row.cells.length > 1).map(row => Number(row.cells[1].textContent));
const drawer = dom => dom.window.document.getElementById('app-evidence-drawer');
function click(dom, el, altKey = false) {
  el.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true, cancelable: true, button: 0, altKey }));
}

test('tổng hợp phân bố đúng mọi nháy theo đầu, đuôi và tổng, rồi cập nhật toàn bộ khi đổi ngày', t => {
  const dom = setup(t, 'thong-ke-tong-hop');
  assert.equal(totals(dom, '#sp-overview-matrix').length, 100);
  assert.equal(totals(dom, '#sp-overview-matrix').find(([label]) => label === '55')[1], 29);
  assert.deepEqual(distribution(dom, 'sp-overview-head'), [34, 12, 1, 3, 2, 29, 0, 0, 0, 0]);
  assert.deepEqual(distribution(dom, 'sp-overview-tail'), [34, 11, 2, 2, 3, 29, 0, 0, 0, 0]);
  assert.deepEqual(distribution(dom, 'sp-overview-sum'), [53, 20, 0, 3, 0, 0, 0, 5, 0, 0]);
  assert.equal(dom.window.document.querySelector('#sp-grid tbody tr').cells[3].textContent, '35.80×');
  change(dom, 'sp-from', '2026-09-02');
  assert.equal(totals(dom, '#sp-overview-matrix').find(([label]) => label === '00')[1], 0);
  assert.deepEqual(distribution(dom, 'sp-overview-head'), [10, 10, 0, 3, 2, 29, 0, 0, 0, 0]);
  assert.equal(dom.window.document.querySelector('#sp-grid tbody tr').cells[1].textContent, '55');
  assert.equal(dom.window.document.querySelector('#sp-grid tbody tr').cells[2].textContent, '29');
});

test('dải tổng hợp rỗng không giữ ma trận, phân bố hoặc số dẫn đầu của dải trước', t => {
  const dom = setup(t, 'thong-ke-tong-hop');
  change(dom, 'sp-from', '2026-09-04');
  assert.equal(totals(dom, '#sp-overview-matrix').length, 0);
  assert.equal(distribution(dom, 'sp-overview-head').length, 0);
  assert.equal(distribution(dom, 'sp-overview-tail').length, 0);
  assert.equal(distribution(dom, 'sp-overview-sum').length, 0);
  assert.equal(dom.window.document.querySelector('#sp-grid tbody tr').cells.length, 1);
  assert.equal(dom.window.document.querySelector('#sp-kpi').textContent.includes('55 (29)'), false);
});

test('tổng 50 họ cặp cộng đủ nháy; lọc họ cặp chỉ đổi bảng theo kỳ, không đổi số liệu trọn dải', t => {
  const dom = setup(t, 'tan-suat-cap-loto');
  const all = totals(dom, '#bf-pair-totals');
  assert.equal(all.length, 50);
  assert.equal(all.reduce((sum, [, value]) => sum + value, 0), 81);
  assert.equal(all.find(([label]) => label === '00–55')[1], 53);
  assert.equal(all.find(([label]) => label === '01–10')[1], 20);
  dom.window.document.querySelector('[data-bf-pick="none"]').click();
  assert.equal(dom.window.document.querySelector('#sp-matrix-grid tbody tr').cells.length, 1);
  assert.equal(totals(dom, '#bf-pair-totals').reduce((sum, [, value]) => sum + value, 0), 81);
  dom.window.document.querySelector('[data-bf-pair="12-21"]').click();
  assert.equal([...dom.window.document.querySelectorAll('#sp-matrix-grid tbody tr')].filter(row => !row.hidden).length, 1);
  change(dom, 'sp-from', '2026-09-02');
  assert.equal(totals(dom, '#bf-pair-totals').find(([label]) => label === '12–21')[1], 0);
  assert.equal(totals(dom, '#bf-pair-totals').find(([label]) => label === '00–55')[1], 29);
});

test('đổi chiều, sắp xếp và bàn phím giữ danh tính dấu của ô LOTO', t => {
  const dom = setup(t, 'tan-suat-loto'), d = dom.window.document;
  const key = 'm|n12|d2026-09-01';
  d.querySelector(`[data-key="${key}"]`).click();
  change(dom, 'sp-orient', 'Xem theo chiều dọc');
  assert.equal(d.querySelector(`[data-key="${key}"]`).classList.contains('marked'), true);
  change(dom, 'sp-sort', 'hit-desc');
  assert.equal(d.querySelector('#sp-matrix-grid thead th:nth-child(2)').textContent, '55');
  const cell = d.querySelector(`[data-key="${key}"]`);
  cell.focus();
  cell.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
  assert.notEqual(d.activeElement.dataset.key, key);
  assert.equal(d.querySelector(`[data-key="${key}"]`).classList.contains('marked'), true);
  d.getElementById('sp-clear-marks').click();
  assert.equal(d.querySelectorAll('.marked').length, 0);
  assert.equal(d.getElementById('sp-from').value, '2026-09-01');
  assert.equal(totals(dom, '#sp-matrix').reduce((sum, [, value]) => sum + value, 0), 81);
});

test('dải LOTO rỗng xóa tổng 00–99 và bảng xếp hạng rồi phục hồi đúng khi chọn lại', t => {
  const dom = setup(t, 'tan-suat-loto'), d = dom.window.document;
  change(dom, 'sp-from', '2026-09-03');
  change(dom, 'sp-to', '2026-09-02');
  assert.equal(totals(dom, '#sp-matrix').length, 0);
  assert.equal(d.querySelector('#sp-grid tbody tr').cells.length, 1);
  assert.equal(d.querySelectorAll('#sp-grid tbody tr').length, 1);
  assert.equal(d.querySelector('#sp-matrix-grid tbody tr').cells.length, 1);
  assert.equal(d.querySelector('#bf-kpis strong').textContent, '0');
  change(dom, 'sp-to', '2026-09-03');
  assert.equal(totals(dom, '#sp-matrix').length, 100);
  assert.equal(totals(dom, '#sp-matrix').reduce((sum, [, value]) => sum + value, 0), 27);
  assert.equal(d.querySelector('#sp-grid tbody tr').cells[1].textContent, '01');
});

test('bấm tổng nháy của số 00 mở đúng khối, con số, phép đếm và dải hiện tại', t => {
  const dom = setup(t, 'thong-ke-tong-hop', { evidence: true }), d = dom.window.document;
  click(dom, d.querySelector('#sp-overview-matrix .sp-cell i'));
  assert.equal(drawer(dom).open, true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '24');
  assert.match(drawer(dom).querySelector('h2').textContent, /00.*nháy/i);
  assert.match(drawer(dom).querySelector('.app-evidence-context').textContent, /Tần suất LOTO/);
  assert.match(drawer(dom).querySelector('.app-evidence-context').textContent, /Số 00/);
  assert.match(drawer(dom).querySelector('.app-evidence-sources').textContent, /3 kỳ.*01-09-2026.*03-09-2026/);
  assert.match(drawer(dom).querySelector('.app-evidence-steps').textContent, /00.*24 nháy/);
  dom.window.appEvidence.close();
  change(dom, 'sp-from', '2026-09-02');
  click(dom, d.querySelector('#sp-overview-matrix .sp-cell i'));
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '0');
  assert.match(drawer(dom).querySelector('.app-evidence-sources').textContent, /2 kỳ.*02-09-2026.*03-09-2026/);
  assert.doesNotMatch(drawer(dom).querySelector('.app-evidence-sources').textContent, /01-09-2026/);
});

test('phân bố và kỳ vọng theo dải có căn cứ riêng, còn gan Đặc Biệt giữ toàn lịch sử', t => {
  const dom = setup(t, 'thong-ke-tong-hop', { evidence: true }), d = dom.window.document;
  const head = d.querySelector('#sp-overview-head tbody tr').cells[1];
  click(dom, head);
  assert.equal(head.classList.contains('marked'), true);
  assert.equal(drawer(dom), null);
  click(dom, head, true);
  assert.equal(drawer(dom).open, true);
  assert.match(drawer(dom).querySelector('.app-evidence-steps').textContent, /đầu.*0.*34 nháy/i);
  dom.window.appEvidence.close();
  change(dom, 'sp-from', '2026-09-02');
  const ratio = d.querySelector('#sp-grid tbody tr').cells[3];
  click(dom, ratio, true);
  assert.match(drawer(dom).querySelector('.app-evidence-steps').textContent, /27\/100.*2.*0[.,]54/);
  assert.match(drawer(dom).querySelector('.app-evidence-sources').textContent, /2 kỳ.*02-09-2026.*03-09-2026/);
  dom.window.appEvidence.close();
  click(dom, d.querySelector('#sp-grid tbody tr').cells[4], true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '3');
  assert.match(drawer(dom).querySelector('.app-evidence-steps').textContent, /toàn bộ lịch sử/i);
  assert.match(drawer(dom).querySelector('.app-evidence-steps').textContent, /bộ lọc.*không|không.*bộ lọc/i);
  assert.doesNotMatch(drawer(dom).querySelector('.app-evidence-steps').textContent, /tính lại theo bộ lọc/);
});

test('từ chế độ minh họa, tab Tổng hợp chỉ rõ dữ liệu thật và không mang query giả lập', t => {
  const dom = setup(t, 'tan-suat-loto', { query: '?demo=1' }), d = dom.window.document;
  const overview = d.querySelector('.bf-tabs a[href*="thong-ke-tong-hop"]');
  assert.equal(new URL(overview.href).search, '');
  assert.match(overview.textContent, /dữ liệu thật/i);
  const frequencyLinks = d.querySelectorAll('.bf-tabs a[href*="tan-suat"]');
  assert.equal(frequencyLinks.length, 2);
  for (const link of frequencyLinks) {
    assert.equal(new URL(link.href).searchParams.get('demo'), '1');
  }
});

test('chu kỳ Đặc Biệt lấy cả lần về ngoài dải LOTO và vẫn giữ cách đánh dấu ô', t => {
  const dom = setup(t, 'thong-ke-tong-hop', { evidence: true }), d = dom.window.document;
  dom.window.__D_DRAWS__.push({ d: '2026-09-04', s: '00001', n: Array(27).fill('01') });
  change(dom, 'sp-from', '2026-09-02');
  const row = [...d.querySelectorAll('#sp-grid tbody tr')].find(item => item.cells[1].textContent === '01');
  assert.equal(row.cells[2].textContent, '10');
  assert.equal(row.cells[4].textContent, '0');
  assert.equal(row.cells[5].textContent, '1');
  click(dom, row.cells[5]);
  assert.equal(row.cells[5].classList.contains('marked'), true);
  assert.equal(drawer(dom), null);
  click(dom, row.cells[5], true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '1');
  assert.match(drawer(dom).querySelector('h2').textContent, /01.*Chu kỳ.*toàn lịch sử/);
  assert.match(drawer(dom).querySelector('.app-evidence-sources').textContent, /4 kỳ.*01-09-2026.*04-09-2026/);
  assert.match(drawer(dom).querySelector('.app-evidence-steps').textContent, /khoảng cách.*01.*1 kỳ/);
  assert.doesNotMatch(drawer(dom).querySelector('.app-evidence-steps').textContent, /tính lại theo bộ lọc/);
});
