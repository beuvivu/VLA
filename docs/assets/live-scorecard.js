/* Bảng đối chiếu kỳ quay: mọi danh sách phỏng đoán đã đóng băng trước 18:10
   (src/evaluation/prediction_board.py) đặt cạnh kết quả đang về. Mỗi danh sách là hai hàng
   song song: "Trước giờ quay" (số và xác suất đã công bố) và "Sau giờ quay"
   (từng số về hay không, tỉ lệ trúng thật so với kỳ vọng).

   Danh sách sinh ra từ cặp vị trí (cầu đẹp nhất, soi cầu, soi đường) mang vị trí cầu trong sổ
   (`bridges` của từng mục, `draws` của sổ). Danh sách khác (tổ hợp, Cầu Kèo, ML…) tra bảng
   `running` của sổ: các cầu đang chạy trên trang Cầu LOTO / Cầu Đặc Biệt ghép ra đúng số ấy.
   Bấm một số ở hàng "Trước giờ quay" mở hàng chi tiết: các cầu và đường cầu qua từng kỳ, tô hai
   chữ số ghép thành số và ô về ở kỳ sau.

   live.json giữ ngày của kỳ vừa quay tới tận phiên hôm sau. Khi kỳ ấy đã quay xong, mỗi danh sách có
   BA hàng để tra trong một chỗ (yêu cầu 05-11-2026): "Trước giờ quay" của kỳ sắp quay (sổ đang mở), rồi
   "Trước giờ quay" và "Sau giờ quay" của kỳ vừa quay — kỳ mà bảng kết quả đầu trang đang hiện —, nên dấu
   về/trượt giữ tới phiên kế tiếp. Trong lúc đang quay chưa có kỳ sắp quay: hai hàng của kỳ đang quay.
   Mỗi hàng ghi rõ kỳ (kèm hôm nay / hôm qua / ngày mai theo giờ VN); sổ của hai kỳ tải độc lập. */
(function () {
  'use strict';
  var root = document.getElementById('live-scorecard');
  if (!root) return;

  var PRIZES = { special: 1, prize1: 1, prize2: 2, prize3: 6, prize4: 4, prize5: 6, prize6: 3, prize7: 4 };
  var TOTAL = 27;
  var LOTO_BASE = 1 - Math.pow(0.99, TOTAL);
  var RETRY_MISSING_MS = 300000;
  var RETRY_ERROR_MS = 60000;
  // Sổ còn được pipeline ghi lại tới giờ khoá (sổ 05-11-2026 ghi bốn lần: 18:43, 20:17, 22:53 hôm trước
  // và 15:39), và commit cuối trước giờ khoá có thể lên muộn vài phút. Nên một sổ được tải lại mỗi
  // REFRESH_MS, cho tới khi lần tải đã cách giờ khoá quá SETTLE_MS: khi ấy nó là bản đóng băng cuối cùng.
  var REFRESH_MS = 600000;
  var SETTLE_MS = 3600000;
  // Tên miền và đường dẫn dữ liệu không được viết thẳng ra trang (luật riêng tư của kho).
  var E = { h: 'cmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbQ==', s: 'LmdpdGh1Yi5pbw==', b: 'bWFpbg==', p: 'ZGF0YS9ldmFsdWF0aW9uL3ByZWRpY3Rpb25fYm9hcmQv',
    c: 'ZGF0YS9ub25fZHJhd19kYXlzLmpzb24=', r: 'ZGF0YS9ldmFsdWF0aW9uL2JvYXJkX3JlY29yZC9yZWNvcmQuanNvbg==' };
  function d(k) { return atob(E[k]); }

  var title = document.getElementById('live-scorecard-date');
  var summary = document.getElementById('live-scorecard-summary');
  var table = document.getElementById('live-scorecard-table');
  // `draw`: kỳ của live.json (vừa quay hoặc đang quay); `next`: kỳ sắp quay, chỉ có khi `draw` đã quay xong.
  // `boards[ngày]`: sổ của đúng ngày ấy và trạng thái tải; chỉ giữ hai ngày đang hiện, nên phản hồi trễ của
  // ngày cũ không còn chỗ để rơi vào. `open`: số đang mở đường cầu {date, list, item, bridge}.
  var state = { draw: '', next: '', boards: {}, last: null, open: null, focus: null, reveal: null, mark: null };
  var BRIDGES_SHOWN = 12;

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
  function source(list, item, board) {
    if (list.bridge || POSITIONAL.test(list.id)) {
      if (!list.bridge) return null;
      if (!Array.isArray(item.bridges) || !item.bridges.length) return null;
      return { cfg: list.bridge, bridges: item.bridges, total: item.bridge_total || item.bridges.length,
        page: list.page, title: list.title, running: false };
    }
    var rule = item.rule || {};
    var mode = rule.on === 'loto' ? 'loto' : rule.on === 'special' ? 'de' : '';
    var table = mode && board && board.running && board.running[mode];
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

  // Bộ chọn đúng một nút số: cùng danh sách và cùng mục có ở cả hai hàng "Trước giờ quay" (hai kỳ).
  function chipSelector(date, listId, index) {
    return '[data-bridge-date="' + date + '"][data-bridge-list="' + listId + '"][data-bridge-item="' + index + '"]';
  }

  function isOpen(date, listId, index) {
    return !!state.open && state.open.date === date && state.open.list === listId &&
      (index === undefined || state.open.item === index);
  }

  function chips(list, board, o, after) {
    var wrap = el('ul', 'live-scorecard-chips');
    var date = board.target_date;
    list.items.forEach(function (item, index) {
      var chip = el('li', 'live-scorecard-chip');
      var host = chip;
      var src = after ? null : source(list, item, board);
      if (src) {
        var open = isOpen(date, list.id, index);
        host = el('button', 'live-scorecard-chip-btn');
        host.type = 'button';
        host.dataset.bridgeDate = date;
        host.dataset.bridgeList = list.id;
        host.dataset.bridgeItem = String(index);
        host.setAttribute('aria-expanded', open ? 'true' : 'false');
        host.setAttribute('aria-controls', 'live-bridge-' + list.id);
        host.setAttribute('aria-label', item.label + (src.running ? ': xem cầu đang chạy ghép ra số này'
          : ': xem vị trí đường cầu'));
        host.addEventListener('click', function () {
          state.open = open ? null : { date: date, list: list.id, item: index, label: item.label, bridge: 0, pick: '' };
          state.focus = chipSelector(date, list.id, index);
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

  // Ô "Thời điểm" của một hàng: lúc (trước / sau giờ quay) và kỳ của hàng ấy.
  function whenCell(text, date) {
    var cell = el('td', 'live-scorecard-when', text);
    cell.appendChild(el('small', 'live-scorecard-day', drawLabel(date)));
    return cell;
  }

  function beforeRow(list, board, o, className) {
    var row = el('tr', className);
    row.dataset.draw = board.target_date;
    var nums = el('td', '');
    nums.appendChild(chips(list, board, o, false));
    row.append(whenCell('Trước giờ quay', board.target_date), nums, el('td', 'live-scorecard-stat', beforeText(tally(list, o))));
    return row;
  }

  // Kỳ có sổ nhưng sổ ấy không có danh sách này (nguồn không khai đúng kỳ, ghi vào `missing` của sổ).
  function absentRow(board, className) {
    var row = el('tr', className + ' is-absent');
    row.dataset.draw = board.target_date;
    var cell = el('td', 'live-scorecard-absent', 'Sổ phỏng đoán của kỳ này không có danh sách này.');
    cell.colSpan = 2;
    row.append(whenCell('Trước giờ quay', board.target_date), cell);
    return row;
  }

  // Một danh sách là một <tbody>: kỳ sắp quay ("Trước giờ quay"), rồi kỳ vừa quay ("Trước giờ quay", "Sau
  // giờ quay"). `listNext` / `listDrawn` là danh sách cùng mã trong sổ của từng kỳ (thiếu thì null).
  function groupRows(id, listNext, listDrawn, next, drawn, o) {
    var tbody = el('tbody', 'live-scorecard-group');
    tbody.dataset.listId = id;
    var main = listDrawn || listNext;
    var head = el('th', 'live-scorecard-name');
    head.scope = 'rowgroup';
    var link = el('a', '', main.title);
    link.href = main.page;
    head.append(link, el('span', 'live-scorecard-group-name', main.group));
    var rows = [];
    if (next) rows.push(listNext ? beforeRow(listNext, next, outcome(null), 'is-next') : absentRow(next, 'is-next'));
    var t = null;
    if (drawn && listDrawn) {
      t = tally(listDrawn, o);
      rows.push(beforeRow(listDrawn, drawn, o, 'is-before'));
      var after = el('tr', 'is-after');
      after.dataset.draw = drawn.target_date;
      after.dataset.done = t.wait === 0 ? 'true' : 'false';
      var numsAfter = el('td', '');
      numsAfter.appendChild(chips(listDrawn, drawn, o, true));
      var stat = el('td', 'live-scorecard-stat', afterText(t));
      if (t.wait === 0) stat.dataset.verdict = t.hits > t.exp ? 'above' : t.hits < t.exp ? 'below' : 'equal';
      after.append(whenCell('Sau giờ quay', drawn.target_date), numsAfter, stat);
      rows.push(after);
    } else if (drawn) {
      rows.push(absentRow(drawn, 'is-before'));
    }
    head.rowSpan = rows.length;
    rows[0].insertBefore(head, rows[0].firstChild);
    rows.forEach(function (row) { tbody.appendChild(row); });
    var openBoard = state.open && state.open.list === id ? boardFor(state.open.date) : null;
    var openList = openBoard === next ? listNext : openBoard === drawn ? listDrawn : null;
    var openItem = openList ? openList.items[state.open.item] : null;
    var openSource = openItem ? source(openList, openItem, openBoard) : null;
    if (openSource) {
      var detail = el('tr', 'is-bridge');
      var cell = el('td', 'live-bridge-cell');
      cell.colSpan = 4;
      cell.appendChild(bridgePanel(openList, openItem, openSource, openBoard));
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

  // Liên kết mở trang nguồn ở đúng cầu đang xem, để các bảng kết quả của trang ấy tô sẵn hai vị trí:
  // soi cầu vị trí (`vt` + tham số chế độ), soi đường (`number` + mã đường `L<trễ>-[a,b]`), bảy trang soi cầu
  // và hai trang tra cầu đang chạy (`ngay` = kỳ cuối của đường cầu, `so` = số ghép ở kỳ ấy, `vt`; trang theo
  // thứ thêm `thu`, cùng cách đánh số 0 = Thứ Hai của bridge_pages.js).
  function bridgeLink(list, src, item, bridge, board) {
    var cfg = src.cfg;
    var q = new URLSearchParams();
    if (!bridge) return src.page;
    if (cfg.type === 'position' && cfg.query) {
      q.set('vt', bridge.a + 'x' + bridge.b);
      Object.keys(cfg.query).forEach(function (k) { q.set(k, String(cfg.query[k])); });
      return src.page + '?' + q.toString() + '#app-bridge-results';
    }
    if (cfg.type === 'path') {
      q.set('number', item.rule.numbers[0]);
      q.set('path', 'L' + bridge.lag + '-[' + bridge.a + ',' + bridge.b + ']');
      return src.page + '?' + q.toString();
    }
    var series = cfg.series || [];
    var last = series[series.length - 1];
    var values = last && board.draws ? board.draws[last] : null;
    if (last) q.set('ngay', last);
    if (Array.isArray(values)) q.set('so', two(formed(values, bridge.a, bridge.b)));
    q.set('vt', bridge.a + 'x' + bridge.b);
    if (last && !src.running && /-theo-thu$/.test(list.id)) {
      q.set('thu', String((new Date(last + 'T00:00:00Z').getUTCDay() + 6) % 7));
    }
    return src.page + '?' + q.toString();
  }

  // Bảng kết quả đầu trang (docs/live.html, #results): 27 ô theo đúng thứ tự giải. Trước giờ quay nó hiện kỳ
  // vừa quay — cũng là kỳ cuối mà cầu ghép số — nên hai vị trí của cầu đang mở được tô ngay trên đó. Chỉ tô khi
  // MỌI ô trùng kết quả đã nhúng của kỳ ấy (bảng đang hiện kỳ khác, hay giải chưa hiện hết, thì không tô).
  var MARK = 'data-bridge-mark';

  function boardSlots(values) {
    var host = document.getElementById('results');
    if (!host || !Array.isArray(values)) return null;
    var slots = host.querySelectorAll('.slot');
    if (slots.length !== VALUE_FIRST.length) return null;
    for (var i = 0; i < slots.length; i++) {
      if (slots[i].textContent !== values[i]) return null;
    }
    return { slots: slots, values: values };
  }

  function markBoard(mark) {
    var host = document.getElementById('results');
    if (!host) return;
    Array.prototype.forEach.call(host.querySelectorAll('[' + MARK + ']'), function (slot) {
      slot.textContent = slot.textContent;
      slot.removeAttribute(MARK);
    });
    var shown = mark && boardSlots(mark.values);
    if (!shown) return;
    var marks = {};
    [['a', mark.a], ['b', mark.b]].forEach(function (pair) {
      var index = POSITIONS[pair[1]].value;
      (marks[index] = marks[index] || {})[pair[1] - VALUE_FIRST[index]] = pair[0];
    });
    Object.keys(marks).forEach(function (index) {
      var slot = shown.slots[index];
      var text = shown.values[index];
      slot.setAttribute(MARK, '');
      slot.replaceChildren();
      for (var k = 0; k < text.length; k++) {
        var which = marks[index][k];
        if (!which) { slot.appendChild(document.createTextNode(text[k])); continue; }
        var span = el('span', 'live-board-src live-board-src--' + which, text[k]);
        span.setAttribute('aria-label', positionText(VALUE_FIRST[index] + k) + ': ' + text[k]);
        slot.appendChild(span);
      }
    });
  }

  function bridgePath(src, bridge, board) {
    var cfg = src.cfg;
    var draws = board.draws || {};
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
        (t === shown.length - 1 ? ' cho kỳ ' + dayLabel(board.target_date) : '') + step;
      wrap.appendChild(dayCard(shown[t], values, bridge, cfg.mark, found, caption));
    }
    return wrap;
  }

  function keysText(keys) {
    return keys.map(function (key) { return key.split(',').join(' · '); }).join(', ');
  }

  function bridgePanel(list, item, src, board) {
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
    var opened = state.open;
    close.addEventListener('click', function () {
      state.open = null;
      state.focus = chipSelector(opened.date, list.id, opened.item);
      render();
    });
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
          state.open = { date: opened.date, list: list.id, item: opened.item, label: opened.label, bridge: i,
            pick: bridgeKey(b) };
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
      panel.appendChild(bridgePath(src, bridge, board));
    }
    if (bridge) {
      // Kỳ ghép số của cầu: kỳ cuối của chuỗi; soi đường thì kỳ gốc của chính đường ấy.
      var source = cfg.type === 'path' ? bridge.base : (cfg.series || [])[(cfg.series || []).length - 1];
      var sourceValues = board.draws ? board.draws[source] : null;
      state.mark = { date: source, a: bridge.a, b: bridge.b, values: sourceValues };
      if (boardSlots(sourceValues)) {
        var onBoard = el('p', 'live-bridge-onboard');
        onBoard.appendChild(document.createTextNode('Hai vị trí này đang được tô trên bảng kết quả kỳ ' +
          dayLabel(source) + ' ở đầu trang. '));
        var up = el('a', '', 'Lên bảng kết quả ↑');
        up.href = '#results';
        onBoard.appendChild(up);
        panel.appendChild(onBoard);
      }
    }
    var link = el('a', 'live-bridge-link', 'Xem trên trang ' + src.title + ' →');
    link.href = bridgeLink(list, src, item, bridge, board);
    panel.appendChild(link);
    if (bridge && validDate(source)) {
      // Sổ kết quả truyền thống mở đúng kỳ ghép số và tô hai vị trí (traditional_results.js, `vt`).
      var book = el('a', 'live-bridge-link live-bridge-book', 'Xem trên Sổ kết quả →');
      book.href = 'so-ket-qua-truyen-thong.html?' + new URLSearchParams({ ngay: source, vt: bridge.a + 'x' + bridge.b });
      panel.appendChild(book);
    }
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

  // ---- Hai kỳ trên một bảng ----------------------------------------------------------

  // Ngày hôm nay theo giờ Việt Nam (UTC+7, không có giờ mùa hè).
  function todayVN() {
    return new Date(Date.now() + 7 * 3600000).toISOString().slice(0, 10);
  }

  function previousDay(value) {
    var day = new Date(value + 'T00:00:00Z');
    day.setUTCDate(day.getUTCDate() - 1);
    return day.toISOString().slice(0, 10);
  }

  // "kỳ 05/11 · hôm nay": ngày của kỳ, kèm hôm nay / hôm qua / ngày mai khi đúng như thế theo giờ VN.
  function drawLabel(date) {
    var today = todayVN();
    var near = date === today ? 'hôm nay' : date === previousDay(today) ? 'hôm qua'
      : date === nextDay(today) ? 'ngày mai' : '';
    return 'kỳ ' + date.slice(8, 10) + '/' + date.slice(5, 7) + (near ? ' · ' + near : '');
  }

  function boardFor(date) {
    var entry = date ? state.boards[date] : null;
    return entry && entry.board ? entry.board : null;
  }

  // Câu trạng thái của một kỳ chưa có sổ để đặt lên bảng.
  function statusText(date) {
    var entry = state.boards[date];
    var status = entry ? entry.status : 'loading';
    return status === 'missing' ? 'Chưa có sổ phỏng đoán đóng băng cho kỳ này.'
      : status === 'mismatch' ? 'Sổ phỏng đoán không khớp kỳ quay này.'
        : status === 'error' ? 'Chưa tải được sổ phỏng đoán. Sẽ thử lại.' : 'Đang tải sổ phỏng đoán…';
  }

  function nextLine(board) {
    var t = { k: 0, exp: 0, base: 0 };
    board.lists.forEach(function (list) {
      var one = tally(list, outcome(null));
      t.k += one.k; t.exp += one.exp; t.base += one.base;
    });
    // Trước giờ khoá sổ còn có thể được ghi lại: nói "khoá lúc", chỉ sau đó mới là "đã đóng băng".
    var at = String(board.locks_at || '').slice(11, 16);
    var locked = !(Date.now() < Date.parse(board.locks_at));
    return board.lists.length + ' danh sách, ' + t.k + ' mục' + (locked ? ' đã đóng băng lúc ' : ', khoá lúc ') + at +
      ' · kỳ vọng trúng ' + number(t.exp, 2) +
      ' mục theo xác suất công bố (' + number(t.base, 2) + ' nếu chọn bừa).';
  }

  function render() {
    var drawn = boardFor(state.draw);
    var next = state.next ? boardFor(state.next) : null;
    if (!drawn && !next) { message(statusText(state.draw)); return; }
    // Kết quả trong live.json là của kỳ `draw`; kỳ sắp quay chưa có giải nào.
    var o = outcome(state.last && state.last.prizes);
    var ids = [], byId = {};
    [drawn, next].forEach(function (board, which) {
      if (!board) return;
      board.lists.forEach(function (list) {
        if (!byId[list.id]) { byId[list.id] = [null, null]; ids.push(list.id); }
        byId[list.id][which] = list;
      });
    });
    var frag = document.createDocumentFragment();
    var total = { hits: 0, exp: 0, base: 0, k: 0, wait: 0 };
    state.mark = null;
    ids.forEach(function (id) {
      var g = groupRows(id, byId[id][1], byId[id][0], next, drawn, o);
      frag.appendChild(g.body);
      if (!g.tally) return;
      total.hits += g.tally.hits; total.exp += g.tally.exp; total.base += g.tally.base;
      total.k += g.tally.k; total.wait += g.tally.wait;
    });
    clearGroups();
    table.appendChild(frag);
    markBoard(state.mark);
    if (state.focus) {
      var target = table.querySelector(state.focus);
      state.focus = null;
      if (target) target.focus();
    }
    // Tóm tắt theo đúng thứ tự các hàng: kỳ sắp quay trước, rồi kỳ vừa quay.
    var lines = [];
    if (state.next) {
      lines.push('Kỳ sắp quay (' + drawLabel(state.next) + '): ' + (next ? nextLine(next) : statusText(state.next)));
    }
    var head = (state.next ? 'Kỳ vừa quay' : 'Kỳ đang quay') + ' (' + drawLabel(state.draw) + '): ';
    if (!drawn) {
      lines.push(head + statusText(state.draw));
    } else if (total.wait === total.k) {
      lines.push(head + nextLine(drawn));
    } else {
      lines.push(head + 'đã trúng ' + total.hits + '/' + total.k + ' mục' + (total.wait ? ' · còn chờ ' + total.wait : '') +
        ' · kỳ vọng ' + number(total.exp, 2) + ' theo xác suất công bố, ' + number(total.base, 2) + ' nếu chọn bừa.');
    }
    if (drawn) lines = lines.concat(vectorLines(drawn, o));
    summary.replaceChildren();
    lines.forEach(function (line) { summary.appendChild(el('p', '', line)); });
    root.dataset.state = drawn ? (o.complete ? 'complete' : (o.filled ? 'partial' : 'waiting')) : 'waiting';
  }

  // Mỗi danh sách là một <tbody> riêng gắn thẳng vào bảng, sau <thead>: lồng <tbody> vào
  // <tbody> là HTML sai và làm trình duyệt dựng lệch cột.
  function clearGroups() {
    Array.prototype.slice.call(table.tBodies).forEach(function (group) { group.remove(); });
  }

  function message(text) {
    clearGroups();
    markBoard(null);
    summary.replaceChildren(el('p', '', text));
    root.dataset.state = 'empty';
  }

  // Tải sổ của một ngày, một lần; 404 hay lỗi thì chờ rồi mới hỏi lại. Kết quả chỉ được dùng khi ngày ấy
  // vẫn còn trên bảng (`entry` vẫn là chỗ của nó): phản hồi trễ của kỳ cũ bị bỏ.
  function ensure(date) {
    if (!date) return Promise.resolve();
    var entry = state.boards[date];
    if (!entry) entry = state.boards[date] = { board: null, status: 'loading', pending: false, retryAt: 0, fetchedAt: 0 };
    if (entry.pending || Date.now() < entry.retryAt || (entry.board && settled(entry))) return Promise.resolve();
    return fetchBoard(date, entry);
  }

  // Sổ đã tải đủ mới: vừa tải chưa tới REFRESH_MS, hoặc lần tải đã cách giờ khoá quá SETTLE_MS (bản cuối).
  function settled(entry) {
    var locks = Date.parse(entry.board.locks_at);
    return Date.now() - entry.fetchedAt < REFRESH_MS || (!isNaN(locks) && entry.fetchedAt >= locks + SETTLE_MS);
  }

  // Tải lại hỏng thì giữ bản đang hiện (status vẫn 'ok'), chỉ hẹn lần thử sau.
  async function fetchBoard(date, entry) {
    entry.pending = true;
    if (!entry.board) entry.status = 'loading';
    var started = Date.now();
    try {
      var response = await fetch(boardUrl(date), { cache: 'no-store' });
      if (state.boards[date] !== entry) return;
      if (response.status === 404) {
        if (!entry.board) entry.status = 'missing';
        entry.retryAt = Date.now() + RETRY_MISSING_MS;
      } else {
        if (!response.ok) throw new Error(String(response.status));
        var board = await response.json();
        if (state.boards[date] !== entry) return;
        if (!board || board.target_date !== date || !Array.isArray(board.lists)) {
          if (!entry.board) entry.status = 'mismatch';
          entry.retryAt = Date.now() + RETRY_MISSING_MS;
        } else {
          entry.board = board;
          entry.status = 'ok';
          entry.fetchedAt = started;
          reconcileOpen(date, board);
          applyReveal();
        }
      }
    } catch (_error) {
      if (state.boards[date] !== entry) return;
      if (!entry.board) entry.status = 'error';
      entry.retryAt = Date.now() + RETRY_ERROR_MS;
    } finally {
      entry.pending = false;
    }
    if (state.boards[date] === entry && (date === state.draw || date === state.next)) render();
  }

  // Danh tính một cầu trong danh sách của một số: cặp vị trí, cộng độ trễ với soi đường — hai đường cầu có thể
  // chung cặp vị trí mà khác độ trễ (sổ 05-11-2026: số 34 của path-loto-active có 14×39 ở trễ 6 và trễ 9).
  function bridgeKey(b) {
    return b.a + 'x' + b.b + (b.lag === undefined || b.lag === null ? '' : '@' + b.lag);
  }

  // Sổ vừa tải lại có thể đã đổi mục (sổ còn được ghi tới giờ khoá): số đang mở giữ đúng NHÃN của nó và cầu
  // đang chọn giữ đúng danh tính (bridgeKey), không theo chỉ số cũ — chỉ số cũ có thể đã trỏ sang số khác. Số
  // không còn trong bản mới thì đóng bảng cầu; cầu không còn thì về cầu đầu.
  function reconcileOpen(date, board) {
    var open = state.open;
    if (!open || open.date !== date) return;
    var list = board.lists.filter(function (l) { return l.id === open.list; })[0];
    var index = -1;
    if (list) {
      for (var i = 0; i < list.items.length; i++) if (list.items[i].label === open.label) { index = i; break; }
    }
    if (index < 0) { state.open = null; return; }
    var src = source(list, list.items[index], board);
    if (!src) { state.open = null; return; }
    var pick = -1;
    for (var k = 0; open.pick && k < src.bridges.length; k++) {
      if (bridgeKey(src.bridges[k]) === open.pick) { pick = k; break; }
    }
    state.open = { date: date, list: open.list, item: index, label: open.label, bridge: pick < 0 ? 0 : pick,
      pick: pick < 0 ? '' : open.pick };
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

  // Đặt hai kỳ của bảng; chỉ giữ sổ của đúng hai ngày ấy.
  function setDraws(draw, next) {
    if (draw !== state.draw) state.open = null;
    state.draw = draw;
    state.next = next;
    Object.keys(state.boards).forEach(function (date) {
      if (date !== draw && date !== next) delete state.boards[date];
    });
    if (state.open && state.open.date !== draw && state.open.date !== next) state.open = null;
    // Lệnh mở số cho kỳ không còn trên bảng bị bỏ, không treo mãi.
    if (state.reveal && state.reveal.date !== draw && state.reveal.date !== next) state.reveal = null;
    title.dateTime = draw;
    title.textContent = draw ? dayLabel(draw) : 'Đang chờ ngày quay';
  }

  function refresh() {
    applyReveal();
    render();
    return Promise.all([ensure(state.draw), ensure(state.next)]).then(function () { return undefined; });
  }

  function update(snapshot) {
    state.last = snapshot || null;
    var date = snapshot && snapshot.draw_date;
    if (!validDate(date)) {
      setDraws('', '');
      message('Đang chờ ngày quay.');
      return Promise.resolve();
    }
    if (!finished(snapshot.status)) {
      setDraws(date, '');
      return refresh();
    }
    // Giữ kỳ sắp quay đã biết trong lúc đọc lịch nghỉ, để bảng không chớp mất hàng của nó.
    if (date !== state.draw) setDraws(date, '');
    return closedDays().then(function (skip) {
      if (state.last !== snapshot) return undefined;
      setDraws(date, nextDraw(date, skip));
      return refresh();
    });
  }

  // Mở đúng số ấy trong bảng (bấm từ khối "Dự đoán trong ngày"): mục của danh sách Cầu Kèo cùng
  // kiểu, không có thì mục đầu tiên nào chỉ gồm số ấy — trong sổ của đúng kỳ đã bấm.
  function applyReveal() {
    var want = state.reveal;
    var board = want ? boardFor(want.date) : null;
    if (!board) return;
    state.reveal = null;
    var lists = board.lists.slice().sort(function (u, v) {
      return (u.id === want.list ? 0 : 1) - (v.id === want.list ? 0 : 1);
    });
    for (var i = 0; i < lists.length; i++) {
      for (var j = 0; j < lists[i].items.length; j++) {
        var item = lists[i].items[j], rule = item.rule || {};
        if (rule.on !== want.on || !Array.isArray(rule.numbers) || rule.numbers.length !== 1 ||
            rule.numbers[0] !== want.number || !source(lists[i], item, board)) continue;
        state.open = { date: want.date, list: lists[i].id, item: j, label: item.label, bridge: 0, pick: '' };
        state.focus = chipSelector(want.date, lists[i].id, j);
        return;
      }
    }
  }

  function reveal(date, mode, value) {
    if (!validDate(date) || (mode !== 'de' && mode !== 'loto')) return Promise.resolve();
    state.reveal = { date: date, list: 'cau-keo-' + mode, on: mode === 'de' ? 'special' : 'loto', number: two(Number(value)) };
    // Chưa biết kỳ ấy có trên bảng không (live.json chưa về, lịch nghỉ đang tải): giữ lệnh, update() xử lý.
    if (date !== state.draw && date !== state.next) return Promise.resolve();
    return refresh();
  }

  // Thành tích qua các kỳ đã quay (src/evaluation/board_record.py): mỗi danh sách trúng bao nhiêu so với chọn
  // bừa, cộng dồn mọi kỳ đã có đủ 27 giải. Một kỳ là mẫu quá nhỏ; khối này là câu trả lời có cỡ mẫu. Chỉ tải khi
  // người đọc mở khối, một lần (tải hỏng thì lần mở sau thử lại). Kết luận in TỪ p của tệp, không viết sẵn.
  var record = el('details', 'live-record');
  record.id = 'live-record';
  var recordTitle = el('summary', 'live-record-summary', 'Thành tích qua các kỳ đã quay');
  var recordBody = el('div', 'live-record-body');
  record.append(recordTitle, recordBody);
  root.appendChild(record);
  var recordLoad = null;

  function pValue(p) {
    return p < 0.001 ? '< 0,001' : number(p, 3);
  }

  function verdictClass(text) {
    return /nhiều hơn/.test(text) ? 'above' : /ít hơn/.test(text) ? 'below' : 'same';
  }

  function validRecord(data) {
    return !!data && data.version === 1 && Array.isArray(data.lists) && !!data.family && data.draws > 0 &&
      validDate(data.first) && validDate(data.last);
  }

  function renderRecord(data) {
    if (!validRecord(data)) {
      recordLoad = null;
      recordBody.replaceChildren(el('p', 'live-record-status', 'Chưa đọc được thành tích các kỳ; mở lại để thử lần nữa.'));
      return;
    }
    recordTitle.textContent = 'Thành tích qua ' + data.draws + ' kỳ đã quay (' + dayLabel(data.first) + ' → ' +
      dayLabel(data.last) + ')';
    var family = data.family;
    var lead = el('p', 'live-record-lead');
    lead.append('Gộp mọi danh sách: trúng ' + family.hits + ' mục, chọn bừa kỳ vọng ' + number(family.expected, 1) +
      ' (p = ' + pValue(family.p) + ') — ');
    var familyVerdict = el('strong', 'live-record-verdict', family.verdict);
    familyVerdict.dataset.verdict = verdictClass(family.verdict);
    lead.appendChild(familyVerdict);
    lead.append('.');

    var tableNode = el('table', 'live-record-table');
    tableNode.appendChild(el('caption', '', 'Mỗi danh sách cộng qua các kỳ có mặt: mục trúng, kỳ vọng và kỳ có ít nhất một mục trúng'));
    var head = el('tr');
    ['Danh sách', 'Số kỳ', 'Mục trúng', 'Chọn bừa', 'Theo xác suất công bố', 'Kỳ có trúng', 'p (Holm)', 'Kết luận']
      .forEach(function (text) {
        var th = el('th', '', text);
        th.scope = 'col';
        head.appendChild(th);
      });
    var thead = el('thead');
    thead.appendChild(head);
    var tbody = el('tbody');
    data.lists.forEach(function (row) {
      var tr = el('tr');
      tr.dataset.listId = row.id;
      var name = el('th', 'live-record-name');
      name.scope = 'row';
      // Lớp riêng, không phải `span`/`small` chung: module bằng chứng bọc chữ số («10») trong span của nó.
      name.appendChild(el('span', 'live-record-title', row.title));
      if (row.group) name.appendChild(el('small', 'live-record-group', row.group));
      var verdict = el('td', 'live-record-verdict', row.verdict);
      verdict.dataset.verdict = verdictClass(row.verdict);
      // Nhãn cột đi kèm từng ô: trên điện thoại bảng xếp thành khối và đầu cột bị ẩn.
      function cell(label, text) {
        var td = el('td', 'live-record-num', text);
        td.dataset.label = label;
        return td;
      }
      tr.append(
        name,
        cell('Số kỳ', row.draws),
        cell('Mục trúng', row.hits),
        cell('Chọn bừa', number(row.expected, 1)),
        cell('Theo xác suất công bố', row.published_items > 0 ? number(row.expected_published, 1) : '—'),
        cell('Kỳ có trúng', row.days_hit + ' / ' + number(row.days_expected, 1)),
        cell('p (Holm)', pValue(row.p_holm)),
        verdict
      );
      tbody.appendChild(tr);
    });
    tableNode.append(thead, tbody);
    var scroll = el('div', 'live-scorecard-scroll');
    scroll.appendChild(tableNode);
    var method = data.method || {};
    var note = el('p', 'live-record-note', 'Chấm theo kỳ, so với ' + Number(method.simulations || 0).toLocaleString('vi-VN') +
      ' kỳ quay công bằng mô phỏng (27 đuôi độc lập, đều trên 00–99), nên tính đúng việc các mục trong một danh sách ' +
      'trùng nhau. «Chọn bừa» là số mục trúng kỳ vọng khi mọi số như nhau; «Kỳ có trúng» là số kỳ có ít nhất một mục ' +
      'trúng so với kỳ vọng. p hai phía, hiệu chỉnh ' + (method.adjust || 'Holm') + ' trên ' + data.lists.length +
      ' danh sách; «chưa khác chọn bừa» nghĩa là chênh lệch nằm trong dao động ngẫu nhiên của chừng ấy kỳ.');
    recordBody.replaceChildren(lead, scroll, note);
  }

  record.addEventListener('toggle', function () {
    if (!record.open || recordLoad) return;
    recordBody.replaceChildren(el('p', 'live-record-status', 'Đang tải thành tích các kỳ…'));
    recordLoad = fetch(root.dataset.recordUrl || dataUrl(d('r')), { cache: 'no-store' })
      .then(function (response) { return response.ok ? response.json() : null; })
      .catch(function () { return null; })
      .then(renderRecord);
  });

  window.LiveScorecard = { update: update, reveal: reveal, judge: judge, outcome: outcome };
})();
