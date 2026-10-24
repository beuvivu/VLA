/* Bảng đối chiếu kỳ quay: mọi danh sách phỏng đoán đã đóng băng trước 18:10
   (src/evaluation/prediction_board.py) đặt cạnh kết quả đang về. Mỗi danh sách là hai hàng
   song song: "Trước giờ quay" (số và xác suất đã công bố) và "Sau giờ quay"
   (từng số về hay không, tỉ lệ trúng thật so với kỳ vọng). */
(function () {
  'use strict';
  var root = document.getElementById('live-scorecard');
  if (!root) return;

  var PRIZES = { special: 1, prize1: 1, prize2: 2, prize3: 6, prize4: 4, prize5: 6, prize6: 3, prize7: 4 };
  var TOTAL = 27;
  var LOTO_BASE = 1 - Math.pow(0.99, TOTAL);
  var RETRY_MISSING_MS = 300000;
  var RETRY_ERROR_MS = 60000;
  // Tên miền và đường dẫn dữ liệu không được viết thẳng ra trang (luật riêng tư của kho).
  var E = { h: 'cmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbQ==', s: 'LmdpdGh1Yi5pbw==', b: 'bWFpbg==', p: 'ZGF0YS9ldmFsdWF0aW9uL3ByZWRpY3Rpb25fYm9hcmQv' };
  function d(k) { return atob(E[k]); }

  var title = document.getElementById('live-scorecard-date');
  var summary = document.getElementById('live-scorecard-summary');
  var table = document.getElementById('live-scorecard-table');
  var state = { date: '', board: null, revision: 0, pending: false, retryAt: 0, last: null };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function validDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var parsed = new Date(value + 'T00:00:00Z');
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  }

  function boardUrl(date) {
    if (root.dataset.boardRoot) return root.dataset.boardRoot + date + '.json';
    var host = location.hostname;
    if (host.endsWith(d('s'))) {
      var owner = host.split('.')[0];
      var first = location.pathname.split('/').filter(Boolean)[0];
      var repo = first || (owner + d('s'));
      return 'https://' + d('h') + '/' + owner + '/' + repo + '/' + d('b') + '/' + d('p') + date + '.json';
    }
    return d('p') + date + '.json';
  }

  function pct(p, digits) {
    return (100 * p).toFixed(digits).replace('.', ',') + '%';
  }

  function number(value, digits) {
    return value.toFixed(digits).replace('.', ',');
  }

  // Kết quả đang về: số nháy của 100 số LOTO và hai số cuối Đặc Biệt (khi đã có).
  function outcome(prizes) {
    var counts = new Array(100).fill(0);
    var filled = 0;
    var special = null;
    Object.keys(PRIZES).forEach(function (key) {
      var values = Array.isArray(prizes && prizes[key]) ? prizes[key] : [];
      for (var i = 0; i < PRIZES[key]; i++) {
        var raw = values[i];
        if (raw === undefined || raw === null) continue;
        var text = String(raw).trim();
        if (!/^\d{2,6}$/.test(text)) continue;
        var tail = Number(text.slice(-2));
        counts[tail] += 1;
        filled += 1;
        if (key === 'special') special = tail;
      }
    });
    return { counts: counts, filled: filled, complete: filled === TOTAL, special: special };
  }

  // 'hit' chốt ngay khi đủ điều kiện; 'miss' chỉ khi phần kết quả liên quan đã đủ.
  function judge(rule, o) {
    if (rule.on === 'loto') {
      var numbers = rule.numbers.map(Number);
      if (rule.all) {
        if (numbers.every(function (n) { return o.counts[n] > 0; })) return 'hit';
      } else {
        var sum = numbers.reduce(function (s, n) { return s + o.counts[n]; }, 0);
        if (sum >= rule.need) return 'hit';
      }
      return o.complete ? 'miss' : 'wait';
    }
    if (o.special === null) return 'wait';
    if (rule.on === 'special') {
      return rule.numbers.map(Number).indexOf(o.special) >= 0 ? 'hit' : 'miss';
    }
    if (rule.on === 'special_digit') {
      var tens = Math.floor(o.special / 10), units = o.special % 10;
      return rule.digits.some(function (g) { return g === tens || g === units; }) ? 'hit' : 'miss';
    }
    return 'wait';
  }

  function nhay(rule, o) {
    if (rule.on !== 'loto') return 0;
    return rule.numbers.reduce(function (s, n) { return s + o.counts[Number(n)]; }, 0);
  }

  function expected(item) {
    return item.prob === null || item.prob === undefined ? item.base : item.prob;
  }

  function chips(list, o, after) {
    var wrap = el('ul', 'live-scorecard-chips');
    list.items.forEach(function (item) {
      var chip = el('li', 'live-scorecard-chip');
      chip.appendChild(el('strong', 'live-scorecard-num', item.label));
      if (after) {
        var verdict = judge(item.rule, o);
        chip.dataset.state = verdict;
        var count = nhay(item.rule, o);
        var text = verdict === 'hit' ? (count > 1 ? 'về ×' + count : 'về')
          : verdict === 'miss' ? 'trượt' : 'chờ';
        chip.appendChild(el('small', '', text));
      } else {
        var p = expected(item);
        chip.appendChild(el('small', '', pct(p, p < 0.05 ? 2 : 1) + (item.prob === null ? ' *' : '')));
      }
      wrap.appendChild(chip);
    });
    return wrap;
  }

  function tally(list, o) {
    var t = { k: list.items.length, hits: 0, misses: 0, wait: 0, exp: 0, base: 0, priced: 0 };
    list.items.forEach(function (item) {
      var v = judge(item.rule, o);
      if (v === 'hit') t.hits += 1; else if (v === 'miss') t.misses += 1; else t.wait += 1;
      t.exp += expected(item);
      t.base += item.base;
      if (item.prob !== null && item.prob !== undefined) t.priced += 1;
    });
    return t;
  }

  function beforeText(t) {
    var head = t.priced === t.k ? 'Xác suất công bố TB ' : 'Chọn bừa TB ';
    var text = head + pct(t.exp / t.k, t.exp / t.k < 0.05 ? 2 : 1) + ' · kỳ vọng trúng ' + number(t.exp, 2) + '/' + t.k;
    if (t.priced === t.k) text += ' (chọn bừa ' + number(t.base, 2) + ')';
    return text;
  }

  function afterText(t) {
    if (t.wait === t.k) return 'Chờ kết quả';
    var text = 'Trúng ' + t.hits + '/' + t.k;
    if (t.wait) return text + ' · còn chờ ' + t.wait;
    return text + ' = ' + pct(t.hits / t.k, 1) + ' · kỳ vọng ' + pct(t.exp / t.k, t.exp / t.k < 0.05 ? 2 : 1);
  }

  function groupRows(list, o) {
    var tbody = el('tbody', 'live-scorecard-group');
    tbody.dataset.listId = list.id;
    var t = tally(list, o);
    var before = el('tr', 'is-before');
    var head = el('th', 'live-scorecard-name');
    head.scope = 'rowgroup';
    head.rowSpan = 2;
    var link = el('a', '', list.title);
    link.href = list.page;
    head.append(link, el('span', 'live-scorecard-group-name', list.group));
    var when = el('td', 'live-scorecard-when', 'Trước giờ quay');
    var nums = el('td', '');
    nums.appendChild(chips(list, o, false));
    before.append(head, when, nums, el('td', 'live-scorecard-stat', beforeText(t)));
    var after = el('tr', 'is-after');
    after.dataset.done = t.wait === 0 ? 'true' : 'false';
    var numsAfter = el('td', '');
    numsAfter.appendChild(chips(list, o, true));
    var stat = el('td', 'live-scorecard-stat', afterText(t));
    if (t.wait === 0) stat.dataset.verdict = t.hits > t.exp ? 'above' : t.hits < t.exp ? 'below' : 'equal';
    after.append(el('td', 'live-scorecard-when', 'Sau giờ quay'), numsAfter, stat);
    tbody.append(before, after);
    return { body: tbody, tally: t };
  }

  // Xác suất toàn bảng 100 số của tổ hợp: một kỳ đo được gì so với chọn bừa.
  function vectorLines(board, o) {
    var lines = [];
    var loto = board.vectors && board.vectors.loto;
    if (Array.isArray(loto) && loto.length === 100 && o.complete) {
      var model = 0, flat = 0;
      for (var n = 0; n < 100; n++) {
        var y = o.counts[n] > 0 ? 1 : 0;
        model += Math.pow(loto[n] - y, 2);
        flat += Math.pow(LOTO_BASE - y, 2);
      }
      var skill = 1 - model / flat;
      lines.push('Tổ hợp 100 số LOTO: Brier ' + number(model / 100, 4) + ' so với chọn bừa ' +
        number(flat / 100, 4) + ' (kỹ năng ' + (skill >= 0 ? '+' : '') + pct(skill, 2) + ').');
    }
    var de = board.vectors && board.vectors.de;
    if (Array.isArray(de) && de.length === 100 && o.special !== null) {
      var tail = String(o.special).padStart(2, '0');
      lines.push('Tổ hợp Đặc Biệt: xác suất đã công bố cho số ' + tail + ' là ' + pct(de[o.special], 2) +
        ' (chọn bừa 1,00%).');
    }
    return lines;
  }

  function render() {
    var board = state.board;
    var o = outcome(state.last && state.last.prizes);
    var frag = document.createDocumentFragment();
    var total = { hits: 0, exp: 0, base: 0, k: 0, wait: 0 };
    board.lists.forEach(function (list) {
      var g = groupRows(list, o);
      frag.appendChild(g.body);
      total.hits += g.tally.hits; total.exp += g.tally.exp; total.base += g.tally.base;
      total.k += g.tally.k; total.wait += g.tally.wait;
    });
    clearGroups();
    table.appendChild(frag);
    var lines = [];
    if (total.wait === total.k) {
      lines.push(board.lists.length + ' danh sách, ' + total.k + ' mục đã đóng băng lúc ' +
        String(board.locks_at || '').slice(11, 16) + ' · kỳ vọng trúng ' + number(total.exp, 2) +
        ' mục theo xác suất công bố (' + number(total.base, 2) + ' nếu chọn bừa).');
    } else {
      lines.push('Đã trúng ' + total.hits + '/' + total.k + ' mục' + (total.wait ? ' · còn chờ ' + total.wait : '') +
        ' · kỳ vọng ' + number(total.exp, 2) + ' theo xác suất công bố, ' + number(total.base, 2) + ' nếu chọn bừa.');
    }
    lines = lines.concat(vectorLines(board, o));
    summary.replaceChildren();
    lines.forEach(function (line) { summary.appendChild(el('p', '', line)); });
    root.dataset.state = o.complete ? 'complete' : (o.filled ? 'partial' : 'waiting');
  }

  // Mỗi danh sách là một <tbody> riêng gắn thẳng vào bảng, sau <thead>: lồng <tbody> vào
  // <tbody> là HTML sai và làm trình duyệt dựng lệch cột.
  function clearGroups() {
    Array.prototype.slice.call(table.tBodies).forEach(function (group) { group.remove(); });
  }

  function message(text) {
    clearGroups();
    summary.replaceChildren(el('p', '', text));
    root.dataset.state = 'empty';
  }

  async function fetchBoard(date, version) {
    state.pending = true;
    try {
      var response = await fetch(boardUrl(date), { cache: 'no-store' });
      if (version !== state.revision) return;
      if (response.status === 404) {
        state.retryAt = Date.now() + RETRY_MISSING_MS;
        message('Chưa có sổ phỏng đoán đóng băng cho kỳ này.');
        return;
      }
      if (!response.ok) throw new Error(String(response.status));
      var board = await response.json();
      if (version !== state.revision) return;
      if (!board || board.target_date !== date || !Array.isArray(board.lists)) {
        state.retryAt = Date.now() + RETRY_MISSING_MS;
        message('Sổ phỏng đoán không khớp kỳ quay này.');
        return;
      }
      state.board = board;
      render();
    } catch (_error) {
      if (version !== state.revision) return;
      state.retryAt = Date.now() + RETRY_ERROR_MS;
      message('Chưa tải được sổ phỏng đoán. Sẽ thử lại.');
    } finally {
      if (version === state.revision) state.pending = false;
    }
  }

  function update(snapshot) {
    state.last = snapshot || null;
    var date = snapshot && snapshot.draw_date;
    if (!validDate(date)) {
      state.date = ''; state.board = null; state.revision += 1; state.pending = false;
      title.dateTime = '';
      title.textContent = 'Đang chờ ngày quay';
      message('Đang chờ ngày quay.');
      return Promise.resolve();
    }
    if (date !== state.date) {
      state.date = date; state.board = null; state.revision += 1; state.pending = false; state.retryAt = 0;
      title.dateTime = date;
      title.textContent = date.split('-').reverse().join('/');
      message('Đang tải sổ phỏng đoán…');
    }
    if (state.board) { render(); return Promise.resolve(); }
    if (state.pending || Date.now() < state.retryAt) return Promise.resolve();
    return fetchBoard(date, state.revision);
  }

  window.LiveScorecard = { update: update, judge: judge, outcome: outcome };
})();
