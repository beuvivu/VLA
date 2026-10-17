import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const script = readFileSync(process.env.APP_EVIDENCE_SCRIPT || new URL('../../src/assets/app-evidence.js', import.meta.url), 'utf8');
function start(t, path) {
  const dom = new JSDOM(`<!doctype html><body><main id="app-main"><section><h2>Kết quả</h2>
    <button data-number="27"><b id="number">27</b></button><output id="calculator">0</output>
    <p><strong id="plain">23,7%</strong></p></section></main></body>`,
  { url: `https://example.test/project/${path}`, runScripts: 'outside-only', pretendToBeVisual: true });
  t.after(() => dom.window.close());
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  let selections = 0;
  dom.window.document.addEventListener('click', event => {
    if (event.target.closest('[data-number]')) {
      selections += 1;
      dom.window.document.getElementById('calculator').textContent = String(selections * 27);
    }
  });
  dom.window.eval(script);
  return dom;
}
function emit(dom, id, type, extra = {}) {
  dom.window.document.getElementById(id).dispatchEvent(new dom.window.MouseEvent(type,
    { button: 0, bubbles: true, cancelable: true, ...extra }));
}
const drawer = dom => dom.window.document.getElementById('app-evidence-drawer');

for (const path of ['', 'index.html', 'landing.html', 'landing_desktop.html']) {
  test(`Trang chủ ${path || '/'}: một click chọn số ngay, double click mở bằng chứng`, t => {
    const dom = start(t, path);
    emit(dom, 'number', 'click', { detail: 1 });
    assert.equal(dom.window.document.getElementById('calculator').textContent, '27');
    assert.equal(drawer(dom), null);
    // Chuỗi sự kiện thật của trình duyệt: click thứ hai rồi mới dblclick.
    emit(dom, 'number', 'click', { detail: 2 });
    emit(dom, 'number', 'dblclick', { detail: 2 });
    assert.equal(dom.window.document.getElementById('calculator').textContent, '54');
    assert.equal(drawer(dom)?.open, true);
    assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '27');
  });
  test(`Trang chủ ${path || '/'}: số tĩnh cũng chỉ mở khi double click`, t => {
    const dom = start(t, path);
    emit(dom, 'plain', 'click');
    assert.equal(drawer(dom), null);
    emit(dom, 'plain', 'dblclick', { detail: 2 });
    assert.equal(drawer(dom)?.open, true);
    assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '23,7%');
  });
}

test('Trang thống kê giữ hành vi click và Alt + click hiện có', t => {
  const dom = start(t, 'tan-suat-loto.html');
  emit(dom, 'number', 'click', { altKey: true });
  assert.equal(dom.window.document.getElementById('calculator').textContent, '0');
  assert.equal(drawer(dom)?.open, true);
});

test('Trang chủ đã thay Alt + click bằng double click và giữ trình xử lý chọn số', t => {
  const dom = start(t, 'index.html');
  emit(dom, 'number', 'click', { altKey: true });
  assert.equal(drawer(dom), null);
  assert.equal(dom.window.document.getElementById('calculator').textContent, '27');
});

test('Trang chủ giữ Alt + Enter và nhấn giữ cảm ứng', t => {
  const dom = start(t, 'index.html'), d = dom.window.document;
  const button = d.querySelector('button');
  button.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', altKey: true, bubbles: true, cancelable: true }));
  assert.equal(drawer(dom)?.open, true);
  drawer(dom).querySelector('.app-evidence-close').click();
  const touch = new dom.window.Event('pointerdown', { bubbles: true });
  Object.defineProperty(touch, 'pointerType', { value: 'touch' });
  d.getElementById('plain').dispatchEvent(touch);
  emit(dom, 'plain', 'contextmenu');
  assert.equal(drawer(dom)?.open, true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '23,7%');
});
