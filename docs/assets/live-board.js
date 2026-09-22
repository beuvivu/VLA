(function () {
  'use strict';

  var PRIZES = [
    {key:'special', label:'ĐB', count:1, digits:5},
    {key:'prize1',  label:'G1', count:1, digits:5},
    {key:'prize2',  label:'G2', count:2, digits:5},
    {key:'prize3',  label:'G3', count:6, digits:5},
    {key:'prize4',  label:'G4', count:4, digits:4},
    {key:'prize5',  label:'G5', count:6, digits:4},
    {key:'prize6',  label:'G6', count:3, digits:3},
    {key:'prize7',  label:'G7', count:4, digits:2}
  ];
  var TOTAL_SLOTS = 27;
  var REVEAL_STAGGER_MS = 170;
  var FRESH_HIGHLIGHT_MS = 6000;

  var slotIndex = Object.create(null);
  var revealQueue = [];
  var revealTimer = null;
  var pollTimer = null;
  var reduceMotion = false;
  try {
    reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {}

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clampNumber(value, min, max, fallback) {
    var n = Number(value);
    return isFinite(n) ? Math.min(max, Math.max(min, n)) : (fallback || 0);
  }

  function buildSkeleton() {
    var root = document.getElementById('results');
    if (!root) return;
    var frag = document.createDocumentFragment();
    PRIZES.forEach(function (prize) {
      var row = el('div', 'prize is-waiting');
      row.setAttribute('data-prize', prize.key);
      var label = el('div', 'prize-label');
      label.append(el('span', 'dot'), el('span', '', prize.label));
      var slots = el('div', 'slots');
      for (var i = 0; i < prize.count; i++) {
        var slot = el('div', 'slot is-empty', '·'.repeat(prize.digits));
        if (prize.key === 'special') slot.classList.add('is-special');
        slot.style.setProperty('--w', (prize.digits * 13 + 26) + 'px');
        slot.setAttribute('aria-label', prize.label + ' vị trí ' + (i + 1));
        slotIndex[prize.key + ':' + i] = {el: slot, value: null, digits: prize.digits};
        slots.appendChild(slot);
      }
      row.append(label, slots);
      frag.appendChild(row);
    });
    root.replaceChildren(frag);
  }

  function queueReveal(entry, value) {
    revealQueue.push({entry: entry, value: value});
    if (revealTimer === null) drainQueue();
  }

  function drainQueue() {
    var item = revealQueue.shift();
    if (!item) { revealTimer = null; return; }
    applyValue(item.entry, item.value);
    revealTimer = window.setTimeout(drainQueue, reduceMotion ? 0 : REVEAL_STAGGER_MS);
  }

  function applyValue(entry, value) {
    var node = entry.el;
    entry.value = value;
    node.textContent = value;
    node.classList.remove('is-empty');
    node.classList.add('is-new', 'is-fresh');
    window.setTimeout(function () { node.classList.remove('is-new'); }, 600);
    window.setTimeout(function () { node.classList.remove('is-fresh'); }, FRESH_HIGHLIGHT_MS);
  }

  function clearValue(entry) {
    entry.value = null;
    entry.el.textContent = '·'.repeat(entry.digits);
    entry.el.classList.add('is-empty');
    entry.el.classList.remove('is-new', 'is-fresh');
  }

  function syncPrizes(prizes) {
    var filled = 0;
    PRIZES.forEach(function (prize) {
      var incoming = Array.isArray(prizes && prizes[prize.key]) ? prizes[prize.key] : [];
      var present = 0;
      for (var i = 0; i < prize.count; i++) {
        var entry = slotIndex[prize.key + ':' + i];
        if (!entry) continue;
        var raw = incoming[i];
        var value = (raw === undefined || raw === null || raw === '') ? null : String(raw);
        if (value !== null) present++;
        if (value === entry.value) continue;
        if (value === null) clearValue(entry);
        else if (entry.value === null) queueReveal(entry, value);
        else applyValue(entry, value);
      }
      filled += present;
      var row = document.querySelector('[data-prize="' + prize.key + '"]');
      if (row) {
        row.classList.toggle('is-done', present === prize.count);
        row.classList.toggle('is-live', present > 0 && present < prize.count);
        row.classList.toggle('is-waiting', present === 0);
      }
    });
    return filled;
  }

  function renderSources(rows) {
    var box = document.getElementById('sources');
    if (!box) return;
    var frag = document.createDocumentFragment();
    (Array.isArray(rows) ? rows : []).forEach(function (source, index) {
      var code = (source && source.source_code) || ('#' + (index + 1));
      var tier = source && source.tier === 'fallback' ? 'dự phòng' : 'chính';
      var row = el('div', 'src');
      row.append(
        el('span', '', code),
        el('span', '', source && source.failed ? tier + ' · lỗi' : tier),
        el('span', '', ((source && source.received_values) || 0) + '/27')
      );
      frag.appendChild(row);
    });
    box.replaceChildren(frag);
  }

  function vietnamMinutes() {
    var now = new Date();
    var utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
    return (utcMinutes + 7 * 60) % (24 * 60);
  }

  function nextDelayMs(status) {
    if (status === 'complete_verified') return 300000;
    if (document.hidden) return 60000;
    if (status === 'partial') return 5000;
    if (status === 'complete') return 15000;
    var m = vietnamMinutes();
    if (m >= 18 * 60 + 10 && m <= 18 * 60 + 50) return 5000;
    if (m >= 17 * 60 + 50 && m < 18 * 60 + 10) return 15000;
    if (m > 18 * 60 + 50 && m <= 19 * 60 + 30) return 20000;
    return 120000;
  }

  function describeDelay(ms) {
    return ms >= 60000
      ? 'làm mới mỗi ' + Math.round(ms / 60000) + ' phút'
      : 'làm mới mỗi ' + Math.round(ms / 1000) + ' giây';
  }

  var E = {h: 'cmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbQ==', s: 'LmdpdGh1Yi5pbw==', b: 'bGl2ZQ==', f: 'bGl2ZS5qc29u', d: 'ZGF0YQ=='};
  function d(k) { return atob(E[k]); }

  function rawUrl() {
    if (window.LIVE_RAW_URL) return window.LIVE_RAW_URL;
    var host = location.hostname;
    if (host.endsWith(d('s'))) {
      var owner = host.split('.')[0];
      var first = location.pathname.split('/').filter(Boolean)[0];
      var repo = first || (owner + d('s'));
      return 'https://' + d('h') + '/' + owner + '/' + repo + '/' + d('b') + '/' + d('f');
    }
    return d('d') + '/' + d('f');
  }

  function candidateUrls() {
    var urls = [];
    if (window.LIVE_WORKER_URL) urls.push(String(window.LIVE_WORKER_URL));
    urls.push(rawUrl());
    return urls;
  }

  async function fetchSnapshot() {
    var lastError = null;
    var urls = candidateUrls();
    for (var i = 0; i < urls.length; i += 1) {
      try {
        var response = await fetch(urls[i] + '?t=' + Date.now(), {cache: 'no-store'});
        if (!response.ok) throw new Error(String(response.status));
        return await response.json();
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error('không có nguồn nào trả lời');
  }

  var STATUS_LABELS = {
    waiting: 'ĐANG CHỜ', partial: 'ĐANG CẬP NHẬT',
    complete: 'HOÀN TẤT', complete_verified: 'ĐÃ XÁC MINH'
  };

  function schedule(status) {
    var delay = nextDelayMs(status);
    var cadence = document.getElementById('cadence');
    if (cadence) cadence.textContent = describeDelay(delay);
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(load, delay);
  }

  async function load() {
    var status = 'waiting';
    try {
      var data = await fetchSnapshot();
      status = String(data.status || 'waiting');
      var progress = clampNumber(data.progress_percent, 0, 100, 0);
      var verification = clampNumber(data.verification_percent, 0, 100, 0);
      var statusEl = document.getElementById('status');
      if (statusEl) statusEl.textContent =
        (data.draw_date || '') + ' · ' + (STATUS_LABELS[status] || status.toUpperCase());
      var checked = document.getElementById('checked');
      if (checked) checked.textContent = 'Cập nhật: ' + (data.checked_at_local || '—');
      var bar = document.getElementById('bar');
      if (bar) bar.style.width = progress + '%';
      var shown = syncPrizes(data.prizes);
      var progressEl = document.getElementById('progress');
      if (progressEl) progressEl.textContent =
        shown + '/' + TOTAL_SLOTS + ' giá trị · hoàn thành ' + progress + '%';
      var verify = document.getElementById('verify');
      if (verify) {
        verify.textContent = 'xác minh ' + verification + '%';
        verify.className = 'badge ' + (data.verified_complete === true ? 'ok' : 'warn');
      }
      var conflicts = Array.isArray(data.conflicts) ? data.conflicts.map(String) : [];
      var conflictsEl = document.getElementById('conflicts');
      if (conflictsEl) conflictsEl.textContent = conflicts.length
        ? 'Đang có bất đồng nguồn: ' + conflicts.join(', ')
        : 'Không phát hiện bất đồng nguồn ở các ô đã xác minh.';
      renderSources(data.source_status);
    } catch (error) {
      var statusEl2 = document.getElementById('status');
      if (statusEl2) statusEl2.textContent = 'Lỗi tải dữ liệu';
      var checked2 = document.getElementById('checked');
      if (checked2) checked2.textContent = String(error && error.message ? error.message : error);
    }
    schedule(status);
  }

  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) {
      window.clearTimeout(pollTimer);
      load();
    }
  });

  buildSkeleton();
  load();
})();
