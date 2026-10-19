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
                  for page in PAGES if page.slug in {"tan-suat-loto", "tan-suat-cap-loto", "thong-ke-tong-hop", "dau-duoi-loto"}}))`;
const pages = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(root), env: { ...process.env, PYTHONPATH: 'src' }, input: JSON.stringify(draws), encoding: 'utf8',
}));

function setup(t, slug, { evidence = false, query = '', mobile = false, savedOrientation = '', storageBlocked = false, sourcePages = pages } = {}) {
  let html = sourcePages[slug];
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
      window.matchMedia = () => ({ matches: mobile, addEventListener() {} });
      if (savedOrientation) window.localStorage.setItem('sp.orientation.v1.' + (query ? 'demo.' : '') + slug + '.html', savedOrientation);
      if (storageBlocked) Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });
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

test('chọn họ cặp giữ tiêu điểm bàn phím trên nút vừa thao tác', t => {
  const dom = setup(t, 'tan-suat-cap-loto'), d = dom.window.document;
  const button = d.querySelector('[data-bf-pair="12-21"]');
  button.closest('details').open = true;
  button.focus();
  button.click();
  assert.equal(d.activeElement, button);
  assert.equal(button.getAttribute('aria-pressed'), 'false');
  button.click();
  assert.equal(d.activeElement, button);
  assert.equal(button.getAttribute('aria-pressed'), 'true');
});

test('popup gan là dialog native, nhận tiêu điểm và đóng trả về nút mở', t => {
  const dom = setup(t, 'tan-suat-loto'), d = dom.window.document;
  const button = d.querySelector('#sp-picker [data-num="12"]');
  button.closest('details').open = true;
  button.focus();
  button.click();
  const modal = d.getElementById('sp-gan-modal');
  assert.equal(modal.tagName, 'DIALOG');
  assert.equal(modal.open, true);
  assert.equal(d.activeElement, modal.querySelector('[data-close]'));
  assert.equal(d.getElementById(modal.getAttribute('aria-labelledby')).textContent, 'Chu kỳ gan · số 12');
  modal.dispatchEvent(new dom.window.Event('cancel', {cancelable: true}));
  assert.equal(modal.open, false);
  assert.equal(modal.hidden, true);
  assert.equal(d.activeElement, button);
});

test('đổi mode popup gan giữ tiêu điểm, nút lọc đóng dialog và vẫn lọc đúng số', t => {
  const dom = setup(t, 'tan-suat-loto'), d = dom.window.document;
  const button = d.querySelector('#sp-picker [data-num="12"]');
  button.closest('details').open = true;
  button.focus();
  button.click();
  const modal = d.getElementById('sp-gan-modal');
  const mode = modal.querySelector('[data-gmode="de"]');
  mode.focus();
  mode.click();
  assert.equal(modal.open, true);
  assert.equal(d.activeElement, modal.querySelector('[data-gmode="de"]'));
  assert.equal(modal.querySelector('[data-gmode="de"]').classList.contains('on'), true);
  modal.querySelector('[data-gfilter="12"]').click();
  assert.equal(modal.open, false);
  assert.equal(d.activeElement, button);
  assert.deepEqual([...d.querySelectorAll('#sp-matrix-grid tbody tr')].filter(row => !row.hidden)
    .map(row => row.cells[0].dataset.key), ['m|n12']);
});

test('đổi chiều, sắp xếp và bàn phím giữ danh tính dấu của ô LOTO', t => {
  const dom = setup(t, 'tan-suat-loto'), d = dom.window.document;
  const key = 'm|n12|d2026-09-01';
  d.querySelector(`[data-key="${key}"]`).click();
  change(dom, 'sp-orient', 'Xem theo chiều dọc');
  assert.equal(d.querySelector(`[data-key="${key}"]`).classList.contains('marked'), true);
  change(dom, 'sp-sort', 'hit-desc');
  assert.equal(d.querySelector('#sp-matrix-grid thead th:nth-child(2)').dataset.key, 'm|n55');
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


test('mobile mặc định Dọc là ma trận ngày theo hàng, giữ đủ số và nhớ chiều thủ công', t => {
  const dom = setup(t, 'tan-suat-loto', { mobile: true }), d = dom.window.document;
  assert.equal(d.querySelector('[data-app-orientation="vertical"]').getAttribute('aria-pressed'), 'true');
  assert.equal(d.querySelectorAll('[data-app-orientation]').length, 2);
  assert.equal(d.querySelectorAll('table[aria-pressed]').length, 0);
  assert.equal(d.querySelector('.bf-matrix-scroll').hidden, false);
  assert.equal(d.querySelector('#sp-matrix-grid thead th').textContent, 'Ngày');
  assert.equal(d.querySelectorAll('#sp-matrix-grid thead .app-frequency-spark').length, 100);
  assert.deepEqual([...d.querySelectorAll('#sp-matrix-grid tbody td:first-child:not(.sp-pending)')].map(c => c.textContent), ['03-09', '02-09', '01-09']);
  d.querySelector('[data-app-orientation="horizontal"]').click();
  assert.equal(d.querySelector('.bf-matrix-scroll').hidden, false);
  assert.equal(dom.window.localStorage.getItem('sp.orientation.v1.tan-suat-loto.html'), 'horizontal');
  assert.equal(d.querySelectorAll('#sp-matrix-grid [tabindex="0"]').length, 0);
  const saved = setup(t, 'tan-suat-loto', { mobile: true, savedOrientation: 'horizontal' });
  assert.equal(saved.window.document.querySelector('.bf-matrix-scroll').hidden, false);
});

test('badge và sparkline theo chính dải đã chọn, cùng thang và rõ lượt/kỳ', t => {
  const dom = setup(t, 'tan-suat-loto', { mobile: true }), d = dom.window.document;
  const card = n => d.querySelector(`[data-app-number="${n}"]`);
  const spark = n => card(n).querySelector('.app-frequency-spark');
  assert.match(card('00').querySelector('.app-frequency-count').textContent, /24 lượt/);
  assert.match(card('00').textContent, /3 kỳ/);
  const path = spark('00').querySelector('path').getAttribute('d');
  assert.equal(new Set([...d.querySelectorAll('.app-frequency-spark')].map(s => s.dataset.scale)).size, 1);
  change(dom, 'sp-from', '2026-09-02');
  assert.match(card('00').querySelector('.app-frequency-count').textContent, /0 lượt/);
  assert.match(card('00').textContent, /2 kỳ/);
  assert.notEqual(spark('00').querySelector('path').getAttribute('d'), path);
  assert.equal(spark('00').dataset.total, '0');
  change(dom, 'sp-to', '2026-09-01');
  assert.equal(d.querySelectorAll('.app-frequency-spark').length, 0);
  assert.match(d.getElementById('sp-matrix-grid').textContent, /Không có kỳ/);
});

test('Dọc họ cặp đặt 50 họ trên đầu cột với 100 chart thành viên, đánh dấu đúng từng kỳ', t => {
  const dom = setup(t, 'tan-suat-cap-loto', { mobile: true }), d = dom.window.document;
  assert.equal(d.querySelector('.bf-matrix-scroll').hidden, false);
  assert.equal(d.querySelectorAll('#sp-matrix-grid thead th[data-key]').length, 50);
  assert.equal(d.querySelectorAll('#sp-matrix-grid thead .app-frequency-spark').length, 100);
  const header = d.querySelector('#sp-matrix-grid th[data-key="p|c12-21"]');
  assert.match(header.querySelector('[data-app-number="12"] .app-frequency-count').textContent, /2 lượt/);
  assert.match(header.querySelector('[data-app-number="21"] .app-frequency-count').textContent, /1 lượt/);
  const mark = d.querySelector('#sp-matrix-grid [data-key="p|c12-21|d2026-09-01"]');
  assert.equal(mark.textContent, '3');
  mark.click();
  assert.equal(mark.classList.contains('marked'), true);
  change(dom, 'sp-from', '2026-09-02');
  assert.match(d.querySelector('#sp-matrix-grid th[data-key="p|c12-21"] [data-app-number="12"] .app-frequency-count').textContent, /0 lượt/);
});

for (const slug of ['tan-suat-loto', 'tan-suat-cap-loto']) {
  test(`${slug}: xoay ma trận giữ nguyên từng ô, màu nháy, Đặc Biệt và dấu chọn sau sắp xếp`, t => {
    const dom = setup(t, slug), d = dom.window.document;
    const read = () => new Map([...d.querySelectorAll('#sp-matrix-grid tbody td[data-key]')]
      .filter(cell => /\|(n\d{2}|c\d{2}-\d{2})\|d/.test(cell.dataset.key))
      .map(cell => [cell.dataset.key, {value: Number(cell.textContent) || 0,
        tier: [1, 2, 3, 4, 5].find(n => cell.classList.contains('sp-n' + n)) || 0,
        special: cell.classList.contains('sp-de-hit'), marked: cell.classList.contains('marked')}]));
    const key = slug === 'tan-suat-loto' ? 'm|n12|d2026-09-01' : 'p|c12-21|d2026-09-01';
    const mark = d.querySelector(`#sp-matrix-grid td[data-key="${key}"]`);
    mark.click();
    const horizontal = read();
    assert.equal(horizontal.get(key).value, slug === 'tan-suat-loto' ? 2 : 3);
    assert.equal(horizontal.get(key).special, true);
    assert.equal(horizontal.get(key).marked, true);
    d.querySelector('[data-app-orientation="vertical"]').click();
    assert.equal(d.querySelector('.bf-matrix-scroll').hidden, false);
    assert.deepEqual(read(), horizontal);
    assert.equal(d.querySelector('#sp-matrix-grid thead th').textContent, 'Ngày');
    change(dom, 'sp-sort', 'hit-desc');
    assert.deepEqual(read(), horizontal);
    d.querySelector('[data-app-orientation="horizontal"]').click();
    assert.deepEqual(read(), horizontal);
  });
}

test('demo có hướng dẫn thao tác, bộ nhớ riêng và vẫn chạy khi storage bị chặn', t => {
  const dom = setup(t, 'tan-suat-loto', { query: '?demo=1', mobile: true }), d = dom.window.document;
  assert.equal(d.getElementById('app-frequency-onboarding').hidden, false);
  assert.match(d.getElementById('app-frequency-onboarding').textContent, /Chọn dải.*Đọc xu hướng.*Đối chiếu/s);
  d.querySelector('[data-app-orientation="horizontal"]').click();
  assert.equal(dom.window.localStorage.getItem('sp.orientation.v1.demo.tan-suat-loto.html'), 'horizontal');
  assert.equal(dom.window.localStorage.getItem('sp.orientation.v1.tan-suat-loto.html'), null);
  const blocked = setup(t, 'tan-suat-loto', { mobile: true, storageBlocked: true });
  assert.equal(blocked.window.document.querySelectorAll('.app-frequency-spark').length, 100);
});


test('đổi30/60/90 kỳ đổi tổng badge thực tế và chart, giữ đúng counts ở cả hai chiều', t => {
  const history = Array.from({length: 95}, (_, i) => ({
    d: new Date(Date.UTC(2026, 5, i + 1)).toISOString().slice(0, 10), s: '00012',
    n: [...Array(i % 4).fill('12'), ...Array(27 - i % 4).fill('55')],
  }));
  const sourcePages = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c', build], {
    cwd: fileURLToPath(root), env: {...process.env, PYTHONPATH: 'src'}, input: JSON.stringify(history), encoding: 'utf8',
  }));
  const dom = setup(t, 'tan-suat-loto', {mobile: true, sourcePages}), d = dom.window.document;
  const paths = new Set();
  for (const days of [30, 60, 90]) {
    d.querySelector(`#sp-quick [data-days="${days}"]`).click();
    const expected = history.slice(-days).reduce((sum, row) => sum + row.n.filter(n => n === '12').length, 0);
    const member = d.querySelector('[data-app-number="12"]');
    assert.equal(Number(member.querySelector('svg').dataset.total), expected);
    assert.match(member.querySelector('small').textContent, new RegExp(`${days} kỳ`));
    paths.add(member.querySelector('path').getAttribute('d'));
    d.querySelector('[data-app-orientation="horizontal"]').click();
    assert.equal(Number(d.querySelector('[data-app-number="12"] svg').dataset.total), expected);
    assert.equal(d.querySelectorAll('.app-frequency-spark').length, 100);
    d.querySelector('[data-app-orientation="vertical"]').click();
  }
  assert.ok(paths.size > 1, 'đường biểu đồ phải tính lại theo dải, không giữ30kỳ');
});


test('bàn phím từ vùng cuộn chỉ đánh dấu họ cặp đang hiện sau lọc', t => {
  const dom = setup(t, 'tan-suat-cap-loto'), d = dom.window.document;
  d.querySelector('[data-app-orientation="horizontal"]').click();
  d.querySelector('[data-bf-pick="none"]').click();
  d.querySelector('[data-bf-pair="12-21"]').click();
  const region = d.querySelector('.bf-matrix-scroll');
  region.focus();
  region.dispatchEvent(new dom.window.KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
  const marked = [...d.querySelectorAll('#sp-matrix-grid td.marked')];
  assert.equal(marked.length, 1);
  assert.match(marked[0].dataset.key, /^p\|c12-21\|d/);
  assert.equal(marked[0].parentElement.hidden, false);
  region.focus();
  region.dispatchEvent(new dom.window.KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true, cancelable: true}));
  assert.match(d.activeElement.dataset.key, /^p\|c12-21\|d/);
});

test('Đầu đuôi: số lượt đúng, cùng giá trị cùng màu và nhiều lượt tối hơn ở cả hai theme', t => {
  const dom = setup(t, 'dau-duoi-loto'), d = dom.window.document;
  dom.window.__D_DRAWS__.push({d:'2026-09-04',s:'00010',n:Array.from({length:27},(_,i)=>'1'+i%10)});
  change(dom, 'sp-to', '2026-09-04');
  const expected = { 'sp-head': [34,39,1,3,2,29,0,0,0,0], 'sp-tail': [37,14,5,5,6,32,3,2,2,2] };
  const brightness = rgb => rgb.match(/\d+/g).map(Number).reduce((s, v, i) => s + v * [.2126,.7152,.0722][i], 0);
  const colors = new Map();
  for (const [id, counts] of Object.entries(expected)) {
    for (const [index, row] of [...d.querySelectorAll(`#${id} tbody tr`)].entries()) {
      assert.equal(Number(row.cells[1].textContent), counts[index]);
      for (const cell of [row.cells[0], row.cells[1]]) {
        assert.equal(Number(cell.dataset.appHitCount), counts[index]);
        assert.ok(cell.hasAttribute('data-app-hit-count'));
        if (!counts[index]) continue;
        const pair = ['light', 'dark'].map(theme => cell.style.getPropertyValue(`--app-hit-bg-${theme}`));
        assert.ok(pair.every(Boolean));
        if (colors.has(counts[index])) assert.deepEqual(pair, colors.get(counts[index]));
        colors.set(counts[index], pair);
      }
    }
  }
  const ordered = [...colors.entries()].sort((a,b) => a[0] - b[0]);
  for (let i = 1; i < ordered.length; i++) for (const theme of [0,1]) {
    assert.ok(brightness(ordered[i][1][theme]) < brightness(ordered[i-1][1][theme]));
  }
});

test('Đầu đuôi: màu từng kỳ theo đúng nháy, cùng thang và cập nhật khi lọc ngày', t => {
  const dom = setup(t, 'dau-duoi-loto'), d = dom.window.document;
  for (const [id, digitAt] of [['sp-day-head',0], ['sp-day-tail',1]]) {
    for (const [index, row] of [...d.querySelectorAll(`#${id} tbody tr`)].entries()) {
      const draw = draws.at(-index - 1);
      for (let digit = 0; digit < 10; digit++) {
        const count = draw.n.filter(n => Number(n[digitAt]) === digit).length;
        const cell = row.cells[digit + 1];
        assert.equal(cell.dataset.appHitCount, String(count));
        assert.equal(parseInt(cell.textContent, 10), count);
      }
    }
  }
  const first = d.querySelector('#sp-day-head tbody tr').cells[2];
  first.click();
  const key = first.dataset.key;
  change(dom, 'sp-from', '2026-09-02');
  const marked = d.querySelector(`#sp-day-head [data-key="${key}"]`);
  assert.ok(marked.classList.contains('marked'));
  assert.equal(marked.dataset.appHitCount, '10');
  assert.equal(d.querySelector('#sp-head tbody tr').cells[1].dataset.appHitCount, '10');
  assert.equal(d.querySelectorAll('#sp-day-head tbody tr').length, 2);
  const swatches = d.querySelectorAll('#app-head-tail-day-legend [data-app-hit-count]');
  assert.equal(swatches[swatches.length-1].dataset.appHitCount, '22');
});

test('Đầu đuôi: dải rỗng không giữ lại thang màu hay dữ liệu cũ', t => {
  const dom = setup(t, 'dau-duoi-loto'), d = dom.window.document;
  change(dom, 'sp-from', '2026-09-04');
  assert.equal(d.querySelectorAll('#sp-day-head .app-head-tail-heat, #sp-day-tail .app-head-tail-heat').length, 0);
  assert.match(d.getElementById('app-head-tail-day-legend').textContent, /Không có kỳ/);
  for (const cell of d.querySelectorAll('#sp-head [data-app-hit-count],#sp-tail [data-app-hit-count]')) {
    assert.equal(cell.dataset.appHitCount, '0');
    assert.equal(cell.style.getPropertyValue('--app-hit-bg-light'), '');
  }
});
