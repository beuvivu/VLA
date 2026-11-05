import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

// Bảng đối chiếu của trang Live (src/web/assets/live-scorecard.js): mỗi danh sách đã đóng băng
// là hai hàng song song, và một mục chỉ "trượt" khi phần kết quả liên quan đã đủ.
const script = readFileSync(new URL('../../src/web/assets/live-scorecard.js', import.meta.url), 'utf8');
const markup = '<section id="live-scorecard" data-board-root="https://example.test/board/" ' +
  'data-closed-days="https://example.test/closed.json" data-record-url="https://example.test/record.json">' +
  '<time id="live-scorecard-date"></time><div id="live-scorecard-summary"></div>' +
  '<table id="live-scorecard-table"><thead><tr><th>Danh sách</th></tr></thead></table></section>';

// Đồng hồ cố định: 19:00 giờ VN ngày 22/10, tức tối của kỳ trong các sổ mẫu (kỳ đã quay hiện mặc định).
const EVENING = '2026-10-22T12:00:00Z';
function setup(t, fetcher, now = EVENING, before = '') {
  const dom = new JSDOM(before + markup, { runScripts: 'outside-only', url: 'https://example.test/live.html' });
  t.after(() => dom.window.close());
  dom.window.fetch = fetcher;
  const fixed = Date.parse(now);
  dom.window.Date.now = () => fixed;
  dom.window.eval(script);
  return { api: dom.window.LiveScorecard, d: dom.window.document, w: dom.window };
}

const loto = (n, prob = null, need = 1) => ({ label: n, rule: { on: 'loto', numbers: [n], need }, prob, base: 0.2377 });
const board = (date = '2026-10-22', extra = {}) => ({
  schema: 1, target_date: date, locks_at: date + 'T18:10+07:00',
  lists: [
    { id: 'top', group: 'Trang chủ', title: 'Top LOTO', page: 'index.html', kind: 'loto',
      items: [loto('12', 0.25), loto('34', 0.24), loto('56', 0.23)] },
    { id: 'de', group: 'Trang chủ', title: 'Top Đặc Biệt', page: 'index.html', kind: 'de',
      items: [{ label: '63', rule: { on: 'special', numbers: ['63'] }, prob: 0.0102, base: 0.01 }] },
    { id: 'rules', group: 'Soi cầu', title: 'Luật', page: 'soi-cau-vi-tri.html', kind: 'mixed', items: [
      { label: '29 · 92', rule: { on: 'loto', numbers: ['29', '92'], need: 2 }, prob: null, base: 0.1 },
      { label: '12 + 34', rule: { on: 'loto', numbers: ['12', '34'], all: true }, prob: null, base: 0.0549 },
      { label: 'chạm 3', rule: { on: 'special_digit', digits: [3] }, prob: null, base: 0.19 },
    ] },
  ],
  vectors: {}, missing: [], ...extra,
});
const ok = (value) => ({ ok: true, status: 200, json: async () => value });
// Đủ 27 giải; `tails` là hai số cuối, Đặc Biệt đứng đầu.
function prizes(tails, upto = 27) {
  const keys = [['special', 1], ['prize1', 1], ['prize2', 2], ['prize3', 6], ['prize4', 4], ['prize5', 6], ['prize6', 3], ['prize7', 4]];
  const out = {}; let i = 0;
  for (const [key, count] of keys) {
    out[key] = [];
    for (let k = 0; k < count; k++, i++) if (i < upto) out[key].push('1' + tails[i]);
  }
  return out;
}
const FULL = ['63', '12', '29', '92', '40', '41', '42', '43', '44', '45', '46', '47', '48', '50', '51', '52',
  '53', '54', '55', '57', '58', '59', '60', '61', '62', '64', '65'];
const states = (d, id, row) => [...d.querySelectorAll(`tbody[data-list-id="${id}"] tr.${row} .live-scorecard-chip`)]
  .map((chip) => chip.dataset.state || chip.querySelector('small').textContent);

test('Mỗi danh sách là hai hàng song song, mỗi nhóm một tbody gắn thẳng vào bảng', async (t) => {
  const urls = [];
  const { api, d } = setup(t, async (url) => { urls.push(url); return ok(board()); });
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  assert.deepEqual(urls, ['https://example.test/board/2026-10-22.json']);
  const table = d.getElementById('live-scorecard-table');
  const groups = [...table.children].filter((n) => n.tagName === 'TBODY');
  assert.equal(groups.length, 3, 'tbody lồng trong tbody làm lệch cột');
  for (const group of groups) {
    assert.deepEqual([...group.rows].map((r) => r.className), ['is-before', 'is-after']);
  }
  assert.equal(d.querySelector('tbody[data-list-id="top"] th').rowSpan, 2);
  assert.deepEqual(states(d, 'top', 'is-before'), ['25,0%', '24,0%', '23,0%']);
  assert.deepEqual(states(d, 'top', 'is-after'), ['wait', 'wait', 'wait']);
  assert.equal(d.querySelector('time').dateTime, '2026-10-22');
  assert.match(d.getElementById('live-scorecard-summary').textContent, /3 danh sách, 7 mục đã đóng băng lúc 18:10/,
    '19:00 đã qua giờ khoá 18:10');
});

test('Đang quay: số đã về chốt ngay, số chưa về là "chờ" chứ không "trượt"', async (t) => {
  const { api, d } = setup(t, async () => ok(board()));
  // Mới về 10 giải, chưa có Đặc Biệt (Đặc Biệt quay sau cùng).
  const partial = prizes(FULL, 11);
  partial.special = [];
  await api.update({ draw_date: '2026-10-22', prizes: partial });
  assert.deepEqual(states(d, 'top', 'is-after'), ['hit', 'wait', 'wait']);
  assert.deepEqual(states(d, 'de', 'is-after'), ['wait'], 'Đặc Biệt chưa về thì chưa chấm');
  // 29 và 92 mỗi số một nháy: cầu lộn cộng gộp hai chiều nên đủ hai nháy.
  assert.deepEqual(states(d, 'rules', 'is-after'), ['hit', 'wait', 'wait']);
  assert.match(d.querySelector('tbody[data-list-id="top"] .is-after .live-scorecard-stat').textContent,
    /Trúng 1\/3 · còn chờ 2/);
});

test('Đủ 27 giải: mục chưa về thành "trượt", Đặc Biệt và chạm chấm theo hai số cuối', async (t) => {
  const { api, d } = setup(t, async () => ok(board()));
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  assert.deepEqual(states(d, 'top', 'is-after'), ['hit', 'miss', 'miss']);
  assert.deepEqual(states(d, 'de', 'is-after'), ['hit']);
  // Xiên 12 + 34: 34 không về nên trượt; chạm 3 khớp hàng đơn vị của 63.
  assert.deepEqual(states(d, 'rules', 'is-after'), ['hit', 'miss', 'hit']);
  const stat = d.querySelector('tbody[data-list-id="top"] .is-after .live-scorecard-stat');
  assert.match(stat.textContent, /Trúng 1\/3 = 33,3% · kỳ vọng 24,0%/);
  assert.equal(stat.dataset.verdict, 'above');
  assert.match(d.getElementById('live-scorecard-summary').textContent, /Kỳ vừa quay \(kỳ 22\/10 · hôm nay\): đã trúng 4\/7 mục/);
});

test('Luật hai nháy cần đủ nháy; một nháy là chờ rồi trượt', async (t) => {
  const { api } = setup(t, async () => ok(board()));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  const rule = { on: 'loto', numbers: ['29', '92'], need: 2 };
  const once = ['63', '12', '29', ...FULL.slice(4), '70'];
  const partial = api.outcome(prizes(once, 5));
  assert.equal(api.judge(rule, partial), 'wait');
  assert.equal(api.judge(rule, api.outcome(prizes(once))), 'miss');
  const tens = api.outcome(prizes(['31', ...FULL.slice(1)]));
  assert.equal(api.judge({ on: 'special_digit', digits: [3] }, tens), 'hit', 'chạm cả hàng chục');
  assert.equal(api.judge({ on: 'special_digit', digits: [7] }, tens), 'miss');
});

test('Sổ của kỳ khác hoặc phản hồi trễ của ngày cũ không được đặt cạnh kết quả', async (t) => {
  const pending = [];
  const { api, d } = setup(t, (url) => url.includes('10-21')
    ? new Promise((resolve) => pending.push(resolve))
    : Promise.resolve(ok(board('2026-10-23'))));
  const old = api.update({ draw_date: '2026-10-21', prizes: {} });
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  assert.match(d.getElementById('live-scorecard-summary').textContent, /không khớp kỳ/);
  pending[0](ok(board('2026-10-21')));
  await old;
  assert.equal(d.querySelectorAll('tbody').length, 0);
  assert.equal(d.querySelector('time').dateTime, '2026-10-22');
});

test('Đổi kỳ trong lúc đang đọc JSON của sổ cũ: sổ cũ không được hiện', async (t) => {
  let release;
  const { api, d } = setup(t, async (url) => url.includes('10-21')
    ? { ok: true, status: 200, json: () => new Promise((resolve) => { release = resolve; }) }
    : { ok: false, status: 404 });
  const old = api.update({ draw_date: '2026-10-21', prizes: {} });
  await new Promise((resolve) => setTimeout(resolve, 0));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  release(board('2026-10-21'));
  await old;
  assert.equal(d.querySelectorAll('tbody').length, 0);
  assert.match(d.getElementById('live-scorecard-summary').textContent, /Chưa có sổ/);
});

test('Chưa có sổ: báo rõ và không gọi lại trong khoảng chờ', async (t) => {
  let calls = 0;
  const { api, d } = setup(t, async () => { calls++; return { ok: false, status: 404 }; });
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  assert.equal(calls, 1);
  assert.match(d.getElementById('live-scorecard-summary').textContent, /Chưa có sổ phỏng đoán/);
  for (const date of ['', '2026-02-30', '../x', undefined]) await api.update({ draw_date: date });
  assert.equal(calls, 1);
  assert.equal(d.querySelector('time').dateTime, '');
});

test('Xác suất toàn bảng 100 số chấm bằng Brier và xác suất của số Đặc Biệt về', async (t) => {
  const flat = Array(100).fill(1 - Math.pow(0.99, 27));
  const de = Array(100).fill(0.0099); de[63] = 0.0199;
  const { api, d } = setup(t, async () => ok(board('2026-10-22', { vectors: { loto: flat, de } })));
  await api.update({ draw_date: '2026-10-22', prizes: prizes(FULL) });
  const text = d.getElementById('live-scorecard-summary').textContent;
  assert.match(text, /kỹ năng \+0,00%/, 'vector hằng số đúng bằng chọn bừa');
  assert.match(text, /cho số 63 là 1,99%/);
});

// ---- Vị trí đường cầu ---------------------------------------------------------------
// 27 giá trị đúng độ rộng giải; `special` là giải Đặc Biệt, `tail7` là hai số cuối giải bảy cuối cùng.
const WIDTHS = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 3, 3, 3, 2, 2, 2, 2];
function values(special, tail7 = '00') {
  return WIDTHS.map((w, i) => (i === 0 ? special : i === 26 ? tail7 : '9'.repeat(w)));
}
// Cầu 0×1 ghép hai chữ số đầu giải Đặc Biệt: 34 (10-19) → 56 (10-20) → 78 (10-21).
// Kỳ 10-20 có giải bảy đuôi 43 (lộn của 34), kỳ 10-21 có đuôi 65 (lộn của 56): cả hai bước trúng.
const DRAWS = {
  '2026-10-19': values('34111'),
  '2026-10-20': values('56111', '43'),
  '2026-10-21': values('78111', '65'),
};
const bridgeBoard = () => board('2026-10-22', {
  schema: 2, draws: DRAWS,
  lists: [
    ...board().lists,
    { id: 'bridge-loto', group: 'Soi cầu', title: 'Cầu LOTO', page: 'soi-cau-loto.html', kind: 'loto',
      bridge: { type: 'rule', mark: 'loto-lon', series: Object.keys(DRAWS) },
      items: [{ ...loto('78'), label: '78 · 87', rule: { on: 'loto', numbers: ['78', '87'], need: 1 },
        bridges: [{ a: 0, b: 1, streak: 2 }, { a: 2, b: 5, streak: 1 }], bridge_total: 2 }] },
    { id: 'path-de-stable', group: 'Soi cầu theo đường', title: 'Đường cầu', page: 'soi-path-de-stable.html',
      kind: 'de', bridge: { type: 'path', mark: 'special', next: '2026-10-22' },
      items: [{ label: '78', rule: { on: 'special', numbers: ['78'] }, prob: 0.011, base: 0.01,
        bridges: [{ a: 0, b: 1, streak: 3, lag: 1, base: '2026-10-21' }], bridge_total: 5 }] },
  ],
});
const chip = (d, id) => d.querySelector(`tbody[data-list-id="${id}"] .is-before .live-scorecard-chip-btn`);

test('Chỉ số trước giờ quay của danh sách cầu mới bấm được; danh sách khác giữ nguyên', async (t) => {
  const { api, d } = setup(t, async () => ok(bridgeBoard()));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  assert.ok(chip(d, 'bridge-loto'), 'mục có vị trí cầu thành nút');
  assert.equal(chip(d, 'top'), null, 'Top LOTO không sinh từ cặp vị trí');
  assert.equal(d.querySelector('.is-after .live-scorecard-chip-btn'), null, 'hàng sau giờ quay không mở cầu');
  assert.equal(chip(d, 'bridge-loto').getAttribute('aria-expanded'), 'false');
  // Sổ cũ (schema 1) không có vị trí: không nút nào.
  const plain = setup(t, async () => ok(board()));
  await plain.api.update({ draw_date: '2026-10-22', prizes: {} });
  assert.equal(plain.d.querySelector('.live-scorecard-chip-btn'), null);
});

test('Bấm số: đường cầu qua từng kỳ, tô hai vị trí và ô về ở kỳ sau', async (t) => {
  const { api, d } = setup(t, async () => ok(bridgeBoard()));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  chip(d, 'bridge-loto').click();
  const group = d.querySelector('tbody[data-list-id="bridge-loto"]');
  assert.deepEqual([...group.rows].map((r) => r.className), ['is-before', 'is-after', 'is-bridge']);
  assert.equal(group.querySelector('.is-bridge td').colSpan, 4);
  assert.equal(chip(d, 'bridge-loto').getAttribute('aria-expanded'), 'true');
  assert.equal(d.activeElement, chip(d, 'bridge-loto'), 'tiêu điểm ở lại trên số vừa bấm');
  const panel = d.getElementById('live-bridge-bridge-loto');
  assert.match(panel.querySelector('h3').textContent, /^78 · 87: 2 cầu báo mục này$/);
  assert.match(panel.querySelector('.live-bridge-where').textContent,
    /Vị trí 0 \(ĐB · chữ số 1\) ghép Vị trí 1 \(ĐB · chữ số 2\)/);
  // Cầu chạy 2 kỳ: vẽ 3 bảng (2 bước), mới nhất ở trên.
  const days = [...panel.querySelectorAll('.live-bridge-day')];
  assert.deepEqual(days.map((day) => day.querySelector('h4').textContent), ['21/10/2026', '20/10/2026', '19/10/2026']);
  assert.match(days[0].querySelector('p').textContent, /Ghép 78 → báo 78 · 87 cho kỳ 22\/10\/2026 · kỳ trước báo 56 · 65: trúng/);
  assert.deepEqual([...days[0].querySelectorAll('.live-bridge-src')].map((s) => s.textContent), ['7', '8']);
  // Chữ số hàng chục lấy ở vị trí a, hàng đơn vị ở vị trí b: đảo hai vị trí là ghép ra số lộn.
  assert.equal(days[0].querySelector('.live-bridge-src--a').textContent, '7');
  assert.equal(days[0].querySelector('.live-bridge-src--b').textContent, '8');
  assert.equal(days[0].querySelector('.live-bridge-src--a').getAttribute('aria-label'), 'Vị trí 0 (ĐB · chữ số 1): 7');
  assert.deepEqual([...days[0].querySelectorAll('.live-bridge-hit')].map((s) => s.textContent).join(''), '65',
    'đuôi 65 của kỳ 21/10 về theo cầu kỳ trước');
  assert.equal(days[2].querySelectorAll('.live-bridge-hit').length, 0, 'kỳ đầu không có kỳ trước để chấm');
  // Trang nguồn mở đúng kỳ biên, đúng số ghép ở kỳ ấy và đúng cầu.
  assert.equal(panel.querySelector('.live-bridge-link').href,
    'https://example.test/soi-cau-loto.html?ngay=2026-10-21&so=78&vt=0x1');
  // Sổ kết quả truyền thống mở cùng kỳ ghép số và tô cùng hai vị trí.
  assert.equal(panel.querySelector('.live-bridge-book').href,
    'https://example.test/so-ket-qua-truyen-thong.html?ngay=2026-10-21&vt=0x1');
});

test('Đổi cầu, trang tự cập nhật và đóng bảng đều giữ đúng trạng thái', async (t) => {
  const { api, d } = setup(t, async () => ok(bridgeBoard()));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  chip(d, 'bridge-loto').click();
  d.querySelector('[data-bridge-pick="1"]').click();
  let panel = d.getElementById('live-bridge-bridge-loto');
  assert.equal(panel.querySelector('[data-bridge-pick="1"]').getAttribute('aria-pressed'), 'true');
  assert.equal(panel.querySelectorAll('.live-bridge-day').length, 2, 'cầu chạy 1 kỳ: hai bảng');
  // Kết quả về giữa chừng: bảng dựng lại nhưng cầu đang xem vẫn mở.
  await api.update({ draw_date: '2026-10-22', prizes: prizes(FULL, 5) });
  panel = d.getElementById('live-bridge-bridge-loto');
  assert.ok(panel, 'cập nhật trực tiếp không đóng bảng cầu');
  assert.equal(panel.querySelector('[data-bridge-pick="1"]').getAttribute('aria-pressed'), 'true');
  panel.querySelector('.live-bridge-close').click();
  assert.equal(d.getElementById('live-bridge-bridge-loto'), null);
  assert.equal(d.activeElement, chip(d, 'bridge-loto'));
});

test('Soi đường: một bảng kỳ gốc với độ trễ, liên kết mở đúng số trên trang', async (t) => {
  const { api, d } = setup(t, async () => ok(bridgeBoard()));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  chip(d, 'path-de-stable').click();
  const panel = d.getElementById('live-bridge-path-de-stable');
  assert.match(panel.querySelector('h3').textContent, /^78: 5 đường cầu báo mục này, hiện 1 cầu dài nhất$/);
  const days = panel.querySelectorAll('.live-bridge-day');
  assert.equal(days.length, 1);
  assert.match(days[0].textContent, /Kỳ gốc · ghép 78 · trễ 1 ngày → báo 78 cho kỳ 22\/10\/2026/);
  assert.equal(panel.querySelector('.live-bridge-link').href,
    'https://example.test/soi-path-de-stable.html?number=78&path=L1-%5B0%2C1%5D');
  // Soi đường: kỳ ghép số là kỳ gốc của đường, không phải kỳ cuối của chuỗi.
  assert.match(panel.querySelector('.live-bridge-book').href, /so-ket-qua-truyen-thong\.html\?ngay=2026-10-21&vt=0x1$/);
});

test('Cầu Đặc Biệt chỉ tô giải Đặc Biệt: số lộn về ở giải bảy không phải "về" theo cầu', async (t) => {
  const special = {
    ...bridgeBoard(),
    lists: [{ id: 'best-db', group: 'Cầu đẹp nhất', title: 'Cầu Đặc Biệt', page: 'soi-cau-vi-tri.html', kind: 'de',
      bridge: { type: 'position', mark: 'special-lon', series: Object.keys(DRAWS),
        query: { limit: 5, exactlimit: 0, lon: 1, nhay: 1, db: 1 } },
      items: [{ label: '78 · 87', rule: { on: 'special', numbers: ['78', '87'] }, prob: null, base: 0.02,
        bridges: [{ a: 0, b: 1, streak: 2 }], bridge_total: 1 }] }],
  };
  const { api, d } = setup(t, async () => ok(special));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  chip(d, 'best-db').click();
  const panel = d.getElementById('live-bridge-best-db');
  const days = [...panel.querySelectorAll('.live-bridge-day')];
  assert.equal(days.length, 3);
  // Đuôi 65 của kỳ 21/10 nằm ở giải bảy: cầu LOTO tô nó, cầu Đặc Biệt thì không.
  assert.equal(days[0].querySelectorAll('.live-bridge-hit').length, 0);
  assert.match(panel.querySelector('.live-bridge-link').href,
    /soi-cau-vi-tri\.html\?vt=0x1&limit=5&exactlimit=0&lon=1&nhay=1&db=1#app-bridge-results$/);
});

test('Sang kỳ khác thì bảng cầu đang mở đóng lại', async (t) => {
  const forDate = (url) => {
    const date = url.match(/(\d{4}-\d\d-\d\d)\.json$/)[1];
    return ok({ ...bridgeBoard(), target_date: date, locks_at: date + 'T18:10+07:00' });
  };
  const { api, d } = setup(t, async (url) => forDate(url));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  chip(d, 'bridge-loto').click();
  assert.ok(d.getElementById('live-bridge-bridge-loto'));
  await api.update({ draw_date: '2026-10-23', prizes: {} });
  assert.equal(d.querySelector('time').dateTime, '2026-10-23');
  assert.ok(chip(d, 'bridge-loto'), 'sổ kỳ mới đã hiện');
  assert.equal(d.getElementById('live-bridge-bridge-loto'), null, 'cầu của kỳ trước không mở sẵn ở kỳ mới');
  assert.equal(chip(d, 'bridge-loto').getAttribute('aria-expanded'), 'false');
});

// ---- Cầu đang chạy cho danh sách không sinh từ cặp vị trí (schema 3) ----------------------
// Cầu 0×1 ghép 78 ở kỳ 21/10 (trang Cầu LOTO); cầu 105×106 ghép 65 từ giải bảy (trang Cầu Đặc Biệt).
const RUNNING = {
  loto: { page: 'soi-cau-loto.html', title: 'Cầu LOTO', count: 3, mark: 'loto-lon', series: Object.keys(DRAWS),
    groups: { '78,87': { total: 1, bridges: [{ a: 0, b: 1, streak: 2 }] } } },
  de: { page: 'soi-cau-dac-biet.html', title: 'Cầu giải Đặc Biệt', count: 2, mark: 'special-touch', series: Object.keys(DRAWS),
    groups: { '56,65': { total: 3, bridges: [{ a: 105, b: 106, streak: 2 }] } } },
};
const runningBoard = (date = '2026-10-22') => board(date, {
  schema: 3, draws: DRAWS, running: RUNNING,
  lists: [
    ...board(date).lists,
    { id: 'cau-keo-loto', group: 'Trang chủ · Live', title: 'Cầu Kèo · Top 10 LOTO', page: 'live.html', kind: 'loto',
      items: [loto('78', 0.24), loto('87', 0.24), loto('99', 0.24)] },
    { id: 'cau-keo-de', group: 'Trang chủ · Live', title: 'Cầu Kèo · Top 10 Đặc Biệt', page: 'live.html', kind: 'de',
      items: [{ label: '65', rule: { on: 'special', numbers: ['65'] }, prob: 0.011, base: 0.01 }] },
  ],
});
// Sổ theo ngày trong URL; lịch nghỉ quay mặc định rỗng (404), hoặc đúng danh sách truyền vào.
const forDate = (make, closedDays = null) => async (url) => {
  if (url.endsWith('/closed.json')) return closedDays ? ok({ ngay_khong_quay: closedDays }) : { ok: false, status: 404 };
  const date = url.match(/(\d{4}-\d\d-\d\d)\.json$/)[1];
  return ok(make(date));
};
const boards = (urls) => urls.filter((u) => u.includes('/board/')).map((u) => u.slice(-15));
const item = (d, id, index) => d.querySelector(`tbody[data-list-id="${id}"] .is-before [data-bridge-item="${index}"]`);

test('Danh sách không sinh từ cặp vị trí: bấm số tra cầu LOTO đang chạy ghép ra số ấy', async (t) => {
  const { api, d } = setup(t, async () => ok(runningBoard()));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  item(d, 'cau-keo-loto', 0).click();
  const panel = d.getElementById('live-bridge-cau-keo-loto');
  assert.equal(panel.querySelector('h3').textContent, '78: 1 cầu đang chạy trên trang Cầu LOTO ghép ra 78 · 87');
  assert.match(panel.querySelector('.live-bridge-note').textContent, /không chọn số theo cầu.*từ 3 kỳ trở lên/);
  const days = [...panel.querySelectorAll('.live-bridge-day')];
  assert.equal(days.length, 3, 'cầu chạy 2 kỳ: ba bảng');
  assert.deepEqual([...days[0].querySelectorAll('.live-bridge-src')].map((s) => s.textContent), ['7', '8']);
  assert.equal([...days[0].querySelectorAll('.live-bridge-hit')].map((s) => s.textContent).join(''), '65');
  assert.equal(panel.querySelector('.live-bridge-link').href,
    'https://example.test/soi-cau-loto.html?ngay=2026-10-21&so=78&vt=0x1');
  // Số lộn tra cùng nhóm; số không có cầu nào vẫn mở được và nói đúng là chưa có.
  item(d, 'cau-keo-loto', 1).click();
  assert.match(d.getElementById('live-bridge-cau-keo-loto').querySelector('h3').textContent, /^87: 1 cầu đang chạy/);
  item(d, 'cau-keo-loto', 2).click();
  const none = d.getElementById('live-bridge-cau-keo-loto');
  assert.equal(none.querySelector('h3').textContent, '99: chưa có cầu nào đang chạy trên trang Cầu LOTO ghép ra 99');
  assert.equal(none.querySelector('.live-bridge-picker'), null);
  assert.match(none.querySelector('.live-bridge-link').href, /soi-cau-loto\.html$/);
  // Luật chạm chữ số không phải một số: không tra được, giữ dạng thường.
  const touch = [...d.querySelectorAll('tbody[data-list-id="rules"] .is-before .live-scorecard-chip')][2];
  assert.equal(touch.querySelector('button'), null);
  assert.ok(item(d, 'rules', 1), 'xiên 2 tra cả hai số');
});

test('Số Đặc Biệt tra trang Cầu Đặc Biệt (chạm), sổ cũ không có bảng thì giữ dạng thường', async (t) => {
  const { api, d } = setup(t, async () => ok(runningBoard()));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  item(d, 'cau-keo-de', 0).click();
  const panel = d.getElementById('live-bridge-cau-keo-de');
  assert.equal(panel.querySelector('h3').textContent,
    '65: 3 cầu đang chạy trên trang Cầu giải Đặc Biệt ghép ra 56 · 65, hiện 1 cầu dài nhất');
  assert.match(panel.querySelector('.live-bridge-day p').textContent, /^Ghép 65 → báo chạm 6, 5 cho kỳ 22\/10\/2026/);
  assert.deepEqual([...panel.querySelectorAll('.live-bridge-day')[0].querySelectorAll('.live-bridge-src')]
    .map((s) => s.getAttribute('aria-label')), ['Vị trí 105 (G7.4 · chữ số 1): 6', 'Vị trí 106 (G7.4 · chữ số 2): 5']);
  const plain = setup(t, async () => ok(bridgeBoard()));
  await plain.api.update({ draw_date: '2026-10-22', prizes: {} });
  assert.equal(item(plain.d, 'top', 0), null, 'sổ schema 2 không có bảng cầu đang chạy');
});

test('Danh sách cầu bị bỏ vị trí (tính lại lệch) không rơi xuống bảng cầu đang chạy', async (t) => {
  const rejected = runningBoard();
  rejected.lists.push(
    { id: 'bridge-loto', group: 'Soi cầu', title: 'Cầu LOTO', page: 'soi-cau-loto.html', kind: 'loto',
      items: [{ ...loto('78'), label: '78 · 87', rule: { on: 'loto', numbers: ['78', '87'], need: 1 } }] },
    { id: 'path-loto-stable', group: 'Soi cầu theo đường', title: 'Đường cầu', page: 'soi-path-loto-stable.html', kind: 'loto',
      items: [loto('78', 0.238)] },
    { id: 'best-db', group: 'Cầu đẹp nhất', title: 'Cầu Đặc Biệt', page: 'soi-cau-vi-tri.html', kind: 'de',
      items: [{ label: '65 · 56', rule: { on: 'special', numbers: ['65', '56'] }, prob: null, base: 0.02 }] });
  const { api, d } = setup(t, async () => ok(rejected));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  for (const id of ['bridge-loto', 'path-loto-stable', 'best-db']) {
    assert.equal(item(d, id, 0), null, id + ' giữ dạng thường');
    assert.ok(d.querySelector(`tbody[data-list-id="${id}"] .is-before .live-scorecard-chip`), id + ' vẫn có trên bảng');
  }
  assert.ok(item(d, 'cau-keo-loto', 0), 'danh sách không vị trí vẫn tra được');
});

// Hàng của một danh sách: lớp, chữ ô "Thời điểm" (lúc · kỳ) và kỳ của hàng.
const rows = (d, id) => [...d.querySelectorAll(`tbody[data-list-id="${id}"] tr:not(.is-bridge)`)].map((r) => [
  r.className, r.querySelector('.live-scorecard-when').firstChild.textContent,
  r.querySelector('.live-scorecard-day').textContent, r.dataset.draw]);
const nextItem = (d, id, index) => d.querySelector(`tbody[data-list-id="${id}"] .is-next [data-bridge-item="${index}"]`);

test('Kỳ đã quay xong: mỗi danh sách ba hàng — trước giờ quay kỳ sắp quay, rồi trước và sau giờ quay kỳ vừa quay', async (t) => {
  const urls = [];
  const { api, d } = setup(t, async (url) => { urls.push(url); return forDate(runningBoard)(url); });
  const done = { draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) };
  await api.update(done);
  assert.deepEqual(boards(urls), ['2026-10-22.json', '2026-10-23.json'], 'sổ của hai kỳ, tải độc lập');
  // 19:00 giờ VN ngày 22/10: kỳ vừa quay là hôm nay, kỳ sắp quay là ngày mai.
  assert.deepEqual(rows(d, 'top'), [
    ['is-next', 'Trước giờ quay', 'kỳ 23/10 · ngày mai', '2026-10-23'],
    ['is-before', 'Trước giờ quay', 'kỳ 22/10 · hôm nay', '2026-10-22'],
    ['is-after', 'Sau giờ quay', 'kỳ 22/10 · hôm nay', '2026-10-22'],
  ]);
  assert.equal(d.querySelector('tbody[data-list-id="top"] th').rowSpan, 3);
  assert.ok(states(d, 'top', 'is-after').every((s) => s !== 'wait'), 'kỳ vừa quay được chấm');
  assert.deepEqual(states(d, 'top', 'is-next'), ['25,0%', '24,0%', '23,0%'], 'kỳ sắp quay in xác suất, không chấm');
  assert.equal(d.querySelector('.live-scorecard-view'), null, 'không còn nút chuyển kỳ');
  assert.equal(d.querySelector('time').dateTime, '2026-10-22', 'đầu bảng là kỳ của bảng kết quả');
  const lines = [...d.getElementById('live-scorecard-summary').children].map((p) => p.textContent);
  assert.match(lines[0], /^Kỳ sắp quay \(kỳ 23\/10 · ngày mai\): 5 danh sách, 11 mục, khoá lúc 18:10 · /,
    'sổ kỳ sắp quay chưa tới giờ khoá: chưa phải «đã đóng băng»');
  assert.match(lines[1], /^Kỳ vừa quay \(kỳ 22\/10 · hôm nay\): đã trúng/);
  // Cùng một số ở hai hàng "Trước giờ quay" là hai nút riêng, mỗi nút mở cầu trong sổ của chính kỳ ấy.
  nextItem(d, 'cau-keo-loto', 0).click();
  assert.equal(nextItem(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'true');
  assert.equal(item(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'false');
  assert.equal(d.activeElement, nextItem(d, 'cau-keo-loto', 0));
  assert.match(d.getElementById('live-bridge-cau-keo-loto').querySelector('h3').textContent, /^78:/);
  item(d, 'cau-keo-loto', 0).click();
  assert.equal(item(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'true');
  assert.equal(nextItem(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'false');
  assert.equal(d.querySelectorAll('.live-bridge').length, 1, 'mỗi lúc một bảng cầu');
  // live.json cập nhật lại cùng kỳ: bảng cầu đang mở được giữ, không tải lại sổ.
  await api.update(done);
  assert.equal(item(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'true');
  assert.deepEqual(boards(urls), ['2026-10-22.json', '2026-10-23.json']);
});

test('Sáng hôm sau (giờ VN): hôm nay là kỳ sắp quay, hôm qua giữ dấu về/trượt; đang quay thì hai hàng của kỳ ấy', async (t) => {
  for (const now of ['2026-10-22T17:30:00Z', '2026-10-23T09:00:00Z']) {
    const morning = setup(t, forDate(runningBoard), now);
    await morning.api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
    assert.deepEqual(rows(morning.d, 'top').map((r) => r[0] + ' ' + r[2]),
      ['is-next kỳ 23/10 · hôm nay', 'is-before kỳ 22/10 · hôm qua', 'is-after kỳ 22/10 · hôm qua'], now);
    assert.ok(states(morning.d, 'top', 'is-after').includes('hit'), 'có số về được tô lúc ' + now);
    assert.equal(morning.d.querySelector('time').dateTime, '2026-10-22', now);
  }
  // 18:20 giờ VN ngày 23/10: kỳ 23/10 đang quay, chưa có kỳ sắp quay.
  const live = setup(t, forDate(runningBoard), '2026-10-23T11:20:00Z');
  await live.api.update({ draw_date: '2026-10-23', status: 'partial', prizes: prizes(FULL, 3) });
  assert.deepEqual(rows(live.d, 'top').map((r) => r[0] + ' ' + r[2]),
    ['is-before kỳ 23/10 · hôm nay', 'is-after kỳ 23/10 · hôm nay']);
  assert.equal(live.d.querySelector('tbody[data-list-id="top"] th').rowSpan, 2);
  assert.match(live.d.getElementById('live-scorecard-summary').textContent, /^Kỳ đang quay \(kỳ 23\/10 · hôm nay\)/);
});

test('Sang phiên mới: sổ của kỳ sắp quay được dùng lại, sổ kỳ cũ bỏ', async (t) => {
  const urls = [];
  const { api, d } = setup(t, async (url) => { urls.push(url); return forDate(runningBoard)(url); }, '2026-10-23T11:20:00Z');
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  await api.update({ draw_date: '2026-10-23', status: 'partial', prizes: prizes(FULL, 3) });
  assert.deepEqual(boards(urls), ['2026-10-22.json', '2026-10-23.json'], 'không tải lại sổ 23/10');
  assert.ok(rows(d, 'top').every((r) => r[3] === '2026-10-23'));
});

test('Một kỳ thiếu danh sách hay chưa có sổ: hàng ấy nói rõ, hai hàng kia vẫn đủ', async (t) => {
  const fetcher = forDate((date) => {
    const made = runningBoard(date);
    if (date === '2026-10-23') made.lists = made.lists.filter((list) => list.id !== 'de');
    return made;
  });
  const { api, d } = setup(t, fetcher);
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  const de = d.querySelector('tbody[data-list-id="de"] .is-next');
  assert.ok(de.classList.contains('is-absent'));
  assert.match(de.textContent, /không có danh sách này/);
  assert.deepEqual(rows(d, 'de').map((r) => r[0]), ['is-next is-absent', 'is-before', 'is-after']);
});

test('Kỳ sắp quay chưa có sổ: hàng của nó là khung chờ, không mượn số của kỳ vừa quay; có sổ thì hiện số', async (t) => {
  let ready = false;
  const urls = [];
  const fetcher = async (url) => {
    urls.push(url);
    if (url.endsWith('2026-10-23.json') && !ready) return { ok: false, status: 404 };
    return forDate(runningBoard)(url);
  };
  const { api, d, w } = setup(t, fetcher);
  let clock = Date.parse(EVENING);
  w.Date.now = () => clock;
  const done = { draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) };
  await api.update(done);
  assert.deepEqual(rows(d, 'top').map((r) => [r[0], r[2], r[3]]), [
    ['is-next is-pending', 'kỳ 23/10 · ngày mai', '2026-10-23'],
    ['is-before', 'kỳ 22/10 · hôm nay', '2026-10-22'],
    ['is-after', 'kỳ 22/10 · hôm nay', '2026-10-22'],
  ]);
  const pending = d.querySelector('tbody[data-list-id="top"] .is-next');
  assert.equal(pending.querySelector('.live-scorecard-num'), null, 'không một số nào, nhất là số của kỳ 22/10');
  assert.equal(pending.querySelectorAll('.live-scorecard-ghost').length, 3, 'khung chờ đúng cỡ danh sách kỳ vừa quay');
  assert.equal(pending.getAttribute('aria-busy'), 'true');
  assert.equal(pending.querySelector('.live-scorecard-ghosts').getAttribute('aria-hidden'), 'true');
  assert.match(pending.textContent, /Đang chờ tính danh sách cho kỳ này/);
  assert.match(d.getElementById('live-scorecard-summary').children[0].textContent,
    /^Kỳ sắp quay \(kỳ 23\/10 · ngày mai\): Đang chờ tính danh sách/);
  // Hệ thống tính xong: lần hỏi lại sau 5 phút đặt số thật vào đúng hàng ấy.
  ready = true;
  clock += 5 * 60000 + 1;
  await api.update(done);
  const next = d.querySelector('tbody[data-list-id="top"] .is-next');
  assert.equal(next.className, 'is-next');
  assert.equal(next.hasAttribute('aria-busy'), false);
  assert.deepEqual([...next.querySelectorAll('.live-scorecard-num')].map((n) => n.textContent), ['12', '34', '56']);
  // Đang tải lần đầu: cũng là khung chờ.
  let release;
  const slow = setup(t, (url) => (url.endsWith('2026-10-23.json')
    ? new Promise((resolve) => { release = () => resolve(ok(runningBoard('2026-10-23'))); })
    : forDate(runningBoard)(url)));
  const first = slow.api.update(done);
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  const loading = slow.d.querySelector('tbody[data-list-id="top"] .is-next');
  assert.equal(loading.dataset.status, 'loading');
  assert.equal(loading.querySelector('.live-scorecard-num'), null);
  assert.match(loading.textContent, /Đang tải sổ phỏng đoán/);
  release();
  await first;
  // Đã quá giờ khoá của kỳ ấy mà vẫn không có sổ: nói thẳng là không có, không treo khung chờ.
  const late = setup(t, (url) => (url.endsWith('2026-10-23.json') ? Promise.resolve({ ok: false, status: 404 })
    : forDate(runningBoard)(url)), '2026-10-23T11:20:00Z');
  await late.api.update(done);
  const gone = late.d.querySelector('tbody[data-list-id="top"] .is-next');
  assert.equal(gone.querySelector('.live-scorecard-ghost'), null);
  assert.equal(gone.hasAttribute('aria-busy'), false);
  assert.match(gone.textContent, /Không có sổ phỏng đoán cho kỳ này/);
});

test('Hàng trước giờ quay ghi giờ ghi sổ (giờ VN), kỳ sắp quay ghi thêm số mục trùng kỳ vừa quay', async (t) => {
  const stamps = { '2026-10-22': '2026-10-22T08:39:24Z', '2026-10-23': '2026-10-22T11:38:53Z' };
  const fetcher = forDate((date) => {
    const made = runningBoard(date);
    made.generated_at = stamps[date];
    // Kỳ sắp quay: Top LOTO giữ 12 và 56, thay 34 bằng 90.
    if (date === '2026-10-23') made.lists[0].items = [loto('56', 0.25), loto('12', 0.24), loto('90', 0.23)];
    return made;
  });
  const { api, d } = setup(t, fetcher);
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  const saved = (row) => d.querySelector(`tbody[data-list-id="top"] .${row} .live-scorecard-saved`);
  assert.equal(saved('is-next').textContent, 'ghi sổ 18:38 · 22/10', 'tính sau kỳ 22/10, không phải số cũ');
  assert.equal(saved('is-before').textContent, 'ghi sổ 15:39 · 22/10');
  assert.equal(saved('is-after'), null, 'hàng sau giờ quay là kết quả, không phải sổ');
  assert.equal(d.querySelector('tbody[data-list-id="top"] .is-next .live-scorecard-overlap').textContent,
    'Trùng 2/3 mục với danh sách kỳ 22/10 · hôm nay');
  assert.equal(d.querySelector('tbody[data-list-id="top"] .is-before .live-scorecard-overlap'), null);
  // Sổ không có giờ ghi (sổ cũ): không in dòng ấy.
  const plain = setup(t, forDate(runningBoard));
  await plain.api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  assert.equal(plain.d.querySelector('.live-scorecard-saved'), null);
});

test('Bấm số ở khối Dự đoán trong ngày: mở đúng số ấy trong hàng của kỳ đã bấm', async (t) => {
  const { api, d } = setup(t, forDate(runningBoard));
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  await api.reveal('2026-10-23', 'loto', '87');
  const button = nextItem(d, 'cau-keo-loto', 1);
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  assert.equal(d.activeElement, button);
  assert.match(d.getElementById('live-bridge-cau-keo-loto').querySelector('h3').textContent, /^87:/);
  await api.reveal('2026-10-22', 'loto', '78');
  assert.equal(item(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'true', 'kỳ vừa quay mở ở hàng của nó');
  await api.reveal('2026-10-23', 'de', '65');
  assert.ok(d.getElementById('live-bridge-cau-keo-de'));
  // Kỳ không có trên bảng: không làm gì.
  await api.reveal('2026-10-30', 'loto', '78');
  assert.ok(d.getElementById('live-bridge-cau-keo-de'));
});

test('Kỳ sắp quay bỏ qua ngày nghỉ quay đã khai (Tết), như next_draw_date của sổ', async (t) => {
  const urls = [];
  const fetcher = forDate(runningBoard, ['2026-10-23', '2026-10-24']);
  const { api, d } = setup(t, async (url) => { urls.push(url); return fetcher(url); }, '2026-10-23T03:00:00Z');
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  assert.equal(rows(d, 'top')[0][2], 'kỳ 25/10');
  assert.deepEqual(boards(urls), ['2026-10-22.json', '2026-10-25.json'], 'không hỏi sổ của ngày nghỉ');
  assert.equal(urls.filter((u) => u.endsWith('/closed.json')).length, 1);
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  assert.equal(urls.filter((u) => u.endsWith('/closed.json')).length, 1, 'lịch nghỉ chỉ đọc một lần');
  // Không đọc được lịch nghỉ: ngày lịch kế tiếp.
  const plain = setup(t, forDate(runningBoard), '2026-10-23T03:00:00Z');
  await plain.api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  assert.equal(rows(plain.d, 'top')[0][3], '2026-10-23');
});

test('Lệnh mở số gắn với kỳ đã bấm: sổ tải xong là kỳ khác thì không mở', async (t) => {
  let release;
  const fetcher = forDate(runningBoard);
  const { api, d } = setup(t, (url) => (url.endsWith('2026-10-23.json')
    ? new Promise((resolve) => { release = () => resolve(ok(runningBoard('2026-10-23'))); })
    : fetcher(url)));
  const first = api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const pending = api.reveal('2026-10-23', 'loto', '78');
  // live.json sang kỳ 24/10 trước khi sổ 23/10 tải xong.
  await api.update({ draw_date: '2026-10-24', status: 'partial', prizes: {} });
  release();
  await pending;
  await first;
  assert.equal(d.querySelector('time').dateTime, '2026-10-24');
  assert.equal(d.querySelector('.live-bridge'), null, 'không mở số 78 của kỳ 23/10');
  assert.equal(item(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'false');
  assert.ok(rows(d, 'top').every((r) => r[3] === '2026-10-24'), 'sổ 23/10 tải trễ không được đặt lên bảng');
});

test('Bấm số trước khi bảng biết có kỳ sắp quay (lịch nghỉ đang tải): lệnh mở chờ rồi mở đúng số', async (t) => {
  let release;
  const fetcher = forDate(runningBoard);
  const { api, d } = setup(t, (url) => (url.endsWith('/closed.json')
    ? new Promise((resolve) => { release = () => resolve({ ok: false, status: 404 }); })
    : fetcher(url)));
  const first = api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  await api.reveal('2026-10-23', 'loto', '78');
  release();
  await first;
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(nextItem(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'true');
  assert.match(d.getElementById('live-bridge-cau-keo-loto').querySelector('h3').textContent, /^78:/);
  // Lệnh cho kỳ không có trên bảng bị bỏ ở lần cập nhật sau, không treo mãi: khi kỳ 24/10 về tới bảng
  // (hôm sau), số 78 không tự mở ra.
  await api.reveal('2026-10-24', 'loto', '78');
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  assert.equal(nextItem(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'true');
  await api.update({ draw_date: '2026-10-23', status: 'complete_verified', prizes: prizes(FULL) });
  assert.equal(rows(d, 'cau-keo-loto')[0][3], '2026-10-24');
  assert.equal(d.querySelector('.live-bridge'), null, 'lệnh mở cũ không áp vào kỳ 24/10');
});

test('Sổ tải lại đổi chỗ các mục: bảng cầu đang mở giữ đúng số, số không còn thì đóng', async (t) => {
  let order = ['78', '87', '99'];
  const make = (date) => {
    const made = runningBoard(date);
    if (date === '2026-10-23') made.lists.find((l) => l.id === 'cau-keo-loto').items = order.map((n) => loto(n, 0.24));
    return made;
  };
  const { api, d, w } = setup(t, forDate(make));
  let clock = Date.parse(EVENING);
  w.Date.now = () => clock;
  const done = { draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) };
  await api.update(done);
  nextItem(d, 'cau-keo-loto', 0).click();
  assert.match(d.getElementById('live-bridge-cau-keo-loto').querySelector('h3').textContent, /^78:/);
  // Bản ghi lại trước giờ khoá: 87 lên đầu, 78 xuống thứ hai.
  order = ['87', '78', '99'];
  clock += 11 * 60000;
  await api.update(done);
  assert.match(d.getElementById('live-bridge-cau-keo-loto').querySelector('h3').textContent, /^78:/,
    'không lặng lẽ chuyển sang số 87 ở chỉ số cũ');
  assert.equal(nextItem(d, 'cau-keo-loto', 1).getAttribute('aria-expanded'), 'true');
  assert.equal(nextItem(d, 'cau-keo-loto', 0).getAttribute('aria-expanded'), 'false');
  // Bản sau bỏ hẳn 78: bảng cầu đóng.
  order = ['87', '99', '12'];
  clock += 11 * 60000;
  await api.update(done);
  assert.equal(d.querySelector('.live-bridge'), null);
});

test('Sổ tải lại: soi đường giữ đúng cầu đã chọn khi hai đường chung cặp vị trí mà khác độ trễ', async (t) => {
  // Như số 34 của path-loto-active trong sổ 05-11-2026: 14×39 ở trễ 6 và ở trễ 9.
  let paths = [{ a: 0, b: 1, streak: 3, lag: 1, base: '2026-10-21' }, { a: 0, b: 1, streak: 2, lag: 2, base: '2026-10-20' }];
  const make = () => board('2026-10-22', {
    schema: 2, draws: DRAWS,
    lists: [{ id: 'path-de-stable', group: 'Soi cầu theo đường', title: 'Đường cầu', page: 'soi-path-de-stable.html',
      kind: 'de', bridge: { type: 'path', mark: 'special', next: '2026-10-22' },
      items: [{ label: '78', rule: { on: 'special', numbers: ['78'] }, prob: 0.011, base: 0.01,
        bridges: paths, bridge_total: 2 }] }],
  });
  // 18:00 giờ VN, trước giờ khoá 18:10: hai lần tải lại sau (18:11, 18:22) đều chưa cách giờ khoá 1 giờ.
  const start = '2026-10-22T11:00:00Z';
  const { api, d, w } = setup(t, forDate(make), start);
  let clock = Date.parse(start);
  w.Date.now = () => clock;
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  chip(d, 'path-de-stable').click();
  d.querySelector('[data-bridge-pick="1"]').click();
  const pressed = () => [...d.getElementById('live-bridge-path-de-stable').querySelectorAll('[data-bridge-pick]')]
    .filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.textContent);
  assert.deepEqual(pressed(), ['0×1 · trễ 2 ngày · chuỗi 2']);
  // Bản ghi lại y hệt: cầu trễ 2 vẫn được chọn, không về cầu trễ 1 chung cặp 0×1.
  clock += 11 * 60000;
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  assert.deepEqual(pressed(), ['0×1 · trễ 2 ngày · chuỗi 2']);
  // Bản sau đảo thứ tự hai đường: lựa chọn đi theo cầu trễ 2 lên đầu.
  paths = [paths[1], paths[0]];
  clock += 11 * 60000;
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  assert.deepEqual(pressed(), ['0×1 · trễ 2 ngày · chuỗi 2']);
  assert.equal(d.querySelector('[data-bridge-pick="0"]').getAttribute('aria-pressed'), 'true');
});

test('Sổ còn có thể được ghi lại tới giờ khoá: tải lại mỗi 10 phút, thôi khi đã là bản đóng băng cuối', async (t) => {
  const urls = [];
  let version = 1;
  const make = (date) => {
    const made = runningBoard(date);
    if (date === '2026-10-23') made.lists[0].items[0] = loto(version === 1 ? '12' : '90', 0.25);
    return made;
  };
  // 19:00 giờ VN 22/10: sổ 22/10 đã khoá lúc 18:10 (chưa đủ 1 giờ), sổ 23/10 còn mở tới 18:10 hôm sau.
  const { api, d, w } = setup(t, async (url) => { urls.push(url); return forDate(make)(url); });
  let clock = Date.parse(EVENING);
  w.Date.now = () => clock;
  const done = { draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) };
  await api.update(done);
  const label = () => d.querySelector('tbody[data-list-id="top"] .is-next .live-scorecard-num').textContent;
  assert.equal(label(), '12');
  clock += 5 * 60000;
  await api.update(done);
  assert.deepEqual(boards(urls), ['2026-10-22.json', '2026-10-23.json'], 'chưa tới 10 phút: không tải lại');
  version = 2;
  clock += 6 * 60000;
  await api.update(done);
  assert.deepEqual(boards(urls).slice(2).sort(), ['2026-10-22.json', '2026-10-23.json'], 'đủ 10 phút: tải lại cả hai');
  assert.equal(label(), '90', 'bản ghi lại của sổ kỳ sắp quay được hiện');
  // Lần tải 19:11 đã cách giờ khoá của sổ 22/10 hơn 1 giờ: bản cuối, không tải nữa; sổ 23/10 vẫn tải lại.
  clock += 11 * 60000;
  await api.update(done);
  assert.deepEqual(boards(urls).slice(4), ['2026-10-23.json']);
  // Tải lại hỏng: giữ bản đang hiện.
  const failing = setup(t, async (url) => (urls.length > 1000 ? null : forDate(make)(url)));
  let clock2 = Date.parse(EVENING);
  failing.w.Date.now = () => clock2;
  await failing.api.update(done);
  failing.w.fetch = async () => { throw new Error('mạng hỏng'); };
  clock2 += 11 * 60000;
  await failing.api.update(done);
  assert.deepEqual(rows(failing.d, 'top').map((r) => r[0]), ['is-next', 'is-before', 'is-after']);
});

// Bảng kết quả đầu trang Live: 27 ô theo thứ tự giải (docs/live.html, #results).
const resultsBoard = (vals) => '<div id="results">' + vals.map((v) => `<div class="slot">${v}</div>`).join('') + '</div>';

test('Mở cầu: hai vị trí được tô trên bảng kết quả đầu trang khi bảng đang hiện đúng kỳ ghép số', async (t) => {
  const { api, d } = setup(t, async () => ok(runningBoard()), EVENING, resultsBoard(DRAWS['2026-10-21']));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  item(d, 'cau-keo-loto', 0).click();
  const slots = [...d.querySelectorAll('#results .slot')];
  assert.deepEqual([...slots[0].querySelectorAll('.live-board-src')].map((s) => [s.className, s.textContent]),
    [['live-board-src live-board-src--a', '7'], ['live-board-src live-board-src--b', '8']]);
  assert.equal(slots[0].textContent, '78111', 'giá trị của ô không đổi');
  assert.equal(d.querySelectorAll('#results .live-board-src').length, 2, 'chỉ hai chữ số được tô');
  const note = d.querySelector('#live-bridge-cau-keo-loto .live-bridge-onboard');
  assert.match(note.textContent, /đang được tô trên bảng kết quả kỳ 21\/10\/2026/);
  assert.equal(note.querySelector('a').getAttribute('href'), '#results');
  // Cầu ở hai giải khác nhau (giải bảy cuối), rồi đóng bảng: dấu được gỡ, ô trở lại chữ thường.
  item(d, 'cau-keo-de', 0).click();
  assert.deepEqual([...d.querySelectorAll('#results .live-board-src')].map((s) => s.textContent), ['6', '5']);
  assert.equal(slots[0].querySelector('.live-board-src'), null, 'cầu cũ không còn tô');
  d.querySelector('#live-bridge-cau-keo-de .live-bridge-close').click();
  assert.equal(d.querySelector('#results [data-bridge-mark]'), null);
  assert.equal(slots[26].childNodes.length, 1);
  assert.equal(slots[26].textContent, '65');
  // Đang tô thì live.json sang kỳ khác và sổ không khớp: bảng đối chiếu thành thông báo, dấu cũng được gỡ.
  item(d, 'cau-keo-loto', 0).click();
  assert.equal(d.querySelectorAll('#results .live-board-src').length, 2);
  await api.update({ draw_date: '2026-10-25', prizes: {} });
  assert.match(d.getElementById('live-scorecard-summary').textContent, /không khớp kỳ/);
  assert.equal(d.querySelector('#results [data-bridge-mark]'), null);
  assert.equal(slots[0].childNodes.length, 1);
});

test('Bảng đầu trang đang hiện kỳ khác (hay chưa hiện hết giải): không tô, không câu nhắc', async (t) => {
  const other = setup(t, async () => ok(runningBoard()), EVENING, resultsBoard(DRAWS['2026-10-20']));
  await other.api.update({ draw_date: '2026-10-22', prizes: {} });
  item(other.d, 'cau-keo-loto', 0).click();
  assert.equal(other.d.querySelector('#results .live-board-src'), null);
  assert.equal(other.d.querySelector('.live-bridge-onboard'), null);
  const partial = DRAWS['2026-10-21'].map((v, i) => (i > 20 ? '·'.repeat(v.length) : v));
  const waiting = setup(t, async () => ok(runningBoard()), EVENING, resultsBoard(partial));
  await waiting.api.update({ draw_date: '2026-10-22', prizes: {} });
  item(waiting.d, 'cau-keo-loto', 0).click();
  assert.equal(waiting.d.querySelector('#results .live-board-src'), null);
});

test('Danh sách cầu theo thứ: liên kết mang thêm thứ của kỳ biên', async (t) => {
  const weekly = runningBoard();
  weekly.lists.push({ id: 'bridge-loto-theo-thu', group: 'Soi cầu', title: 'Cầu LOTO theo thứ', page: 'soi-cau-loto-theo-thu.html',
    kind: 'loto', bridge: { type: 'rule', mark: 'loto-lon', series: Object.keys(DRAWS) },
    items: [{ ...loto('78'), label: '78 · 87', rule: { on: 'loto', numbers: ['78', '87'], need: 1 },
      bridges: [{ a: 0, b: 1, streak: 2 }], bridge_total: 1 }] });
  const { api, d } = setup(t, async () => ok(weekly));
  await api.update({ draw_date: '2026-10-22', prizes: {} });
  item(d, 'bridge-loto-theo-thu', 0).click();
  // 21/10/2026 là Thứ Tư: 2 theo cách đánh số 0 = Thứ Hai của trang soi cầu.
  assert.equal(d.querySelector('#live-bridge-bridge-loto-theo-thu .live-bridge-link').href,
    'https://example.test/soi-cau-loto-theo-thu.html?ngay=2026-10-21&so=78&vt=0x1&thu=2');
});

// Thành tích qua các kỳ (src/evaluation/board_record.py): khối thu gọn dưới bảng, chỉ tải khi mở.
const RECORD = {
  version: 1, draws: 14, first: '2026-10-21', last: '2026-11-03',
  method: { simulations: 20000, adjust: 'Holm' },
  family: { lists: 2, hits: 117, expected: 52.28, p: 0.0004, verdict: 'trúng nhiều hơn chọn bừa' },
  lists: [
    { id: 'cau-keo-loto', title: 'Cầu Kèo · Top 10 LOTO', group: 'Trang chủ · Live', draws: 14, items: 140, hits: 37,
      expected: 33.27, expected_published: 33.32, published_items: 140, days_hit: 13, days_expected: 13.18,
      p: 0.49, p_holm: 0.98, verdict: 'chưa khác chọn bừa' },
    { id: 'biet-truoc', title: 'Biết trước', group: '', draws: 8, items: 80, hits: 80, expected: 19.01,
      expected_published: 19.01, published_items: 0, days_hit: 8, days_expected: 7.4, p: 0.0002, p_holm: 0.0004,
      verdict: 'trúng nhiều hơn chọn bừa' },
  ],
};

// Như trình duyệt: đổi `open` là phát MỘT sự kiện toggle (jsdom tự phát, không cần phát tay).
function openRecord(d) {
  const details = d.getElementById('live-record');
  details.open = true;
  return details;
}
function closeRecord(d) {
  d.getElementById('live-record').open = false;
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test('Thành tích nhiều kỳ: chỉ tải khi mở, một lần, in từng danh sách và kết luận TỪ tệp', async (t) => {
  const urls = [];
  const { api, d } = setup(t, async (url) => { urls.push(url); return ok(url.endsWith('/record.json') ? RECORD : board()); });
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  const details = d.getElementById('live-record');
  assert.ok(details && !details.open);
  assert.equal(urls.filter((u) => u.endsWith('/record.json')).length, 0, 'chưa mở thì chưa tải');
  openRecord(d);
  await settle(); await settle(); await settle();
  assert.equal(details.querySelector('summary').textContent, 'Thành tích qua 14 kỳ đã quay (21/10/2026 → 03/11/2026)');
  const rows = [...details.querySelectorAll('tbody tr')];
  assert.deepEqual(rows.map((tr) => tr.dataset.listId), ['cau-keo-loto', 'biet-truoc']);
  assert.deepEqual([...rows[0].querySelectorAll('td')].map((td) => td.textContent),
    ['14', '37', '33,3', '33,3', '13 / 13,2', '0,980', 'chưa khác chọn bừa']);
  assert.deepEqual([...rows[1].querySelectorAll('td')].map((td) => td.textContent),
    ['8', '80', '19,0', '—', '8 / 7,4', '< 0,001', 'trúng nhiều hơn chọn bừa']);
  assert.equal(rows[1].querySelector('.live-record-verdict').dataset.verdict, 'above');
  assert.equal(rows[0].querySelector('.live-record-verdict').dataset.verdict, 'same');
  assert.equal(rows[0].querySelectorAll('td')[1].dataset.label, 'Mục trúng');
  assert.match(details.querySelector('.live-record-lead').textContent,
    /^Gộp mọi danh sách: trúng 117 mục, chọn bừa kỳ vọng 52,3 \(p = < 0,001\) — trúng nhiều hơn chọn bừa\.$/);
  assert.match(details.querySelector('.live-record-note').textContent, /20\.000 kỳ quay công bằng mô phỏng/);
  // Đóng rồi mở lại: không tải lần nữa.
  closeRecord(d); await settle();
  openRecord(d); await settle(); await settle();
  assert.equal(urls.filter((u) => u.endsWith('/record.json')).length, 1);
});

test('Thành tích nhiều kỳ: tệp hỏng hay thiếu thì báo, và lần mở sau thử lại', async (t) => {
  let calls = 0;
  const { d } = setup(t, async (url) => {
    if (!url.endsWith('/record.json')) return ok(board());
    calls += 1;
    return calls === 1 ? { ok: false, status: 404 } : ok({ ...RECORD, lists: 'hỏng' });
  });
  const details = openRecord(d);
  await settle(); await settle(); await settle();
  assert.match(details.querySelector('.live-record-status').textContent, /Chưa đọc được thành tích/);
  assert.equal(details.querySelector('table'), null);
  closeRecord(d); await settle();
  openRecord(d); await settle(); await settle(); await settle();
  assert.equal(calls, 2, 'lần mở sau thử lại');
  assert.match(details.querySelector('.live-record-status').textContent, /Chưa đọc được thành tích/);
});
