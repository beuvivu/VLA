import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const script = process.env.APP_LANDING_SCRIPT ? readFileSync(process.env.APP_LANDING_SCRIPT, 'utf8')
  : execFileSync('python3', ['-c', 'from pages.build_landing_page import _LANDING_SCRIPT; print(_LANDING_SCRIPT)'],
    { cwd: root, env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8' });
function start(t) {
  const ids = ['num', 'mode', 'title', 'score', 'prob', 'reason', 'evidence', 'summary', 'lines'];
  const dom = new JSDOM(`<!doctype html><body><script type="application/json" id="landing-data">{"explain":{}}</script>
    ${ids.map(id => `<div id="inspect-${id}"></div>`).join('')}
    <button id="first" data-mode="loto" data-number="12">12</button>
    <button id="again" data-mode="loto" data-number="12">12</button>
    <button id="other" data-mode="de" data-number="12">12</button>
    <button id="pair" data-pair="49-54">49–54</button>
    <button id="nextpair" data-pair="12-68">12–68</button>
    <p id="app-pair-feedback" role="status"></p></body>`, { runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.IntersectionObserver = class { observe() {} };
  dom.window.eval(script);
  return dom.window.document;
}
test('Chọn số phản hồi đồng bộ ở mọi bản sao và giữ riêng Đặc Biệt/LOTO', t => {
  const doc = start(t);
  doc.getElementById('other').click();
  assert.equal(doc.getElementById('other').getAttribute('aria-pressed'), 'true');
  assert.equal(doc.getElementById('first').getAttribute('aria-pressed'), 'false');
  doc.getElementById('again').click();
  assert.equal(doc.getElementById('first').getAttribute('aria-pressed'), 'true');
  assert.equal(doc.getElementById('again').getAttribute('aria-pressed'), 'true');
  assert.equal(doc.getElementById('other').getAttribute('aria-pressed'), 'false');
  assert.equal(doc.getElementById('inspect-num').textContent, '12');
  assert.match(doc.getElementById('app-pair-feedback').textContent, /Đã chọn số 12/);
});
test('Chọn cặp cho phản hồi rõ số đang xem; chọn số khác bỏ trạng thái cặp cũ', t => {
  const doc = start(t);
  doc.getElementById('pair').click();
  assert.equal(doc.getElementById('inspect-num').textContent, '49');
  assert.equal(doc.getElementById('pair').getAttribute('aria-pressed'), 'true');
  assert.match(doc.getElementById('app-pair-feedback').textContent, /49–54.*số 49/);
  doc.getElementById('nextpair').click();
  assert.equal(doc.getElementById('pair').getAttribute('aria-pressed'), 'false');
  assert.equal(doc.getElementById('nextpair').getAttribute('aria-pressed'), 'true');
  doc.getElementById('other').click();
  assert.equal(doc.getElementById('nextpair').getAttribute('aria-pressed'), 'false');
  assert.equal(doc.querySelectorAll('[data-pair].app-number-selected').length, 0);
});
