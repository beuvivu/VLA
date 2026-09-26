import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fixture, setup, type, key } from './shell-fixture.mjs';

function start(t, options) {
  const dom = setup(options);
  t.after(() => dom.window.close());
  return dom;
}
function results(dom) {
  return [...dom.window.document.querySelectorAll('.app-global-result')].filter(node => !node.hidden);
}
function open(dom) { dom.window.document.getElementById('app-search-open').click(); }

test('Lỗi matchMedia không làm mất điều hướng và tìm kiếm', t => {
  const dom = start(t, { mediaThrows: true });
  const d = dom.window.document;
  d.getElementById('app-toggle').click();
  assert.equal(d.body.classList.contains('app-panel-open'), true);
  key(dom, 'k', { ctrlKey: true });
  assert.equal(d.getElementById('app-global-search').open, true);
  type(dom, 'app-global-search-input', 'tan suat');
  assert.ok(results(dom).length >= 2);
});

test('Global search có đủ đích thật, không trùng href và bọc lại không nhân dialog', t => {
  const dom = start(t), d = dom.window.document;
  const links = [...d.querySelectorAll('#app-global-search a[href]')];
  assert.deepEqual(links.map(node => node.getAttribute('href')).sort(), fixture.targets);
  assert.equal(links.length, new Set(links.map(node => node.getAttribute('href'))).size);
  assert.equal(fixture.twice, fixture.html);
  assert.ok(d.getElementById('app-global-search').compareDocumentPosition(d.getElementById('app-main')) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING);
});

test('Global search phủ mọi trang xuất bản kể cả giao diện máy tính', t => {
  const dom = start(t), d = dom.window.document;
  const pages = [...new Set([...d.querySelectorAll('#app-global-search a[href]')]
    .map(node => node.getAttribute('href').split('#')[0]))].sort();
  assert.ok(fixture.pages.length > 0);
  assert.deepEqual(pages, fixture.pages);
  assert.match(d.querySelector('#app-global-search a[href="landing_desktop.html"]').textContent, /Giao diện máy tính/);
});

test('Hai truy vấn độc lập và mở global không đổi trạng thái sidebar', t => {
  const dom = start(t), d = dom.window.document;
  d.getElementById('app-tab-2').click();
  type(dom, 'app-sidebar-filter', 'dac biet');
  const before = [...d.querySelectorAll('.app-nav-item')].map(node => node.hidden);
  const panelSaved = dom.window.localStorage.getItem('app-panel-open');
  open(dom);
  type(dom, 'app-global-search-input', 'tan suat');
  assert.deepEqual(results(dom).map(node => node.getAttribute('href')), [
    'index.html#tan-suat-loto', 'tan-suat-loto.html', 'tan-suat-cap-loto.html', 'index.html#tan-suat-de',
  ]);
  assert.equal(d.getElementById('app-sidebar-filter').value, 'dac biet');
  assert.deepEqual([...d.querySelectorAll('.app-nav-item')].map(node => node.hidden), before);
  assert.equal(dom.window.localStorage.getItem('app-panel-open'), panelSaved);
  assert.equal(d.body.classList.contains('app-panel-open'), true);
  key(dom, 'Escape');
  assert.equal(d.body.classList.contains('app-panel-open'), true);
});

test('Lọc sidebar không được làm lộ nhóm khác dù không có kết quả', t => {
  const dom = start(t), d = dom.window.document;
  d.getElementById('app-tab-0').click();
  type(dom, 'app-sidebar-filter', 'tan suat');
  assert.equal(d.getElementById('app-sidebar-filter-empty').hidden, false);
  assert.deepEqual([...d.querySelectorAll('.app-panel-group')].filter(node => !node.hidden).map(node => node.id), ['app-panel-0']);
  assert.equal([...d.querySelectorAll('#app-panel-0 .app-nav-item')].filter(node => !node.hidden).length, 0);
});

test('Global search hỗ trợ nhãn nhóm, không dấu và trạng thái rỗng an toàn', t => {
  const dom = start(t), d = dom.window.document;
  open(dom);
  type(dom, 'app-global-search-input', 'LOTO chi tiet');
  assert.equal(results(dom).length, 8);
  type(dom, 'app-global-search-input', '<img src=x onerror=alert(1)>');
  assert.equal(results(dom).length, 0);
  assert.equal(d.getElementById('app-global-search-empty').hidden, false);
  assert.match(d.getElementById('app-global-search-status').textContent, /0/);
  assert.equal(d.querySelector('#app-global-search img'), null);
  assert.equal(d.getElementById('app-global-search-input').hasAttribute('aria-activedescendant'), false);
  type(dom, 'app-global-search-input', '');
  assert.equal(results(dom).length, fixture.targets.length);
});

test('Escape khi đang gõ IME không đóng modal hoặc xóa truy vấn sidebar', t => {
  const dom = start(t), d = dom.window.document;
  d.getElementById('app-tab-0').click();
  type(dom, 'app-sidebar-filter', 'ket qua');
  const sidebar = d.getElementById('app-sidebar-filter'); sidebar.focus();
  key(dom, 'Escape', { isComposing: true });
  assert.equal(sidebar.value, 'ket qua');
  open(dom);
  const event = key(dom, 'Escape', { isComposing: true });
  assert.equal(event.defaultPrevented, false);
  assert.equal(d.getElementById('app-global-search').open, true);
  assert.equal(d.activeElement.id, 'app-global-search-input');
});

test('Mũi tên Home End và Enter chọn rồi mở đúng kết quả thật', t => {
  const dom = start(t), d = dom.window.document;
  open(dom);
  type(dom, 'app-global-search-input', 'tan suat');
  const input = d.getElementById('app-global-search-input'), links = results(dom);
  const selected = () => input.getAttribute('aria-activedescendant');
  assert.equal(selected(), links[0].id);
  key(dom, 'ArrowDown'); assert.equal(selected(), links[1].id);
  key(dom, 'End'); assert.equal(selected(), links[3].id);
  key(dom, 'ArrowUp'); assert.equal(selected(), links[2].id);
  key(dom, 'Home'); assert.equal(selected(), links[0].id);
  let followed = null;
  links[0].addEventListener('click', event => { event.preventDefault(); followed = event.currentTarget.getAttribute('href'); });
  key(dom, 'Enter');
  assert.equal(followed, 'index.html#tan-suat-loto');
  assert.equal(d.getElementById('app-global-search').open, false);
});

test('Escape đóng modal và trả focus về phần tử đã mở, không đóng menu di động', t => {
  const dom = start(t, { narrow: true }), d = dom.window.document;
  d.getElementById('app-toggle').click();
  const filter = d.getElementById('app-sidebar-filter'); filter.focus();
  const event = key(dom, 'k', { metaKey: true });
  assert.equal(event.defaultPrevented, true);
  assert.equal(d.activeElement.id, 'app-global-search-input');
  key(dom, 'Escape');
  assert.equal(d.activeElement, filter);
  assert.equal(d.getElementById('app-global-search').open, false);
  assert.equal(d.body.classList.contains('app-panel-open'), true);
  assert.equal(d.getElementById('app-main').inert, true);
});

test('Tab giữ focus trong dialog và close backdrop cancel đều trả về đúng nút', t => {
  const dom = start(t), d = dom.window.document;
  const trigger = d.getElementById('app-search-open'); trigger.focus(); open(dom);
  const close = d.getElementById('app-global-search-close'), input = d.getElementById('app-global-search-input');
  input.focus(); key(dom, 'Tab'); assert.equal(d.activeElement, close);
  close.focus(); key(dom, 'Tab'); assert.equal(d.activeElement, input);
  input.focus(); key(dom, 'Tab', { shiftKey: true }); assert.equal(d.activeElement, close);
  close.click(); assert.equal(d.activeElement, trigger);
  open(dom);
  d.getElementById('app-global-search').click();
  assert.equal(d.getElementById('app-global-search').open, false);
  assert.equal(d.activeElement, trigger);
  open(dom);
  d.getElementById('app-global-search').dispatchEvent(new dom.window.Event('cancel', { cancelable: true }));
  assert.equal(d.getElementById('app-global-search').open, false);
  assert.equal(d.activeElement, trigger);
});

test('Chọn kết quả trên điện thoại đóng menu để đích điều hướng nhận tương tác', t => {
  const dom = start(t, { narrow: true }), d = dom.window.document;
  d.getElementById('app-tab-1').click();
  d.getElementById('app-sidebar-filter').focus();
  key(dom, 'k', { ctrlKey: true });
  type(dom, 'app-global-search-input', 'tan suat');
  const result = results(dom)[0];
  result.addEventListener('click', event => event.preventDefault());
  key(dom, 'Enter');
  assert.equal(d.body.classList.contains('app-panel-open'), false);
  assert.equal(d.getElementById('app-main').inert, false);
  assert.equal(d.getElementById('app-global-search').open, false);
  assert.equal(d.activeElement.id, 'app-search-open');
});

test('Sự kiện close đến muộn không xóa trạng thái của lần mở modal tiếp theo', t => {
  const dom = start(t), d = dom.window.document;
  const dialog = d.getElementById('app-global-search');
  // Trình duyệt xếp sự kiện close vào hàng đợi sau khi đã đổi thuộc tính open.
  dialog.close = function () { this.open = false; };
  const trigger = d.getElementById('app-search-open'); trigger.focus(); open(dom);
  d.getElementById('app-global-search-close').click();
  assert.equal(d.getElementById('app-global-search-input').getAttribute('aria-expanded'), 'false');
  assert.equal(d.activeElement, trigger);
  open(dom);
  dialog.dispatchEvent(new dom.window.Event('close'));
  assert.equal(dialog.open, true);
  assert.equal(d.getElementById('app-global-search-input').getAttribute('aria-expanded'), 'true');
  assert.equal(d.body.classList.contains('app-global-search-open'), true);
  assert.equal(d.activeElement.id, 'app-global-search-input');
});
