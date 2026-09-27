/* Archived two-digit forecasts, keyed strictly to the LIVE draw date. */
(function () {
  'use strict';
  var root = document.getElementById('live-predictions');
  if (!root) return;
  var dateLabel = document.getElementById('live-prediction-date');
  var currentDate = '', revision = 0, pending = null;
  var ready = new Set();
  var modes = ['de', 'loto'];

  function validDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var parsed = new Date(value + 'T00:00:00Z');
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  }

  function column(mode, state, message, numbers) {
    var section = root.querySelector('[data-prediction-mode="' + mode + '"]');
    section.dataset.state = state;
    section.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
    var list = section.querySelector('.live-prediction-list');
    var fragment = document.createDocumentFragment();
    (numbers || []).forEach(function (number) {
      var item = document.createElement('li');
      var value = document.createElement('strong');
      value.className = 'live-prediction-number';
      value.textContent = number;
      item.appendChild(value);
      fragment.appendChild(item);
    });
    list.replaceChildren(fragment);
    var note = section.querySelector('.live-prediction-message');
    note.textContent = message;
    note.hidden = !message;
  }

  function parseNumbers(csv) {
    var lines = String(csv).replace(/^\uFEFF/, '').trim().split(/\r?\n/);
    var columns = lines.shift().split(',').map(function (s) { return s.trim().replace(/^"|"$/g, ''); });
    var index = columns.indexOf('number');
    if (index < 0) return [];
    var result = [];
    lines.forEach(function (line) {
      var value = (line.split(',')[index] || '').trim().replace(/^"|"$/g, '');
      if (!/^\d{1,2}$/.test(value)) return;
      value = value.padStart(2, '0');
      if (result.length < 10 && result.indexOf(value) < 0) result.push(value);
    });
    return result;
  }

  async function fetchMode(mode, date, version) {
    var controller = new AbortController();
    var timer = window.setTimeout(function () { controller.abort(); }, 10000);
    column(mode, 'loading', 'Đang tải dự đoán…');
    try {
      var url = root.dataset.predictionRoot + 'predict_next_' + mode + '_top10_' + date + '.csv';
      var response = await fetch(url, { cache: 'no-store', signal: controller.signal });
      if (!response.ok && response.status !== 404) throw new Error('Forecast unavailable');
      var values = response.ok ? parseNumbers(await response.text()) : [];
      if (version !== revision) return;
      if (values.length) {
        ready.add(mode);
        column(mode, 'ready', '', values);
      } else {
        column(mode, 'missing', 'Chưa có dự đoán cho ngày này.');
      }
    } catch (_error) {
      if (version === revision) column(mode, 'error', 'Chưa tải được dự đoán. Sẽ thử lại.');
    } finally {
      window.clearTimeout(timer);
    }
  }

  function load(date) {
    if (!validDate(date)) {
      currentDate = ''; revision++; pending = null; ready.clear();
      dateLabel.dateTime = '';
      dateLabel.textContent = 'Đang chờ ngày quay';
      modes.forEach(function (mode) { column(mode, 'missing', 'Đang chờ ngày quay.'); });
      return Promise.resolve();
    }
    if (date !== currentDate) {
      currentDate = date; revision++; pending = null; ready.clear();
      dateLabel.dateTime = date;
      dateLabel.textContent = date.split('-').reverse().join('/');
      modes.forEach(function (mode) { column(mode, 'loading', 'Đang tải dự đoán…'); });
    }
    if (pending) return pending;
    var version = revision;
    pending = Promise.all(modes.filter(function (mode) { return !ready.has(mode); })
      .map(function (mode) { return fetchMode(mode, date, version); }))
      .finally(function () { if (version === revision) pending = null; });
    return pending;
  }
  window.VLALivePredictions = { load: load };
})();
