import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import { setup, type } from './shell-fixture.mjs';
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
function input(dom, value) {
  type(dom, 'app-sidebar-filter', value);
}
function visibleLinks(dom) {
  return [...dom.window.document.querySelectorAll('.app-nav-item')]
    .filter(a => !a.hidden && !a.closest('[hidden]'));
}
test('Lọc sidebar không dấu chỉ trả về mục của nhóm đã chọn', () => {
  const dom = setup();
  dom.window.document.getElementById('app-tab-1').click();
  input(dom, 'tan suat');
  assert.deepEqual(visibleLinks(dom).map(a => a.getAttribute('href')), ['index.html#tan-suat-loto']);
  dom.window.close();
});
test('Đổi nhóm sau khi tìm kiếm phải khôi phục các mục của nhóm', () => {
  const dom = setup(); input(dom, 'zzzz');
  dom.window.document.querySelector('[data-app-group="2"]').click();
  assert.equal(visibleLinks(dom).length, 5);
  assert.equal(dom.window.document.getElementById('app-sidebar-filter').value, ''); dom.window.close();
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
for (const target of ['app-sidebar-filter', 'app-tab-1']) {
  test(`Đóng bằng nền phủ trả focus khỏi ${target} trước khi khóa menu`, () => {
    const dom = setup({ narrow: true }), d = dom.window.document;
    d.getElementById('app-toggle').click();
    d.getElementById(target).focus();
    assert.equal(d.activeElement.id, target);
    const focusStates = [];
    d.getElementById('app-toggle').addEventListener('focus', () => {
      focusStates.push([
        d.getElementById('app-panel').inert,
        d.getElementById('app-panel').getAttribute('aria-hidden'),
        d.getElementById('app-rail').inert,
      ]);
    });
    d.getElementById('app-scrim').click();
    assert.equal(d.activeElement.id, 'app-toggle');
    assert.deepEqual(focusStates, [[false, 'false', false]]);
    assert.equal(d.getElementById('app-panel').inert, true);
    assert.equal(d.getElementById('app-main').inert, false);
    dom.window.close();
  });
}
test('Bấm nền phủ trả focus ngay cả khi thao tác chuột đã làm bộ lọc mất focus', () => {
  const dom = setup({ narrow: true }), d = dom.window.document;
  d.getElementById('app-toggle').click();
  const sidebar = d.getElementById('app-sidebar-filter');
  sidebar.focus();
  // Chromium bỏ focus khỏi ô nhập khi nhấn chuột xuống nền phủ trước sự kiện click.
  sidebar.blur();
  assert.equal(d.activeElement, d.body);
  const focusStates = [];
  d.getElementById('app-toggle').addEventListener('focus', () => {
    focusStates.push([d.getElementById('app-panel').inert, d.getElementById('app-scrim').hidden]);
  });
  d.getElementById('app-scrim').click();
  assert.equal(d.activeElement.id, 'app-toggle');
  assert.deepEqual(focusStates, [[false, false]]);
  assert.equal(d.getElementById('app-panel').inert, true);
  assert.equal(d.getElementById('app-scrim').hidden, true);
  assert.equal(d.getElementById('app-main').inert, false);
  dom.window.close();
});
test('Thu cửa sổ trả focus khỏi dải biểu tượng bị khóa', () => {
  const dom = setup(), d = dom.window.document;
  d.getElementById('app-tab-1').focus();
  const railStates = [];
  d.getElementById('app-toggle').addEventListener('focus', () => {
    railStates.push(d.getElementById('app-rail').inert);
  });
  dom.window.matchMedia = () => ({ matches: true });
  dom.window.dispatchEvent(new dom.window.Event('resize'));
  assert.equal(d.getElementById('app-rail').inert, true);
  assert.equal(d.activeElement.id, 'app-toggle');
  assert.deepEqual(railStates, [false]);
  dom.window.close();
});
test('Đóng panel máy tính giữ focus trên dải biểu tượng còn dùng được', () => {
  const dom = setup(), d = dom.window.document;
  d.getElementById('app-toggle').click();
  d.getElementById('app-tab-1').focus();
  d.getElementById('app-toggle').click();
  assert.equal(d.getElementById('app-panel').inert, true);
  assert.equal(d.getElementById('app-rail').inert, false);
  assert.equal(d.activeElement.id, 'app-tab-1');
  dom.window.close();
});
test('Thu cửa sổ giữ focus ở nội dung không bị khóa', () => {
  const dom = setup(), d = dom.window.document;
  const target = d.getElementById('backtest');
  target.tabIndex = -1;
  target.focus();
  dom.window.matchMedia = () => ({ matches: true });
  dom.window.dispatchEvent(new dom.window.Event('resize'));
  assert.equal(d.getElementById('app-main').inert, false);
  assert.equal(d.activeElement, target);
  dom.window.close();
});
test('Mục neo chỉ đánh dấu đúng một liên kết và đường dẫn', () => {
  const dom = setup({ hash: '#backtest' }), d = dom.window.document;
  assert.equal(d.querySelectorAll('.app-nav-item[aria-current="page"]').length, 1);
  assert.equal(d.querySelector('.app-nav-item[aria-current="page"]').getAttribute('href'), 'index.html#backtest');
  assert.equal(d.querySelector('.app-crumb--now').textContent, 'Kiểm định AI/ML'); dom.window.close();
});
test('Ctrl K mở tìm kiếm và đưa focus vào ô nhập', () => {
  const dom = setup(), d = dom.window.document;
  d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }));
  assert.equal(d.activeElement.id, 'app-global-search-input');
  assert.equal(d.body.classList.contains('app-panel-open'), false); dom.window.close();
});

test('Nút toàn màn hình đồng bộ tooltip với nhãn và trạng thái khi vào rồi thoát', () => {
  const dom = setup(), d = dom.window.document;
  const button = d.getElementById('app-fullscreen');
  for (const [element, label, pressed] of [
    [d.documentElement, 'Thoát toàn màn hình', 'true'],
    [null, 'Toàn màn hình', 'false'],
  ]) {
    d.fullscreenElement = element;
    d.dispatchEvent(new dom.window.Event('fullscreenchange'));
    assert.equal(button.title, label);
    assert.equal(button.getAttribute('aria-label'), label);
    assert.equal(button.getAttribute('aria-pressed'), pressed);
  }
  dom.window.close();
});


test('Đi tới neo thuộc nhóm mới xóa bộ lọc để mục đích luôn hiện', () => {
  const dom = setup(); input(dom, 'zzzz');
  dom.window.history.replaceState(null, '', '#tan-suat-loto');
  dom.window.dispatchEvent(new dom.window.HashChangeEvent('hashchange'));
  assert.equal(dom.window.document.getElementById('app-sidebar-filter').value, '');
  assert.deepEqual(visibleLinks(dom).map(a => a.getAttribute('href')), [
    'statistics.html', 'index.html#tan-suat-loto', 'index.html#gan-nhip', 'index.html#cap-lon',
  ]); dom.window.close();
});

test('Header dropdowns exclude each other, dismiss outside and return focus with Escape', () => {
  const dom = setup(), d = dom.window.document;
  const profile = d.getElementById('app-profile-toggle');
  const notifications = d.getElementById('app-notifications-toggle');
  profile.click();
  assert.equal(d.getElementById('app-profile-menu').hidden, false);
  notifications.click();
  assert.equal(d.getElementById('app-profile-menu').hidden, true);
  assert.equal(profile.getAttribute('aria-expanded'), 'false');
  assert.equal(d.getElementById('app-notifications-menu').hidden, false);
  d.getElementById('app-notifications-menu').querySelector('a').focus();
  d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  assert.equal(d.activeElement, notifications);
  assert.equal(d.getElementById('app-notifications-menu').hidden, true);
  profile.click(); d.body.click();
  assert.equal(d.getElementById('app-profile-menu').hidden, true);
  dom.window.close();
});

test('Rail plus opens global search and exit closes the mobile menu', () => {
  const dom = setup({ narrow: true }), d = dom.window.document;
  d.getElementById('app-toggle').click();
  d.getElementById('app-rail-add').click();
  assert.equal(d.getElementById('app-global-search').open, true);
  d.getElementById('app-global-search-close').click();
  d.getElementById('app-rail-exit').click();
  assert.equal(d.getElementById('app-panel').inert, true);
  assert.equal(d.activeElement.id, 'app-toggle');
  dom.window.close();
});

test('Header same-page destination releases the mobile overlay and hidden dropdown focus', () => {
  const dom = setup({ narrow: true }), d = dom.window.document;
  d.getElementById('app-toggle').click();
  d.getElementById('app-notifications-toggle').click();
  const link = d.querySelector('#app-notifications-menu a[href="index.html#backtest"]');
  link.focus(); link.click();
  dom.window.history.replaceState(null, '', '#backtest');
  dom.window.dispatchEvent(new dom.window.HashChangeEvent('hashchange'));
  assert.equal(d.getElementById('app-main').inert, false);
  assert.equal(d.getElementById('app-panel').inert, true);
  assert.equal(d.getElementById('app-notifications-menu').hidden, true);
  assert.equal(d.activeElement.id, 'app-notifications-toggle');
  dom.window.close();
});

test('Reloading shell runtime does not double-bind header menus', () => {
  const dom = setup(), d = dom.window.document;
  dom.window.eval(readFileSync(new URL('src/assets/app-shell.js', root), 'utf8'));
  d.getElementById('app-profile-toggle').click();
  assert.equal(d.getElementById('app-profile-menu').hidden, false);
  dom.window.close();
});
