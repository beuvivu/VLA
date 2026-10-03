import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const SCRIPT = readFileSync(process.env.APP_EVIDENCE_SCRIPT || new URL('src/assets/app-evidence.js', root), 'utf8');

const REGISTRY = {
  schema: 1,
  page: { sources: [{ title: 'Sổ kết quả XSMB đã lưu', snippet: '4 224 kỳ', url: 'so-ket-qua-truyen-thong.html' }],
    reasoningTrace: { steps: ['Đọc sổ kết quả đã lưu.'] } },
  sections: [{ match: '#ai-ml', title: 'Dự báo AI/ML',
    sources: [{ title: 'Dự báo đã công bố trước kỳ quay', snippet: 'Vector 100 số' }, { title: 'Ngoài', snippet: 'x', url: 'javascript:alert(1)' }],
    reasoningTrace: { steps: ['Trộn các thành phần.', 'Hiệu chỉnh.'] } }],
  values: {},
};
const ROW = { 'ml-loto-63': { title: 'Số 63 · ML LOTO', sources: [{ title: 'Mô hình ML thành phần', snippet: 'Cây tăng cường' }],
  reasoningTrace: { steps: ['Thô 24,213%.', 'Co về nền.'], confidenceScore: 0.35 } } };

function page({ registry = JSON.stringify(REGISTRY) } = {}) {
  return `<!doctype html><html><head><title>t</title>
<script type="application/json" id="app-evidence-data">${registry}</script></head><body>
<nav class="app-rail"><span id="rail-count">12</span></nav>
<main class="app-main" id="app-main">
  <header><h1>Tần suất LOTO</h1><p class="ui-sub">Đếm số nháy.</p></header>
  <section id="kpi"><h2>Tổng quan</h2>
    <div class="kpi"><span>Số kỳ</span><strong id="kpi-value">4 224</strong></div>
    <p id="prose">Trong 4 224 kỳ quay gần đây, số 27 về nhiều hơn mức trung bình một chút.</p>
    <span id="date">03-10-2026</span>
    <button id="btn" type="button">12</button>
    <input id="field" value="45">
  </section>
  <section id="ai-ml"><h2>Bảng xác suất</h2>
    <table><thead><tr><th>#</th><th>Số</th><th>Xác suất (%)</th></tr></thead>
      <tbody><tr data-evidence-row="ml-loto-63" data-evidence-cols="1,2"><td id="rank">1</td><td id="num">63</td><td id="prob">23,943%</td></tr>
        <tr><td>2</td><td>95</td><td id="prob2">23,936%</td></tr>
        <tr><td>3</td><td id="sci">-7.15393e-05</td><td id="sci2">3.39239E+05</td></tr></tbody></table>
    <script type="application/json" data-app-evidence-values>${JSON.stringify(ROW)}</script>
  </section>
  <section id="ma-tran"><h2>Ma trận</h2>
    <table><tbody><tr><td class="cell" id="marked" data-key="k|n27">2</td></tr>
      <tr id="row"><td id="empty"></td><td>1</td><td>0</td></tr>
      <tr id="row1"><td>7</td></tr></tbody></table>
    <div id="kv"><p id="blank"></p>42</div>
    <div id="pair"><span id="pair-a">46</span><span>64</span></div>
    <p class="note">Gan dài nhất: <b id="unit">565 kỳ</b></p>
  </section>
  <div id="loose"><span id="alone">99</span></div>
  <div class="tr-board"><span class="tr-number" tabindex="0" id="special">779<span id="tail" class="tr-special-tail">61</span></span></div>
  <section id="ma-tran-2">
    <div class="scroller" tabindex="0"><span id="phoi">323</span></div>
  </section>
  <section id="text-only"><h2>Ghi chú</h2><p>Không có con số nào ở đây.</p></section>
</main></body></html>`;
}

function start(t, options) {
  const dom = new JSDOM(page(options), { url: 'https://example.test/tan-suat-loto.html', runScripts: 'outside-only', pretendToBeVisual: true });
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new dom.window.Event('close')); };
  // Trình xử lý sẵn có của trang: nhấp ô [data-key] để đánh dấu.
  dom.window.document.addEventListener('click', event => {
    const cell = event.target.closest('td[data-key]');
    if (cell) cell.classList.toggle('marked');
  });
  dom.window.eval(SCRIPT);
  t.after(() => dom.window.close());
  return dom;
}
const $ = (dom, id) => dom.window.document.getElementById(id);
const drawer = dom => $(dom, 'app-evidence-drawer');
function click(dom, el, init = {}) {
  el.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init }));
}
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

test('Nhận diện đúng con số: số trong bảng, KPI; không phải ngày, câu văn, ô nhập hay khung điều hướng', t => {
  const dom = start(t), find = el => dom.window.appEvidence.find(el);
  assert.equal(find($(dom, 'prob')), $(dom, 'prob'));
  assert.equal(find($(dom, 'kpi-value')), $(dom, 'kpi-value'));
  assert.equal(find($(dom, 'kpi-value').firstChild), $(dom, 'kpi-value'));
  for (const id of ['date', 'prose', 'field', 'rail-count']) assert.equal(find($(dom, id)), null, id);
});

test('Không nhận hàng, khối hay hai số dính nhau làm "con số"; nhận số có đơn vị', t => {
  const dom = start(t), find = el => dom.window.appEvidence.find(el);
  // Ô rỗng: không được leo lên hàng có chữ "10" do hai ô "1" và "0" nối lại.
  assert.equal(find($(dom, 'empty')), null);
  assert.equal(find($(dom, 'row')), null);
  // Hàng chỉ có một ô số vẫn là hàng: con số là ô, không phải hàng.
  assert.equal(find($(dom, 'row1')), null);
  assert.equal(find($(dom, 'row1').firstElementChild), $(dom, 'row1').firstElementChild);
  // Đoạn rỗng là biên: không leo lên khối chứa số 42 ở ngoài nó.
  assert.equal(find($(dom, 'blank')), null);
  assert.equal(find($(dom, 'pair')), null);
  assert.equal(find($(dom, 'pair-a')), $(dom, 'pair-a'));
  assert.equal(find($(dom, 'unit')), $(dom, 'unit'));
  // Số dạng khoa học (chỉ số cổng mô hình trên trang bảng điều khiển).
  assert.equal(find($(dom, 'sci')), $(dom, 'sci'));
  assert.equal(find($(dom, 'sci2')), $(dom, 'sci2'));
});

test('Khung cuộn có tabindex không biến con số bên trong thành "đã có chức năng"', t => {
  const dom = start(t);
  click(dom, $(dom, 'phoi'));
  assert.equal(drawer(dom).open, true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '323');
});

test('Nhấp một con số mở ngăn kéo: giá trị, nguồn của khối, bước tính và ngữ cảnh ô', t => {
  const dom = start(t);
  click(dom, $(dom, 'prob2'));
  const d = drawer(dom);
  assert.equal(d.open, true);
  assert.equal(d.querySelector('.app-evidence-value').textContent, '23,936%');
  assert.deepEqual([...d.querySelectorAll('.app-evidence-source-title')].map(n => n.textContent),
    ['Dự báo đã công bố trước kỳ quay', 'Ngoài']);
  // Liên kết lạ (javascript:) không bao giờ thành thẻ a.
  assert.equal(d.querySelectorAll('a.app-evidence-source-title').length, 0);
  const steps = [...d.querySelectorAll('.app-evidence-steps li')].map(n => n.textContent);
  assert.deepEqual(steps.slice(0, 2), ['Trộn các thành phần.', 'Hiệu chỉnh.']);
  assert.match(steps.at(-1), /hàng «#2 · Số: 95», cột «Xác suất \(%\)»: 23,936%/);
  const ctx = [...d.querySelectorAll('.app-evidence-context dd')].map(n => n.textContent);
  assert.deepEqual(ctx, ['Tần suất LOTO', 'Bảng xác suất', '#2 · Số: 95', 'Xác suất (%)']);
  assert.equal(dom.window.document.activeElement, d.querySelector('.app-evidence-close'));
});

test('Hàng khai data-evidence-row dùng bằng chứng riêng, kèm độ tin cậy', t => {
  const dom = start(t);
  click(dom, $(dom, 'prob'));
  const d = drawer(dom);
  assert.equal(d.querySelector('h2').textContent, 'Số 63 · ML LOTO');
  assert.equal(d.querySelector('.app-evidence-source-title').textContent, 'Mô hình ML thành phần');
  assert.equal(d.querySelector('.app-evidence-meter').getAttribute('aria-valuenow'), '35');
  assert.equal(dom.window.appEvidence.evidenceFor($(dom, 'num')).reasoningTrace.confidenceScore, 0.35);
  // Cột hạng không nằm trong data-evidence-cols: không mượn bằng chứng xác suất.
  const rank = dom.window.appEvidence.evidenceFor($(dom, 'rank'));
  assert.notEqual(rank.scope, 'Số 63 · ML LOTO');
  assert.equal(rank.sources[0].title, 'Dự báo đã công bố trước kỳ quay');
});

test('Ô đã có chức năng nhấp giữ nguyên chức năng; Alt + nhấp mở bằng chứng mà không đánh dấu', t => {
  const dom = start(t), cell = $(dom, 'marked');
  click(dom, cell);
  assert.equal(cell.classList.contains('marked'), true);
  assert.equal(drawer(dom), null);
  click(dom, cell, { altKey: true });
  assert.equal(cell.classList.contains('marked'), true, 'Alt + nhấp không được chạm tới trình xử lý của trang');
  assert.equal(drawer(dom).open, true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '2');
  click(dom, $(dom, 'btn'));
  assert.equal(drawer(dom).open, true, 'nút không mở lại hay đóng ngăn kéo');
});

test('Đóng bằng nút hoặc Escape trả tiêu điểm về chỗ cũ', t => {
  const dom = start(t), btn = $(dom, 'btn');
  btn.focus();
  dom.window.appEvidence.open($(dom, 'prob'));
  drawer(dom).querySelector('.app-evidence-close').click();
  assert.equal(drawer(dom).open, false);
  assert.equal(dom.window.document.activeElement, btn);
  dom.window.appEvidence.open($(dom, 'prob'));
  drawer(dom).dispatchEvent(new dom.window.Event('cancel', { cancelable: true }));
  assert.equal(drawer(dom).open, false);
});

test('Rê chuột hiện tooltip tóm tắt nguồn và gợi ý thao tác đúng loại con số', async t => {
  const dom = start(t), tip = $(dom, 'app-evidence-tip');
  $(dom, 'kpi-value').dispatchEvent(new dom.window.MouseEvent('mouseover', { bubbles: true }));
  await wait(220);
  assert.equal(tip.hidden, false);
  assert.match(tip.textContent, /Nguồn: Sổ kết quả XSMB đã lưu/);
  assert.match(tip.textContent, /Suy luận qua 2 bước · Số kỳ/);
  assert.match(tip.textContent, /Click để xem chi tiết bằng chứng suy luận/);
  assert.equal($(dom, 'kpi-value').classList.contains('app-evidence-hot'), true);
  $(dom, 'marked').dispatchEvent(new dom.window.MouseEvent('mouseover', { bubbles: true }));
  await wait(220);
  assert.match(tip.textContent, /Alt \+ nhấp/);
  assert.equal($(dom, 'kpi-value').classList.contains('app-evidence-hot'), false);
  $(dom, 'prose').dispatchEvent(new dom.window.MouseEvent('mouseover', { bubbles: true }));
  await wait(150);
  assert.equal(tip.hidden, true);
});

test('Danh mục hỏng không làm sập trang: con số vẫn mở được, nguồn rơi về mặc định', t => {
  const dom = start(t, { registry: '{hỏng' });
  click(dom, $(dom, 'kpi-value'));
  assert.equal(drawer(dom).open, true);
  assert.match(drawer(dom).textContent, /Dữ liệu hiển thị trên chính trang này/);
});

function key(dom, target, name) {
  target.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true }));
}
const activeText = dom => dom.window.document.querySelector('.app-evidence-active')?.textContent;

test('Bàn phím: mỗi bảng/khối có số là một điểm dừng Tab, không gắn cho từng con số', t => {
  const dom = start(t), d = dom.window.document;
  const regions = [...d.querySelectorAll('[data-evidence-region]')];
  assert.ok(regions.includes(d.querySelector('#ai-ml table')));
  assert.ok(regions.includes($(dom, 'kpi')));
  assert.ok(!regions.includes($(dom, 'text-only')), 'khối không có số thì không thành điểm dừng');
  assert.ok(regions.every(r => r.getAttribute('tabindex') === '0'));
  assert.equal(d.querySelectorAll('td[tabindex], strong[tabindex]').length, 0);
  assert.match(d.querySelector('#ai-ml table').getAttribute('aria-describedby'), /app-evidence-kbd/);
});

test('Bàn phím: mũi tên chọn số theo hàng/cột, Enter mở đúng số, đóng thì tiêu điểm về bảng', t => {
  const dom = start(t), d = dom.window.document, table = d.querySelector('#ai-ml table');
  key(dom, d.body, 'Tab');
  table.focus();
  assert.equal(activeText(dom), '1');
  assert.match($(dom, 'app-evidence-tip').textContent, /Enter để xem chi tiết/);
  key(dom, table, 'ArrowRight');
  assert.equal(activeText(dom), '63');
  key(dom, table, 'ArrowRight');
  assert.equal(activeText(dom), '23,943%');
  key(dom, table, 'ArrowDown');
  assert.equal(activeText(dom), '23,936%');
  assert.match($(dom, 'app-evidence-live').textContent, /^23,936%, Xác suất \(%\)$/);
  key(dom, table, 'Home');
  assert.equal(activeText(dom), '1');
  key(dom, table, 'End');
  assert.equal(activeText(dom), '3.39239E+05');
  key(dom, table, 'ArrowUp');
  assert.equal(activeText(dom), '23,936%');
  key(dom, table, 'Enter');
  assert.equal(drawer(dom).open, true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '23,936%');
  drawer(dom).querySelector('.app-evidence-close').click();
  assert.equal(d.activeElement, table);
  assert.equal(activeText(dom), '23,936%', 'quay lại đúng số đang chọn');
});

test('Bàn phím trong khối không phải bảng: đi theo thứ tự, bỏ qua nút đã tự nhận tiêu điểm', t => {
  const dom = start(t), kpi = $(dom, 'kpi');
  key(dom, dom.window.document.body, 'Tab');
  kpi.focus();
  assert.equal(activeText(dom), '4 224');
  key(dom, kpi, 'ArrowRight');
  assert.equal(activeText(dom), '4 224', 'nút "12" có tiêu điểm riêng, không phải mục của khối');
  key(dom, kpi, ' ');
  assert.equal(drawer(dom).open, true);
});

test('Bảng dựng sau khi tải cũng thành điểm dừng bàn phím', async t => {
  const dom = start(t), d = dom.window.document;
  const late = d.createElement('table');
  const row = late.insertRow();
  row.insertCell().textContent = '88';
  $(dom, 'text-only').appendChild(late);
  await wait(400);
  assert.equal(late.getAttribute('data-evidence-region'), '');
  assert.equal(late.getAttribute('tabindex'), '0');
});

test('Con số đứng riêng thành vùng bàn phím của chính nó mà nhấp thường vẫn mở bằng chứng', t => {
  const dom = start(t), alone = $(dom, 'alone');
  assert.equal(alone.getAttribute('data-evidence-region'), '');
  assert.equal(alone.getAttribute('tabindex'), '0');
  click(dom, alone);
  assert.equal(drawer(dom).open, true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '99');
});

test('Giải tách để tô (779<span>61</span>) vẫn là một giá trị 77961, không phải 61', t => {
  const dom = start(t), special = $(dom, 'special');
  assert.equal(dom.window.appEvidence.find($(dom, 'tail')), special);
  assert.equal(dom.window.appEvidence.find(special), special);
  click(dom, $(dom, 'tail'), { altKey: true });
  assert.equal(drawer(dom).open, true);
  assert.equal(drawer(dom).querySelector('.app-evidence-value').textContent, '77961');
  // Số liền nhau KHÔNG phải phần tử kết quả vẫn bị từ chối.
  assert.equal(dom.window.appEvidence.find($(dom, 'pair')), null);
});
