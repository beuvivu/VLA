(function () {
  'use strict';
  const root = document.getElementById('app-calendar');
  const engine = globalThis.AppVietnameseCalendar;
  if (!root || !engine) return;
  let payload;
  try { payload = JSON.parse(document.getElementById('app-calendar-data').textContent); }
  catch (_) { root.textContent = 'Không đọc được dữ liệu lịch. Vui lòng tải lại trang.'; return; }
  const results = Object.create(null);
  for (const [date, value] of Object.entries(payload.results || {})) {
    if (engine.getDay(date) && typeof value === 'string' && /^\d{5}$/.test(value)) results[date] = value;
  }
  const weekdays = ['Chủ nhật', 'Thứ hai', 'Thứ ba', 'Thứ tư', 'Thứ năm', 'Thứ sáu', 'Thứ bảy'];
  const $ = id => document.getElementById(`app-calendar-${id}`);
  const monthInput = $('month'), yearInput = $('year'), days = $('days'), detail = $('detail');
  const latest = engine.getDay(payload.latest) ? payload.latest : '';
  let today = engine.todayISO(), selected = latest || today;
  if (!engine.getDay(selected)) selected = '2026-01-01';
  let viewYear = Number(selected.slice(0, 4)), viewMonth = Number(selected.slice(5, 7));
  const civil = (year, month, day) => new Date(Date.UTC(year, month - 1, day)).toISOString().slice(0, 10);
  const monthLength = (year, month) => new Date(Date.UTC(year, month, 0)).getUTCDate();
  const formatDate = iso => iso.split('-').reverse().join('/');

  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function state(iso) {
    if (Object.hasOwn(results, iso)) return `Đặc Biệt ${results[iso]}`;
    return iso > today ? 'Chưa đến ngày quay' : 'Chưa có kết quả';
  }
  function specialNumber(value, className) {
    const item = node('span', className);
    item.append(document.createTextNode(value.slice(0, 3)), node('b', '', value.slice(3)));
    return item;
  }
  function field(label, value) {
    const item = node('div', 'app-calendar-fact');
    item.append(node('dt', '', label), node('dd', '', value));
    return item;
  }
  function renderDetail() {
    const info = engine.getDay(selected), { solar, lunar } = info;
    const header = node('div', 'app-calendar-day-heading');
    const headline = node('div');
    headline.append(node('p', 'app-calendar-eyebrow', weekdays[solar.weekday]),
      node('h4', '', `${String(solar.day).padStart(2, '0')} / ${String(solar.month).padStart(2, '0')} / ${solar.year}`));
    header.append(headline, node('span', 'app-calendar-day-badge', selected === today ? 'Hôm nay' : 'Đang chọn'));
    const lunarBlock = node('div', 'app-calendar-lunar-detail');
    lunarBlock.append(node('span', 'app-calendar-lunar-number', String(lunar.day)),
      node('span', '', `Tháng ${lunar.month}${lunar.leap ? ' nhuận' : ''} âm lịch`),
      node('small', '', `Năm ${info.canChi.year} · ${lunar.year}`));
    const prize = node('div', 'app-calendar-special');
    prize.append(node('span', 'app-calendar-eyebrow', 'GIẢI ĐẶC BIỆT'));
    if (Object.hasOwn(results, selected)) {
      prize.append(specialNumber(results[selected], 'app-calendar-special-number'),
        node('small', '', `Hai số cuối: ${results[selected].slice(-2)}`));
    } else {
      prize.append(node('p', 'app-calendar-no-result', state(selected)),
        node('small', '', selected > today ? 'Kết quả được cập nhật sau kỳ quay.' : 'Dữ liệu đã lưu chưa có kết quả ngày này.'));
    }
    const facts = node('dl', 'app-calendar-facts');
    facts.append(field('Ngày', info.canChi.day), field('Tháng', info.canChi.month),
      field('Năm', info.canChi.year), field('Tiết khí', `${info.termChange ? 'Vào tiết ' : ''}${info.term}`));
    const events = node('div', 'app-calendar-events');
    const labels = [...info.holidays];
    if (lunar.day === 1) labels.push('Mùng một');
    if (lunar.day === 15) labels.push('Ngày rằm');
    if (labels.length) labels.forEach(label => events.append(node('span', 'app-calendar-event', label)));
    else events.append(node('span', 'app-calendar-quiet-day', 'Không có ngày lễ trong lịch'));
    const hourBlock = node('section', 'app-calendar-hours');
    hourBlock.append(node('h5', '', 'Giờ hoàng đạo'));
    const hours = node('div', 'app-calendar-hour-grid');
    info.hours.forEach(hour => {
      const item = node('div');
      item.append(node('b', '', hour.name), node('span', '', hour.range));
      hours.append(item);
    });
    hourBlock.append(hours, node('p', 'app-calendar-hint', 'Theo lịch dân gian · Giờ Việt Nam. Giờ Tý bắt đầu từ 23:00 hôm trước.'));
    detail.replaceChildren(header, lunarBlock, prize, facts, events, hourBlock);
  }
  function render(focus = false) {
    today = engine.todayISO();
    const first = new Date(Date.UTC(viewYear, viewMonth - 1, 1));
    const offset = (first.getUTCDay() + 6) % 7;
    const count = monthLength(viewYear, viewMonth);
    const total = Math.ceil((offset + count) / 7) * 7;
    const fragment = document.createDocumentFragment();
    let monthResults = 0;
    for (let i = 0; i < total; i += 7) {
      const row = node('div', 'app-calendar-week');
      row.setAttribute('role', 'row');
      for (let j = 0; j < 7; j += 1) {
        const iso = civil(viewYear, viewMonth, i + j - offset + 1), info = engine.getDay(iso);
        const cell = node('div', 'app-calendar-cell');
        cell.setAttribute('role', 'gridcell');
        if (!info) { cell.setAttribute('aria-disabled', 'true'); row.append(cell); continue; }
        const ownMonth = info.solar.month === viewMonth;
        const chosen = selected === iso;
        cell.setAttribute('aria-selected', String(chosen));
        const button = node('button', 'app-calendar-day');
        button.type = 'button';
        button.dataset.calendarDate = iso;
        button.tabIndex = chosen ? 0 : -1;
        if (!ownMonth) button.classList.add('is-outside');
        if (j >= 5) button.classList.add('is-weekend');
        if (chosen) button.classList.add('is-selected');
        if (iso === today) { button.classList.add('is-today'); button.setAttribute('aria-current', 'date'); }
        const { lunar } = info;
        button.setAttribute('aria-label', `${weekdays[info.solar.weekday]}, ${formatDate(iso)}; âm lịch ${lunar.day}/${lunar.month}${lunar.leap ? ' nhuận' : ''}/${lunar.year}; ${state(iso)}${info.holidays.length ? '; ' + info.holidays.join(', ') : ''}`);
        const dateLine = node('span', 'app-calendar-date-line');
        dateLine.append(node('span', 'app-calendar-solar', String(info.solar.day)),
          node('span', 'app-calendar-lunar', `${lunar.day}${lunar.day === 1 || info.solar.day === 1 ? '/' + lunar.month : ''}${lunar.leap ? 'n' : ''}`));
        button.append(dateLine);
        if (Object.hasOwn(results, iso)) {
          const resultLine = node('span', 'app-calendar-result');
          resultLine.append(node('small', '', 'ĐB'), specialNumber(results[iso], ''));
          button.append(resultLine);
          if (ownMonth) monthResults += 1;
        } else {
          button.append(node('span', 'app-calendar-pending', iso > today ? 'Sắp tới' : '—'));
        }
        if (info.holidays.length || lunar.day === 1 || lunar.day === 15) {
          const marker = node('span', 'app-calendar-marker');
          marker.append(node('i', 'app-calendar-dot'), node('span', '', info.holidays[0] || (lunar.day === 15 ? 'Ngày rằm' : 'Mùng một')));
          marker.title = info.holidays.join(' · ') || marker.textContent;
          button.append(marker);
        }
        cell.append(button);
        row.append(cell);
      }
      fragment.append(row);
    }
    days.replaceChildren(fragment);
    $('title').textContent = `Tháng ${String(viewMonth).padStart(2, '0')}, ${viewYear}`;
    $('summary').textContent = `${monthResults} ngày có kết quả Đặc Biệt · Âm lịch Việt Nam`;
    monthInput.value = String(viewMonth);
    yearInput.value = String(viewYear);
    $('prev').disabled = viewYear === engine.MIN_YEAR && viewMonth === 1;
    $('next').disabled = viewYear === engine.MAX_YEAR && viewMonth === 12;
    renderDetail();
    if (focus) days.querySelector(`[data-calendar-date="${selected}"]`)?.focus({ preventScroll: true });
  }
  function select(iso, focus = false) {
    const info = engine.getDay(iso);
    if (!info) return;
    selected = iso; viewYear = info.solar.year; viewMonth = info.solar.month;
    render(focus);
  }
  function changeMonth(year, month, focus = false) {
    if (!Number.isInteger(year) || year < engine.MIN_YEAR || year > engine.MAX_YEAR) {
      yearInput.value = String(viewYear);
      $('summary').textContent = 'Vui lòng chọn năm từ 1900 đến 2099.';
      return;
    }
    const normalized = new Date(Date.UTC(year, month - 1, 1));
    const y = normalized.getUTCFullYear(), m = normalized.getUTCMonth() + 1;
    select(civil(y, m, Math.min(Number(selected.slice(8)), monthLength(y, m))), focus);
  }
  $('prev').addEventListener('click', () => changeMonth(viewYear, viewMonth - 1));
  $('next').addEventListener('click', () => changeMonth(viewYear, viewMonth + 1));
  $('today').addEventListener('click', () => select(engine.todayISO()));
  monthInput.addEventListener('change', () => changeMonth(viewYear, Number(monthInput.value)));
  yearInput.addEventListener('change', () => changeMonth(Number(yearInput.value), viewMonth));
  days.addEventListener('click', event => {
    const button = event.target.closest('[data-calendar-date]');
    if (button) select(button.dataset.calendarDate, true);
  });
  days.addEventListener('keydown', event => {
    const button = event.target.closest('[data-calendar-date]');
    if (!button) return;
    const info = engine.getDay(button.dataset.calendarDate);
    const shifts = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7,
      Home: -((info.solar.weekday + 6) % 7), End: 6 - ((info.solar.weekday + 6) % 7) };
    if (Object.hasOwn(shifts, event.key)) {
      event.preventDefault();
      select(civil(info.solar.year, info.solar.month, info.solar.day + shifts[event.key]), true);
    } else if (event.key === 'PageUp' || event.key === 'PageDown') {
      event.preventDefault();
      const delta = event.key === 'PageUp' ? -1 : 1;
      changeMonth(viewYear + (event.shiftKey ? delta : 0), viewMonth + (event.shiftKey ? 0 : delta), true);
    }
  });
  render();
})();
