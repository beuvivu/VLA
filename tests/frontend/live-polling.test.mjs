import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM, VirtualConsole } from 'jsdom';

// Vòng thăm dò của docs/live.html (trang viết tay duy nhất), chạy đúng mã của trang.
// Trang xuất bản không được mang chú thích, nên lý do nằm ở đây:
// - chỉ một lượt tải tại một thời điểm: đổi tab gọi load() khi lượt trước còn chờ thì hai
//   phản hồi về lệch thứ tự, và bản cũ ("đang cập nhật") có thể đè bản mới ("đã xác minh");
// - fetch có hạn: trình duyệt không tự đặt hạn, một kết nối treo làm đứng cả vòng thăm dò
//   vài phút, đúng lúc đang quay số.
const html = readFileSync(new URL('../../docs/live.html', import.meta.url), 'utf8');

function setup(t, fetcher, extra = {}) {
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,                     // document.hidden = false, như tab đang mở
    url: 'https://example.test/live.html',
    virtualConsole: new VirtualConsole(),        // các script khác của khung không phải đối tượng kiểm
    beforeParse(window) {
      window.fetch = fetcher;
      window.LIVE_RAW_URL = 'https://example.test/live.json';
      Object.assign(window, extra);
    },
  });
  t.after(() => dom.window.close());
  return dom.window;
}

const snapshot = (status, drawDate = '2026-10-08', prizes = {}) => ({
  ok: true, json: async () => ({ status, draw_date: drawDate, prizes, progress_percent: 50 }),
});
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

// Điều khiển thời gian của trang, giữ nguyên mã dựng ô và vòng tải thật.
function clock() {
  let now = 0, nextId = 0;
  const timers = new Map();
  return {
    setTimeout(callback, delay = 0) {
      const id = ++nextId;
      timers.set(id, { callback, at: now + delay });
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
    advance(ms) {
      const until = now + ms;
      while (true) {
        const next = [...timers].filter(([, timer]) => timer.at <= until)
          .sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        timers.delete(next[0]);
        now = next[1].at;
        next[1].callback();
      }
      now = until;
    },
  };
}

const values = (window) => [...window.document.querySelectorAll('.slot:not(.is-empty)')]
  .map((node) => node.textContent);

for (const [label, date, nextPrizes, expected] of [
  ['đổi sang kỳ mới', '2026-10-09', {}, []],
  ['thu hồi số trong cùng kỳ', '2026-10-08', { special: ['11111'] }, ['11111']],
  ['sửa số đang chờ hiện trong cùng kỳ', '2026-10-08',
    { special: ['11111'], prize1: ['99999'], prize2: ['88888'] }, ['11111', '99999', '88888']],
]) {
  test(`Snapshot ${label} không bị hàng đợi cũ ghi đè`, async (t) => {
    const timers = clock();
    let response = snapshot('partial', '2026-10-08', {
      special: ['11111'], prize1: ['22222'], prize2: ['33333', '44444'],
    });
    const window = setup(t, async () => response, timers);
    await tick();
    assert.deepEqual(values(window), ['11111'], 'snapshot đầu vẫn hiện lần lượt');
    response = snapshot('waiting', date, nextPrizes);
    window.document.dispatchEvent(new window.Event('visibilitychange'));
    await tick();
    timers.advance(5000);
    assert.deepEqual(values(window), expected, 'chỉ còn số thuộc snapshot mới nhất');
    assert.match(window.document.getElementById('status').textContent, new RegExp(date));
  });
}

test('Snapshot mới vẫn hiện từng số một khi lượt cũ đang có hẹn giờ', async (t) => {
  const timers = clock();
  let response = snapshot('partial', '2026-10-08', {
    special: ['11111'], prize1: ['22222'], prize2: ['33333', '44444'],
  });
  const window = setup(t, async () => response, timers);
  await tick();
  response = snapshot('partial', '2026-10-08', {
    special: ['11111'], prize1: ['99999'], prize2: ['88888', '77777'],
  });
  window.document.dispatchEvent(new window.Event('visibilitychange'));
  await tick();
  assert.deepEqual(values(window), ['11111', '99999']);
  timers.advance(170);
  assert.deepEqual(values(window), ['11111', '99999', '88888']);
  timers.advance(170);
  assert.deepEqual(values(window), ['11111', '99999', '88888', '77777']);
});

test('Đổi tab khi một lượt đang chờ không mở lượt thứ hai chạy song song', async (t) => {
  const pending = [];
  const window = setup(t, () => new Promise((resolve) => pending.push(resolve)));
  await tick();
  assert.equal(pending.length, 1);
  window.document.dispatchEvent(new window.Event('visibilitychange'));
  window.document.dispatchEvent(new window.Event('visibilitychange'));
  await tick();
  assert.equal(pending.length, 1, 'lượt cũ còn đang chờ thì không được gọi thêm');
  pending[0](snapshot('complete_verified'));
  await tick(); await tick();
  assert.match(window.document.getElementById('status').textContent, /ĐÃ XÁC MINH/);
});

test('Mỗi lượt gọi mang tín hiệu huỷ để kết nối treo không làm đứng vòng thăm dò', async (t) => {
  const seen = [];
  const window = setup(t, (url, init) => {
    seen.push(init && init.signal);
    return new Promise((resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new Error('aborted')));
    });
  }, { LIVE_FETCH_TIMEOUT_MS: 20 });
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.ok(seen[0], 'fetch phải nhận signal');
  assert.equal(seen[0].aborted, true, 'kết nối treo phải bị huỷ sau thời hạn');
  assert.match(window.document.getElementById('status').textContent, /Chưa lấy được/);
});
