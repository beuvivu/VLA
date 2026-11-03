/* Bảng đối chiếu kỳ quay: mọi danh sách phỏng đoán đã đóng băng trước 18:10
   (src/evaluation/prediction_board.py) đặt cạnh kết quả đang về. Mỗi danh sách là hai hàng
   song song: "Trước giờ quay" (số và xác suất đã công bố) và "Sau giờ quay"
   (từng số về hay không, tỉ lệ trúng thật so với kỳ vọng).

   Danh sách sinh ra từ cặp vị trí (cầu đẹp nhất, soi cầu, soi đường) mang vị trí cầu trong sổ
   (`bridges` của từng mục, `draws` của sổ). Danh sách khác (tổ hợp, Cầu Kèo, ML…) tra bảng
   `running` của sổ: các cầu đang chạy trên trang Cầu LOTO / Cầu Đặc Biệt ghép ra đúng số ấy.
   Bấm một số ở hàng "Trước giờ quay" mở hàng chi tiết: các cầu và đường cầu qua từng kỳ, tô hai
   chữ số ghép thành số và ô về ở kỳ sau.

   live.json giữ ngày của kỳ vừa quay tới tận phiên hôm sau. Khi kỳ ấy đã quay xong, bảng có hai
   nút: kỳ đã quay (đối chiếu) và kỳ sắp quay (sổ đang mở) — sang ngày mới (giờ VN) thì mặc định là
   kỳ sắp quay, để số "trước giờ quay" người đọc thấy là của kỳ chưa quay. */
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
  var E = { h: 'cmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbQ==', s: 'LmdpdGh1Yi5pbw==', b: 'bWFpbg==', p: 'ZGF0YS9ldmFsdWF0aW9uL3ByZWRpY3Rpb25fYm9hcmQv',
    c: 'ZGF0YS9ub25fZHJhd19kYXlzLmpzb24=' };
  function d(k) { return atob(E[k]); }

  var title = document.getElementById('live-scorecard-date');
  var summary = document.getElementById('live-scorecard-summary');
  var table = document.getElementById('live-scorecard-table');
  var state = { draw: '', views: [], chosen: '', date: '', board: null, revision: 0, pending: false, retryAt: 0,
    last: null, open: null, focus: null, reveal: null };
  var BRIDGES_SHOWN = 12;

  // Hai nút chọn kỳ, đặt ngay trên dòng tóm tắt; chỉ hiện khi kỳ của live.json đã quay xong.
  var viewBar = el('div', 'live-scorecard-views');
  viewBar.setAttribute('role', 'group');
  viewBar.setAttribute('aria-label', 'Chọn kỳ quay');
  viewBar.hidden = true;
  summary.parentNode.insertBefore(viewBar, summary);

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

  // Tệp trong kho: trên trang Pages đọc từ nhánh chính, chạy cục bộ thì đọc đường dẫn tương đối.
  function dataUrl(path) {
    var host = location.hostname;
    if (host.endsWith(d('s'))) {
      var owner = host.split('.')[0];
      var first = location.pathname.split('/').filter(Boolean)[0];
      var repo = first || (owner + d('s'));
      return 'https://' + d('h') + '/' + owner + '/' + repo + '/' + d('b') + '/' + path;
    }
    return path;
  }

  function boardUrl(date) {
    if (root.dataset.boardRoot) return root.dataset.boardRoot + date + '.json';
    return dataUrl(d('p') + date + '.json');
  }

  // Lịch nghỉ quay (Tết…), đọc một lần: kỳ sắp quay bỏ qua những ngày ấy, cùng luật với
  // forecast.multi_hit_forecast.next_draw_date — sổ của kỳ sắp quay mang đúng ngày quay thật.
  // Không đọc được thì coi như không có ngày nghỉ nào.
  var closed = null;
  function closedDays() {
    if (!closed) {
      closed = fetch(root.dataset.closedDays || dataUrl(d('c')), { cache: 'no-store' })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (data) { return new Set(data && Array.isArray(data.ngay_khong_quay) ? data.ngay_khong_quay : []); })
        .catch(function () { return new Set(); });
    }
    return closed;
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

  // Danh sách sinh từ cặp vị trí (src/evaluation/prediction_board.py, `attach_bridges`). Sổ bỏ `bridge` của
  // một danh sách như thế khi cầu tính lại lệch số trang in; nó vẫn KHÔNG được tra bảng cầu đang chạy, vì câu
  // "danh sách không chọn số theo cầu" khi ấy là sai.
  var POSITIONAL = /^(best|bridge|path)-/;

  // Cầu của một mục: của chính danh sách (cầu đẹp nhất, soi cầu, soi đường), hoặc tra bảng cầu đang chạy
  // của sổ cho danh sách không sinh từ cặp vị trí. null = mục không mở được (sổ cũ, luật nhiều chữ số).
  function source(list, item) {
    if (list.bridge || POSITIONAL.test(list.id)) {
      if (!list.bridge) return null;
      if (!Array.isArray(item.bridges) || !item.bridges.length) return null;
      return { cfg: list.bridge, bridges: item.bridges, total: item.bridge_total || item.bridges.length,
        page: list.page, title: list.title, running: false };
    }
    var rule = item.rule || {};
    var mode = rule.on === 'loto' ? 'loto' : rule.on === 'special' ? 'de' : '';
    var table = mode && state.board && state.board.running && state.board.running[mode];
    if (!table || !table.groups || !Array.isArray(rule.numbers) || !rule.numbers.length) return null;
    var keys = [], bridges = [], total = 0;
    rule.numbers.forEach(function (text) {
      var key = pairKey(Number(text));
      if (keys.indexOf(key) >= 0) return;
      keys.push(key);
      var group = table.groups[key];
      if (!group) return;
      total += group.total;
      group.bridges.forEach(function (b) { bridges.push(b); });
    });
    bridges.sort(function (u, v) { return v.streak - u.streak || u.a - v.a || u.b - v.b; });
    return { cfg: { type: 'rule', mark: table.mark, series: table.series }, bridges: bridges.slice(0, BRIDGES_SHOWN),
      total: total, page: table.page, title: table.title, running: true, count: table.count, keys: keys };
  }

  function chips(list, o, after) {
    var wrap = el('ul', 'live-scorecard-chips');
    list.items.forEach(function (item, index) {
      var chip = el('li', 'live-scorecard-chip');
      var host = chip;
      var src = after ? null : source(list, item);
      if (src) {
        var open = state.open && state.open.list === list.id && state.open.item === index;
        host = el('button', 'live-scorecard-chip-btn');
        host.type = 'button';
        host.dataset.bridgeList = list.id;
        host.dataset.bridgeItem = String(index);
        host.setAttribute('aria-expanded', open ? 'true' : 'false');
        host.setAttribute('aria-controls', 'live-bridge-' + list.id);
        host.setAttribute('aria-label', item.label + (src.running ? ': xem cầu đang chạy ghép ra số này'
          : ': xem vị trí đường cầu'));
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
    var openItem = state.open && state.open.list === list.id ? list.items[state.open.item] : null;
    var openSource = openItem ? source(list, openItem) : null;
    if (openSource) {
      var detail = el('tr', 'is-bridge');
      var cell = el('td', 'live-bridge-cell');
      cell.colSpan = 4;
      cell.appendChild(bridgePanel(list, openItem, openSource));
      detail.appendChild(cell);
      tbody.appendChild(detail);
    }
    return { body: tbody, tally: t };
  }

  // ---- Vị trí đường cầu -------------------------------------------------------------

  function two(n) { return String(n).padStart(2, '0'); }
  function reverse(n) { return 10 * (n % 10) + Math.floor(n / 10); }
  // Khoá nhóm của hai trang cầu: cặp số ghép {n, lộn n}, xếp tăng (src/evaluation/prediction_board.py).
  function pairKey(n) {
    var r = reverse(n);
    return n === r ? two(n) : two(Math.min(n, r)) + ',' + two(Math.max(n, r));
  }
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

  function bridgeLink(src, item, bridge) {
    var cfg = src.cfg;
    if (src.running || !bridge) return src.page;
    if (cfg.type === 'position' && cfg.query) {
      var q = new URLSearchParams();
      q.set('vt', bridge.a + 'x' + bridge.b);
      Object.keys(cfg.query).forEach(function (k) { q.set(k, String(cfg.query[k])); });
      return src.page + '?' + q.toString() + '#app-bridge-results';
    }
    if (cfg.type === 'path') return src.page + '?number=' + encodeURIComponent(item.rule.numbers[0]);
    return src.page;
  }

  function bridgePath(src, bridge) {
    var cfg = src.cfg;
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

  function keysText(keys) {
    return keys.map(function (key) { return key.split(',').join(' · '); }).join(', ');
  }

  function bridgePanel(list, item, src) {
    var cfg = src.cfg;
    var panel = el('div', 'live-bridge');
    panel.id = 'live-bridge-' + list.id;
    var head = el('div', 'live-bridge-head');
    var shown = src.total > src.bridges.length ? ', hiện ' + src.bridges.length + ' cầu dài nhất' : '';
    // Dấu hai chấm tách nhãn khỏi số cầu: nhãn đã có dấu « · » giữa số và số lộn.
    var text = !src.running
      ? item.label + ': ' + src.total + (cfg.type === 'path' ? ' đường cầu' : ' cầu') + ' báo mục này' + shown
      : src.total
        ? item.label + ': ' + src.total + ' cầu đang chạy trên trang ' + src.title + ' ghép ra ' + keysText(src.keys) + shown
        : item.label + ': chưa có cầu nào đang chạy trên trang ' + src.title + ' ghép ra ' + keysText(src.keys);
    var close = el('button', 'live-bridge-close', 'Đóng');
    close.type = 'button';
    close.addEventListener('click', function () {
      state.open = null;
      state.focus = '[data-bridge-list="' + list.id + '"][data-bridge-item="' + state.lastItem + '"]';
      render();
    });
    state.lastItem = state.open.item;
    head.append(el('h3', '', text), close);
    panel.appendChild(head);
    if (src.running) {
      // Nói thẳng đây là phép TRA, không phải lý do danh sách chọn số.
      panel.appendChild(el('p', 'live-bridge-note', 'Danh sách ' + list.title + ' không chọn số theo cầu. Đây là các cầu ' +
        'đang chạy từ ' + src.count + ' kỳ trở lên trên trang ' + src.title + ' mà kỳ cuối ghép ra đúng số này.'));
    }
    var bridge = null;
    if (src.bridges.length) {
      var pick = Math.min(state.open.bridge || 0, src.bridges.length - 1);
      bridge = src.bridges[pick];
      var picker = el('div', 'live-bridge-picker');
      picker.setAttribute('role', 'group');
      picker.setAttribute('aria-label', 'Chọn cầu');
      src.bridges.forEach(function (b, i) {
        var label = b.a + '×' + b.b + ' · ' + (cfg.type === 'path' ? 'trễ ' + b.lag + ' ngày · chuỗi ' + b.streak : b.streak + ' kỳ');
        var button = el('button', 'live-bridge-pick', label);
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
      panel.appendChild(bridgePath(src, bridge));
    }
    var link = el('a', 'live-bridge-link', 'Xem trên trang ' + src.title + ' →');
    link.href = bridgeLink(src, item, bridge);
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
    // Kỳ sắp quay chưa có giải nào: kết quả trong live.json là của kỳ đã quay.
    var o = outcome(state.date === state.draw ? state.last && state.last.prizes : null);
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
      applyReveal();
      render();
    } catch (_error) {
      if (version !== state.revision) return;
      state.retryAt = Date.now() + RETRY_ERROR_MS;
      message('Chưa tải được sổ phỏng đoán. Sẽ thử lại.');
    } finally {
      if (version === state.revision) state.pending = false;
    }
  }

  // Mọi trạng thái "complete*" đều nghĩa là kỳ đã quay đủ 27 giải (như live-predictions.js).
  function finished(status) {
    return typeof status === 'string' && status.indexOf('complete') === 0;
  }

  function nextDay(value) {
    var day = new Date(value + 'T00:00:00Z');
    day.setUTCDate(day.getUTCDate() + 1);
    return day.toISOString().slice(0, 10);
  }

  function nextDraw(date, skip) {
    var day = nextDay(date);
    for (var i = 0; i < 366 && skip.has(day); i++) day = nextDay(day);
    return day;
  }

  function vnToday() {
    return new Date(Date.now() + 7 * 3600000).toISOString().slice(0, 10);
  }

  function renderViews() {
    viewBar.replaceChildren();
    viewBar.hidden = state.views.length < 2;
    if (viewBar.hidden) return;
    state.views.forEach(function (date, i) {
      var button = el('button', 'live-scorecard-view', 'Kỳ ' + dayLabel(date) + (i === 0 ? ' · đã quay' : ' · sắp quay'));
      button.type = 'button';
      button.dataset.view = date;
      button.setAttribute('aria-pressed', date === state.date ? 'true' : 'false');
      button.addEventListener('click', function () {
        state.chosen = date;
        state.focus = null;
        show(date);
        var again = viewBar.querySelector('[data-view="' + date + '"]');
        if (again) again.focus();
      });
      viewBar.appendChild(button);
    });
  }

  function show(date) {
    if (date !== state.date) {
      state.date = date; state.board = null; state.revision += 1; state.pending = false; state.retryAt = 0;
      state.open = null;
      title.dateTime = date;
      title.textContent = date.split('-').reverse().join('/');
      message('Đang tải sổ phỏng đoán…');
    }
    renderViews();
    if (state.board) { applyReveal(); render(); return Promise.resolve(); }
    if (state.pending || Date.now() < state.retryAt) return Promise.resolve();
    return fetchBoard(date, state.revision);
  }

  function update(snapshot) {
    state.last = snapshot || null;
    var date = snapshot && snapshot.draw_date;
    if (!validDate(date)) {
      state.draw = ''; state.views = []; state.chosen = '';
      state.date = ''; state.board = null; state.revision += 1; state.pending = false;
      renderViews();
      title.dateTime = '';
      title.textContent = 'Đang chờ ngày quay';
      message('Đang chờ ngày quay.');
      return Promise.resolve();
    }
    if (date !== state.draw) { state.draw = date; state.chosen = ''; }
    if (!finished(snapshot.status)) {
      state.views = [date];
      return choose();
    }
    return closedDays().then(function (skip) {
      if (state.last !== snapshot) return undefined;
      state.views = [date, nextDraw(date, skip)];
      return choose();
    });
  }

  function choose() {
    // Lệnh mở số đang chờ (bấm trước khi biết có những kỳ nào): kỳ của nó có thì chọn kỳ ấy, không thì bỏ.
    if (state.reveal) {
      if (state.views.indexOf(state.reveal.date) >= 0) state.chosen = state.reveal.date;
      else state.reveal = null;
    }
    var target = state.views.indexOf(state.chosen) >= 0 ? state.chosen
      : state.views.length > 1 && vnToday() > state.draw ? state.views[1] : state.views[0];
    return show(target);
  }

  // Mở đúng số ấy trong bảng (bấm từ khối "Dự đoán trong ngày"): mục của danh sách Cầu Kèo cùng
  // kiểu, không có thì mục đầu tiên nào chỉ gồm số ấy.
  function applyReveal() {
    var want = state.reveal;
    if (!want || !state.board) return;
    state.reveal = null;
    // Lệnh mở gắn với kỳ đã bấm: live.json sang kỳ khác trong lúc sổ đang tải thì bỏ.
    if (want.date !== state.board.target_date) return;
    var lists = state.board.lists.slice().sort(function (u, v) {
      return (u.id === want.list ? 0 : 1) - (v.id === want.list ? 0 : 1);
    });
    for (var i = 0; i < lists.length; i++) {
      for (var j = 0; j < lists[i].items.length; j++) {
        var item = lists[i].items[j], rule = item.rule || {};
        if (rule.on !== want.on || !Array.isArray(rule.numbers) || rule.numbers.length !== 1 ||
            rule.numbers[0] !== want.number || !source(lists[i], item)) continue;
        state.open = { list: lists[i].id, item: j, bridge: 0 };
        state.focus = '[data-bridge-list="' + lists[i].id + '"][data-bridge-item="' + j + '"]';
        return;
      }
    }
  }

  function reveal(date, mode, value) {
    if (!validDate(date) || (mode !== 'de' && mode !== 'loto')) return Promise.resolve();
    state.reveal = { date: date, list: 'cau-keo-' + mode, on: mode === 'de' ? 'special' : 'loto', number: two(Number(value)) };
    // Chưa biết kỳ ấy có trên bảng không (live.json chưa về, lịch nghỉ đang tải): giữ lệnh, update() xử lý.
    if (state.views.indexOf(date) < 0) return Promise.resolve();
    state.chosen = date;
    return show(date);
  }

  window.LiveScorecard = { update: update, reveal: reveal, judge: judge, outcome: outcome };
})();
