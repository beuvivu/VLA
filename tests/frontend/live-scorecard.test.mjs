import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

// Bảng đối chiếu của trang Live (src/assets/live-scorecard.js): mỗi danh sách đã đóng băng
// là hai hàng song song, và một mục chỉ "trượt" khi phần kết quả liên quan đã đủ.
const script = readFileSync(new URL('../../src/assets/live-scorecard.js', import.meta.url), 'utf8');
const markup = '<section id="live-scorecard" data-board-root="https://example.test/board/">' +
  '<time id="live-scorecard-date"></time><div id="live-scorecard-summary"></div>' +
  '<table id="live-scorecard-table"><thead><tr><th>Danh sách</th></tr></thead></table></section>';

function setup(t, fetcher) {
  const dom = new JSDOM(markup, { runScripts: 'outside-only', url: 'https://example.test/live.html' });
  t.after(() => dom.window.close());
  dom.window.fetch = fetcher;
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
