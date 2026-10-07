import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
const script = readFileSync(new URL('../../src/assets/live-predictions.js', import.meta.url), 'utf8');
function setup(t, fetcher) {
  const dom = new JSDOM('<section id="live-predictions" data-prediction-root="https://example.test/predict/"><time id="live-prediction-date"></time>' +
    ['de', 'loto'].map(mode => '<section data-prediction-mode="' + mode + '"><ol class="live-prediction-list"></ol><p class="live-prediction-message"></p></section>').join('') + '</section>', {runScripts: 'outside-only'});
  t.after(() => dom.window.close());
  dom.window.fetch = fetcher;
  dom.window.eval(script);
  return {load: dom.window.LivePredictions.load, d: dom.window.document};
}
const csv = text => ({ok: true, text: async () => text});
const numbers = (d, mode) => [...d.querySelectorAll('[data-prediction-mode="' + mode + '"] .live-prediction-number')].map(n => n.textContent);
test('Exact draw date, zero padding, validation and ten unique numbers', async t => {
  const urls = [];
  const {load, d} = setup(t, async url => { urls.push(url); return csv('number,prob\n5,0.01\n00,0.01\n5,0.01\n<img>,0.01\n100,0.01\n-2,0.01\n' + Array.from({length: 12}, (_, i) => (i + 10) + ',0.01').join('\n')); });
  await load('2026-09-26');
  assert.deepEqual(urls, ['https://example.test/predict/cau_keo_de_top10_2026-09-26.csv', 'https://example.test/predict/cau_keo_loto_top10_2026-09-26.csv']);
  assert.deepEqual(numbers(d, 'de'), ['05','00','10','11','12','13','14','15','16','17']);
  assert.equal(d.querySelector('img'), null);
  assert.equal(d.querySelector('time').dateTime, '2026-09-26');
  await load('2026-09-26');
  assert.equal(urls.length, 2);
});
test('Partial availability retries the missing column without refetching success', async t => {
  let calls = 0;
  const {load, d} = setup(t, async url => { calls++; return url.includes('_de_') && calls === 1 ? {ok:false,status:404} : csv('number,prob\n7,0.1'); });
  await load('2026-09-26');
  assert.deepEqual(numbers(d, 'de'), []);
  assert.deepEqual(numbers(d, 'loto'), ['07']);
  assert.match(d.querySelector('[data-prediction-mode="de"] p').textContent, /Chưa có/);
  await load('2026-09-26');
  assert.deepEqual(numbers(d, 'de'), ['07']);
  assert.equal(calls, 3);
});
test('Late previous-day responses cannot overwrite the selected day', async t => {
  const pending = [];
  const {load, d} = setup(t, url => url.includes('09-26') ? new Promise(resolve => pending.push(resolve)) : Promise.resolve(csv('number,prob\n88,0.1')));
  const old = load('2026-09-26');
  await load('2026-09-27');
  for (const resolve of pending) resolve(csv('number,prob\n11,0.1'));
  await old;
  assert.deepEqual(numbers(d, 'de'), ['88']);
  assert.deepEqual(numbers(d, 'loto'), ['88']);
  assert.equal(d.querySelector('time').dateTime, '2026-09-27');
});
test('Invalid dates clear stale values and malformed CSV produces an empty state', async t => {
  let calls = 0;
  const {load, d} = setup(t, async () => { calls++; return csv('number,prob\n12,0.1'); });
  await load('2026-09-26');
  for (const date of ['', '2026-02-30', '../2026-09-26', undefined]) await load(date);
  assert.equal(calls, 2);
  assert.deepEqual(numbers(d, 'de'), []);
  assert.equal(d.querySelector('time').dateTime, '');
  const empty = setup(t, async () => csv('<html>Not found</html>'));
  await empty.load('2026-09-26');
  assert.deepEqual(numbers(empty.d, 'de'), []);
  assert.match(empty.d.querySelector('[data-prediction-mode="de"] p').textContent, /Chưa có/);
});
test('A finished draw moves the block to the next draw date', async t => {
  const urls = [];
  const {d} = setup(t, async url => { urls.push(url); return csv('number\n31'); });
  const api = d.defaultView.LivePredictions;
  // Đang quay: vẫn là số của chính kỳ ấy.
  await api.loadForDraw('2026-10-07', 'partial');
  assert.equal(d.querySelector('time').dateTime, '2026-10-07');
  // Quay xong (kể cả qua cuối tháng/năm): số của kỳ kế tiếp.
  // Mọi trạng thái hoàn tất mà hai nguồn trực tiếp thật sự ghi ra.
  for (const [status, draw, next] of [['complete_verified', '2026-10-07', '2026-10-08'], ['complete_provisional', '2026-10-31', '2026-11-01'], ['complete_conflict', '2026-12-31', '2027-01-01'], ['complete', '2026-10-09', '2026-10-10']]) {
    await api.loadForDraw(draw, status);
    assert.equal(d.querySelector('time').dateTime, next);
    assert.ok(urls.at(-1).endsWith('_top10_' + next + '.csv'), urls.at(-1));
  }
  for (const status of ['waiting', 'partial', undefined]) {
    await api.loadForDraw('2026-10-11', status);
    assert.equal(d.querySelector('time').dateTime, '2026-10-11');
  }
  await api.loadForDraw('2026-02-30', 'complete_verified');
  assert.equal(d.querySelector('time').dateTime, '');
});
