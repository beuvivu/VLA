import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

const script = readFileSync(process.env.APP_MOTION_SCRIPT || new URL('../../src/assets/app-motion.js', import.meta.url), 'utf8');

function setup(t, { saved, reduced = false, fine = true, hover = true, blocked = false, observe = false } = {}) {
  const dom = new JSDOM(`<!doctype html><body data-app-design="crafto">
    <aside data-app-effects aria-hidden="true"><div class="app-cursor"></div></aside>
    <button id="app-motion-toggle" aria-pressed="false" hidden>Hiệu ứng: Tắt</button>
    <a href="#content"><span id="link-child">Liên kết</span></a>
    <div data-app-parallax></div><main id="content" data-app-reveal>Nội dung thật</main>
  </body>`, { url: 'https://example.test/', runScripts: 'outside-only', pretendToBeVisual: true });
  t.after(() => dom.window.close());
  const w = dom.window, d = w.document, media = new Map(), frames = new Map();
  let frameId = 0, hidden = false, observerCallback;
  Object.defineProperty(d, 'hidden', { get: () => hidden });
  w.matchMedia = query => {
    if (!media.has(query)) {
      const item = new w.EventTarget();
      item.matches = query.includes('reduced-motion') ? reduced :
        query.includes('hover') && query.includes('pointer') ? hover && fine :
        query.includes('hover') ? hover : fine;
      item.media = query;
      media.set(query, item);
    }
    return media.get(query);
  };
  w.requestAnimationFrame = callback => { frames.set(++frameId, callback); return frameId; };
  w.cancelAnimationFrame = id => frames.delete(id);
  if (saved) w.localStorage.setItem('app-motion', saved);
  if (blocked) Object.defineProperty(w, 'localStorage', { get() { throw new Error('Bộ nhớ bị chặn'); } });
  if (observe) w.IntersectionObserver = class {
    constructor(callback) { observerCallback = callback; }
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  const state = {
    w, d, frames, button: d.getElementById('app-motion-toggle'), cursor: d.querySelector('.app-cursor'),
    parallax: d.querySelector('[data-app-parallax]'), reveal: d.querySelector('[data-app-reveal]'),
    init() { w.eval(script); },
    flush() { const pending = [...frames.values()]; frames.clear(); pending.forEach(callback => callback(0)); },
    move(x = 100, y = 80, target = d.body, pointerType = 'mouse') {
      const event = new w.MouseEvent('pointermove', { bubbles: true, clientX: x, clientY: y });
      Object.defineProperty(event, 'pointerType', { value: pointerType });
      target.dispatchEvent(event);
    },
    media(kind, value) {
      for (const [query, item] of media) if (query.includes(kind)) {
        item.matches = value;
        item.dispatchEvent(new w.Event('change'));
      }
    },
    hidden(value) { hidden = value; d.dispatchEvent(new w.Event('visibilitychange')); },
    intersect(value) { observerCallback([{ target: state.reveal, isIntersecting: value }]); },
  };
  state.init();
  return state;
}

test('Bộ nhớ bị chặn vẫn khởi tạo và cho phép tắt bật hiệu ứng', t => {
  const s = setup(t, { blocked: true });
  assert.equal(s.d.body.dataset.appMotion, 'on');
  assert.equal(s.button.hidden, false);
  s.button.click();
  assert.equal(s.d.body.dataset.appMotion, 'off');
  assert.equal(s.button.getAttribute('aria-pressed'), 'false');
  s.button.click();
  assert.equal(s.d.body.dataset.appMotion, 'on');
});

test('Khôi phục lựa chọn tắt và ghi nhớ lựa chọn mới', t => {
  const s = setup(t, { saved: 'off' });
  assert.equal(s.d.body.dataset.appMotion, 'off');
  assert.equal(s.button.textContent, 'Hiệu ứng: Tắt');
  s.button.click();
  assert.equal(s.w.localStorage.getItem('app-motion'), 'on');
  assert.equal(s.button.getAttribute('aria-pressed'), 'true');
  assert.equal(s.button.textContent, 'Hiệu ứng: Bật');
  s.button.click();
  assert.equal(s.w.localStorage.getItem('app-motion'), 'off');
});

test('Giảm chuyển động của hệ điều hành luôn thắng lựa chọn đã lưu và cập nhật trực tiếp', t => {
  const s = setup(t, { saved: 'on', reduced: true });
  assert.equal(s.d.body.dataset.appMotion, 'off');
  assert.equal(s.button.disabled, true);
  assert.equal(s.button.getAttribute('aria-pressed'), 'false');
  assert.equal(s.button.textContent, 'Giảm chuyển động');
  assert.match(s.button.title, /hệ điều hành/);
  s.button.click();
  assert.equal(s.w.localStorage.getItem('app-motion'), 'on');
  s.media('reduced-motion', false);
  assert.equal(s.d.body.dataset.appMotion, 'on');
  assert.equal(s.button.disabled, false);
  s.move(); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), true);
  s.media('reduced-motion', true);
  assert.equal(s.d.body.dataset.appMotion, 'off');
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.media('reduced-motion', false);
  s.button.click();
  s.media('reduced-motion', true);
  s.media('reduced-motion', false);
  assert.equal(s.d.body.dataset.appMotion, 'off');
});

test('Con trỏ chỉ hiện khi thiết bị có hover và con trỏ chính xác, bỏ qua chạm', t => {
  for (const options of [{ fine: false }, { hover: false }]) {
    const s = setup(t, options);
    s.move(); s.flush();
    assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
    assert.equal(s.parallax.style.getPropertyValue('--app-parallax-x'), '0px');
  }
  const s = setup(t);
  s.move(10, 20, s.d.body, 'touch'); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.move(); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), true);
});

test('Thay đổi khả năng con trỏ hủy tác vụ cũ và chỉ hiện lại khi di chuyển mới', t => {
  const s = setup(t);
  s.move(); s.flush();
  s.move(500, 400);
  s.media('pointer', false);
  assert.equal(s.frames.size, 0);
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.media('pointer', true);
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.move(); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), true);
});

test('Gộp nhiều lần di chuột vào một khung hình và giới hạn parallax trên lớp trang trí', t => {
  const s = setup(t);
  const content = s.reveal.textContent;
  s.move(10, 20);
  s.move(s.w.innerWidth, s.w.innerHeight, s.d.getElementById('link-child'));
  assert.equal(s.frames.size, 1);
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.flush();
  assert.equal(s.frames.size, 0);
  assert.equal(s.cursor.style.getPropertyValue('--app-pointer-x'), `${s.w.innerWidth}px`);
  assert.equal(s.cursor.style.getPropertyValue('--app-pointer-y'), `${s.w.innerHeight}px`);
  assert.equal(s.cursor.classList.contains('app-cursor--active'), true);
  assert.equal(s.parallax.style.getPropertyValue('--app-parallax-x'), '6px');
  assert.equal(s.parallax.style.getPropertyValue('--app-parallax-y'), '6px');
  assert.equal(s.reveal.textContent, content);
  s.move(0, 0); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--active'), false);
  assert.equal(s.parallax.style.getPropertyValue('--app-parallax-x'), '-6px');
});

test('Tắt hiệu ứng hủy khung hình chờ và xóa vị trí cũ trước khi bật lại', t => {
  const s = setup(t);
  s.move(200, 300, s.button); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--active'), true);
  s.move(400, 500);
  s.button.click();
  assert.equal(s.frames.size, 0);
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  assert.equal(s.cursor.classList.contains('app-cursor--active'), false);
  assert.equal(s.parallax.style.getPropertyValue('--app-parallax-x'), '0px');
  assert.equal(s.cursor.style.getPropertyValue('--app-pointer-x'), '');
  s.button.click(); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.move(); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), true);
});

test('Tab ẩn dừng chuyển động và trở lại không khôi phục vị trí chuột cũ', t => {
  const s = setup(t);
  s.move(); s.flush(); s.move(300, 200);
  s.hidden(true);
  assert.equal(s.d.body.dataset.appHidden, 'true');
  assert.equal(s.frames.size, 0);
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.move(); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.hidden(false);
  assert.notEqual(s.d.body.dataset.appHidden, 'true');
  assert.equal(s.d.body.dataset.appMotion, 'on');
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
  s.move(); s.flush();
  assert.equal(s.cursor.classList.contains('app-cursor--visible'), true);
});

test('Rời trang và mất focus đều hủy con trỏ đang hiện hoặc đang chờ', t => {
  const s = setup(t);
  for (const [target, name] of [[s.d, 'pointerleave'], [s.w, 'blur']]) {
    s.move(); s.flush(); s.move(300, 200);
    target.dispatchEvent(new s.w.Event(name));
    assert.equal(s.frames.size, 0);
    assert.equal(s.cursor.classList.contains('app-cursor--visible'), false);
    assert.equal(s.parallax.style.getPropertyValue('--app-parallax-y'), '0px');
  }
});

test('Khởi tạo nhiều lần không gắn lặp hành vi nút', t => {
  const s = setup(t);
  s.init(); s.init();
  s.move();
  assert.equal(s.frames.size, 1);
  s.button.click();
  assert.equal(s.frames.size, 0);
  assert.equal(s.d.body.dataset.appMotion, 'off');
  assert.equal(s.w.localStorage.getItem('app-motion'), 'off');
});

test('Nội dung xuất hiện khi cuộn vào màn hình và luôn hiện khi không có bộ quan sát', t => {
  const s = setup(t, { observe: true });
  assert.equal(s.reveal.classList.contains('app-is-revealed'), false);
  s.intersect(false);
  assert.equal(s.reveal.classList.contains('app-is-revealed'), false);
  s.intersect(true);
  assert.equal(s.reveal.classList.contains('app-is-revealed'), true);
  const fallback = setup(t);
  assert.equal(fallback.reveal.classList.contains('app-is-revealed'), true);
  const disabled = setup(t, { observe: true, saved: 'off' });
  assert.equal(disabled.reveal.classList.contains('app-is-revealed'), true);
});
