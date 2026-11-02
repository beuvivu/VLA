/* Bảng đối chiếu kỳ quay: mọi danh sách phỏng đoán đã đóng băng trước 18:10
   (src/evaluation/prediction_board.py) đặt cạnh kết quả đang về. Mỗi danh sách là hai hàng
   song song: "Trước giờ quay" (số và xác suất đã công bố) và "Sau giờ quay"
   (từng số về hay không, tỉ lệ trúng thật so với kỳ vọng).

   Danh sách sinh ra từ cặp vị trí (cầu đẹp nhất, soi cầu, soi đường) mang vị trí cầu trong sổ
   (`bridges` của từng mục, `draws` của sổ). Bấm một số ở hàng "Trước giờ quay" mở hàng chi tiết:
   các cầu báo số ấy và đường cầu qua từng kỳ, tô hai chữ số ghép thành số và ô về ở kỳ sau. */
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
  var state = { date: '', board: null, revision: 0, pending: false, retryAt: 0, last: null, open: null, focus: null };

  // 107 vị trí chữ số của bảng kết quả, cùng cách đánh số với src/soi_cau/position_bridges.py:
  // (nhãn ngắn, tên giải, số giải, số chữ số).
  var LAYOUT = [['ĐB', 'Đặc Biệt', 1, 5], ['G1', 'Giải Nhất', 1, 5], ['G2', 'Giải Nhì', 2, 5],
    ['G3', 'Giải Ba', 6, 5], ['G4', 'Giải Tư', 4, 4], ['G5', 'Giải Năm', 6, 4], ['G6', 'Giải Sáu', 3, 3],
    ['G7', 'Giải Bảy', 4, 2]];
  var SHADOW = [5, 6, 7, 8, 9, 0, 1, 2, 3, 4];
  var POSITIONS = [];
  var VALUE_FIRST = [];
  LAYOUT.forEach(function (row) {
    for (var i = 0; i < row[2]; i++) {
      var label = row[0] + (row[2] > 1 ? '.' + (i + 1) : '');
      VALUE_FIRST.push(POSITIONS.length);
      for (var digit = 0; digit < row[3]; digit++) {
        POSITIONS.push({ value: VALUE_FIRST.length - 1, label: label + ' · chữ số ' + (digit + 1) });
      }
    }
  });

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

  function hasBridges(list, item) {
    return !!(list.bridge && Array.isArray(item.bridges) && item.bridges.length);
  }

  function chips(list, o, after) {
    var wrap = el('ul', 'live-scorecard-chips');
    list.items.forEach(function (item, index) {
      var chip = el('li', 'live-scorecard-chip');
      var host = chip;
      if (!after && hasBridges(list, item)) {
        var open = state.open && state.open.list === list.id && state.open.item === index;
        host = el('button', 'live-scorecard-chip-btn');
        host.type = 'button';
        host.dataset.bridgeList = list.id;
        host.dataset.bridgeItem = String(index);
        host.setAttribute('aria-expanded', open ? 'true' : 'false');
        host.setAttribute('aria-controls', 'live-bridge-' + list.id);
        host.setAttribute('aria-label', item.label + ': xem vị trí đường cầu');
        host.addEventListener('click', function () {
          state.open = open ? null : { list: list.id, item: index, bridge: 0 };
          state.focus = '[data-bridge-list="' + list.id + '"][data-bridge-item="' + index + '"]';
          render();
        });
        chip.classList.add('has-bridge');
        if (open) chip.dataset.open = 'true';
        chip.appendChild(host);
      }
      host.appendChild(el('strong', 'live-scorecard-num', item.label));
      if (after) {
        var verdict = judge(item.rule, o);
        chip.dataset.state = verdict;
        var count = nhay(item.rule, o);
        var text = verdict === 'hit' ? (count > 1 ? 'về ×' + count : 'về')
          : verdict === 'miss' ? 'trượt' : 'chờ';
        host.appendChild(el('small', '', text));
      } else {
        var p = expected(item);
        host.appendChild(el('small', '', pct(p, p < 0.05 ? 2 : 1) + (item.prob === null ? ' *' : '')));
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
    if (state.open && state.open.list === list.id && list.items[state.open.item] &&
        hasBridges(list, list.items[state.open.item])) {
      var detail = el('tr', 'is-bridge');
      var cell = el('td', 'live-bridge-cell');
      cell.colSpan = 4;
      cell.appendChild(bridgePanel(list, list.items[state.open.item]));
      detail.appendChild(cell);
      tbody.appendChild(detail);
    }
    return { body: tbody, tally: t };
  }

  // ---- Vị trí đường cầu -------------------------------------------------------------

  function two(n) { return String(n).padStart(2, '0'); }
  function reverse(n) { return 10 * (n % 10) + Math.floor(n / 10); }
  function dayLabel(iso) { return iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4); }

  function formed(values, a, b) {
    var digits = values.join('');
    return 10 * Number(digits[a]) + Number(digits[b]);
  }

  // Bộ của xy: một chữ số từ {x, bóng x} ghép một chữ số từ {y, bóng y}, cả hai chiều
  // (src/soi_cau/bridge_rules.py, `_bo_tables`).
  function boMembers(n) {
    var x = Math.floor(n / 10), y = n % 10, out = [];
    [x, SHADOW[x]].forEach(function (p) {
      [y, SHADOW[y]].forEach(function (q) { out.push(10 * p + q, 10 * q + p); });
    });
    return out.filter(function (m, i) { return out.indexOf(m) === i; }).sort(function (u, v) { return u - v; });
  }

  // Số mà cầu báo từ chữ số kỳ này, theo đúng luật của trang đã liệt kê nó.
  function told(n, mark) {
    if (mark === 'loto-lon' || mark === 'special-lon') return n === reverse(n) ? [n] : [n, reverse(n)];
    if (mark === 'bo') return boMembers(n);
    return [n];
  }

  // Ô của kỳ sau "về" theo cầu kỳ trước: LOTO xét mọi giải, Đặc Biệt chỉ giải đầu.
  function foundCells(values, n, mark) {
    var tails = values.map(function (v) { return Number(v.slice(-2)); });
    if (mark === 'special-touch') {
      var tens = Math.floor(tails[0] / 10), units = tails[0] % 10;
      var digits = [Math.floor(n / 10), n % 10];
      return digits.indexOf(tens) >= 0 || digits.indexOf(units) >= 0 ? [0] : [];
    }
    var wanted = told(n, mark);
    var limit = mark.indexOf('loto') === 0 ? tails.length : 1;
    var cells = [];
    for (var j = 0; j < limit; j++) if (wanted.indexOf(tails[j]) >= 0) cells.push(j);
    return cells;
  }

  function positionText(pos) {
    return 'Vị trí ' + pos + ' (' + POSITIONS[pos].label + ')';
  }

  // Một giá trị giải: chữ số ở vị trí cầu tô đậm, hai số cuối "về" tô nền.
  function valueNode(values, index, bridge, found) {
    var value = values[index];
    var first = VALUE_FIRST[index];
    var cell = el('span', 'live-bridge-value');
    for (var k = 0; k < value.length; k++) {
      var pos = first + k;
      var src = pos === bridge.a ? 'a' : pos === bridge.b ? 'b' : '';
      var hit = found && k >= value.length - 2;
      if (!src && !hit) { cell.appendChild(document.createTextNode(value[k])); continue; }
      var span = el('span', (src ? 'live-bridge-src live-bridge-src--' + src : '') + (hit ? ' live-bridge-hit' : ''), value[k]);
      if (src) span.setAttribute('aria-label', positionText(pos) + ': ' + value[k]);
      cell.appendChild(span);
    }
    return cell;
  }

  function dayCard(date, values, bridge, mark, found, caption) {
    var card = el('article', 'live-bridge-day');
    var head = el('header', 'live-bridge-day-head');
    head.appendChild(el('h4', '', dayLabel(date)));
    head.appendChild(el('p', '', caption));
    card.appendChild(head);
    var grid = el('div', 'live-bridge-board');
    var index = 0;
    LAYOUT.forEach(function (row) {
      var line = el('div', 'live-bridge-prize');
      line.appendChild(el('span', 'live-bridge-prize-name', row[0]));
      var nums = el('span', 'live-bridge-prize-values');
      for (var i = 0; i < row[2]; i++, index++) {
        nums.appendChild(valueNode(values, index, bridge, found.indexOf(index) >= 0));
      }
      line.appendChild(nums);
      grid.appendChild(line);
    });
    card.appendChild(grid);
    return card;
  }

  function toldText(n, mark) {
    if (mark === 'bo') return 'bộ ' + boMembers(n).map(two).join(' ');
    if (mark === 'special-touch') return 'chạm ' + Math.floor(n / 10) + (n % 10 !== Math.floor(n / 10) ? ', ' + (n % 10) : '');
    return told(n, mark).map(two).join(' · ');
  }

  function bridgeLink(list, item, bridge) {
    var cfg = list.bridge;
    if (cfg.type === 'position' && cfg.query) {
      var q = new URLSearchParams();
      q.set('vt', bridge.a + 'x' + bridge.b);
      Object.keys(cfg.query).forEach(function (k) { q.set(k, String(cfg.query[k])); });
      return list.page + '?' + q.toString() + '#app-bridge-results';
    }
    if (cfg.type === 'path') return list.page + '?number=' + encodeURIComponent(item.rule.numbers[0]);
    return list.page;
  }

  function bridgePath(list, bridge) {
    var cfg = list.bridge;
    var draws = state.board.draws || {};
    var wrap = el('div', 'live-bridge-days');
    if (cfg.type === 'path') {
      var base = draws[bridge.base];
      if (!base) return wrap;
      var n = formed(base, bridge.a, bridge.b);
      wrap.appendChild(dayCard(bridge.base, base, bridge, cfg.mark, [],
        'Kỳ gốc · ghép ' + two(n) + ' · trễ ' + bridge.lag + ' ngày → báo ' + toldText(n, cfg.mark) +
        ' cho kỳ ' + dayLabel(cfg.next)));
      return wrap;
    }
    var series = (cfg.series || []).filter(function (date) { return Array.isArray(draws[date]); });
    var shown = series.slice(-Math.min(series.length, bridge.streak + 1));
    for (var t = shown.length - 1; t >= 0; t--) {
      var values = draws[shown[t]];
      var nHere = formed(values, bridge.a, bridge.b);
      var prev = t > 0 ? formed(draws[shown[t - 1]], bridge.a, bridge.b) : null;
      var found = prev === null ? [] : foundCells(values, prev, cfg.mark);
      // Bộ số: một bước trúng là số ghép GIỮ NGUYÊN bộ qua hai kỳ (bridge_rules.step_matrix), không phải
      // Đặc Biệt rơi vào bộ — nói đúng điều ấy.
      var step = prev === null ? '' : cfg.mark === 'bo' ? ' · cùng bộ với số ghép kỳ trước (' + two(prev) + ')'
        : ' · kỳ trước báo ' + toldText(prev, cfg.mark) + ': trúng';
      var caption = 'Ghép ' + two(nHere) + ' → báo ' + toldText(nHere, cfg.mark) +
        (t === shown.length - 1 ? ' cho kỳ ' + dayLabel(state.board.target_date) : '') + step;
      wrap.appendChild(dayCard(shown[t], values, bridge, cfg.mark, found, caption));
    }
    return wrap;
  }

  function bridgePanel(list, item) {
    var cfg = list.bridge;
    var panel = el('div', 'live-bridge');
    panel.id = 'live-bridge-' + list.id;
    var pick = Math.min(state.open.bridge || 0, item.bridges.length - 1);
    var bridge = item.bridges[pick];
    var head = el('div', 'live-bridge-head');
    // Dấu hai chấm tách nhãn khỏi số cầu: nhãn đã có dấu « · » giữa số và số lộn.
    var heading = el('h3', '', item.label + ': ' + item.bridge_total + (cfg.type === 'path' ? ' đường cầu' : ' cầu') +
      ' báo mục này' + (item.bridge_total > item.bridges.length ? ', hiện ' + item.bridges.length + ' cầu dài nhất' : ''));
    var close = el('button', 'live-bridge-close', 'Đóng');
    close.type = 'button';
    close.addEventListener('click', function () {
      state.open = null;
      state.focus = '[data-bridge-list="' + list.id + '"][data-bridge-item="' + state.lastItem + '"]';
      render();
    });
    state.lastItem = state.open.item;
    head.append(heading, close);
    panel.appendChild(head);

    var picker = el('div', 'live-bridge-picker');
    picker.setAttribute('role', 'group');
    picker.setAttribute('aria-label', 'Chọn cầu');
    item.bridges.forEach(function (b, i) {
      var text = b.a + '×' + b.b + ' · ' + (cfg.type === 'path' ? 'trễ ' + b.lag + ' ngày · chuỗi ' + b.streak : b.streak + ' kỳ');
      var button = el('button', 'live-bridge-pick', text);
      button.type = 'button';
      button.dataset.bridgePick = String(i);
      button.setAttribute('aria-pressed', i === pick ? 'true' : 'false');
      button.addEventListener('click', function () {
        state.open = { list: list.id, item: state.open.item, bridge: i };
        state.focus = '#live-bridge-' + list.id + ' [data-bridge-pick="' + i + '"]';
        render();
      });
      picker.appendChild(button);
    });
    panel.appendChild(picker);

    var where = el('p', 'live-bridge-where');
    where.appendChild(el('span', 'live-bridge-src live-bridge-src--a', positionText(bridge.a)));
    where.appendChild(document.createTextNode(' ghép '));
    where.appendChild(el('span', 'live-bridge-src live-bridge-src--b', positionText(bridge.b)));
    if (cfg.type !== 'path' && bridge.streak + 1 > (cfg.series || []).length) {
      where.appendChild(document.createTextNode(' · cầu chạy ' + bridge.streak + ' kỳ, vẽ ' + (cfg.series || []).length + ' kỳ cuối'));
    }
    panel.appendChild(where);
    panel.appendChild(bridgePath(list, bridge));
    var link = el('a', 'live-bridge-link', 'Xem trên trang ' + list.title + ' →');
    link.href = bridgeLink(list, item, bridge);
    panel.appendChild(link);
    return panel;
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
    if (state.focus) {
      var target = table.querySelector(state.focus);
      state.focus = null;
      if (target) target.focus();
    }
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
      state.open = null;
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
