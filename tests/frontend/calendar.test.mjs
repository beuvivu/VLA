import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const source = readFileSync(process.env.APP_CALENDAR_ENGINE || new URL('../../src/templates/vietnamese_calendar.js', import.meta.url), 'utf8');
const context = vm.createContext({ Intl, Date });
vm.runInContext(source, context);
const engine = context.AppVietnameseCalendar;

test('ngày âm Việt Nam: Tết, Trung thu và tháng nhuận', () => {
  const fixtures = [
    ['1984-02-02', 1, 1, 1984, false], ['1985-01-21', 1, 1, 1985, false],
    ['2004-03-21', 1, 2, 2004, true], ['2024-02-10', 1, 1, 2024, false],
    ['2025-01-29', 1, 1, 2025, false], ['2025-07-25', 1, 6, 2025, true],
    ['2026-02-17', 1, 1, 2026, false], ['2026-09-25', 15, 8, 2026, false],
  ];
  for (const [iso, day, month, year, leap] of fixtures) {
    const lunar = engine.getDay(iso).lunar;
    assert.deepEqual(JSON.parse(JSON.stringify(lunar)), { day, month, year, leap }, iso);
  }
});

test('can chi, ngày lễ và sáu giờ hoàng đạo có dữ liệu thực', () => {
  const day = engine.getDay('2024-02-10');
  assert.equal(day.canChi.year, 'Giáp Thìn');
  assert.equal(day.canChi.month, 'Bính Dần');
  assert.equal(day.canChi.day, 'Giáp Thìn');
  assert.equal(day.hours.length, 6);
  assert.ok(day.holidays.includes('Tết Nguyên đán'));
  assert.ok(engine.getDay('2026-09-25').holidays.includes('Tết Trung thu'));
  assert.equal(engine.getDay('2025-07-25').holidays.includes('Mùng một'), false);
});

test('ngày hiện tại dựa vào UTC+7 và từ chối ngày không hợp lệ', () => {
  assert.equal(engine.todayISO(new Date('2026-09-25T17:01:00Z')), '2026-09-26');
  assert.equal(engine.todayISO(new Date('2026-09-25T16:59:00Z')), '2026-09-25');
  for (const iso of ['2026-02-29', '2026-13-01', '2026-00-12', '1899-12-31', '2100-01-01', '<script>']) {
    assert.equal(engine.getDay(iso), null, iso);
  }
  assert.ok(engine.getDay('2024-02-29'));
});

test('điểm sóc gần đầu ngày không sinh ngày âm bằng 0 hoặc tháng dài 31 ngày', () => {
  for (const iso of ['2054-05-07', '2062-04-09', '2072-12-09', '2077-11-15']) {
    const lunar = engine.getDay(iso).lunar;
    assert.ok(lunar.day >= 1 && lunar.day <= 30, iso);
  }
  assert.deepEqual(JSON.parse(JSON.stringify(engine.getDay('2062-04-09').lunar)),
    { day: 30, month: 2, year: 2062, leap: false });
  assert.deepEqual(JSON.parse(JSON.stringify(engine.getDay('2033-12-22').lunar)),
    { day: 1, month: 11, year: 2033, leap: true });
});

const fixture = execFileSync('python3', ['-c', 'from pathlib import Path\nfrom calendar_widget import render_calendar\nprint(render_calendar(Path(".")))'], {
  cwd: fileURLToPath(new URL('../../', import.meta.url)), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
});
const widgetSource = readFileSync(new URL('../../src/templates/calendar_widget.js', import.meta.url), 'utf8');
function setup(t, payload = { latest: '2026-09-25', results: { '2026-09-25': '34465', '2026-09-01': '00001', '2026-09-02': '00000' } }) {
  const dom = new JSDOM(fixture, { url: 'https://example.test/index.html', runScripts: 'outside-only', pretendToBeVisual: true });
  t.after(() => dom.window.close());
  dom.window.Date = class extends Date {
    constructor(...args) { super(...(args.length ? args : ['2026-09-26T09:00:00Z'])); }
    static now() { return Date.parse('2026-09-26T09:00:00Z'); }
  };
  dom.window.document.getElementById('app-calendar-data').textContent = JSON.stringify(payload);
  dom.window.eval(source);
  dom.window.eval(widgetSource);
  return dom;
}
function change(dom, id, value) {
  const input = dom.window.document.getElementById(`app-calendar-${id}`);
  input.value = value;
  input.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
}

test('lịch thật có giải đủ 5 số, số 0 đầu, chi tiết âm lịch và trạng thái thiếu', t => {
  const dom = setup(t), d = dom.window.document;
  assert.equal(d.querySelectorAll('[data-calendar-date]').length, 35);
  assert.equal(d.querySelectorAll('[data-calendar-date][tabindex="0"]').length, 1);
  assert.match(d.getElementById('app-calendar-detail').textContent, /34465/);
  assert.match(d.getElementById('app-calendar-detail').textContent, /Tết Trung thu/);
  d.querySelector('[data-calendar-date="2026-09-01"]').click();
  assert.equal(d.querySelector('.app-calendar-special-number').textContent, '00001');
  d.querySelector('[data-calendar-date="2026-09-02"]').click();
  assert.equal(d.querySelector('.app-calendar-special-number').textContent, '00000');
  d.querySelector('[data-calendar-date="2026-09-26"]').click();
  assert.match(d.querySelector('.app-calendar-no-result').textContent, /Chưa có kết quả/);
  d.querySelector('[data-calendar-date="2026-09-27"]').click();
  assert.match(d.querySelector('.app-calendar-no-result').textContent, /Chưa đến ngày quay/);
});

test('chọn tháng, năm nhuận, bàn phím qua năm và nút hôm nay', t => {
  const dom = setup(t, { latest: '2024-01-31', results: {} }), d = dom.window.document;
  d.getElementById('app-calendar-next').click();
  assert.equal(d.querySelector('[tabindex="0"]').dataset.calendarDate, '2024-02-29');
  change(dom, 'year', '2025');
  assert.equal(d.querySelector('[tabindex="0"]').dataset.calendarDate, '2025-02-28');
  change(dom, 'month', '12');
  d.querySelector('[data-calendar-date="2025-12-31"]').click();
  d.activeElement.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal(d.activeElement.dataset.calendarDate, '2026-01-01');
  d.getElementById('app-calendar-today').click();
  assert.equal(d.querySelector('[tabindex="0"]').dataset.calendarDate, '2026-09-26');
});

test('giới hạn năm, dữ liệu trống và chuỗi chèn mã không phá lịch', t => {
  const dom = setup(t, { latest: '1900-01-01', results: { '1900-01-01': '<img>', '__proto__': '12345', '1900-01-02': 12345 } }), d = dom.window.document;
  assert.equal(d.getElementById('app-calendar-prev').disabled, true);
  assert.equal(d.querySelectorAll('img').length, 0);
  assert.equal(d.querySelectorAll('.app-calendar-result').length, 0);
  change(dom, 'year', '3000');
  assert.equal(d.getElementById('app-calendar-year').value, '1900');
  assert.match(d.getElementById('app-calendar-summary').textContent, /1900 đến 2099/);
  change(dom, 'year', '2099'); change(dom, 'month', '12');
  assert.equal(d.getElementById('app-calendar-next').disabled, true);
});
