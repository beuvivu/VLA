import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const script = new URL('src/assets/vietlott-comparison.js', root);
const main = [1, 2, 3, 4, 5, 6];
const plain = value => JSON.parse(JSON.stringify(value));

function setup(product = 'mega645', reducedMotion = false) {
  const dom = new JSDOM('<!doctype html><main></main>', {
    url: 'https://example.test/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const w = dom.window, d = w.document;
  w.matchMedia = () => ({ matches: reducedMotion });
  const form = d.createElement('form');
  form.dataset.vlComparisonWidget = product;
  for (const name of ['prediction', 'actual', 'predicted-bonus', 'actual-bonus']) {
    const input = d.createElement('input');
    input.setAttribute(`data-vl-${name}`, '');
    form.appendChild(input);
  }
  const button = d.createElement('button');
  button.type = 'submit'; button.className = 'vl-button';
  button.setAttribute('data-vl-comparison-submit', '');
  button.textContent = 'Đối chiếu'; form.appendChild(button);
  for (const name of ['output', 'status']) {
    const element = d.createElement('div');
    element.setAttribute(`data-vl-comparison-${name}`, '');
    form.appendChild(element);
  }
  d.querySelector('main').appendChild(form);
  w.eval(readFileSync(script, 'utf8'));
  return { dom, w, d, form, button,
    compare: (...args) => w.vietlottComparison.comparePrediction(...args),
    input: name => form.querySelector(`[data-vl-${name}]`),
    submit: () => form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true })),
    output: form.querySelector('[data-vl-comparison-output]'),
    status: form.querySelector('[data-vl-comparison-status]'),
  };
}

test('Mega tính giao hai tập hợp, không đổi đầu vào và nhận số có chữ số 0 đầu', () => {
  const f = setup();
  const predicted = Object.freeze(['01', '02', 3, 4, 5, 6]);
  const actual = Object.freeze([6, 2, 1, 7, 8, 9]);
  const result = f.compare('mega645', predicted, actual);
  assert.equal(result.hits, 3);
  assert.equal(result.total, 6);
  assert.equal(result.accuracy, 50);
  assert.deepEqual(plain(result.matchedNumbers), [1, 2, 6]);
  assert.equal(result.bonusMatched, false);
  assert.equal(result.tier, 'third');
  assert.deepEqual(predicted, ['01', '02', 3, 4, 5, 6]);
  f.dom.window.close();
});

test('Mọi mức Mega và Power khớp quy tắc engine; Jackpot 2 chỉ khi 5 số chính cùng số đặc biệt', () => {
  const f = setup();
  const expected = [null, null, null, 'third', 'second', 'first', 'jackpot1'];
  for (let hits = 0; hits <= 6; hits++) {
    const actual = [...main.slice(0, hits), ...[11, 12, 13, 14, 15, 16].slice(hits)];
    const mega = f.compare('mega645', main, actual);
    const power = f.compare('power655', main, actual, { actualBonus: 55 });
    assert.equal(mega.tier, expected[hits]);
    assert.equal(power.tier, expected[hits]);
    assert.equal(mega.accuracy, hits / 6 * 100);
    if (hits < 6) {
      const withBonus = f.compare('power655', main, actual, { actualBonus: 6 });
      assert.equal(withBonus.bonusMatched, true);
      assert.equal(withBonus.hits, hits);
      assert.equal(withBonus.accuracy, hits / 6 * 100);
      assert.equal(withBonus.tier, hits === 5 ? 'jackpot2' : expected[hits]);
    }
  }
  f.dom.window.close();
});

test('Lotto giữ mẫu số 5 và phân biệt đủ bảy mức giải theo số đặc biệt', () => {
  const f = setup('lotto535');
  const predicted = main.slice(0, 5);
  const plainTiers = [null, null, null, 'fifth', 'third', 'first'];
  const bonusTiers = ['consolation', 'consolation', 'consolation', 'fourth', 'second', 'jackpot1'];
  for (let hits = 0; hits <= 5; hits++) {
    const actual = [...predicted.slice(0, hits), ...[21, 22, 23, 24, 25].slice(hits)];
    for (const bonusMatched of [false, true]) {
      const result = f.compare('lotto535', predicted, actual, { predictedBonus: '01', actualBonus: bonusMatched ? 1 : 12 });
      assert.equal(result.tier, (bonusMatched ? bonusTiers : plainTiers)[hits]);
      assert.equal(result.bonusMatched, bonusMatched);
      assert.equal(result.accuracy, hits / 5 * 100);
      assert.equal(result.total, 5);
    }
  }
  assert.equal(f.compare('lotto535', predicted, predicted, { predictedBonus: 1, actualBonus: 1 }).tier, 'jackpot1');
  f.dom.window.close();
});

test('Bộ số thiếu, trùng, ngoài miền, thập phân hoặc chuỗi lỗi bị từ chối ở cả hai mảng', () => {
  const f = setup();
  const invalid = [
    [], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6, 7],
    [1, '01', 3, 4, 5, 6], [0, 2, 3, 4, 5, 6], [46, 2, 3, 4, 5, 6],
    ['', 2, 3, 4, 5, 6], [' ', 2, 3, 4, 5, 6], [1.5, 2, 3, 4, 5, 6],
    ['1.0', 2, 3, 4, 5, 6], ['1e0', 2, 3, 4, 5, 6], ['+1', 2, 3, 4, 5, 6],
    ['1x', 2, 3, 4, 5, 6], [null, 2, 3, 4, 5, 6], [true, 2, 3, 4, 5, 6],
    [NaN, 2, 3, 4, 5, 6], [Infinity, 2, 3, 4, 5, 6], '1 2 3 4 5 6',
    [1, 2, 3, 4, 5, ,], Array(6), [1n, 2, 3, 4, 5, 6], [new Number(1), 2, 3, 4, 5, 6],
  ];
  for (const numbers of invalid) {
    assert.throws(() => f.compare('mega645', numbers, main));
    assert.throws(() => f.compare('mega645', main, numbers));
  }
  assert.throws(() => f.compare('unknown', main, main));
  assert.throws(() => f.compare('__proto__', main, main));
  assert.throws(() => f.compare('lotto535', [1, 2, 3, 4, 36], [1, 2, 3, 4, 5], { predictedBonus: 1, actualBonus: 2 }));
  assert.equal(f.compare('power655', [1, 2, 3, 4, 5, 55], main, { actualBonus: 54 }).hits, 5);
  f.dom.window.close();
});

test('Hai mảng chính đủ để tính tỷ lệ; thiếu số đặc biệt giữ mức giải chưa xác định', () => {
  const f = setup();
  for (const absent of [undefined, null, '', ' ']) {
    const power = f.compare('power655', main, [1, 2, 3, 4, 5, 7], { actualBonus: absent });
    assert.equal(power.hits, 5);
    assert.equal(power.accuracy, 5 / 6 * 100);
    assert.equal(power.bonusMatched, null);
    assert.equal(power.tierKnown, false);
    assert.equal(power.tier, null);
    assert.match(power.tierLabel, /Chưa đủ số đặc biệt/);
    for (const options of [{}, { predictedBonus: 1, actualBonus: absent }, { predictedBonus: absent, actualBonus: 1 }]) {
      const lotto = f.compare('lotto535', main.slice(0, 5), main.slice(0, 5), options);
      assert.equal(lotto.accuracy, 100);
      assert.equal(lotto.bonusMatched, null);
      assert.equal(lotto.tierKnown, false);
      assert.equal(lotto.tier, null);
    }
  }
  assert.equal(f.compare('mega645', main, main).tierKnown, true);
  assert.equal(f.compare('power655', main, main, { actualBonus: 55 }).tierKnown, true);
  assert.throws(() => f.compare('lotto535', main.slice(0, 5), main.slice(0, 5), { predictedBonus: 13 }));
  assert.throws(() => f.compare('lotto535', main.slice(0, 5), main.slice(0, 5), { actualBonus: 0 }));
  f.dom.window.close();
});

test('Số đặc biệt được kiểm riêng; không nhận số thứ bảy Power hoặc số trùng kết quả chính', () => {
  const f = setup();
  for (const actualBonus of [0, 56, 1.2, '2x', 6]) {
    assert.throws(() => f.compare('power655', main, main, { actualBonus }));
  }
  assert.throws(() => f.compare('power655', main, [1, 2, 3, 4, 5, 7], { predictedBonus: 8, actualBonus: 6 }));
  assert.throws(() => f.compare('mega645', main, main, { actualBonus: 7 }));
  for (const bad of [0, 13, '1.1']) {
    assert.throws(() => f.compare('lotto535', main.slice(0, 5), main.slice(0, 5), { predictedBonus: bad, actualBonus: 1 }));
    assert.throws(() => f.compare('lotto535', main.slice(0, 5), main.slice(0, 5), { predictedBonus: 1, actualBonus: bad }));
  }
  f.dom.window.close();
});

test('Submit dựng hai hàng số, phần trăm và mức giải với thông báo trực tiếp truy cập được', () => {
  const f = setup();
  f.input('prediction').value = '01 02 03 04 05 06';
  f.input('actual').value = '01, 02, 03, 07, 08, 09';
  f.submit();
  assert.equal(f.output.hidden, false);
  assert.equal(f.output.querySelectorAll('.vl-compare-sequence').length, 2);
  assert.equal(f.output.querySelectorAll('.vl-ball--match').length, 6);
  assert.match(f.output.querySelector('.vl-comparison-score').textContent, /3\s*\/\s*6.*50\s*%/);
  assert.match(f.output.querySelector('.vl-comparison-tier').textContent, /Giải ba/);
  assert.equal(f.output.querySelector('[data-vl-comparison-score]').dataset.vlComparisonHits, '3');
  assert.equal(f.output.querySelector('[data-vl-comparison-score]').dataset.vlComparisonAccuracy, '50');
  assert.equal(f.output.querySelector('[data-vl-comparison-tier]').dataset.vlComparisonTier, 'third');
  assert.match(f.status.textContent, /đối chiếu.*hồi cứu/i);
  assert.match(f.status.textContent, /không.*dự báo.*đăng ký/i);
  assert.equal(f.status.getAttribute('aria-live'), 'polite');
  assert.equal(f.status.getAttribute('aria-atomic'), 'true');
  f.dom.window.close();
});

test('Power tô riêng số đặc biệt; tỷ lệ vẫn chỉ là 5/6', () => {
  const f = setup('power655');
  f.input('prediction').value = '1 2 3 4 5 6';
  f.input('actual').value = '1 2 3 4 5 7';
  f.input('actual-bonus').value = '6';
  f.submit();
  assert.match(f.output.textContent, /Jackpot 2/);
  assert.match(f.output.querySelector('.vl-comparison-score').textContent, /5\s*\/\s*6.*83,33\s*%/);
  assert.equal(f.output.querySelectorAll('.vl-ball--bonus-hit').length, 2);
  assert.equal(f.output.querySelectorAll('.vl-ball--match').length, 10);
  f.dom.window.close();
});

test('Lotto tô hai số đặc biệt và giữ tỷ lệ số chính khi chỉ trúng khuyến khích', () => {
  const f = setup('lotto535');
  f.input('prediction').value = '1 2 3 4 5';
  f.input('actual').value = '21 22 23 24 25';
  f.input('predicted-bonus').value = '01';
  f.input('actual-bonus').value = '1';
  f.submit();
  assert.match(f.output.textContent, /Khuyến khích/);
  assert.match(f.output.querySelector('.vl-comparison-score').textContent, /0\s*\/\s*5.*0\s*%/);
  assert.equal(f.output.querySelectorAll('.vl-ball--bonus-hit').length, 2);
  f.dom.window.close();
});

test('Kết quả thiếu là chờ đối chiếu, không tạo tỷ lệ 0% hoặc giữ điểm kỳ trước', () => {
  for (const product of ['mega645', 'power655', 'lotto535']) {
    const f = setup(product);
    f.input('prediction').value = product === 'lotto535' ? '1 2 3 4 5' : '1 2 3 4 5 6';
    f.submit();
    assert.equal(f.output.children.length, 0);
    assert.equal(f.output.hidden, true);
    assert.match(f.status.textContent, /Chưa có kết quả thực tế/);
    assert.doesNotMatch(f.status.textContent, /0\s*%/);
    f.input('actual').value = f.input('prediction').value;
    if (product !== 'mega645') {
      f.submit();
      assert.ok(f.output.querySelector('.vl-comparison-score'));
      assert.equal(f.output.hidden, false);
      assert.match(f.status.textContent, /Chưa đủ số đặc biệt/);
      assert.match(f.output.querySelector('.vl-comparison-bonus-status').textContent, /chưa đủ dữ liệu/);
      f.input('actual-bonus').value = product === 'power655' ? '55' : '1';
      if (product === 'lotto535') f.input('predicted-bonus').value = '1';
    }
    f.submit();
    assert.ok(f.output.querySelector('.vl-comparison-score'));
    assert.equal(f.output.hidden, false);
    f.input('actual').value = ''; f.submit();
    assert.equal(f.output.children.length, 0);
    assert.equal(f.output.hidden, true);
    f.dom.window.close();
  }
});

test('Dữ liệu sai xóa điểm cũ và chỉ hiển thị lỗi văn bản, không dựng phần tử từ dữ liệu nhập', () => {
  const f = setup();
  f.input('prediction').value = f.input('actual').value = '1 2 3 4 5 6';
  f.submit();
  f.input('prediction').value = '1 1 3 4 5 6'; f.submit();
  assert.equal(f.output.children.length, 0);
  assert.equal(f.output.hidden, true);
  assert.match(f.status.textContent, /khác nhau/);
  f.input('prediction').value = '<img src=x onerror=alert(1)> 2 3 4 5 6'; f.submit();
  assert.equal(f.output.children.length, 0);
  assert.equal(f.form.querySelectorAll('img,script').length, 0);
  f.dom.window.close();
});

test('Ripple chỉ theo nút Vietlott, tự dọn khi kết thúc và tôn trọng giảm chuyển động', () => {
  for (const reduced of [false, true]) {
    const f = setup('mega645', reduced);
    f.button.dispatchEvent(new f.w.MouseEvent('pointerdown', { bubbles: true, clientX: 12, clientY: 8 }));
    const ripple = f.button.querySelector('.vl-button-ripple');
    assert.equal(Boolean(ripple), !reduced);
    if (ripple) {
      assert.equal(ripple.getAttribute('aria-hidden'), 'true');
      ripple.dispatchEvent(new f.w.Event('animationend'));
      assert.equal(f.button.querySelector('.vl-button-ripple'), null);
    }
    const outside = f.d.createElement('button'); f.d.body.appendChild(outside);
    outside.dispatchEvent(new f.w.MouseEvent('pointerdown', { bubbles: true }));
    assert.equal(outside.querySelector('.vl-button-ripple'), null);
    f.button.disabled = true;
    f.button.dispatchEvent(new f.w.MouseEvent('pointerdown', { bubbles: true }));
    assert.equal(f.button.querySelector('.vl-button-ripple'), null);
    f.dom.window.close();
  }
});
