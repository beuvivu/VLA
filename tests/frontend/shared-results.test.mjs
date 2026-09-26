import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const build = `import json
from build_traditional_results import embedded_payload, render_page
from shared_results import decode_row, render_result_board
row = "2026-09-26" + "00001" + "00000" + "0000200003" + "00004" * 6 + "0005" * 4 + "0006" * 6 + "007" * 3 + "08" * 4
metadata = {"station": "Nam Định", "special_codes": ["1AB", "2CD"]}
draw = decode_row(row, metadata=metadata)
print(json.dumps({"traditional": render_page(embedded_payload([row], generated="x", draw_metadata={"2026-09-26": metadata})), "landing": render_result_board(draw), "draw": draw}))`;
const fixture = JSON.parse(execFileSync(process.env.APP_TEST_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(new URL('../../', import.meta.url)), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
}));

function setup(t, kind = 'landing', execute = true) {
  const dom = new JSDOM(fixture[kind], { url: 'https://example.test/', runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.TextEncoder = TextEncoder;
  if (execute) run(dom);
  return dom;
}

function run(dom) {
  const sharedSource = readFileSync(new URL('../../src/templates/shared_results.js', import.meta.url), 'utf8');
  const override = process.env.APP_SHARED_RESULTS_SCRIPT
    ? readFileSync(process.env.APP_SHARED_RESULTS_SCRIPT, 'utf8') : sharedSource;
  for (const script of dom.window.document.querySelectorAll('script:not([src])')) {
    if (script.type !== 'application/json') dom.window.eval(script.textContent.replace(sharedSource, override));
  }
}

function marked(document) {
  return [...document.querySelectorAll('.tr-number[data-marked], .tr-mini[data-marked]')];
}

test('bản dự phòng và bộ dựng thật cùng giữ đủ 27 giải và số 0 đầu', t => {
  for (const kind of ['traditional', 'landing']) {
    const dom = setup(t, kind, false), d = dom.window.document;
    for (const stage of ['trước', 'sau']) {
      const values = [...d.querySelectorAll('.tr-number')].map(node => node.textContent);
      assert.equal(values.length, 27, `${kind} ${stage}`);
      assert.deepEqual(values.slice(0, 4), ['00001', '00000', '00002', '00003']);
      assert.deepEqual(values.slice(-7), ['007', '007', '007', '08', '08', '08', '08']);
      if (stage === 'trước') run(dom);
    }
  }
});

test('trang chủ và Sổ KQ dùng cùng DOM bảng giải, đầu LOTO và metadata', t => {
  const home = setup(t), book = setup(t, 'traditional');
  for (const selector of ['.tr-day-head', '.tr-prizes', '.tr-head-tail']) {
    assert.equal(home.window.document.querySelector(selector).isEqualNode(book.window.document.querySelector(selector)), true, selector);
  }
  assert.equal(home.window.document.querySelector('.tr-loto'), null);
  assert.ok(book.window.document.querySelector('.tr-loto'));
  assert.equal(home.window.document.querySelector('h2').textContent, 'Xổ số Miền Bắc (Nam Định)');
  assert.deepEqual([...home.window.document.querySelectorAll('.tr-special-code')].map(node => node.textContent), ['1AB', '2CD']);
});

test('bấm đúng ô giải đổi dấu và bấm lại bỏ dấu trên cả hai trang', t => {
  for (const kind of ['traditional', 'landing']) {
    const dom = setup(t, kind), d = dom.window.document;
    const numbers = d.querySelectorAll('.tr-number');
    numbers[4].click();
    assert.deepEqual(marked(d), [numbers[4]], kind);
    assert.equal(numbers[4].getAttribute('aria-pressed'), 'true');
    numbers[4].click();
    assert.equal(marked(d).length, 0);
    assert.equal(numbers[4].getAttribute('aria-pressed'), 'false');
    numbers[0].querySelector('.tr-special-tail').click();
    assert.deepEqual(marked(d), [numbers[0]]);
  }
});

test('Enter và Space đánh dấu từng giải và từng cặp, chặn cuộn khi nhấn Space', t => {
  const dom = setup(t), d = dom.window.document;
  for (const selector of ['.tr-number', '.tr-mini']) {
    const node = d.querySelector(selector);
    assert.equal(node.tabIndex, 0);
    for (const [key, expected] of [['Enter', 'true'], [' ', 'false']]) {
      const event = new dom.window.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
      node.dispatchEvent(event);
      assert.equal(event.defaultPrevented, true);
      assert.equal(node.getAttribute('aria-pressed'), expected);
    }
  }
});

test('đánh dấu không kích hoạt bộ mở chi tiết số của trang chủ', t => {
  const dom = setup(t), d = dom.window.document;
  let outsideEvents = 0;
  for (const type of ['click', 'keydown']) d.addEventListener(type, () => { outsideEvents += 1; });
  d.querySelector('.tr-number').click();
  d.querySelector('.tr-mini').dispatchEvent(new dom.window.KeyboardEvent('keydown', {
    key: 'Enter', bubbles: true, cancelable: true,
  }));
  assert.equal(marked(d).length, 2);
  assert.equal(outsideEvents, 0);
});

test('chế độ cặp, đổi bố cục, dựng lại và xoá dấu của Sổ KQ vẫn hoạt động', t => {
  const dom = setup(t, 'traditional'), d = dom.window.document;
  const pairMode = d.getElementById('tr-pair-mode');
  pairMode.checked = true;
  pairMode.dispatchEvent(new dom.window.Event('change'));
  d.querySelectorAll('.tr-number')[4].click();
  assert.equal(marked(d).length, 12);
  assert.ok(marked(d).every(node => node.textContent.slice(-2) === '04'));
  const layout = d.querySelector('input[name="tr-layout"][value="4"]');
  layout.checked = true;
  layout.dispatchEvent(new dom.window.Event('change'));
  assert.equal(d.getElementById('tr-results').dataset.layout, '4');
  const period = d.getElementById('tr-period');
  period.value = 'all';
  period.dispatchEvent(new dom.window.Event('change'));
  assert.equal(marked(d).length, 12);
  pairMode.checked = false;
  pairMode.dispatchEvent(new dom.window.Event('change'));
  assert.equal(marked(d).length, 12);
  d.querySelectorAll('.tr-number')[4].click();
  assert.equal(marked(d).length, 0);
  d.querySelector('.tr-number').click();
  assert.equal(d.getElementById('tr-mark-clear').hidden, false);
  d.getElementById('tr-mark-clear').click();
  assert.equal(marked(d).length, 0);
  assert.equal(d.getElementById('tr-mark-clear').hidden, true);
});

test('thiếu ký hiệu không nhận mã hôm trước và metadata chỉ được dựng thành chữ', t => {
  const dom = setup(t), d = dom.window.document;
  const shared = dom.window.TraditionalResults;
  const row = '2026-09-26' + '0'.repeat(107);
  const absent = shared.decode(row, { date: '2026-09-25', station: 'Hà Nội', special_codes: ['1AB'] });
  const board = shared.renderDraw(absent);
  assert.equal(board.querySelector('.tr-special-code'), null);
  assert.match(board.querySelector('.tr-code-missing').textContent, /Chưa có dữ liệu ký hiệu/);
  assert.equal(board.querySelector('h2').textContent, 'Xổ số Miền Bắc');
  const unsafe = shared.decode(row, { station: '<img src=x>', special_codes: ['<script>x</script>'] });
  const safeBoard = shared.renderDraw(unsafe);
  d.body.append(safeBoard);
  assert.equal(safeBoard.querySelector('img, script'), null);
  assert.match(safeBoard.querySelector('h2').textContent, /<img src=x>/);
});

test('dòng nhúng hỏng bị bỏ qua mà không làm mất những kỳ hợp lệ', t => {
  const dom = setup(t, 'traditional', false), d = dom.window.document;
  const embedded = d.getElementById('tr-embedded-data');
  const payload = JSON.parse(embedded.textContent);
  payload.rows.unshift(null, 42, 'không phải kỳ quay');
  embedded.textContent = JSON.stringify(payload);
  run(dom);
  assert.equal(d.querySelectorAll('.tr-number').length, 27);
  assert.equal(d.getElementById('tr-result-count').textContent, '1');
  assert.equal(d.getElementById('tr-source-status').dataset.state, 'ready');
});
