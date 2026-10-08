import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
function setup(product = 'mega-645') {
  const dom = new JSDOM(readFileSync(new URL(`docs/vietlott-${product}.html`, root), 'utf8'), {
    url: 'https://example.test/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const w = dom.window, d = w.document;
  const board = d.querySelector('[data-vl-picks]');
  assert.ok(board, 'Trang thật phải có bộ chọn số');
  w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  w.HTMLDialogElement.prototype.close = function () {
    this.open = false; this.dispatchEvent(new w.Event('close'));
  };
  const downloads = [];
  w.URL.createObjectURL = blob => { downloads.push(blob); return 'blob:local-draft'; };
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = function () { downloads.push(this.download); };
  w.eval(readFileSync(process.env.VIETLOTT_PICKS_SCRIPT || new URL('src/assets/vietlott-picks.js', root), 'utf8'));
  return { dom, w, d, board, downloads,
    number: n => board.querySelector(`[data-vl-number="${n}"]`),
    selected: () => [...board.querySelectorAll('[data-vl-number][aria-pressed="true"]')].map(b => Number(b.dataset.vlNumber)),
  };
}

test('Chỉ chọn sáu số khác nhau; bỏ chọn giải phóng đúng một chỗ', () => {
  const f = setup();
  for (let n = 1; n <= 7; n++) f.number(n).click();
  assert.deepEqual(f.selected(), [1, 2, 3, 4, 5, 6]);
  assert.equal(f.board.querySelector('[data-vl-review]').disabled, false);
  assert.match(f.board.querySelector('[data-vl-status]').textContent, /6 số/);
  f.number(3).click(); f.number(7).click();
  assert.deepEqual(f.selected(), [1, 2, 4, 5, 6, 7]);
  f.dom.window.close();
});

test('Chọn nhanh đúng miền Mega/Power; xóa đưa nút xem trước về trạng thái khóa', () => {
  for (const [product, maximum] of [['mega-645', 45], ['power-655', 55]]) {
    const f = setup(product);
    assert.equal(f.number(maximum).textContent.trim(), String(maximum));
    for (let i = 0; i < 12; i++) {
      f.board.querySelector('[data-vl-random]').click();
      const values = f.selected();
      assert.equal(values.length, 6);
      assert.equal(new Set(values).size, 6);
      assert.ok(values.every(n => n >= 1 && n <= maximum));
    }
    f.board.querySelector('[data-vl-clear]').click();
    assert.deepEqual(f.selected(), []);
    assert.equal(f.board.querySelector('[data-vl-review]').disabled, true);
    assert.equal(f.board.querySelector('[data-vl-count]').textContent, '0 / 6');
    f.dom.window.close();
  }
});

test('Bàn phím dùng một điểm Tab; mũi tên, Home/End và phím chọn hoạt động', () => {
  const f = setup();
  const press = key => f.d.activeElement.dispatchEvent(new f.w.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
  f.number(1).focus(); press('ArrowRight');
  assert.equal(f.d.activeElement, f.number(2));
  press('ArrowDown'); assert.equal(f.d.activeElement, f.number(11));
  press('End'); assert.equal(f.d.activeElement, f.number(45));
  press('Home'); assert.equal(f.d.activeElement, f.number(1));
  assert.equal(f.board.querySelectorAll('[data-vl-number][tabindex="0"]').length, 1);
  f.number(1).click(); assert.deepEqual(f.selected(), [1]);
  f.dom.window.close();
});

test('Xem trước và tải chỉ bộ số hiện tại; đóng dialog trả focus và không mất lựa chọn', async () => {
  const f = setup();
  for (const n of [40, 2, 12, 4, 8, 45]) f.number(n).click();
  const review = f.board.querySelector('[data-vl-review]');
  review.click();
  const dialog = f.board.querySelector('dialog');
  assert.equal(dialog.open, true);
  assert.equal(dialog.querySelector('[data-vl-preview]').textContent, '02 · 04 · 08 · 12 · 40 · 45');
  dialog.querySelector('[data-vl-download]').click();
  assert.equal(f.downloads.length, 2);
  assert.equal(f.downloads[1], 'mega645-bo-so-nhap.txt');
  const content = await new Promise(resolve => {
    const reader = new f.w.FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(f.downloads[0]);
  });
  assert.match(content, /Mega 6\/45/);
  assert.match(content, /02 04 08 12 40 45/);
  assert.match(content, /BỘ SỐ NHÁP/);
  assert.doesNotMatch(content, /đã thanh toán|đã đặt cược|Jackpot/i);
  dialog.close();
  assert.equal(f.d.activeElement, review);
  f.d.documentElement.classList.add('dark');
  assert.deepEqual(f.selected(), [2, 4, 8, 12, 40, 45]);
  f.dom.window.close();
});
