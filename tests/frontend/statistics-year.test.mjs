import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { JSDOM } from 'jsdom';

// Chạy bộ dựng thật để kiểm bộ lọc trên đúng cấu trúc lịch được xuất bản.
function calendar(mobile = false) {
  const fixture = JSON.parse(execFileSync(process.env.APP_TEST_PYTHON || 'python3', ['-c', `
import json, sys
sys.path.insert(0, 'src')
import pandas as pd
import build_statistics_dashboard as d
assert hasattr(d, '_DASHBOARD_SCRIPT_YEAR'), 'Thiếu điều khiển lịch năm'
raw = pd.DataFrame({'date': ['2024-02-29', '2024-03-01', '2026-01-01'], 'special': ['04789', '00001', '']})
print(json.dumps({'markup': d._board_year_table(raw), 'script': d._DASHBOARD_SCRIPT_YEAR}))
`], { cwd: new URL('../..', import.meta.url), encoding: 'utf8' }));
  const dom = new JSDOM(fixture.markup, { runScripts: 'outside-only' });
  dom.window.matchMedia = () => ({ matches: mobile });
  dom.window.eval(fixture.script);
  return dom;
}

test('đổi năm và lọc số gốc giữ đúng lịch nhuận, thông báo và bộ lọc', () => {
  const dom = calendar();
  const { document, Event } = dom.window;
  const year = document.querySelector('select');
  const input = document.querySelector('input');
  const status = document.querySelector('[data-app-year-status]');
  assert.match(status.textContent, /0 kết quả.*2026/);
  year.value = '2024';
  year.dispatchEvent(new Event('change'));
  assert.equal(document.querySelector('[data-app-year="2026"]').hidden, true);
  assert.equal(document.querySelector('[data-app-year="2024"]').hidden, false);
  assert.match(status.textContent, /2 kết quả.*2024/);
  input.value = '04789';
  input.dispatchEvent(new Event('input'));
  assert.match(status.textContent, /1 kết quả khớp.*2024/);
  assert.equal(document.querySelector('[data-app-year="2024"] [data-app-day="29"]').hidden, false);
  assert.equal(document.querySelector('[data-app-year="2024"] [data-app-day="01"]').hidden, true);
  assert.equal(document.querySelector('[data-app-date="2024-02-29"]').classList.contains('app-year-match'), true);
  year.value = '2026';
  year.dispatchEvent(new Event('change'));
  assert.equal(document.querySelector('[data-app-year-no-match]').hidden, false);
  assert.match(status.textContent, /0 kết quả khớp.*2026/);
  input.value = '';
  input.dispatchEvent(new Event('input'));
  assert.equal(document.querySelector('[data-app-year-no-match]').hidden, true);
  assert.equal(document.querySelectorAll('[data-app-year="2026"] tbody tr[hidden]').length, 0);
  assert.equal(document.querySelector('[data-app-date="2024-02-29"]').textContent, '04789');
  dom.window.close();
});

test('điện thoại mặc định tháng mới nhất và có thể chọn lại đủ 12 tháng', () => {
  const dom = calendar(true);
  const { document, Event } = dom.window;
  const year = document.querySelector('[data-app-year-select]');
  const month = document.querySelector('[data-app-month-select]');
  assert.ok(month, 'Thiếu chế độ xem riêng tháng');
  assert.equal(month.value, '01');
  year.value = '2024';
  year.dispatchEvent(new Event('change'));
  assert.equal(month.value, '03');
  const panel = document.querySelector('[data-app-year="2024"]');
  assert.equal(panel.classList.contains('app-year-single-month'), true);
  assert.equal(panel.querySelectorAll('thead th:not([hidden])').length, 2);
  assert.match(document.querySelector('[data-app-year-status]').textContent, /1 kết quả.*2024.*tháng 03/);
  month.value = '02';
  month.dispatchEvent(new Event('change'));
  assert.equal(panel.querySelector('[data-app-date="2024-02-29"]').hidden, false);
  assert.equal(panel.querySelector('[data-app-date="2024-03-01"]').hidden, true);
  month.value = '';
  month.dispatchEvent(new Event('change'));
  assert.equal(panel.classList.contains('app-year-single-month'), false);
  assert.equal(panel.querySelectorAll('thead th:not([hidden])').length, 13);
  assert.match(document.querySelector('[data-app-year-status]').textContent, /2 kết quả.*2024/);
  dom.window.close();
});
