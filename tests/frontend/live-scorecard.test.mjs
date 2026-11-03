import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

// Bảng đối chiếu của trang Live (src/web/assets/live-scorecard.js): mỗi danh sách đã đóng băng
// là hai hàng song song, và một mục chỉ "trượt" khi phần kết quả liên quan đã đủ.
const script = readFileSync(new URL('../../src/web/assets/live-scorecard.js', import.meta.url), 'utf8');
const markup = '<section id="live-scorecard" data-board-root="https://example.test/board/">' +
  '<time id="live-scorecard-date"></time><div id="live-scorecard-summary"></div>' +
  '<table id="live-scorecard-table"><thead><tr><th>Danh sách</th></tr></thead></table></section>';

// Đồng hồ cố định: 19:00 giờ VN ngày 22/10, tức tối của kỳ trong các sổ mẫu (kỳ đã quay hiện mặc định).
const EVENING = '2026-10-22T12:00:00Z';
function setup(t, fetcher, now = EVENING) {
  const dom = new JSDOM(markup, { runScripts: 'outside-only', url: 'https://example.test/live.html' });
  t.after(() => dom.window.close());
  dom.window.fetch = fetcher;
  const fixed = Date.parse(now);
  dom.window.Date.now = () => fixed;
  dom.window.eval(script);
  return { api: dom.window.LiveScorecard, d: dom.window.document };
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
  assert.match(d.getElementById('live-scorecard-summary').textContent, /Đã trúng 4\/7 mục/);
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
  assert.match(panel.querySelector('.live-bridge-link').href, /soi-cau-loto\.html$/);
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
  assert.match(panel.querySelector('.live-bridge-link').href, /soi-path-de-stable\.html\?number=78$/);
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
const forDate = (make) => async (url) => {
  const date = url.match(/(\d{4}-\d\d-\d\d)\.json$/)[1];
  return ok(make(date));
};
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
  assert.match(panel.querySelector('.live-bridge-link').href, /soi-cau-loto\.html$/);
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

test('Kỳ đã quay xong: tối hôm ấy mặc định đối chiếu, có nút sang kỳ sắp quay', async (t) => {
  const urls = [];
  const { api, d } = setup(t, async (url) => { urls.push(url); return forDate(runningBoard)(url); });
  const done = { draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) };
  await api.update(done);
  const views = [...d.querySelectorAll('.live-scorecard-view')];
  assert.deepEqual(views.map((b) => b.textContent), ['Kỳ 22/10/2026 · đã quay', 'Kỳ 23/10/2026 · sắp quay']);
  assert.deepEqual(views.map((b) => b.getAttribute('aria-pressed')), ['true', 'false']);
  assert.equal(d.querySelector('time').dateTime, '2026-10-22');
  assert.ok(states(d, 'top', 'is-after').every((s) => s !== 'wait'), 'kỳ đã quay được chấm');
  views[1].click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(d.querySelector('time').dateTime, '2026-10-23');
  assert.deepEqual(urls.map((u) => u.slice(-15)), ['2026-10-22.json', '2026-10-23.json']);
  assert.ok(states(d, 'top', 'is-after').every((s) => s === 'wait'), 'kỳ sắp quay chưa có giải nào');
  assert.ok(item(d, 'cau-keo-loto', 0), 'số trước giờ quay của kỳ sắp quay bấm được');
  // live.json cập nhật lại cùng kỳ: lựa chọn của người đọc được giữ.
  await api.update(done);
  assert.equal(d.querySelector('time').dateTime, '2026-10-23');
  assert.equal(d.querySelector('.live-scorecard-view[aria-pressed="true"]').dataset.view, '2026-10-23');
});

test('Sang ngày mới (giờ VN) thì mặc định là kỳ sắp quay; kỳ đang quay thì không có nút chọn', async (t) => {
  const urls = [];
  const morning = setup(t, async (url) => { urls.push(url); return forDate(runningBoard)(url); }, '2026-10-22T17:30:00Z');
  await morning.api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  assert.equal(morning.d.querySelector('time').dateTime, '2026-10-23', '00:30 giờ VN ngày 23/10');
  assert.deepEqual(urls.map((u) => u.slice(-15)), ['2026-10-23.json']);
  const live = setup(t, forDate(runningBoard), '2026-10-23T11:20:00Z');
  await live.api.update({ draw_date: '2026-10-23', status: 'partial', prizes: prizes(FULL, 3) });
  assert.equal(live.d.querySelector('.live-scorecard-views').hidden, true);
  assert.equal(live.d.querySelector('time').dateTime, '2026-10-23');
});

test('Bấm số ở khối Dự đoán trong ngày: mở đúng số ấy trong bảng của kỳ sắp quay', async (t) => {
  const { api, d } = setup(t, forDate(runningBoard));
  await api.update({ draw_date: '2026-10-22', status: 'complete_verified', prizes: prizes(FULL) });
  await api.reveal('2026-10-23', 'loto', '87');
  assert.equal(d.querySelector('time').dateTime, '2026-10-23');
  const button = item(d, 'cau-keo-loto', 1);
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  assert.equal(d.activeElement, button);
  assert.match(d.getElementById('live-bridge-cau-keo-loto').querySelector('h3').textContent, /^87:/);
  await api.reveal('2026-10-23', 'de', '65');
  assert.ok(d.getElementById('live-bridge-cau-keo-de'));
  // Kỳ không có trên bảng: không làm gì.
  await api.reveal('2026-10-30', 'loto', '78');
  assert.equal(d.querySelector('time').dateTime, '2026-10-23');
});
