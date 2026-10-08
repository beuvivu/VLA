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

const snapshot = (status, drawDate = '2026-10-08') => ({
  ok: true, json: async () => ({ status, draw_date: drawDate, prizes: {}, progress_percent: 50 }),
});
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

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
