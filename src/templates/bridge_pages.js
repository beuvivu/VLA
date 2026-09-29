(() => {
  "use strict";

  // Bảy trang cầu vị trí (LOTO, hai nháy, bạch thủ, Đặc Biệt, bộ số, theo thứ) —
  // bản trình duyệt của `src/bridge_rules.py`, cùng luật và cùng cách đếm.
  // `tests/frontend/bridge-pages.test.mjs` so từng ô với bản Python.
  //
  // Mọi phần tử dựng bằng createElement + textContent; không gán chuỗi HTML.

  const DATA = document.getElementById("app-cau-data");
  if (!DATA) return;
  const REPORT = JSON.parse(DATA.textContent);

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
  const WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"];

  const POSITIONS = [];
  const VALUES = [];
  for (const [code, short, name, count, width] of LAYOUT) {
    for (let i = 0; i < count; i += 1) {
      const label = short + (count > 1 ? `.${i + 1}` : "");
      VALUES.push({ code, name, width, first: POSITIONS.length });
      for (let d = 0; d < width; d += 1) POSITIONS.push({ value: VALUES.length - 1, label: `${label} · chữ số ${d + 1}` });
    }
  }
  const N_POS = POSITIONS.length;
  const WIDTHS = VALUES.map((v) => v.width);

  // Bộ số: {x, bóng x} × {y, bóng y}, cả hai chiều. Đại diện = số nhỏ nhất.
  const BO_MEMBERS = [];
  const BO_ID = new Int16Array(100);
  for (let n = 0; n < 100; n += 1) {
    const x = Math.floor(n / 10);
    const y = n % 10;
    const set = new Set();
    for (const p of [x, SHADOW[x]]) for (const q of [y, SHADOW[y]]) { set.add(10 * p + q); set.add(10 * q + p); }
    BO_MEMBERS.push(set);
    BO_ID[n] = Math.min(...set);
  }

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const pad = (n) => String(n).padStart(2, "0");
  const weekdayOf = (iso) => (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7;
  const formatDate = (iso) => { const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; };

  function decode(row) {
    const date = row.slice(0, 10);
    const digits = new Int8Array(N_POS);
    for (let i = 0; i < N_POS; i += 1) digits[i] = row.charCodeAt(10 + i) - 48;
    const values = [];
    let cursor = 10;
    for (const w of WIDTHS) { values.push(row.slice(cursor, cursor + w)); cursor += w; }
    const two = values.map((v) => Number(v.slice(-2)));
    const counts = new Int16Array(100);
    for (const n of two) counts[n] += 1;
    return { date, digits, values, two, counts };
  }

  const PAIRS = (() => {
    const a = [];
    const b = [];
    for (let i = 0; i < N_POS; i += 1) for (let j = i + 1; j < N_POS; j += 1) { a.push(i); b.push(j); }
    return { a: Int16Array.from(a), b: Int16Array.from(b) };
  })();

  const numberAt = (draw, a, b) => 10 * draw.digits[a] + draw.digits[b];

  /** Bước từ kỳ `prev` sang kỳ `next` của cặp (a, b) có trúng không — như `step_matrix`. */
  function step(kind, prev, next, a, b, both) {
    const x = prev.digits[a];
    const y = prev.digits[b];
    const n1 = 10 * x + y;
    if (kind === "bo-so") return BO_ID[n1] === BO_ID[numberAt(next, a, b)];
    if (kind === "dac-biet") {
      const tens = Math.floor(next.two[0] / 10);
      const units = next.two[0] % 10;
      if (both) return (x === tens && y === units) || (x === units && y === tens);
      return x === tens || x === units || y === tens || y === units;
    }
    const n2 = 10 * y + x;
    const c1 = next.counts[n1];
    const c2 = n1 !== n2 ? next.counts[n2] : 0;
    if (kind === "loto") return c1 + c2 >= 1;
    if (kind === "hai-nhay") return c1 >= 2 || (c1 >= 1 && c2 >= 1);
    if (kind === "bach-thu") return c1 >= 1;
    throw new Error(`Kiểu cầu lạ: ${kind}`);
  }

  /** Cầu chạy ≥ `count` bước tính đến kỳ cuối của `series`, và cầu dài nhất. */
  function scan(series, kind, count, both) {
    const draws = series.slice(-REPORT.window);
    const runs = new Int16Array(PAIRS.a.length);
    for (let t = 0; t + 1 < draws.length; t += 1) {
      for (let p = 0; p < runs.length; p += 1) {
        runs[p] = step(kind, draws[t], draws[t + 1], PAIRS.a[p], PAIRS.b[p], both) ? runs[p] + 1 : 0;
      }
    }
    const last = draws[draws.length - 1];
    const bridges = [];
    let longest = 0;
    for (let p = 0; p < runs.length; p += 1) {
      if (runs[p] > longest) longest = runs[p];
      if (runs[p] < count) continue;
      const a = PAIRS.a[p];
      const b = PAIRS.b[p];
      bridges.push({ a, b, vt: `${a}x${b}`, streak: runs[p], number: pad(numberAt(last, a, b)) });
    }
    bridges.sort((u, v) => (u.number < v.number ? -1 : u.number > v.number ? 1 : u.a - v.a || u.b - v.b));
    return { bridges, longest };
  }

  function boKey(n) { return [...BO_MEMBERS[BO_ID[n]]].sort((u, v) => u - v).map(pad).join(","); }

  function tally(bridges, kind) {
    const counts = {};
    for (const bridge of bridges) counts[bridge.number] = (counts[bridge.number] || 0) + 1;
    const groups = {};
    for (const [number, n] of Object.entries(counts)) {
      const key = kind === "bo-so" ? boKey(Number(number))
        : [...new Set([number, number[1] + number[0]])].sort().join(",");
      groups[key] = (groups[key] || 0) + n;
    }
    const ranked = Object.entries(groups).sort((u, v) => v[1] - u[1] || (u[0] < v[0] ? -1 : 1));
    return { counts, total: bridges.length, groups: ranked.map(([key, n]) => ({ key, bridges: n })) };
  }

  /** Ô nào của kỳ `draw` thể hiện điều cầu (a, b) dựng từ kỳ `prev` báo. */
  function fulfilled(kind, prev, draw, a, b, both) {
    const n1 = numberAt(prev, a, b);
    const n2 = 10 * prev.digits[b] + prev.digits[a];
    if (kind === "dac-biet") return step(kind, prev, draw, a, b, both) ? [0] : [];
    if (kind === "bo-so") return BO_MEMBERS[n1].has(draw.two[0]) ? [0] : [];
    const wanted = kind === "bach-thu" ? [n1] : [n1, n2];
    const cells = [];
    draw.two.forEach((n, j) => { if (wanted.includes(n)) cells.push(j); });
    return cells;
  }

  // ---- Tham số ------------------------------------------------------------

  const ALL = REPORT.draws.map(decode);

  function readParams(search) {
    const q = new URLSearchParams(search);
    const int = (name, lo, hi, fallback) => {
      const raw = q.get(name);
      const n = raw === null || !/^-?\d+$/.test(raw) ? NaN : Number(raw);
      return Number.isInteger(n) && n >= lo && n <= hi ? n : fallback;
    };
    const params = {
      count: int("count", 1, REPORT.window - 1, REPORT.rule.count),
      both: REPORT.rule.kind === "dac-biet" && q.get("both") === "1",
      weekday: REPORT.rule.weekday ? int("thu", 0, 6, REPORT.rule.default_weekday) : null,
      end: null,
    };
    const end = q.get("ngay");
    if (end && /^\d{4}-\d{2}-\d{2}$/.test(end)) params.end = end;
    return params;
  }

  /** Chuỗi kỳ tính đến biên ngày. Biên ngày không còn đủ `window` kỳ trước nó thì
   *  KHÔNG được âm thầm đổi sang kỳ mới nhất: bỏ biên ấy và báo rõ (`params.rejected`). */
  function seriesFor(params) {
    const series = params.weekday === null ? ALL : ALL.filter((d) => weekdayOf(d.date) === params.weekday);
    if (!params.end) return series;
    const cut = series.filter((d) => d.date <= params.end);
    if (cut.length >= REPORT.window) return cut;
    params.rejected = params.end;
    params.end = null;
    return series;
  }

  /** Các biên ngày chọn được: kỳ của chuỗi còn đủ `window` kỳ lịch sử trước nó. */
  function boundaries(series) {
    return series.slice(REPORT.window - 1).slice(-REPORT.window);
  }

  function query(params) {
    const q = new URLSearchParams();
    q.set("count", String(params.count));
    if (params.both) q.set("both", "1");
    if (params.weekday !== null) q.set("thu", String(params.weekday));
    if (params.end) q.set("ngay", params.end);
    return `?${q.toString()}`;
  }

  // ---- Dựng giao diện -------------------------------------------------------

  const percent = (x) => `${(x * 100).toFixed(1).replace(".", ",")}%`;

  function renderGrid(host, result, onPick, onHover) {
    host.replaceChildren();
    const table = el("table", "app-cau-grid");
    table.append(el("caption", "ui-sr-only", "Số cầu theo các số 00 đến 99"));
    const thead = el("thead");
    const header = el("tr");
    for (const label of ["Đầu / Đuôi", ...Array.from({ length: 10 }, (_, i) => String(i))]) {
      const th = el("th", "", label);
      th.scope = "col";
      header.append(th);
    }
    thead.append(header);
    table.append(thead);
    const body = el("tbody");
    for (let head = 0; head < 10; head += 1) {
      const row = el("tr");
      const rowhead = el("th", "", `Đầu ${head}`);
      rowhead.scope = "row";
      row.append(rowhead);
      for (let tail = 0; tail < 10; tail += 1) {
        const number = `${head}${tail}`;
        const n = result.counts[number] || 0;
        const cell = el("td");
        if (n) {
          const button = el("button", "app-cau-cell");
          button.type = "button";
          button.dataset.number = number;
          button.setAttribute("aria-pressed", "false");
          button.setAttribute("aria-label", `Số ${number}, ${n} cầu. Xem vị trí cầu`);
          button.append(el("b", "", number), el("span", "", `${n} cầu`));
          button.addEventListener("click", () => onPick(number));
          button.addEventListener("mouseenter", () => onHover(number));
          button.addEventListener("focus", () => onHover(number));
          button.addEventListener("mouseleave", () => onHover(null));
          button.addEventListener("blur", () => onHover(null));
          cell.append(button);
        } else {
          cell.className = "app-cau-empty";
          cell.append(el("span", "", number));
        }
        row.append(cell);
      }
      body.append(row);
    }
    table.append(body);
    const wrap = el("div", "app-cau-grid-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", "Bảng cầu theo đầu và đuôi, cuộn ngang để xem đủ 00 đến 99");
    wrap.append(table);
    host.append(wrap);
  }

  function renderGroups(host, result, kind) {
    host.replaceChildren();
    if (!result.groups.length) {
      host.append(el("p", "app-cau-empty-state", "Không có cầu phù hợp. Giảm số ngày cầu chạy hoặc chọn kỳ khác để xem kết quả."));
      return;
    }
    host.append(el("h3", "app-cau-subhead", kind === "bo-so" ? "Xếp hạng bộ số (tổng số cầu thuộc bộ)" : "Tổng số cầu theo cặp số"));
    const list = el("ol", "app-cau-groups");
    for (const group of result.groups) {
      const item = el("li");
      item.append(el("b", "", kind === "bo-so" ? `Bộ ${group.key.split(",")[0]}` : group.key.replace(",", " – ")));
      if (kind === "bo-so") item.append(el("small", "", group.key.split(",").join(" ")));
      item.append(el("span", "", `${group.bridges} cầu`));
      list.append(item);
    }
    host.append(list);
  }

  /** Bảng kết quả kiểu Sổ kết quả; mỗi chữ số mang `data-pos` để tô vị trí cầu. */
  function renderDay(draw, facts) {
    const article = el("article", "tr-day app-cau-day");
    const header = el("header", "tr-day-head");
    const title = el("div", "tr-day-title");
    title.append(el("h2", "", `${WEEKDAYS[weekdayOf(draw.date)]}, ${formatDate(draw.date)}`));
    if (facts) title.append(facts);
    header.append(title);
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
        const info = VALUES[valueIndex];
        const cell = el("div", "tr-number");
        cell.dataset.value = String(valueIndex);
        [...draw.values[valueIndex]].forEach((ch, d) => {
          const span = el("span", "app-cau-digit", ch);
          span.dataset.pos = String(info.first + d);
          cell.append(span);
        });
        grid.append(cell);
        valueIndex += 1;
      }
      row.append(grid);
      prizes.append(row);
    }
    article.append(prizes);
    return article;
  }

  /** Nạp ô "Biên ngày" bằng các kỳ của chuỗi (theo thứ nếu có), mới nhất trước. */
  function fillDates(select, weekday, selected) {
    select.replaceChildren();
    const pool = weekday === null ? ALL : ALL.filter((d) => weekdayOf(d.date) === weekday);
    for (const draw of boundaries(pool).reverse()) {
      const option = el("option", "", `${WEEKDAYS[weekdayOf(draw.date)]}, ${formatDate(draw.date)}`);
      option.value = draw.date;
      select.append(option);
    }
    select.value = selected && [...select.options].some((o) => o.value === selected) ? selected : select.options[0].value;
  }

  function mount() {
    const tabs = document.querySelector(".app-cau-tabs");
    const activeTab = tabs?.querySelector('[aria-current="page"]');
    if (tabs && activeTab) {
      const revealTab = () => {
        if (tabs.scrollWidth <= tabs.clientWidth) return;
        const frame = tabs.getBoundingClientRect();
        const item = activeTab.getBoundingClientRect();
        if (item.left < frame.left + 16) tabs.scrollLeft += item.left - frame.left - 16;
        else if (item.right > frame.right - 16) tabs.scrollLeft += item.right - frame.right + 16;
      };
      revealTab();
      window.addEventListener("load", revealTab, { once: true });
      window.addEventListener("resize", revealTab);
    }
    const rule = REPORT.rule;
    const params = readParams(window.location.search);
    const series = seriesFor(params);
    const result = { ...scan(series, rule.kind, params.count, params.both) };
    Object.assign(result, tally(result.bridges, rule.kind));
    const last = series[series.length - 1];
    for (const [key, value] of Object.entries({
      total: result.total.toLocaleString("vi-VN"),
      longest: String(result.longest),
      date: formatDate(last.date),
    })) {
      const metric = document.querySelector(`[data-cau-metric="${key}"]`);
      if (metric) metric.textContent = value;
    }

    const form = document.getElementById("app-cau-form");
    if (form) {
      form.elements.count.value = String(params.count);
      if (form.elements.both) form.elements.both.checked = params.both;
      if (form.elements.thu) form.elements.thu.value = String(params.weekday);
      const dates = form.elements.ngay;
      fillDates(dates, params.weekday, last.date);
      // Đổi thứ thì các biên ngày của thứ cũ không còn hợp lệ: nạp lại, chọn kỳ mới nhất.
      if (form.elements.thu) {
        form.elements.thu.addEventListener("change", () => fillDates(dates, Number(form.elements.thu.value), null));
      }
      form.addEventListener("submit", (event) => {
        // CSP cấm gửi biểu mẫu (form-action 'none'): tự dựng truy vấn rồi chuyển trang.
        event.preventDefault();
        window.location.assign(formQuery(form));
      });
    }

    const summary = document.getElementById("app-cau-summary");
    if (summary) {
      summary.replaceChildren();
      summary.append(document.createTextNode(`${rule.title} tính đến kỳ ${formatDate(last.date)}`
        + `${params.weekday === null ? "" : ` (chỉ các kỳ ${WEEKDAYS[params.weekday]})`}: `));
      summary.append(el("b", "", `${result.total} cầu`));
      summary.append(document.createTextNode(` chạy từ ${params.count} ngày. Cầu dài nhất: `));
      summary.append(el("b", "", `${result.longest} ngày`));
      summary.append(document.createTextNode("."));
      if (params.rejected) {
        summary.append(el("span", "app-cau-notice", ` Biên ngày ${formatDate(params.rejected)} không còn đủ `
          + `${REPORT.window} kỳ lịch sử trước nó nên không tính được — đang hiện kỳ mới nhất.`));
      }
    }

    // Các bảng kết quả: count + 1 kỳ cuối của chuỗi, mới nhất trước.
    const shown = series.slice(-(params.count + 1)).reverse();
    const daysHost = document.getElementById("app-cau-days");
    const digitNodes = [];
    if (daysHost) {
      daysHost.replaceChildren();
      for (const draw of shown) {
        const facts = el("p", "app-cau-facts");
        const card = renderDay(draw, facts);
        card.dataset.date = draw.date;
        daysHost.append(card);
        digitNodes.push(card);
      }
    }

    const detail = document.getElementById("app-cau-detail");
    const hovered = (number) => paint(number ? result.bridges.filter((x) => x.number === number) : null, null);

    function paint(set, single) {
      for (const card of digitNodes) {
        for (const span of card.querySelectorAll(".app-cau-digit")) {
          const pos = Number(span.dataset.pos);
          span.classList.toggle("is-cau", !!set && set.some((x) => x.a === pos || x.b === pos));
          span.classList.toggle("is-src", !!single && (single.a === pos || single.b === pos));
        }
        for (const cell of card.querySelectorAll(".tr-number")) cell.classList.remove("is-hit");
        const facts = card.querySelector(".app-cau-facts");
        facts.replaceChildren();
        if (!single) continue;
        const index = series.findIndex((d) => d.date === card.dataset.date);
        const draw = series[index];
        facts.append(el("span", "app-cau-fact-src", `Cầu báo: ${pad(numberAt(draw, single.a, single.b))}`
          + (rule.kind === "bo-so" ? ` (bộ ${pad(BO_ID[numberAt(draw, single.a, single.b)])})` : "")));
        if (index > 0) {
          const prev = series[index - 1];
          const cells = fulfilled(rule.kind, prev, draw, single.a, single.b, params.both);
          for (const j of cells) card.querySelector(`.tr-number[data-value="${j}"]`).classList.add("is-hit");
          const ok = step(rule.kind, prev, draw, single.a, single.b, params.both);
          if (rule.kind === "bo-so") {
            // Bộ số có HAI điều khác nhau: cầu còn chạy (số giữ bộ) và điều cầu báo
            // (ĐB rơi vào bộ). Không gộp làm một nhãn "trúng".
            const inSet = cells.length > 0;
            const set = pad(BO_ID[numberAt(prev, single.a, single.b)]);
            facts.append(el("span", ok ? "app-cau-fact-hit" : "app-cau-fact-miss",
              ok ? "Cầu giữ bộ" : "Cầu gãy bộ"));
            facts.append(el("span", inSet ? "app-cau-fact-hit" : "app-cau-fact-miss",
              `ĐB ${pad(draw.two[0])} ${inSet ? "trong" : "ngoài"} bộ ${set}`));
          } else {
            facts.append(el("span", ok ? "app-cau-fact-hit" : "app-cau-fact-miss",
              ok ? "Trúng theo cầu kỳ trước" : "Trượt theo cầu kỳ trước"));
          }
        }
      }
    }

    function pick(number) {
      if (!detail) return;
      for (const cell of document.querySelectorAll("button.app-cau-cell")) {
        cell.setAttribute("aria-pressed", String(cell.dataset.number === number));
      }
      detail.replaceChildren();
      const list = result.bridges.filter((x) => x.number === number);
      detail.append(el("h3", "app-cau-subhead", `Số ${number}: ${list.length} cầu`));
      const buttons = el("div", "app-cau-bridges");
      for (const bridge of list) {
        const button = el("button", "app-cau-bridge", `${bridge.vt} · ${bridge.streak} ngày`);
        button.type = "button";
        button.title = `Vị trí ${bridge.a}: ${POSITIONS[bridge.a].label} · Vị trí ${bridge.b}: ${POSITIONS[bridge.b].label}`;
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => {
          for (const other of buttons.children) other.setAttribute("aria-pressed", String(other === button));
          paint(list, bridge);
        });
        buttons.append(button);
      }
      detail.append(buttons);
      // "Cả hai chữ số" là luật khác: dùng kiểm lịch sử của chính nó.
      const tested = params.both && REPORT.backtest_both ? REPORT.backtest_both : REPORT.backtest;
      const history = tested && tested.rows[Math.min(params.count, tested.rows.length - 1)];
      if (history && history.n >= 200) {
        detail.append(el("p", "app-cau-honest",
          `Trên toàn lịch sử, cầu kiểu này đã chạy ${history.plus ? "từ " : ""}${history.k} ngày thì kỳ sau đúng `
          + `${percent(history.rate)} số lần — kỳ vọng nếu độ dài cầu không mang thông tin là ${percent(history.expected)}.`));
      }
      paint(list, list[0]);
      buttons.firstChild?.setAttribute("aria-pressed", "true");
      detail.scrollIntoView?.({ block: "nearest" });
    }

    const grid = document.getElementById("app-cau-grid");
    if (grid) renderGrid(grid, result, pick, (number) => { if (!detail || !detail.childElementCount) hovered(number); });
    const groups = document.getElementById("app-cau-groups");
    if (groups) renderGroups(groups, result, rule.kind);

    window.BridgePages.state = { params, result, series };
  }

  function formQuery(form) {
    const q = new URLSearchParams();
    q.set("count", form.elements.count.value);
    if (form.elements.both && form.elements.both.checked) q.set("both", "1");
    if (form.elements.thu) q.set("thu", form.elements.thu.value);
    if (form.elements.ngay.value) q.set("ngay", form.elements.ngay.value);
    return query(readParams(`?${q.toString()}`));
  }

  window.BridgePages = {
    POSITIONS, decode, scan, tally, step, fulfilled, readParams, query, formQuery, boKey, BO_ID, boundaries,
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
