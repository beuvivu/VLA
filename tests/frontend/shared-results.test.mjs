import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const build = `import json
from pages.build_traditional_results import embedded_payload, render_page
from web.shared_results import decode_row, render_result_board
row = "2026-09-26" + "00001" + "00000" + "0000200003" + "00004" * 6 + "0005" * 4 + "0006" * 6 + "007" * 3 + "08" * 4
metadata = {"station": "Nam Định", "special_codes": ["1AB", "2CD"]}
draw = decode_row(row, metadata=metadata)
# Kỳ "vị trí": chữ số ở vị trí i là i % 10, nên chữ số được tô cho biết ngay nó là vị trí nào.
from soi_cau.position_bridges import positions
row_pos = "2026-09-27" + "".join(str(i % 10) for i in range(107))
chips = '<aside><a href="#" data-bridge-a="4" data-bridge-b="57">45</a><a href="#" data-bridge-a="0" data-bridge-b="1">01</a></aside>'
print(json.dumps({"traditional": render_page(embedded_payload([row], generated="x", draw_metadata={"2026-09-26": metadata})),
                  "traditional_positions": render_page(embedded_payload([row_pos, row], generated="x", draw_metadata={"2026-09-26": metadata})),
                  "landing": render_result_board(draw), "draw": draw,
                  "positions_board": render_result_board(decode_row(row_pos)),
                  "chips_board": render_result_board(decode_row(row_pos), extra=chips),
                  "positions": [[p["value_index"], p["label"]] for p in positions()]}))`;
const fixture = JSON.parse(execFileSync(process.env.APP_TEST_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(new URL('../../', import.meta.url)), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
}));

function setup(t, kind = 'landing', execute = true, url = 'https://example.test/') {
  const dom = new JSDOM(fixture[kind], { url, runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.TextEncoder = TextEncoder;
  if (execute) run(dom);
  return dom;
}

function run(dom) {
  const sharedSource = readFileSync(new URL('../../src/web/templates/shared_results.js', import.meta.url), 'utf8');
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

test('chọn cả cặp gộp dấu ô riêng để bấm bỏ cặp không còn ô mắc dấu', t => {
  const dom = setup(t, 'traditional'), d = dom.window.document;
  const numbers = d.querySelectorAll('.tr-number');
  numbers[4].click();
  assert.deepEqual(marked(d), [numbers[4]]);
  const pairMode = d.getElementById('tr-pair-mode');
  pairMode.checked = true;
  pairMode.dispatchEvent(new dom.window.Event('change'));
  numbers[5].click();
  assert.equal(marked(d).length, 12);
  assert.equal(d.getElementById('tr-mark-clear').textContent, 'Bỏ đánh dấu (1)');
  numbers[4].click();
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

// ---- Vị trí cầu trên bảng kết quả (markBridge / clearBridge) ------------------------------------

test('markBridge tô đúng chữ số của cả 107 vị trí; nhãn vị trí trùng bản Python', t => {
  const dom = setup(t, 'positions_board'), d = dom.window.document, TR = dom.window.TraditionalResults;
  const root = d.getElementById('app-daily-results');
  const cells = [...d.querySelectorAll('.tr-number')];
  const before = cells.map((cell) => cell.textContent);
  fixture.positions.forEach(([valueIndex, label], i) => {
    assert.equal(TR.positionLabel(i), label, `nhãn ${i}`);
    const j = (i + 50) % 107;
    assert.ok(TR.markBridge(root, '2026-09-27', i, j) >= 1, `tô ${i}`);
    const a = root.querySelector('.tr-bridge-src--a');
    assert.equal(cells.indexOf(a.closest('.tr-number')), valueIndex, `ô của vị trí ${i}`);
    assert.equal(a.textContent, String(i % 10), `chữ số của vị trí ${i}`);
    assert.equal(root.querySelector('.tr-bridge-src--b').textContent, String(j % 10));
  });
  TR.clearBridge(root);
  assert.equal(root.querySelectorAll('.tr-bridge-src, [data-bridge-mark]').length, 0);
  assert.deepEqual(cells.map((cell) => cell.textContent), before, 'gỡ dấu trả đúng chữ như lúc dựng');
  assert.equal(cells[0].querySelector('.tr-special-tail').textContent, '34', 'ô Đặc Biệt giữ vỏ hai số cuối');
});

test('markBridge: hai vị trí cùng một ô, kỳ không có trên bảng hay vị trí sai thì không tô gì', t => {
  const dom = setup(t, 'positions_board'), d = dom.window.document, TR = dom.window.TraditionalResults;
  const root = d.getElementById('app-daily-results');
  assert.equal(TR.markBridge(root, '2026-09-27', 0, 4), 1);
  const special = d.querySelector('.tr-number[data-bridge-mark]');
  assert.deepEqual([...special.querySelectorAll('.tr-bridge-src')].map((s) => s.textContent), ['0', '4']);
  assert.equal(special.textContent, '01234');
  for (const [date, a, b] of [['2026-09-26', 4, 57], ['2026-09-27', 4, 107], ['x"]', 1, 2]]) {
    assert.equal(TR.markBridge(root, date, a, b), 0, `${date} ${a}x${b}`);
    assert.equal(root.querySelectorAll('[data-bridge-mark]').length, 0, 'lần tô trước đã được gỡ');
  }
});

test('trang chủ: đưa chuột hay Tab tới cầu đẹp nhất thì hai vị trí sáng trên bảng, rời đi thì tắt', t => {
  const dom = setup(t, 'chips_board'), d = dom.window.document, W = dom.window;
  const root = d.getElementById('app-daily-results');
  const [chip, other] = d.querySelectorAll('[data-bridge-a]');
  chip.dispatchEvent(new W.MouseEvent('mouseover', { bubbles: true }));
  assert.deepEqual([...root.querySelectorAll('.tr-bridge-src')].map((s) => s.textContent), ['4', '7']);
  chip.dispatchEvent(new W.MouseEvent('mouseout', { bubbles: true, relatedTarget: d.body }));
  assert.equal(root.querySelectorAll('.tr-bridge-src').length, 0);
  other.dispatchEvent(new W.FocusEvent('focusin', { bubbles: true }));
  assert.deepEqual([...root.querySelectorAll('.tr-bridge-src')].map((s) => s.textContent), ['0', '1']);
  other.dispatchEvent(new W.FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
  assert.equal(root.querySelectorAll('[data-bridge-mark]').length, 0);
});

test('Sổ KQ mở từ liên kết cầu: đúng kỳ, tô hai vị trí, dòng báo và nút bỏ tô; liên kết hỏng thì bỏ qua', t => {
  const dom = setup(t, 'traditional_positions', true, 'https://example.test/so-ket-qua-truyen-thong.html?ngay=2026-09-27&vt=4x57');
  const d = dom.window.document;
  assert.deepEqual([...d.querySelectorAll('#tr-results .tr-day time')].map((n) => n.dateTime), ['2026-09-27']);
  assert.equal(d.getElementById('tr-period').value, 'custom');
  assert.deepEqual([...d.querySelectorAll('#tr-results .tr-bridge-src')].map((s) => s.textContent), ['4', '7']);
  const note = d.querySelector('.tr-bridge-note');
  assert.match(note.textContent, /Đang tô vị trí cầu kỳ 27\/09\/2026: vị trí 4 \(ĐB · chữ số 5\) ghép vị trí 57 \(G4\.2 · chữ số 4\)\./);
  // Đổi bộ lọc sang kỳ khác: không tô, dòng báo nói rõ; quay lại thì tô lại.
  d.getElementById('tr-from').value = '2026-09-26'; d.getElementById('tr-to').value = '2026-09-26';
  d.getElementById('tr-to').dispatchEvent(new dom.window.Event('change'));
  assert.equal(d.querySelectorAll('#tr-results .tr-bridge-src').length, 0);
  assert.match(note.textContent, /đang bị bộ lọc ẩn/);
  d.getElementById('tr-period').value = 'all';
  d.getElementById('tr-period').dispatchEvent(new dom.window.Event('change'));
  assert.equal(d.querySelectorAll('#tr-results .tr-bridge-src').length, 2);
  note.querySelector('button').click();
  assert.equal(d.querySelectorAll('#tr-results .tr-bridge-src, .tr-bridge-note').length, 0);
  for (const query of ['?ngay=2026-09-27&vt=4x107', '?ngay=2020-01-01&vt=4x57', '?ngay=2026-09-27&vt=4x4', '?vt=4x57']) {
    const other = setup(t, 'traditional_positions', true, 'https://example.test/so-ket-qua-truyen-thong.html' + query);
    assert.equal(other.window.document.querySelector('.tr-bridge-note'), null, query);
    assert.equal(other.window.document.querySelectorAll('.tr-bridge-src').length, 0, query);
  }
});
