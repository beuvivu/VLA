(() => {
  "use strict";

  // Soi cầu vị trí — bản trình duyệt của `src/soi_cau/position_bridges.py`.
  //
  // Hai bản PHẢI đếm ra cùng một con số: trang chủ in ba ô "đẹp nhất" từ bản
  // Python, còn trang này tính lại từ đúng những kỳ đã nhúng. Phép kiểm
  // `tests/frontend/position-bridges.test.mjs` chạy bản này trên dữ liệu thật
  // và so từng cầu với bản Python.
  //
  // Mọi phần tử dựng bằng createElement + textContent; không gán chuỗi HTML.

  const DATA = document.getElementById("app-bridge-data");
  if (!DATA) return;
  const REPORT = JSON.parse(DATA.textContent);

  // (mã giải, nhãn ngắn, nhãn Sổ kết quả, số giải, số chữ số) — cùng thứ tự
  // với LAYOUT bên Python.
  const LAYOUT = [
    ["special", "ĐB", "Đặc Biệt", 1, 5],
    ["prize1", "G1", "Giải Nhất", 1, 5],
    ["prize2", "G2", "Giải Nhì", 2, 5],
    ["prize3", "G3", "Giải Ba", 6, 5],
    ["prize4", "G4", "Giải Tư", 4, 4],
    ["prize5", "G5", "Giải Năm", 6, 4],
    ["prize6", "G6", "Giải Sáu", 3, 3],
    ["prize7", "G7", "Giải Bảy", 4, 2],
  ];
  const SHADOW = [5, 6, 7, 8, 9, 0, 1, 2, 3, 4];
  const WEEKDAYS = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];

  // Vị trí 0..106: thuộc giá trị nào trong 27 giải, chữ số thứ mấy.
  const POSITIONS = [];
  const VALUES = [];
  for (const [code, short, name, count, width] of LAYOUT) {
    for (let i = 0; i < count; i += 1) {
      const valueIndex = VALUES.length;
      const label = short + (count > 1 ? `.${i + 1}` : "");
      VALUES.push({ code, name, label, width, first: POSITIONS.length });
      for (let d = 0; d < width; d += 1) {
        POSITIONS.push({ value: valueIndex, digit: d, label: `${label} · chữ số ${d + 1}` });
      }
    }
  }
  const N_POS = POSITIONS.length;

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const pad = (n) => String(n).padStart(2, "0");

  function formatDate(iso, weekday = false) {
    const [y, m, d] = iso.split("-").map(Number);
    const text = `${pad(d)}/${pad(m)}/${y}`;
    if (!weekday) return text;
    return `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}, ${text}`;
  }

  // ---- Dữ liệu --------------------------------------------------------------

  function prepare(draws) {
    return draws.map((draw) => {
      const digits = new Int8Array(N_POS);
      let cursor = 0;
      for (const value of draw.values) {
        for (const ch of value) digits[cursor++] = ch.charCodeAt(0) - 48;
      }
      const two = draw.values.map((value) => Number(value.slice(-2)));
      const counts = new Int16Array(100);
      for (const n of two) counts[n] += 1;
      return { date: draw.date, values: draw.values, digits, two, counts };
    });
  }

  /** Mọi cặp vị trí: a < b khi lộn, a ≠ b khi không lộn — như `pair_index`. */
  function pairs(lon) {
    const a = [];
    const b = [];
    for (let i = 0; i < N_POS; i += 1) {
      for (let j = 0; j < N_POS; j += 1) {
        if (lon ? i < j : i !== j) { a.push(i); b.push(j); }
      }
    }
    return { a: Int16Array.from(a), b: Int16Array.from(b) };
  }

  /** Số cầu (a, b) dựng từ một kỳ báo cho kỳ sau. */
  function numbersOf(digits, a, b, lon) {
    const x = digits[a];
    const y = digits[b];
    const first = 10 * x + y;
    return !lon || x === y ? [first] : [first, 10 * y + x];
  }

  /** Kỳ `next` có trúng các số `nums` không, theo đúng luật của `hit_matrix`. */
  function hits(nums, next, params) {
    if (params.db) return nums.includes(next.two[0]);
    let total = 0;
    for (const n of nums) total += next.counts[n];
    return total >= params.nhay;
  }

  /** Độ dài cầu (số kỳ trúng liên tiếp) của mọi cặp vị trí tính đến kỳ cuối. */
  function streaks(prepared, params) {
    const { a, b } = pairs(params.lon);
    const runs = new Int16Array(a.length);
    for (let t = 0; t + 1 < prepared.length; t += 1) {
      const digits = prepared[t].digits;
      const next = prepared[t + 1];
      for (let p = 0; p < a.length; p += 1) {
        runs[p] = hits(numbersOf(digits, a[p], b[p], params.lon), next, params) ? runs[p] + 1 : 0;
      }
    }
    return { a, b, runs };
  }

  function shadowOf(nums) {
    if (nums.length !== 1 || Math.floor(nums[0] / 10) !== nums[0] % 10) return null;
    const d = SHADOW[nums[0] % 10];
    return `${d}${d}`;
  }

  const pairKey = (numbers) => [...numbers].sort().join(",");

  function findBridges(prepared, params) {
    const { a, b, runs } = streaks(prepared, params);
    const last = prepared[prepared.length - 1].digits;
    const out = [];
    for (let p = 0; p < runs.length; p += 1) {
      const keep = params.exact ? runs[p] === params.limit : runs[p] >= params.limit;
      if (!keep) continue;
      const nums = numbersOf(last, a[p], b[p], params.lon);
      out.push({
        a: a[p], b: b[p], vt: `${a[p]}x${b[p]}`, streak: runs[p],
        numbers: nums.map(pad), shadow: shadowOf(nums),
      });
    }
    out.sort((u, v) => (u.numbers[0] < v.numbers[0] ? -1 : u.numbers[0] > v.numbers[0] ? 1
      : u.a - v.a || u.b - v.b));
    return out;
  }

  function summarize(bridges, limit) {
    const byPair = new Map();
    for (const bridge of bridges) {
      const key = pairKey(bridge.numbers);
      if (!byPair.has(key)) byPair.set(key, []);
      byPair.get(key).push(bridge);
    }
    // sort ổn định: hoà thì giữ thứ tự xuất hiện trong danh sách cầu.
    const repeats = [...byPair.entries()].sort((u, v) => v[1].length - u[1].length);
    return {
      count: bridges.length,
      longer: bridges.filter((x) => x.streak > limit).length,
      pairs: byPair.size,
      pairsLonger: [...byPair.values()].filter((v) => v.some((x) => x.streak > limit)).length,
      repeats: repeats.map(([pair, list]) => ({ pair, bridges: list.length })),
    };
  }

  /** Đường cầu của một cặp vị trí qua mọi kỳ đã nhúng. */
  function pathOf(prepared, a, b, params) {
    const days = prepared.map((draw, t) => {
      const nums = numbersOf(draw.digits, a, b, params.lon);
      const prev = t > 0 ? numbersOf(prepared[t - 1].digits, a, b, params.lon) : null;
      return {
        draw, nums, prev,
        hit: prev ? hits(prev, draw, params) : null,
        found: prev ? foundCells(draw, prev, params) : [],
      };
    });
    let streak = 0;
    for (let t = days.length - 1; t > 0 && days[t].hit; t -= 1) streak += 1;
    return { days, streak };
  }

  /** Ô nào của kỳ này mang số mà cầu kỳ trước báo — tô cả khi chưa đủ nháy. */
  function foundCells(draw, nums, params) {
    const cells = [];
    const limit = params.db ? 1 : draw.two.length;
    for (let j = 0; j < limit; j += 1) {
      if (nums.includes(draw.two[j])) cells.push(j);
    }
    return cells;
  }

  // ---- Tham số ----------------------------------------------------------

  const DEFAULTS = { limit: 5, exact: false, nhay: 1, db: false, lon: true };

  function readParams(search) {
    const q = new URLSearchParams(search);
    const int = (name, lo, hi, fallback) => {
      const n = Number.parseInt(q.get(name) ?? "", 10);
      return Number.isInteger(n) && n >= lo && n <= hi ? n : fallback;
    };
    const params = {
      limit: int("limit", 1, REPORT.window - 1, DEFAULTS.limit),
      exact: q.get("exactlimit") === "1",
      nhay: int("nhay", 1, 5, DEFAULTS.nhay),
      db: q.get("db") === "1",
      lon: q.has("lon") ? q.get("lon") !== "0" : DEFAULTS.lon,
      vt: null,
      days: int("days", 1, REPORT.window - 1, 0),
    };
    if (params.db) params.nhay = 1;
    const match = /^(\d{1,3})x(\d{1,3})$/.exec(q.get("vt") || "");
    if (match) {
      let a = Number(match[1]);
      let b = Number(match[2]);
      if (a < N_POS && b < N_POS && a !== b) {
        if (params.lon && a > b) [a, b] = [b, a];
        params.vt = { a, b };
      }
    }
    return params;
  }

  function query(params, vt) {
    const q = new URLSearchParams();
    if (vt) q.set("vt", `${vt.a}x${vt.b}`);
    q.set("limit", String(params.limit));
    q.set("exactlimit", params.exact ? "1" : "0");
    q.set("lon", params.lon ? "1" : "0");
    q.set("nhay", String(params.nhay));
    q.set("db", params.db ? "1" : "0");
    return `?${q.toString()}`;
  }

  function modeTitle(params) {
    const kind = params.db ? "Cầu Đặc Biệt" : params.nhay > 1 ? `Cầu LOTO ${params.nhay} nháy` : "Cầu LOTO";
    return params.lon ? kind : `${kind} (không lộn)`;
  }

  /** Dòng lịch sử khớp chế độ đang xem, nếu chế độ ấy có trong ba ô mẫu. */
  function backtestFor(params) {
    for (const mode of Object.values(REPORT.backtests || {})) {
      if (mode.db === params.db && mode.lon === params.lon && (params.db || mode.nhay === params.nhay)) {
        return mode;
      }
    }
    return null;
  }

  const percent = (x) => `${(x * 100).toFixed(1).replace(".", ",")}%`;

  // ---- Dựng giao diện ---------------------------------------------------

  function numberChips(bridge, big = false) {
    const box = el("span", big ? "app-bridge-numbers app-bridge-numbers--big" : "app-bridge-numbers");
    // Mỗi số một phần tử: "67,76" viết liền đọc như số thập phân 67,76.
    const pair = el("b", "");
    bridge.numbers.forEach((n, i) => {
      if (i) pair.append(",");
      pair.append(el("span", "app-bridge-num", n));
    });
    box.append(pair);
    if (bridge.shadow) {
      const note = el("small", "app-bridge-shadow", "bóng ");
      note.append(el("span", "app-bridge-num", bridge.shadow));
      note.setAttribute("aria-label", `Số bóng ${bridge.shadow}, chỉ tham khảo, không tính vào cầu`);
      box.append(note);
    }
    return box;
  }

  function renderPrediction(host, params, path, a, b) {
    const last = path.days[path.days.length - 1];
    const nums = last.nums.map(pad);
    const card = el("div", "app-bridge-predict");
    const head = el("p", "app-bridge-predict-label", `Cầu báo cho kỳ ${formatDate(REPORT.target_date)}`);
    card.append(head);
    card.append(numberChips({ numbers: nums, shadow: shadowOf(last.nums) }, true));
    const run = el("p", "app-bridge-run");
    if (path.streak > 0) {
      run.append(document.createTextNode("Đã chạy "));
      run.append(el("b", "", `${path.streak} kỳ`));
      run.append(document.createTextNode(` liên tiếp tính đến ${formatDate(REPORT.source_date)}.`));
    } else {
      run.textContent = `Cầu này không trúng ở kỳ ${formatDate(REPORT.source_date)} — không phải cầu đang chạy.`;
    }
    card.append(run);
    const where = el("p", "app-bridge-where");
    where.textContent = `Vị trí ${a}: ${POSITIONS[a].label} · Vị trí ${b}: ${POSITIONS[b].label}`;
    card.append(where);
    const history = backtestFor(params);
    if (history && path.streak > 0) {
      const k = Math.min(path.streak, history.rows.length - 1);
      const row = history.rows[k];
      if (row && row.n >= 200) {
        const note = el("p", "app-bridge-honest");
        note.textContent = `Trên ${history.draws.toLocaleString("vi-VN")} kỳ đã quay, cầu đã chạy `
          + `${row.plus ? `từ ${row.k}` : row.k} kỳ trúng tiếp ${percent(row.rate)} số lần; `
          + `kỳ vọng nếu độ dài không mang thông tin là ${percent(row.expected)}.`;
        card.append(note);
      }
    }
    host.append(card);
  }

  function renderDayCard(day, a, b, params) {
    const article = el("article", "tr-day app-bridge-day");
    const header = el("header", "tr-day-head");
    const title = el("div", "tr-day-title");
    title.append(el("h2", "", `Mở thưởng ${formatDate(day.draw.date, true)}`));
    const facts = el("p", "app-bridge-facts");
    facts.append(el("span", "app-bridge-fact-src", `Ghép từ kỳ này → kỳ sau: ${day.nums.map(pad).join(", ")}`));
    if (day.prev) {
      const seen = new Map();
      for (const j of day.found) {
        const n = pad(day.draw.two[j]);
        seen.set(n, (seen.get(n) || 0) + 1);
      }
      const got = [...seen].map(([n, c]) => (c > 1 ? `${n}×${c}` : n)).join(", ");
      const text = got ? `Kỳ trước báo ${day.prev.map(pad).join(", ")} · Về: ${got}`
        : `Kỳ trước báo ${day.prev.map(pad).join(", ")} · Không về`;
      facts.append(el("span", day.hit ? "app-bridge-fact-hit" : "app-bridge-fact-miss", text));
    }
    title.append(facts);
    header.append(title);
    if (day.prev) header.append(el("span", day.hit ? "tr-badge" : "tr-badge app-bridge-badge-miss", day.hit ? "Trúng" : "Trượt"));
    article.append(header);

    const prizes = el("section", "tr-prizes");
    let valueIndex = 0;
    for (const [code, , name, count] of LAYOUT) {
      const row = el("div", "tr-prize-row");
      row.dataset.prize = code;
      row.append(el("div", "tr-prize-label", name));
      const grid = el("div", "tr-number-grid");
      grid.style.setProperty("--count", String(count));
      for (let i = 0; i < count; i += 1) {
        grid.append(renderValue(day, valueIndex, a, b, params));
        valueIndex += 1;
      }
      row.append(grid);
      prizes.append(row);
    }
    article.append(prizes);
    return article;
  }

  /** Một ô giải: chữ số ở vị trí cầu tô xanh đậm, hai số cuối trúng tô vàng. */
  function renderValue(day, valueIndex, a, b, params) {
    const value = day.draw.values[valueIndex];
    const first = VALUES[valueIndex].first;
    const found = day.found.includes(valueIndex);
    const cell = el("div", "tr-number");
    const kinds = [...value].map((ch, d) => {
      const pos = first + d;
      const src = pos === a ? "a" : pos === b ? "b" : "";
      const hit = found && d >= value.length - 2;
      return { ch, src, hit };
    });
    let i = 0;
    while (i < kinds.length) {
      const k = kinds[i];
      let j = i + 1;
      while (!k.src && j < kinds.length && !kinds[j].src && kinds[j].hit === k.hit) j += 1;
      const text = kinds.slice(i, j).map((x) => x.ch).join("");
      if (!k.src && !k.hit) {
        cell.append(document.createTextNode(text));
      } else {
        const classes = [];
        if (k.hit) classes.push("app-bridge-hit");
        if (k.src) classes.push(params.lon || k.src === "a" ? "app-bridge-src" : "app-bridge-src app-bridge-src--b");
        const span = el("span", classes.join(" "), text);
        if (k.src) span.setAttribute("aria-label", `Vị trí ${k.src === "a" ? a : b}: ${POSITIONS[k.src === "a" ? a : b].label}`);
        cell.append(span);
      }
      i = j;
    }
    return cell;
  }

  function renderPath(host, prepared, params) {
    const { a, b } = params.vt;
    const path = pathOf(prepared, a, b, params);
    host.replaceChildren();
    const frame = host.closest(".ui-card");
    if (frame) frame.hidden = false;
    host.append(el("p", "app-position-section-label", "3 · Xem từng kỳ của cầu đã chọn"));
    const head = el("div", "app-bridge-path-head");
    head.append(el("h2", "", `${modeTitle(params)} tại vị trí ${a}x${b}`));
    const back = el("a", "app-bridge-back", "← Chọn cầu khác");
    back.href = query(params, null) + "#app-bridge-results";
    head.append(back);
    host.append(head);
    renderPrediction(host, params, path, a, b);

    // Tối thiểu 7 kỳ để thấy cả những kỳ cầu trượt trước khi chạy — cầu nào cũng
    // "đẹp" nếu chỉ nhìn đúng đoạn nó đang trúng.
    const MIN_DAYS = 7;
    const maxDays = Math.max(1, Math.min(prepared.length - 1, Math.max(path.streak + 1, MIN_DAYS, params.days)));
    // Mặc định cũng tối thiểu 7 kỳ (hoặc cả đoạn cầu nếu dài hơn); `days` tường minh thì theo đúng nó.
    let chosen = params.days || Math.max(MIN_DAYS, path.streak);
    chosen = Math.min(chosen, maxDays);
    const picker = el("div", "app-bridge-days-picker");
    picker.setAttribute("role", "group");
    picker.setAttribute("aria-label", "Khoảng đối chiếu theo kỳ quay");
    picker.append(el("span", "app-bridge-picker-label", "Số kỳ đối chiếu:"));
    const tables = el("div", "tr-results app-bridge-days");
    tables.dataset.layout = "2";
    const legend = el("p", "app-bridge-legend");
    legend.append(el("span", "app-bridge-src", "7"));
    legend.append(document.createTextNode(params.lon ? " chữ số ở vị trí cầu  " : " chữ số thứ nhất  "));
    if (!params.lon) {
      legend.append(el("span", "app-bridge-src app-bridge-src--b", "7"));
      legend.append(document.createTextNode(" chữ số thứ hai  "));
    }
    legend.append(el("span", "app-bridge-hit", "46"));
    legend.append(document.createTextNode(" số về đúng theo cầu của kỳ trước"));

    const draw = (n) => {
      tables.replaceChildren();
      for (let t = path.days.length - 1; t >= Math.max(0, path.days.length - 1 - n); t -= 1) {
        tables.append(renderDayCard(path.days[t], a, b, params));
      }
      for (const button of picker.querySelectorAll("button")) {
        button.setAttribute("aria-pressed", String(Number(button.value) === n));
      }
    };
    for (let n = 1; n <= maxDays; n += 1) {
      const button = el("button", "app-bridge-day-button", `${n} kỳ`);
      button.type = "button";
      button.value = String(n);
      button.addEventListener("click", () => draw(n));
      picker.append(button);
    }
    host.append(picker);
    host.append(el("p", "app-bridge-help", "Mỗi bước đối chiếu dùng hai kỳ liên tiếp: 7 kỳ đối chiếu tương ứng 8 bảng kết quả. Mới nhất ở trên."));
    host.append(legend);
    host.append(tables);
    draw(chosen);
  }

  function renderList(host, bridges, summary, params) {
    host.replaceChildren();
    // Đoạn tóm tắt in kết quả tính được: khai để mỗi con số có bằng chứng.
    const summaryLine = (...parts) => {
      const p = el("p", "app-bridge-summary");
      p.setAttribute("data-evidence-split", "");
      p.append(...parts);
      return p;
    };
    const intro = summaryLine();
    intro.append(document.createTextNode(`${modeTitle(params)} · `));
    intro.append(el("b", "", String(summary.count)));
    intro.append(document.createTextNode(` cầu, ${summary.pairs} cặp số · đã chạy ${params.exact ? "đúng" : "từ"} ${params.limit} kỳ quay${params.exact ? "" : " trở lên"}.`));
    host.append(intro);
    if (params.vt) {
      const selected = el("a", "app-bridge-active-path", `Đang chọn cầu ${params.vt.a}x${params.vt.b} · Xem từng kỳ ↓`);
      selected.href = "#app-bridge-path";
      host.append(selected);
    }
    if (!bridges.length) {
      host.append(el("p", "app-bridge-empty", "Không có cầu nào khớp tham số này. Thử giảm độ dài hoặc số nháy."));
      return;
    }
    const filters = el("div", "app-bridge-pair-filters");
    filters.setAttribute("role", "group");
    filters.setAttribute("aria-label", "Chọn cặp số để lọc danh sách cầu");
    const status = el("p", "app-bridge-selection-status");
    status.setAttribute("aria-live", "polite");
    const list = el("ol", "app-bridge-links");
    list.setAttribute("aria-label", "Các cầu phù hợp với điều kiện");
    const selectPair = (pair) => {
      let count = 0;
      for (const row of list.children) {
        row.hidden = Boolean(pair && row.dataset.pair !== pair);
        if (!row.hidden) count += 1;
      }
      for (const button of filters.children) {
        button.setAttribute("aria-pressed", String(button.dataset.pair === pair));
      }
      status.textContent = pair ? `Đang xem ${count} cầu báo ${pair.split(",").join(", ")}. Chọn một cầu để xem từng kỳ.`
        : `Đang xem tất cả ${count} cầu. Mỗi hàng là một cặp vị trí riêng.`;
    };
    const filterButton = (pair, count) => {
      const button = el("button", "app-bridge-pair-button");
      button.type = "button";
      button.dataset.pair = pair;
      button.append(el("b", "", pair ? pair.split(",").join(", ") : "Tất cả"));
      button.append(el("span", "", `${count} cầu`));
      button.addEventListener("click", () => selectPair(pair));
      filters.append(button);
    };
    filterButton("", bridges.length);
    for (const row of summary.repeats) filterButton(row.pair, row.bridges);
    host.append(filters);
    host.append(status);
    for (const bridge of bridges) {
      const item = el("li", bridge.streak > params.limit ? "is-longer" : "");
      item.dataset.pair = pairKey(bridge.numbers);
      const link = el("a");
      link.href = query(params, bridge) + "#app-bridge-path";
      if (params.vt && params.vt.a === bridge.a && params.vt.b === bridge.b) link.setAttribute("aria-current", "true");
      link.append(numberChips(bridge));
      const detail = el("span", "app-bridge-link-detail");
      detail.append(el("b", "", `Vị trí ${bridge.vt}`));
      detail.append(el("small", "", `${POSITIONS[bridge.a].label} + ${POSITIONS[bridge.b].label}`));
      link.append(detail);
      link.append(el("span", "app-bridge-link-run", `${bridge.streak} kỳ`));
      link.append(el("span", "app-bridge-link-action", "Xem từng kỳ →"));
      item.append(link);
      list.append(item);
    }
    const scroll = el("div", "app-bridge-list-scroll");
    scroll.setAttribute("tabindex", "0");
    scroll.setAttribute("aria-label", "Danh sách cầu, cuộn để xem thêm");
    scroll.append(list);
    host.append(scroll);
    selectPair("");
    const repeatsDisclosure = el("details", "app-bridge-repeats-details");
    repeatsDisclosure.append(el("summary", "", "Số cầu cùng báo mỗi cặp"));
    const repeats = el("ul", "app-bridge-repeats");
    for (const row of summary.repeats) {
      const item = el("li");
      item.append(el("b", "", row.pair));
      item.append(el("span", "", `${row.bridges} cầu`));
      repeats.append(item);
    }
    repeatsDisclosure.append(repeats);
    host.append(repeatsDisclosure);
    host.append(el("p", "app-bridge-help", "Độ dài và số cầu cùng báo là mô tả lịch sử; không phải điểm tin cậy. Số bóng chỉ để tham khảo."));
  }

  function renderMatrix(host, prepared, bridges, params) {
    host.replaceChildren();
    const last = prepared[prepared.length - 1];
    const partners = new Map();
    for (const bridge of bridges) {
      if (!partners.has(bridge.a)) partners.set(bridge.a, []);
      if (!partners.has(bridge.b)) partners.set(bridge.b, []);
      partners.get(bridge.a).push(bridge);
      partners.get(bridge.b).push(bridge);
    }
    const help = el("p", "app-bridge-help",
      `Kết quả ${formatDate(last.date)}. Số lớn là chữ số của giải; số nhỏ bên dưới là vị trí 0–106. `
      + "Chọn một ô có viền, rồi chọn ô có nhãn Ghép hoặc liên kết hiện bên dưới để xem từng kỳ.");
    host.append(help);
    const selection = el("div", "app-bridge-matrix-selection");
    selection.setAttribute("aria-live", "polite");
    selection.hidden = true;
    const table = el("div", "app-bridge-matrix");
    const buttons = new Map();
    let selected = null;
    const paint = () => {
      const mates = new Set();
      if (selected !== null) {
        for (const bridge of partners.get(selected) || []) mates.add(bridge.a === selected ? bridge.b : bridge.a);
      }
      for (const [pos, button] of buttons) {
        button.classList.toggle("is-selected", pos === selected);
        button.classList.toggle("is-partner", mates.has(pos));
        button.setAttribute("aria-pressed", String(pos === selected));
        button.setAttribute("aria-label", `Vị trí ${pos}: ${POSITIONS[pos].label} · chữ số ${last.digits[pos]}`
          + (mates.has(pos) ? ` · Ghép với vị trí ${selected}, xem từng kỳ` : ""));
        button.querySelector(".app-bridge-cell-hint").textContent = pos === selected ? "Đã chọn" : mates.has(pos) ? "Ghép" : "";
      }
      selection.replaceChildren();
      selection.hidden = selected === null;
      if (selected !== null) {
        selection.append(el("p", "", `Đã chọn vị trí ${selected}: ${POSITIONS[selected].label}. Chọn đường cầu để xem từng kỳ:`));
        const choices = el("ul", "app-bridge-matrix-choices");
        for (const bridge of partners.get(selected) || []) {
          const mate = bridge.a === selected ? bridge.b : bridge.a;
          const item = el("li");
          const link = el("a", "", `Vị trí ${mate} · ${POSITIONS[mate].label} · Cầu ${bridge.vt} báo ${bridge.numbers.join(", ")} · ${bridge.streak} kỳ · Xem từng kỳ →`);
          link.href = query(params, bridge) + "#app-bridge-path";
          link.dataset.position = String(mate);
          item.append(link);
          choices.append(item);
        }
        selection.append(choices);
      }
    };
    let valueIndex = 0;
    for (const [code, , name, count] of LAYOUT) {
      const row = el("div", "app-bridge-matrix-row");
      row.dataset.prize = code;
      row.append(el("span", "app-bridge-matrix-label", name));
      const cells = el("div", "app-bridge-matrix-values");
      for (let i = 0; i < count; i += 1) {
        const group = el("span", "app-bridge-matrix-value");
        const info = VALUES[valueIndex];
        group.append(el("span", "app-bridge-value-label", info.label));
        for (let d = 0; d < info.width; d += 1) {
          const pos = info.first + d;
          const digit = String(last.digits[pos]);
          if (partners.has(pos)) {
            const button = el("button", "app-bridge-cell");
            button.type = "button";
            button.dataset.position = String(pos);
            button.setAttribute("aria-label", `Vị trí ${pos}: ${POSITIONS[pos].label} · chữ số ${digit}`);
            button.setAttribute("aria-pressed", "false");
            button.append(el("span", "app-bridge-cell-digit", digit));
            button.append(el("small", "app-bridge-position-index", String(pos)));
            button.append(el("small", "app-bridge-cell-hint"));
            button.addEventListener("click", () => {
              if (selected !== null && selected !== pos && button.classList.contains("is-partner")) {
                const bridge = (partners.get(selected) || []).find((x) => x.a === pos || x.b === pos);
                if (bridge) window.location.assign(query(params, bridge) + "#app-bridge-path");
                return;
              }
              selected = selected === pos ? null : pos;
              paint();
            });
            buttons.set(pos, button);
            group.append(button);
          } else {
            const cell = el("span", "app-bridge-cell");
            cell.setAttribute("aria-label", `Vị trí ${pos}: ${POSITIONS[pos].label} · chữ số ${digit} · Không có cầu phù hợp`);
            cell.append(el("span", "app-bridge-cell-digit", digit));
            cell.append(el("small", "app-bridge-position-index", String(pos)));
            group.append(cell);
          }
        }
        cells.append(group);
        valueIndex += 1;
      }
      row.append(cells);
      table.append(row);
    }
    host.append(table);
    host.append(selection);
  }

  function syncForm(form, params) {
    if (!form) return;
    form.elements.limit.value = String(params.limit);
    form.elements.exactlimit.value = params.exact ? "1" : "0";
    form.elements.nhay.value = String(params.nhay);
    form.elements.db.checked = params.db;
    for (const radio of form.querySelectorAll('input[name="lon"]')) radio.checked = radio.value === (params.lon ? "1" : "0");
  }

  /** Truy vấn chuẩn hoá từ các ô của biểu mẫu — cùng luật kiểm như khi đọc URL. */
  function formQuery(form) {
    const q = new URLSearchParams();
    q.set("limit", form.elements.limit.value);
    q.set("exactlimit", form.elements.exactlimit.value);
    q.set("nhay", form.elements.nhay.value);
    if (form.elements.db.checked) q.set("db", "1");
    const lon = form.querySelector('input[name="lon"]:checked');
    q.set("lon", lon ? lon.value : "1");
    return query(readParams(`?${q.toString()}`), null);
  }

  // CSP của trang cấm gửi biểu mẫu (form-action 'none'), nên bấm "Soi cầu" không
  // được để trình duyệt tự gửi: tự dựng truy vấn rồi chuyển trang bằng location.
  function bindForm(form) {
    if (!form) return;
    const syncMode = () => {
      form.elements.nhay.disabled = form.elements.db.checked;
      const help = document.getElementById("app-bridge-mode-help");
      if (help) help.textContent = form.elements.db.checked
        ? "Đặc Biệt: chỉ dò hai số cuối giải Đặc Biệt; số nháy LOTO không áp dụng."
        : "LOTO: dò hai số cuối của cả 27 giải; số nháy là tổng số lần cặp số về trong một kỳ.";
    };
    form.elements.db.addEventListener("change", syncMode);
    syncMode();
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      window.location.assign(formQuery(form));
    });
  }

  function mount() {
    const params = readParams(window.location.search);
    document.body.dataset.bridgeMode = params.db ? "db" : "lo";
    const prepared = prepare(REPORT.draws);
    const bridges = findBridges(prepared, params);
    const summary = summarize(bridges, params.limit);
    syncForm(document.getElementById("app-bridge-form"), params);
    bindForm(document.getElementById("app-bridge-form"));
    const title = document.getElementById("app-bridge-list-title");
    if (title) title.textContent = "2 · Chọn số và cầu";
    const list = document.getElementById("app-bridge-list");
    if (list) renderList(list, bridges, summary, params);
    const matrix = document.getElementById("app-bridge-matrix");
    if (matrix) renderMatrix(matrix, prepared, bridges, params);
    const path = document.getElementById("app-bridge-path");
    if (path && params.vt) {
      renderPath(path, prepared, params);
      document.title = `${modeTitle(params)} tại vị trí ${params.vt.a}x${params.vt.b} — Soi cầu vị trí`;
    }
  }

  window.PositionBridges = Object.freeze({
    LAYOUT, POSITIONS, prepare, findBridges, summarize, pathOf, readParams, query, shadowOf, formQuery,
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
