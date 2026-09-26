import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

const script = readFileSync(process.env.APP_THEME_SCRIPT || new URL('../../src/assets/app-theme.js', import.meta.url), 'utf8');
function setup({ saved = null, dark = false, blocked = false, mediaMissing = false, mediaThrows = false, listenerThrows = false } = {}) {
  const dom = new JSDOM('<!doctype html><html><head></head><body><button id="app-theme"><span class="app-theme-ic"><svg></svg></span></button></body></html>', {
    url: 'https://example.test/', runScripts: 'outside-only',
  });
  const win = dom.window;
  if (saved !== null) win.localStorage.setItem('app-theme', saved);
  if (blocked) Object.defineProperty(win, 'localStorage', { get() { throw new Error('blocked'); } });
  const listeners = [];
  const media = { matches: dark, addEventListener: (_type, cb) => listeners.push(cb) };
  if (listenerThrows) media.addEventListener = () => { throw new Error('listener unavailable'); };
  if (!mediaMissing) win.matchMedia = () => media;
  if (mediaThrows) win.matchMedia = () => { throw new Error('media unavailable'); };
  win.eval(script);
  win.document.dispatchEvent(new win.Event('DOMContentLoaded'));
  return {
    dom, win, root: win.document.documentElement, button: win.document.getElementById('app-theme'),
    os(value) { media.matches = value; listeners.forEach(cb => cb({ matches: value })); },
    storage(value, key = 'app-theme') { win.dispatchEvent(new win.StorageEvent('storage', { key, newValue: value })); },
  };
}

test('Theme được áp dụng ngay trước DOMContentLoaded và đồng bộ .dark', () => {
  const dom = new JSDOM('<html><head></head></html>', { url: 'https://example.test', runScripts: 'outside-only' });
  dom.window.localStorage.setItem('app-theme', 'dark');
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {} });
  dom.window.eval(script);
  assert.equal(dom.window.document.documentElement.classList.contains('dark'), true);
  assert.equal(dom.window.document.documentElement.getAttribute('data-ui-theme'), 'dark');
  dom.window.close();
});

test('Mặc định theo OS, đổi OS cập nhật theme và trạng thái nút', () => {
  const s = setup({ dark: true });
  assert.equal(s.root.classList.contains('dark'), true);
  assert.equal(s.root.hasAttribute('data-ui-theme'), false);
  assert.equal(s.button.getAttribute('aria-pressed'), 'true');
  s.os(false);
  assert.equal(s.root.classList.contains('dark'), false);
  assert.equal(s.button.getAttribute('aria-pressed'), 'false');
  s.dom.window.close();
});

test('Chọn sáng thắng OS tối; click đảo màu thực tế và lưu qua reload', () => {
  const s = setup({ saved: 'light', dark: true });
  assert.equal(s.root.classList.contains('dark'), false);
  s.os(true);
  assert.equal(s.root.classList.contains('dark'), false);
  s.button.click();
  assert.equal(s.root.classList.contains('dark'), true);
  assert.equal(s.win.localStorage.getItem('app-theme'), 'dark');
  assert.match(s.button.getAttribute('aria-label'), /sáng/);
  assert.ok(s.button.querySelector('svg'));
  const restored = setup({ saved: s.win.localStorage.getItem('app-theme') });
  assert.equal(restored.root.classList.contains('dark'), true);
  s.button.click();
  assert.equal(s.root.classList.contains('dark'), false);
  s.dom.window.close(); restored.dom.window.close();
});

test('Click đầu tiên đổi được màu khi OS sáng hoặc tối', () => {
  for (const dark of [false, true]) {
    const s = setup({ dark });
    s.button.click();
    assert.equal(s.root.classList.contains('dark'), !dark);
    s.dom.window.close();
  }
});

test('Đồng bộ tab khác và reset storage quay lại theo OS', () => {
  const s = setup({ saved: 'dark' });
  s.storage('light'); assert.equal(s.root.classList.contains('dark'), false);
  s.storage('dark', 'unrelated'); assert.equal(s.root.classList.contains('dark'), false);
  s.storage('dark'); assert.equal(s.root.classList.contains('dark'), true);
  s.storage(null); assert.equal(s.root.hasAttribute('data-ui-theme'), false);
  assert.equal(s.root.classList.contains('dark'), false);
  s.os(true); assert.equal(s.root.classList.contains('dark'), true);
  s.storage(null, null); assert.equal(s.root.hasAttribute('data-ui-theme'), false);
  s.dom.window.close();
});

test('Storage hỏng, dữ liệu lạ hoặc matchMedia thiếu vẫn chuyển màu được', () => {
  for (const options of [{ blocked: true }, { saved: 'corrupt' }, { mediaMissing: true }]) {
    const s = setup(options);
    assert.equal(s.root.classList.contains('dark'), false);
    s.button.click();
    assert.equal(s.root.classList.contains('dark'), true);
    s.dom.window.close();
  }
});

test('Nạp runtime lặp không nhân handler và không xóa class gốc', () => {
  const s = setup();
  s.root.classList.add('existing');
  s.win.eval(script);
  s.win.document.dispatchEvent(new s.win.Event('DOMContentLoaded'));
  s.button.click();
  assert.equal(s.root.classList.contains('dark'), true);
  assert.equal(s.root.classList.contains('existing'), true);
  s.dom.window.close();
});

test('matchMedia ném lỗi vẫn khôi phục lựa chọn và đổi màu được', () => {
  const s = setup({ saved: 'dark', mediaThrows: true });
  assert.equal(s.root.classList.contains('dark'), true);
  s.button.click();
  assert.equal(s.root.classList.contains('dark'), false);
  s.dom.window.close();
});

test('Không đăng ký được thay đổi OS vẫn dùng được nút theme', () => {
  const s = setup({ dark: true, listenerThrows: true });
  assert.equal(s.root.classList.contains('dark'), true);
  s.button.click();
  assert.equal(s.root.classList.contains('dark'), false);
  s.storage('dark');
  assert.equal(s.root.classList.contains('dark'), true);
  s.dom.window.close();
});

test('Runtime không ghim color-scheme nội tuyến làm vô hiệu màu bản in', () => {
  const s = setup({ saved: 'dark' });
  assert.equal(s.root.style.colorScheme, '');
  s.dom.window.close();
});

test('API hệ thống bị chặn: màu CSS, nhãn nút và lần bấm đầu vẫn đồng bộ', () => {
  for (const options of [{ mediaMissing: true }, { mediaThrows: true }]) {
    const s = setup(options);
    // Nhánh CSS khi OS tối vẫn hoạt động dù JavaScript không đọc được OS.
    const style = s.win.document.createElement('style');
    style.textContent = ':root{background:rgb(255,255,255)}' +
      ':root.dark,:root[data-ui-theme="dark"],:root:not([data-ui-theme="light"]){background:rgb(17,17,17)}';
    s.win.document.head.append(style);
    const renderedDark = () => s.win.getComputedStyle(s.root).backgroundColor === 'rgb(17, 17, 17)';
    const before = renderedDark();
    assert.equal(s.root.classList.contains('dark'), before);
    assert.equal(s.button.getAttribute('aria-pressed'), String(before));
    assert.equal(s.win.localStorage.getItem('app-theme'), null);
    s.button.click();
    assert.equal(renderedDark(), !before);
    assert.equal(s.root.classList.contains('dark'), !before);
    assert.equal(s.button.getAttribute('aria-pressed'), String(!before));
    s.storage(null);
    assert.equal(s.root.classList.contains('dark'), renderedDark());
    s.dom.window.close();
  }
});
