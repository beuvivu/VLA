import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import { JSDOM } from 'jsdom';
const root = new URL('../../', import.meta.url);
test('Định danh cặp chỉ nhận số thuần, từ chối chuỗi chứa thẻ', () => {
  const source = readFileSync(new URL('src/templates/stat_pages.js', root), 'utf8');
  const start = source.indexOf('function asPair(value) {');
  const end = source.indexOf('\nfunction markPair(', start);
  const asPair = runInNewContext(`${source.slice(start, end)}; asPair`);
  for (const [input, expected] of [[34, '34'], ['07', '07'], [' 34 - 66 ', '34-66'], ['00', '00']]) {
    assert.equal(asPair(input), expected);
  }
  for (const input of [null, undefined, 7, '7', '123', '<b>07</b>', '<script>07</script>', '0<b></b>7', '<scr<script>ipt>07']) {
    assert.equal(asPair(input), null, String(input));
  }
});
function setup({ narrow = false, hash = '' } = {}) {
  const dom = new JSDOM(readFileSync(new URL('docs/index.html', root), 'utf8'), {
    url: `https://example.test/index.html${hash}`, runScripts: 'outside-only',
  });
  dom.window.matchMedia = () => ({ matches: narrow });
  dom.window.eval(readFileSync(process.env.APP_SHELL_SCRIPT || new URL('src/assets/app-shell.js', root), 'utf8'));
  return dom;
}
function input(dom, value) {
  const search = dom.window.document.getElementById('app-search');
  search.value = value;
  search.dispatchEvent(new dom.window.Event('input'));
}
function visibleLinks(dom) {
  return [...dom.window.document.querySelectorAll('.app-nav-item')]
    .filter(a => !a.hidden && !a.closest('[hidden]'));
}
test('Tìm không dấu trả về chức năng tiếng Việt', () => {
  const dom = setup(); input(dom, 'tan suat');
  assert.equal(visibleLinks(dom).length, 3); dom.window.close();
});
test('Đổi nhóm sau khi tìm kiếm phải khôi phục các mục của nhóm', () => {
  const dom = setup(); input(dom, 'zzzz');
  dom.window.document.querySelector('[data-app-group="2"]').click();
  assert.equal(visibleLinks(dom).length, 5);
  assert.equal(dom.window.document.getElementById('app-search').value, ''); dom.window.close();
});
test('Menu đóng không nhận focus; nội dung bị khóa khi mở menu điện thoại', () => {
  const dom = setup({ narrow: true }), d = dom.window.document;
  assert.equal(d.getElementById('app-panel').inert, true);
  d.getElementById('app-toggle').click();
  assert.equal(d.getElementById('app-panel').inert, false);
  assert.equal(d.getElementById('app-main').inert, true);
  d.getElementById('app-scrim').click();
  assert.equal(d.getElementById('app-main').inert, false);
  assert.equal(d.getElementById('app-toggle').getAttribute('aria-expanded'), 'false'); dom.window.close();
});
test('Escape đóng menu cả trên máy tính', () => {
  const dom = setup(), d = dom.window.document;
  d.getElementById('app-toggle').click();
  d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  assert.equal(d.getElementById('app-toggle').getAttribute('aria-expanded'), 'false'); dom.window.close();
});
test('Mục neo chỉ đánh dấu đúng một liên kết và đường dẫn', () => {
  const dom = setup({ hash: '#backtest' }), d = dom.window.document;
  assert.equal(d.querySelectorAll('.app-nav-item[aria-current="page"]').length, 1);
  assert.equal(d.querySelector('.app-nav-item[aria-current="page"]').getAttribute('href'), 'index.html#backtest');
  assert.equal(d.querySelector('.app-crumb--now').textContent, 'Kiểm định AI/ML'); dom.window.close();
});
test('Đổi màu giữ biểu tượng SVG và ghi nhớ lựa chọn', () => {
  const dom = setup(), d = dom.window.document;
  for (const state of ['light', 'dark', null]) {
    d.getElementById('app-theme').click();
    assert.equal(d.documentElement.getAttribute('data-ui-theme'), state);
    assert.ok(d.querySelector('#app-theme svg'));
  }
  assert.equal(dom.window.localStorage.getItem('app-theme'), 'auto'); dom.window.close();
});
test('Ctrl K mở tìm kiếm và đưa focus vào ô nhập', () => {
  const dom = setup(), d = dom.window.document;
  d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }));
  assert.equal(d.activeElement.id, 'app-search'); dom.window.close();
});


test('Đi tới neo không làm mất kết quả đang tìm ở các nhóm khác', () => {
  const dom = setup(); input(dom, 'tan suat');
  dom.window.history.replaceState(null, '', '#tan-suat-loto');
  dom.window.dispatchEvent(new dom.window.HashChangeEvent('hashchange'));
  assert.equal(visibleLinks(dom).length, 3); dom.window.close();
});

test('Đóng menu bằng lớp phủ trả focus khỏi vùng bị khóa', () => {
  const dom = setup({ narrow: true }), d = dom.window.document;
  d.getElementById('app-toggle').click();
  d.getElementById('app-search').focus();
  d.getElementById('app-scrim').click();
  assert.equal(d.activeElement.id, 'app-toggle');
  dom.window.close();
});
