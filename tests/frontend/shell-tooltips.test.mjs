import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setup } from './shell-fixture.mjs';

const settled = () => new Promise(resolve => setTimeout(resolve, 0));

test('Khung không dựng tooltip; tên nhóm và menu vẫn dùng được', () => {
  const dom = setup(), d = dom.window.document;
  assert.equal(d.querySelector('.app-rail-tooltip'), null);
  assert.equal(d.querySelector('.app-rail [title], .app-header [title]'), null);
  const tab = d.querySelector('[data-app-group="3"][role="tab"]');
  tab.click();
  assert.equal(d.getElementById('app-panel-title').textContent, 'Thống kê LOTO');
  assert.equal(tab.getAttribute('aria-label'), 'Thống kê LOTO');
  dom.window.close();
});

test('Title ban đầu thành mô tả hoặc tên truy cập, không mất mô tả đã có', () => {
  const dom = setup({ beforeShell(d) {
    d.title = 'Tên tab trình duyệt';
    const number = d.createElement('span');
    number.id = 'number'; number.textContent = '42'; number.title = 'Tần suất đã đo';
    number.setAttribute('aria-description', 'Đã công bố'); d.body.append(number);
    const button = d.createElement('button');
    button.id = 'icon-action'; button.title = 'Mở chi tiết'; d.body.append(button);
    const named = d.createElement('button');
    named.id = 'named-action'; named.setAttribute('aria-label', 'Giữ tên đã đặt');
    named.title = 'Mô tả bổ sung'; d.body.append(named);
  } }), d = dom.window.document;
  assert.equal(d.querySelector('body [title]'), null);
  assert.equal(d.getElementById('number').getAttribute('aria-description'), 'Đã công bố; Tần suất đã đo');
  assert.equal(d.getElementById('icon-action').getAttribute('aria-label'), 'Mở chi tiết');
  assert.equal(d.getElementById('named-action').getAttribute('aria-label'), 'Giữ tên đã đặt');
  assert.equal(d.getElementById('named-action').getAttribute('aria-description'), 'Mô tả bổ sung');
  assert.equal(d.title, 'Tên tab trình duyệt');
  dom.window.close();
});

test('Nội dung thêm và title đổi động đều được dọn, mô tả không tích lũy giá trị cũ', async () => {
  const dom = setup(), d = dom.window.document;
  const container = d.createElement('section'), value = d.createElement('span');
  value.textContent = '17'; value.title = 'Kỳ trước'; container.append(value); d.body.append(container);
  await settled();
  assert.equal(value.hasAttribute('title'), false);
  assert.equal(value.getAttribute('aria-description'), 'Kỳ trước');
  value.title = 'Kỳ hiện tại';
  await settled();
  assert.equal(value.hasAttribute('title'), false);
  assert.equal(value.getAttribute('aria-description'), 'Kỳ hiện tại');
  value.title = '';
  await settled();
  assert.equal(value.hasAttribute('title'), false);
  assert.equal(value.getAttribute('aria-description'), null);
  dom.window.close();
});

test('SVG giữ tên và đích aria-labelledby sau khi bỏ title native, kể cả SVG thêm sau', async () => {
  const dom = setup(), d = dom.window.document;
  const ns = 'http://www.w3.org/2000/svg';
  const svg = d.createElementNS(ns, 'svg'), title = d.createElementNS(ns, 'title');
  title.id = 'chart-name'; title.textContent = 'Biểu đồ tần suất'; svg.append(title);
  svg.setAttribute('aria-labelledby', title.id); d.body.append(svg);
  const icon = d.createElementNS(ns, 'svg'), iconTitle = d.createElementNS(ns, 'title');
  iconTitle.textContent = 'Tải xuống'; icon.append(iconTitle); d.body.append(icon);
  const point = d.createElementNS(ns, 'circle'), pointTitle = d.createElementNS(ns, 'title');
  pointTitle.textContent = 'Ngày 10: 42 lần'; point.append(pointTitle); svg.append(point);
  await settled();
  assert.equal(d.querySelector('svg title'), null);
  assert.equal(svg.getAttribute('aria-labelledby'), 'chart-name');
  assert.equal(d.getElementById('chart-name').textContent, 'Biểu đồ tần suất');
  assert.equal(d.getElementById('chart-name').localName, 'desc');
  assert.equal(icon.getAttribute('aria-label'), 'Tải xuống');
  assert.equal(point.getAttribute('aria-label'), 'Ngày 10: 42 lần');
  dom.window.close();
});
