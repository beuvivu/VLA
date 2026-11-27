"use strict";
const DRAWS = window.__D_DEMO_DRAWS__ || window.__D_DRAWS__ || [];
const NHAY_PER_DRAW = 27 / 100;
const PAIR_BASELINE = 1 - 2 * Math.pow(0.99, 27) + Math.pow(0.98, 27);

const PAIR_CHANCE_GRID = window.__D_PAIR_CHANCE__ || [];

function pairChanceMaximum(n) {
  const g = PAIR_CHANCE_GRID;
  if (!g.length || n <= 0) return null;
  if (n <= g[0][0]) return { mean: g[0][1], low: g[0][2], high: g[0][3] };
  const last = g[g.length - 1];
  if (n >= last[0]) return { mean: last[1], low: last[2], high: last[3] };
  for (let i = 0; i + 1 < g.length; i++) {
    const a = g[i], b = g[i + 1];
    if (n >= a[0] && n <= b[0]) {
      const t = (n - a[0]) / (b[0] - a[0]);
      return {
        mean: a[1] + t * (b[1] - a[1]),
        low: Math.round(a[2] + t * (b[2] - a[2])),
        high: Math.round(a[3] + t * (b[3] - a[3])),
      };
    }
  }
  return null;
}

function updateChanceNote(nDraws) {
  const el = $("sp-chance");
  if (!el) return;
  const c = pairChanceMaximum(nDraws);
  if (!c) { el.textContent = "—"; return; }
  const fmt = (x) => x.toFixed(1).replace(".", ",");
  el.textContent =
    `Trên lịch sử ngẫu nhiên dài đúng ${nDraws} kỳ, cực đại trung bình là ` +
    `${fmt(c.mean)} lần (khoảng 90%: ${c.low}–${c.high}), trong khi kỳ vọng ` +
    `mỗi cặp chỉ ${fmt(PAIR_BASELINE * nDraws)}.`;
}

const $ = (id) => document.getElementById(id);
const pad2 = (n) => String(n).padStart(2, "0");

function mk(tag, attrs, kids) {
  const node = ["svg", "path"].includes(tag)
    ? document.createElementNS("http://www.w3.org/2000/svg", tag)
    : document.createElement(tag);
  if (attrs) {
    for (const k in attrs) {
      const v = attrs[k];
      if (v === null || v === undefined || v === false || v === "") continue;
      node.setAttribute(k, v === true ? "" : String(v));
    }
  }
  if (kids !== undefined) put(node, kids);
  return node;
}

function put(node, kids) {
  if (kids === null || kids === undefined || kids === false || kids === "") return node;
  if (Array.isArray(kids)) {
    for (let i = 0; i < kids.length; i += 1) put(node, kids[i]);
    return node;
  }
  node.appendChild(kids.nodeType ? kids : document.createTextNode(String(kids)));
  return node;
}

function fill(node, kids) {
  node.textContent = "";
  return put(node, kids);
}

function weekdayOf(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
}

function selected() {
  const fromInput = $("sp-from"), toInput = $("sp-to");
  const from = fromInput && fromInput.value;
  const to = toInput && toInput.value;
  let rows = DRAWS;
  if (!fromInput && !toInput) {
    const active = document.querySelector(".sp-chips .sp-chip.on[data-days]");
    const count = active ? Number(active.dataset.days) : 0;
    if (Number.isInteger(count) && count > 0) rows = rows.slice(-count);
  }
  if (from) rows = rows.filter((r) => r.d >= from);
  if (to) rows = rows.filter((r) => r.d <= to);
  const weekday = $("sp-weekday");
  if (weekday && weekday.value !== "all") {
    const want = Number(weekday.value);
    if (Number.isInteger(want) && want >= 0 && want <= 6) {
      rows = rows.filter((r) => weekdayOf(r.d) === want);
    }
  }
  return rows;
}

function todayInVietnam() {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
  } catch (err) {
    return "";
  }
}

function pendingDay(rows) {
  const today = todayInVietnam();
  if (!today) return "";
  const latest = DRAWS.length ? DRAWS[DRAWS.length - 1].d : "";
  if (!latest || today <= latest) return "";
  const from = $("sp-from"), to = $("sp-to");
  if ((from && from.value > today) || (to && to.value && to.value < latest)) return "";
  const weekday = $("sp-weekday");
  if (weekday && weekday.value !== "all" && weekdayOf(today) !== Number(weekday.value)) {
    return "";
  }
  return today;
}

function setCount(rows) {
  const el = $("sp-count");
  if (!el) return;
  const first = rows.length ? rows[0].d : "—";
  const last = rows.length ? rows[rows.length - 1].d : "—";
  el.textContent = `${rows.length} kỳ · ${first} → ${last}`;
}

function specialFull(value) {
  const s = String(value).padStart(5, "0");
  return mk("span", { class: "sp-de" }, [s.slice(0, 3), mk("b", null, s.slice(3))]);
}

const BO_LOOKUP = window.__D_BO__ || [];

const DE_FIELDS = [
  { key: "ngay", label: "Ngày", hint: "Ngày quay, dạng ngày-tháng" },
  { key: "tong", label: "Tổng", hint: "(Đầu + Đuôi) chia lấy dư 10" },
  { key: "dau", label: "Đầu", hint: "Chữ số hàng chục của hai số cuối" },
  { key: "duoi", label: "Đuôi", hint: "Chữ số hàng đơn vị của hai số cuối" },
  {
    key: "chanle",
    label: "Chẵn lẻ",
    hint: "Hai ký tự: chẵn/lẻ của Đầu, rồi của Đuôi. 68 cho CC vì 6 và 8 đều chẵn",
  },
  {
    key: "bo",
    label: "Bộ",
    hint: "Họ bộ số: gom một con với bóng dương và số lộn của nó. " +
      "68 thuộc bộ 13 vì bóng của 6 là 1, bóng của 8 là 3. Có 15 họ",
  },
];

const FIELD_KEY = "sp.defields." + (location.pathname.split("/").pop() || "index");
let SHOWN = new Set(DE_FIELDS.map((f) => f.key));
try {
  const saved = localStorage.getItem(FIELD_KEY);
  if (saved) SHOWN = new Set(JSON.parse(saved));
} catch (e) {   }

function specialCell(value, iso) {
  const s = String(value).padStart(5, "0");
  const two = s.slice(3);
  const dau = +two[0];
  const duoi = +two[1];

  const tip = (key) => (DE_FIELDS.find((f) => f.key === key) || {}).hint || "";
  const parts = [];
  if (iso && SHOWN.has("ngay")) {
    parts.push(mk("i", { class: "sp-f sp-f-ngay", title: `Ngày ${iso}` },
      `${iso.slice(8)}-${iso.slice(5, 7)}`));
  }
  if (SHOWN.has("tong")) {
    parts.push(mk("i", { class: "sp-f", title: `Tổng — ${tip("tong")}` }, (dau + duoi) % 10));
  }
  if (SHOWN.has("dau")) parts.push(mk("i", { class: "sp-f", title: `Đầu — ${tip("dau")}` }, dau));
  if (SHOWN.has("duoi")) parts.push(mk("i", { class: "sp-f", title: `Đuôi — ${tip("duoi")}` }, duoi));
  if (SHOWN.has("chanle")) {
    parts.push(mk("i", { class: "sp-f", title: `Chẵn/Lẻ — ${tip("chanle")}` },
      `${dau % 2 === 0 ? "C" : "L"}${duoi % 2 === 0 ? "C" : "L"}`));
  }
  if (SHOWN.has("bo")) {
    parts.push(mk("i", { class: "sp-f", title: `Bộ — ${tip("bo")}` }, BO_LOOKUP[+two] || ""));
  }

  return parts.length
    ? [specialFull(s), mk("span", { class: "sp-fields" }, parts)]
    : [specialFull(s)];
}

function renderLegend() {
  const box = $("sp-legend");
  if (!box) return;
  const last = DRAWS.length ? DRAWS[DRAWS.length - 1] : null;
  if (!last) { box.textContent = ""; return; }

  const s = String(last.s).padStart(5, "0");
  const two = s.slice(3);
  const dau = +two[0];
  const duoi = +two[1];
  const iso = last.d;
  const val = {
    ngay: `${iso.slice(8)}-${iso.slice(5, 7)}`,
    tong: String((dau + duoi) % 10),
    dau: String(dau),
    duoi: String(duoi),
    chanle: `${dau % 2 === 0 ? "C" : "L"}${duoi % 2 === 0 ? "C" : "L"}`,
    bo: BO_LOOKUP[+two] || "—",
  };
  const bo = BO_LOOKUP[+two];
  const family = [];
  for (let n = 0; n < 100 && bo; n += 1) {
    if (BO_LOOKUP[n] === bo) family.push(pad2(n));
  }
  const items = DE_FIELDS.map((f) =>
    mk("span", { class: "sp-lg-item", title: f.hint }, [
      mk("b", { class: "sp-lg-val" }, val[f.key]),
      mk("span", { class: "sp-lg-lab" }, f.label),
      mk("span", { class: "sp-lg-hint" }, f.hint),
    ]));

  const rule = mk("p", { class: "sp-legend-rule" }, [
    `Tổng = (Đầu + Đuôi) chia lấy dư 10 = (${dau} + ${duoi}) mod 10 = `,
    mk("b", null, val.tong),
    ". ",
  ]);
  if (bo) {
    put(rule, [
      "Bộ gom một con với bóng dương (0↔5, 1↔6, 2↔7, 3↔8, 4↔9) và số lộn của nó: ",
      `${two} nằm ở bộ `,
      mk("b", null, bo),
      `, gồm ${family.join(" ")}. Cả thảy 15 bộ. `,
    ]);
  }
  put(rule, "Bật/tắt từng trường bằng các ô dưới đây; lựa chọn được nhớ lại cho lần sau.");

  fill(box, [
    mk("div", { class: "sp-legend-head" }, "Đọc một ô: chữ nhỏ dưới mỗi giải là gì"),
    mk("div", { class: "sp-legend-sample" }, [
      specialFull(s),
      mk("span", { class: "sp-lg-src" }, [
        `giải Đặc Biệt kỳ ${iso.slice(8)}-${iso.slice(5, 7)}-${iso.slice(0, 4)}, hai số cuối `,
        mk("b", null, two),
        " — sáu trường dưới đây tách ra từ chính ô này",
      ]),
    ]),
    mk("div", { class: "sp-legend-items" }, items),
    rule,
  ]);
}

function bindFieldToggles(render) {
  const box = $("sp-fields-toggle");
  if (!box) return;
  fill(box, DE_FIELDS.map((f) =>
    mk("label", { class: "sp-fchk", title: f.hint }, [
      mk("input", { type: "checkbox", "data-field": f.key, checked: SHOWN.has(f.key) }),
      ` ${f.label}`,
    ])));
  box.addEventListener("change", (ev) => {
    const key = ev.target.dataset.field;
    if (!key) return;
    if (ev.target.checked) SHOWN.add(key); else SHOWN.delete(key);
    try { localStorage.setItem(FIELD_KEY, JSON.stringify(Array.from(SHOWN))); } catch (e) {}
    render();
  });
}

function lastTwo(value) {
  return String(value).padStart(5, "0").slice(-2);
}

function table(el, headers, rows, opts) {
  opts = opts || {};
  if (!opts.windowed && typeof renderFrequencyWindow === 'function' &&
      renderFrequencyWindow(el, headers, rows, opts)) return;
  const headRow = mk("tr");
  headers.forEach((h, i) => {
    const headKey = opts.headKey && opts.headKey(i);
    const extra = opts.headExtra ? opts.headExtra(i) : "";
    if (!headKey) { put(headRow, mk("th", null, [h, extra])); return; }
    const hPair = opts.headPairOf ? opts.headPairOf(i) : pairInKey(headKey);
    const hKey = hPair && !pairInKey(headKey) ? `${headKey}|n${hPair}` : headKey;
    const on = (MARKS.has(hKey) || (hPair && PAIR_MARKS.has(hPair))) ? " marked" : "";
    put(headRow, mk("th", { class: "cell" + on, "data-key": hKey }, [h, extra]));
  });
  const thead = mk("thead", null, headRow);
  const body = rows.map((r, y) => {
    const tr = mk("tr");
    r.forEach((c, i) => {
      const cls = opts.numeric && opts.numeric.includes(i) ? " num" : "";
      const baseKey = opts.key ? opts.key(y, i) : `${el.id}:${y}:${i}`;
      const pair = opts.pairOf ? opts.pairOf(y, i) : pairInKey(baseKey);
      const key = pair && !pairInKey(baseKey) ? `${baseKey}|n${pair}` : baseKey;
      const on = (MARKS.has(key) || (pair && PAIR_MARKS.has(pair))) ? " marked" : "";
      const blank = (c === "" || c === null || c === undefined) ? " is-empty" : "";
      let state = "";
      const isDataCell = opts.rowHead === false || i > 0;
      if (!blank && isDataCell) {
        state = " sp-hit";
        if (opts.nhay) {
          const k = parseInt(c, 10);
          if (k >= 1) state += ` sp-n${Math.min(k, 5)}`;
        }
      }
      const waiting = opts.pending && (opts.pending(y, i) || {}).pending ? " sp-pending" : "";
      const gan = !waiting && blank && opts.gan && opts.gan(y, i) ? " sp-gan" : "";
      const de = !blank && opts.de && opts.de(y, i) ? " sp-de-hit" : "";
      const tip = opts.title ? opts.title(y, i) : "";
      const style = opts.style ? opts.style(y, i) : "";
      const extra = opts.cellExtra ? opts.cellExtra(y, i) : "";
      put(tr, mk("td", {
        class: `cell${cls}${on}${blank}${state}${waiting}${gan}${de}`,
        "data-key": key,
        title: tip,
        style: style,
      }, [c, extra]));
    });
    return tr;
  });

  const empty = mk("tr", null,
    mk("td", { class: "sp-empty-row", colspan: headers.length },
      "Không có kỳ nào trong dải đã chọn. Kiểm lại Từ ngày / Đến ngày — " +
      "chọn ngược thứ tự cũng cho dải rỗng."));
  fill(el, [thead, mk("tbody", null, rows.length ? body : empty)]);

  el.classList.toggle("has-rowhead", opts.rowHead !== false);
  el.classList.toggle("sp-nhay", !!opts.nhay);
}

const MARK_SCOPE = (window.__D_DEMO_DRAWS__ ? "demo." : "");
const MARK_IDENTITY_SUFFIX = /\/(?:bang-dac-biet|cap-lon-loto|cau-giai-dac-biet|giai-db-ngay-mai)\.html$/.test(location.pathname) ? ".identity-v3" : "";
const MARK_KEY = "sp.marks.v2." + MARK_SCOPE + (location.pathname.split("/").pop() || "index") + MARK_IDENTITY_SUFFIX;

const PAIR_KEY = "sp.pairmarks.v1." + MARK_SCOPE;
let MARKS = new Set();
let PAIR_MARKS = new Set();
try {
  const saved = JSON.parse(localStorage.getItem(MARK_KEY) || "{}");
  MARKS = new Set(Array.isArray(saved) ? saved : (saved.cells || []));
} catch (e) { MARKS = new Set(); }
try {
  PAIR_MARKS = new Set(JSON.parse(localStorage.getItem(PAIR_KEY) || "[]"));
} catch (e) { PAIR_MARKS = new Set(); }

function saveMarks() {
  try {
    localStorage.setItem(MARK_KEY, JSON.stringify({ cells: Array.from(MARKS) }));
    localStorage.setItem(PAIR_KEY, JSON.stringify(Array.from(PAIR_MARKS)));
  } catch (e) {}
}

function bindColumnHint() {
  let lastTable = null, lastIndex = -1, lastRow = null, lastCell = null;
  const clear = () => {
    if (lastTable && lastIndex >= 0) {
      const th = lastTable.querySelectorAll("thead th")[lastIndex];
      if (th) th.classList.remove("col-hint");
    }
    if (lastRow) lastRow.classList.remove("row-hint");
    if (lastCell) lastCell.classList.remove("cell-hint");
    lastTable = null; lastIndex = -1; lastRow = null; lastCell = null;
  };
  document.addEventListener("mouseover", (ev) => {
    const td = ev.target.closest("td");
    const tb = td && td.closest("table");
    if (!td || !tb) { clear(); return; }
    const i = td.cellIndex;
    if (tb === lastTable && i === lastIndex && td === lastCell) return;
    clear();
    const th = tb.querySelectorAll("thead th")[i];
    if (th) { th.classList.add("col-hint"); lastTable = tb; lastIndex = i; }
    const tr = td.parentElement;
    if (tr) { tr.classList.add("row-hint"); lastRow = tr; }
    td.classList.add("cell-hint"); lastCell = td;
  });
  document.addEventListener("mouseleave", clear, true);
}

const PAIR_IN_KEY = /\|(?:n|c)([0-9]{2}(?:-[0-9]{2})?)/;

function pairInKey(key) {
  const found = PAIR_IN_KEY.exec(key || "");
  return found ? found[1] : null;
}

function asPair(value) {
  if (value === null || value === undefined) return null;
  const raw = String(value).trim();
  const two = /^([0-9]{2})$/.exec(raw);
  if (two) return two[1];
  const both = /^([0-9]{2})\s*-\s*([0-9]{2})$/.exec(raw);
  if (both) return `${both[1]}-${both[2]}`;
  return null;
}

function markPair(td) {
  return pairInKey(td.dataset.key);
}

function pairCols(body, ...cols) {
  const want = new Set(cols);
  return (y, i) => (want.has(i) ? asPair((body[y] || [])[i]) : null);
}

function pairModeOn() {
  const box = $("sp-pair-mode");
  return !!(box && box.checked);
}

function isMarked(td) {
  if (MARKS.has(td.dataset.key)) return true;
  const pair = markPair(td);
  return pair !== null && PAIR_MARKS.has(pair);
}

function paintMarks() {
  document.querySelectorAll("td.cell, th.cell").forEach((td) => {
    td.classList.toggle("marked", isMarked(td));
  });
  updateMarkCount();
}

function toggleMark(td) {
  const key = td.dataset.key;
  const pair = markPair(td);
  const clearPairCells = () => {
    for (const saved of MARKS) if (pairInKey(saved) === pair) MARKS.delete(saved);
  };
  if (pair !== null && PAIR_MARKS.has(pair)) {
    PAIR_MARKS.delete(pair);
    clearPairCells();
  }
  else if (MARKS.has(key)) MARKS.delete(key);
  else if (pairModeOn() && pair !== null) {
    clearPairCells();
    PAIR_MARKS.add(pair);
  }
  else MARKS.add(key);
}

function bindMarking() {
  document.addEventListener("click", (ev) => {
    const td = ev.target.closest("td.cell, th.cell");
    if (!td || !td.dataset.key) return;
    toggleMark(td);
    saveMarks();
    paintMarks();
  });

  const pairBox = $("sp-pair-mode");
  if (pairBox) pairBox.addEventListener("change", paintMarks);

  window.addEventListener("storage", (ev) => {
    const pairsChanged = ev.key === PAIR_KEY || ev.key === null;
    const cellsChanged = ev.key === MARK_KEY || ev.key === null;
    if (!pairsChanged && !cellsChanged) return;
    if (pairsChanged) {
      try {
        const saved = JSON.parse(localStorage.getItem(PAIR_KEY) || "[]");
        PAIR_MARKS = new Set(Array.isArray(saved) ? saved.filter(value => asPair(value) === value) : []);
      } catch (err) { PAIR_MARKS = new Set(); }
    }
    if (cellsChanged) {
      try {
        const saved = JSON.parse(localStorage.getItem(MARK_KEY) || "{}");
        const cells = Array.isArray(saved) ? saved : saved && saved.cells;
        MARKS = new Set(Array.isArray(cells) ? cells.filter(value => typeof value === "string") : []);
      } catch (err) { MARKS = new Set(); }
    }
    paintMarks();
  });

  const clear = $("sp-clear-marks");
  if (clear) {
    clear.addEventListener("click", () => {
      MARKS.clear();
      PAIR_MARKS.clear();
      saveMarks();
      paintMarks();
    });
  }
  updateMarkCount();
}

function updateMarkCount() {
  const el = $("sp-mark-count");
  const total = MARKS.size + PAIR_MARKS.size;
  if (el) {
    el.textContent = total
      ? (PAIR_MARKS.size
        ? `${MARKS.size} ô + ${PAIR_MARKS.size} cặp đang đánh dấu`
        : `${MARKS.size} ô đang đánh dấu`)
      : "";
  }
}

function heat(value, max) {
  if (!max) return "";
  const t = Math.min(1, value / max);
  return `background:rgba(124,58,237,${(t * 0.55).toFixed(3)})`;
}

function countLoto(rows) {
  const c = new Array(100).fill(0);
  rows.forEach((r) => r.n.forEach((x) => { c[parseInt(x, 10)] += 1; }));
  return c;
}

let MATRIX_GAN = new Array(100).fill(0);
let MATRIX_RECENT = new Array(100).fill(0);

const PICK_KEY = "sp.picked." + (window.__D_DEMO_DRAWS__ ? "demo." : "") + (location.pathname.split("/").pop() || "index");
let PICKED = null;
try {
  const saved = localStorage.getItem(PICK_KEY);
  if (saved) PICKED = new Set(JSON.parse(saved));
} catch (e) { PICKED = null; }

function savePicked() {
  try {
    if (PICKED) localStorage.setItem(PICK_KEY, JSON.stringify(Array.from(PICKED)));
    else localStorage.removeItem(PICK_KEY);
  } catch (e) {}
}

function isPicked(n) {
  return PICKED === null || PICKED.has(n);
}

function bindPicker(render) {
  const box = $("sp-picker");
  if (!box) return;
  const nutNhanh = (pick, nhan) => mk("button", { type: "button", "data-pick": pick }, nhan);
  const draw = () => {
    fill(box, [
      mk("div", { class: "sp-pick-quick" }, [
        nutNhanh("all", "Tất cả"),
        nutNhanh("none", "Bỏ hết"),
        nutNhanh("even", "Số chẵn"),
        nutNhanh("odd", "Số lẻ"),
      ]),
      mk("div", { class: "sp-pick-grid" },
        Array.from({ length: 100 }, (_, n) => mk("button", {
          type: "button",
          class: "sp-pick" + (isPicked(n) ? " on" : ""),
          "aria-pressed": String(isPicked(n)),
          "data-num": n,
        }, pad2(n)))),
    ]);
  };
  draw();

  box.addEventListener("click", (ev) => {
    const quick = ev.target.dataset.pick;
    if (quick) {
      if (quick === "all") PICKED = null;
      else if (quick === "none") PICKED = new Set();
      else {
        PICKED = new Set();
        for (let n = 0; n < 100; n++) {
          if ((n % 2 === 0) === (quick === "even")) PICKED.add(n);
        }
      }
      savePicked(); draw(); render();
      return;
    }
    const num = ev.target.dataset.num;
    if (num === undefined) return;
    openGanPopup(pad2(+num));
  });
}

function renderLotoMatrix(rows) {
  const grid = $("sp-matrix-grid");
  if (!grid) return;
  if (grid._spWindow) grid._spWindow.destroy();

  const shown = rows;
  const nums = Array.from({ length: 100 }, (_, n) => n).filter(isPicked);

  const note = $("sp-matrix-note");
  if (note) {
    note.textContent = `${shown.length} kỳ × ${nums.length} con.`;
  }
  if (!nums.length) { grid.textContent = ""; return; }

  const per = shown.map((r) => {
    const c = new Array(100).fill(0);
    r.n.forEach((x) => { c[parseInt(x, 10)] += 1; });
    return c;
  });

  const opts = { nhay: true };
  const vertical = ($("sp-orient") || {}).value === "Xem theo chiều dọc";
  const byDate = shown.map((r, i) => ({ d: r.d, c: per[i] })).reverse();
  const ganOf = new Array(100).fill(byDate.length);
  for (let n = 0; n < 100; n += 1) {
    for (let k = 0; k < byDate.length; k += 1) {
      if (byDate[k].c[n]) { ganOf[n] = k; break; }
    }
  }
  const recent30 = new Array(100).fill(0);
  for (let k = 0; k < Math.min(30, byDate.length); k += 1) {
    for (let n = 0; n < 100; n += 1) recent30[n] += byDate[k].c[n] || 0;
  }
  MATRIX_GAN = ganOf;
  MATRIX_RECENT = recent30;

  const sort = ($("sp-sort") || {}).value || "num";
  if (sort !== "num") {
    const totalOf = (n) => byDate.reduce((sum, r) => sum + (r.c[n] || 0), 0);
    const score = sort.startsWith("gan") ? (n) => ganOf[n] : totalOf;
    const dir = sort.endsWith("-asc") ? 1 : -1;
    nums.sort((a, b) => (score(a) - score(b)) * dir || a - b);
  }
  const waiting = pendingDay(shown);
  if (waiting) byDate.unshift({ d: waiting, c: new Array(100).fill(null), pending: true });
  opts.pending = (y, i) => (vertical ? byDate[y] : byDate[i - 1]);
  const deOf = new Map();
  shown.forEach((r) => deOf.set(r.d, String(r.s || "").slice(-2)));
  opts.de = (y, i) => {
    if (i === 0) return false;
    const day = vertical ? byDate[y] : byDate[i - 1];
    const num = vertical ? nums[i - 1] : nums[y];
    return !!day && deOf.get(day.d) === pad2(num);
  };
  opts.gan = (y, i) => {
    if (i === 0) return false;
    const day = vertical ? y : i - 1;
    const num = vertical ? nums[i - 1] : nums[y];
    return day < ganOf[num];
  };
  opts.title = (y, i) => {
    if (i === 0) return "";
    const num = vertical ? nums[i - 1] : nums[y];
    return `Số ${pad2(num)} — số ngày chưa ra tính đến ngày hiện tại: ${ganOf[num]} ngày`;
  };
  if (vertical) {
    const head = ["Ngày"].concat(nums.map(pad2));
    const body = byDate.map((r) =>
      [mk("b", null, `${r.d.slice(8)}-${r.d.slice(5, 7)}`)]
        .concat(nums.map((n) => r.c[n] || "")));
    opts.key = (y, i) => (i === 0
      ? `m|d${byDate[y].d}`
      : `m|n${pad2(nums[i - 1])}|d${byDate[y].d}`);
    opts.headKey = (i) => (i === 0 ? null : `m|n${pad2(nums[i - 1])}`);
    opts.headExtra = (i) => (i === 0 ? "" : miniBar(recent30[nums[i - 1]]));
    table(grid, head, body, opts);
  } else {
    const head = ["Số"].concat(byDate.map((r) => `${r.d.slice(8)}-${r.d.slice(5, 7)}`));
    const body = nums.map((n) =>
      [mk("b", null, pad2(n))].concat(byDate.map((r) => r.c[n] || "")));
    opts.key = (y, i) => (i === 0
      ? `m|n${pad2(nums[y])}`
      : `m|n${pad2(nums[y])}|d${byDate[i - 1].d}`);
    opts.headKey = (i) => (i === 0 ? null : `m|d${byDate[i - 1].d}`);
    opts.cellExtra = (y, i) => (i === 0 ? miniBar(recent30[nums[y]]) : "");
    table(grid, head, body, opts);
  }
  renderNhayLegend(grid);
}

function ganCycles(pair, mode) {
  const hits = [];
  for (let i = 0; i < DRAWS.length; i += 1) {
    const r = DRAWS[i];
    const on = mode === "de"
      ? String(r.s || "").slice(-2) === pair
      : (r.n || []).indexOf(pair) >= 0;
    if (on) hits.push(i);
  }
  const cycles = [];
  for (let k = 1; k < hits.length; k += 1) cycles.push(hits[k] - hits[k - 1] - 1);
  const current = hits.length ? DRAWS.length - 1 - hits[hits.length - 1] : DRAWS.length;
  return {
    hits, cycles, current,
    max: cycles.length ? Math.max(...cycles) : 0,
    dates: hits.slice(-8).reverse().map((i) => DRAWS[i].d),
  };
}

function openGanPopup(pair) {
  const host = $("sp-gan-modal");
  if (!host) return;
  const opening = !host.open;
  const focusedMode = !opening && host.contains(document.activeElement)
    ? document.activeElement.dataset.gmode : null;
  const mode = (host.dataset.mode === "de") ? "de" : "loto";
  const g = ganCycles(pair, mode);
  const tab = (value, label) => mk("button", {
    type: "button",
    class: "sp-btn" + (mode === value ? " on" : ""),
    "data-gmode": value,
  }, label);
  const o = (nhan, so) => mk("div", null, [mk("span", null, nhan), mk("strong", null, so)]);
  const day = (xs) => mk("div", { class: "sp-modal-days" },
    xs.length ? xs.map((x) => mk("span", null, x)) : mk("span", null, "—"));
  const body = [
    mk("div", { class: "sp-modal-tabs" }, [tab("loto", "Lô tô"), tab("de", "Giải Đặc Biệt")]),
    mk("div", { class: "sp-modal-kpi" }, [
      o("Gan hiện tại", g.current),
      o("Gan cực đại", g.max),
      o("Số lần về", g.hits.length),
      o("Số chu kỳ", g.cycles.length),
    ]),
    mk("p", { class: "sp-hint" }, "Các kỳ về gần nhất"),
    day(g.dates),
    mk("p", { class: "sp-hint" }, "Độ dài 12 chu kỳ gan gần nhất (số kỳ trượt giữa hai lần về)"),
    day(g.cycles.slice(-12).reverse()),
  ];
  if ($("sp-picker")) {
    body.push(mk("div", { class: "sp-modal-tabs" },
      mk("button", { type: "button", class: "sp-btn", "data-gfilter": pair },
        `Chỉ xem số ${pair} trên ma trận`)));
  }
  fill(host.querySelector(".sp-modal-body"), body);
  host.querySelector(".sp-modal-title").textContent = `Chu kỳ gan · số ${pair}`;
  host.dataset.pair = pair;
  if (opening) {
    host._spReturnFocus = document.activeElement;
    host.hidden = false;
    host.showModal();
    host.querySelector("[data-close]").focus();
  } else if (focusedMode) {
    host.querySelector(`[data-gmode="${focusedMode}"]`).focus();
  }
}

function bindGanPopup(render) {
  const host = $("sp-gan-modal");
  if (!host) return;
  const redraw = typeof render === "function" ? render : () => {};
  host.addEventListener("close", () => {
    if (host.open) return;
    host.hidden = true;
    const trigger = host._spReturnFocus;
    delete host._spReturnFocus;
    if (trigger && trigger.isConnected) trigger.focus({preventScroll: true});
  });
  host.addEventListener("cancel", (ev) => { ev.preventDefault(); host.close(); });
  host.addEventListener("keydown", (ev) => {
    if (ev.key !== "Tab") return;
    const controls = Array.from(host.querySelectorAll(
      "a[href], button, input, select, textarea, [tabindex]"
    )).filter(node => node.tabIndex >= 0 && !node.disabled && node.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  });
  host.addEventListener("click", (ev) => {
    if (ev.target === host || ev.target.dataset.close !== undefined) { host.close(); return; }
    const gmode = ev.target.dataset.gmode;
    if (gmode) { host.dataset.mode = gmode; openGanPopup(host.dataset.pair); return; }
    const only = ev.target.dataset.gfilter;
    if (only !== undefined) {
      PICKED = new Set([Number(only)]);
      savePicked(); host.close(); redraw();
    }
  });
}

function miniBar(total) {
  const pct = Math.max(6, Math.min(100, Math.round((total / 12) * 100)));
  return mk("i", { class: "sp-mini-bar", style: `--h:${pct}%`, "aria-hidden": "true" });
}

function renderNhayLegend(grid) {
  const host = grid && grid.parentElement;
  if (!host || host.querySelector(".sp-nhay-legend")) return;
  const tiers = [
    [1, "1 nháy"], [2, "2 nháy"], [3, "3 nháy"], [4, "4 nháy"], [5, "5 nháy trở lên"],
  ];
  const box = document.createElement("div");
  box.className = "sp-nhay-legend";
  fill(box, [
    mk("b", null, "Số nháy"),
    tiers.map(([k, label]) => mk("span", { class: "sp-nl" }, [
      mk("i", { class: "sp-n" + k }, k === 5 ? "5+" : k),
      mk("span", null, label),
    ])),
    mk("span", { class: "sp-nl" }, [
      mk("i", { class: "sp-empty-key" }),
      mk("span", null, "không về"),
    ]),
  ]);
  host.insertBefore(box, grid);
}

function renderLotoFrequency() {
  const rows = selected();
  setCount(rows);
  renderLotoMatrix(rows);
  const counts = countLoto(rows);
  const expected = NHAY_PER_DRAW * rows.length;
  const max = Math.max(...counts, 1);

  const m = $("sp-matrix");
  if (m) {
    fill(m, rows.length ? counts.map((v, i) =>
      mk("span", { class: "sp-cell", style: heat(v, max), title: `Số ${pad2(i)}: ${v} lần` }, [
        mk("b", null, pad2(i)),
        mk("i", null, v),
      ])) : mk("p", { class: "sp-empty-row" }, "Không có kỳ phù hợp với dải đang chọn."));
  }
  const order = counts.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  const rankBody = rows.length ? order.map((p, k) => [
    k + 1, pad2(p[0]), p[1], expected.toFixed(1),
    expected ? (p[1] / expected).toFixed(2) + "×" : "—",
  ]) : [];
  table($("sp-grid"),
    ["Hạng", "Số", "Số lần về", "Kỳ vọng", "So kỳ vọng"],
    rankBody, { numeric: [0, 2, 3, 4], pairOf: pairCols(rankBody, 1) });
}

function reversePairs() {
  const out = [];
  for (let a = 0; a < 100; a++) {
    const b = (a % 10) * 10 + Math.floor(a / 10);
    if (a < b) out.push([a, b]);
  }
  return out;
}

function doubleNumbers() {
  return Array.from({ length: 10 }, (_, d) => d * 11);
}

function renderReversePairs() {
  const rows = selected();
  setCount(rows);

  const c = new Array(100).fill(0);
  rows.forEach((r) => r.n.forEach((x) => { c[parseInt(x, 10)] += 1; }));

  const pairs = reversePairs()
    .map(([a, b]) => [a, b, c[a], c[b], c[a] + c[b]])
    .sort((x, y) => y[4] - x[4]);
  const maximum = Math.max(0, ...pairs.map(p => p[4]), ...doubleNumbers().map(n => c[n]));

  table($("sp-grid"),
    ["Hạng", "Cặp số", "Lượt thuận", "Lượt lộn", "Tổng lượt", "Chênh lệch"],
    pairs.map((p, k) => [
      k + 1,
      `${pad2(p[0])} ↔ ${pad2(p[1])}`,
      p[2], p[3], p[4],
      (p[2] - p[3] > 0 ? "+" : "") + (p[2] - p[3]),
    ]), {
      numeric: [0, 2, 3, 4, 5],
      key: (y, i) => `reverse|pair${pad2(pairs[y][0])}-${pad2(pairs[y][1])}|field${i}`,
      pairOf: (y, i) => (i === 1 ? `${pad2(pairs[y][0])}-${pad2(pairs[y][1])}` : null),
    });
  $("sp-grid").prepend(mk("colgroup", null, [9,25,16.5,16.5,16.5,16.5].map(width => mk("col", {style: `width:${width}%`}))));
  pairs.forEach((pair, index) => [2, 3, 4].forEach(column =>
    specialMetricCell($("sp-grid").tBodies[0].rows[index].cells[column], pair[column], maximum,
      "frequency", `Cặp ${pad2(pair[0])} ↔ ${pad2(pair[1])} · ${["", "", "Lượt thuận", "Lượt lộn", "Tổng lượt"][column]}`, "lượt")));

  const kep = $("sp-kep");
  if (kep) {
    const ds = doubleNumbers().map((n) => [pad2(n), c[n]]).sort((a, b) => b[1] - a[1]);
    table(kep, ["Số kép", "Số lần về"], ds,
      { numeric: [1], pairOf: pairCols(ds, 0), key: (y, i) => `double|number${ds[y][0]}|field${i}` });
    ds.forEach((row, index) => specialMetricCell(kep.tBodies[0].rows[index].cells[1],
      row[1], maximum, "frequency", `Số kép ${row[0]}`, "lượt"));
  }
  specialMetricLegend("app-loto-reverse-frequency-legend", "frequency", maximum, "lượt",
    "Số lượt · chung cho hai chiều, tổng và số kép");
}

const CAP50 = window.__D_CAP50__ || [];

function renderPairMatrix(rows) {
  const grid = $("sp-matrix-grid");
  if (!grid || !CAP50.length) return;
  if (grid._spWindow) grid._spWindow.destroy();

  const shown = rows;
  const note = $("sp-matrix-note");
  if (note) {
    note.textContent = `${shown.length} kỳ × ${CAP50.length} họ cặp.`;
  }

  const per = shown.map((r) => {
    const c = new Array(100).fill(0);
    r.n.forEach((x) => { c[parseInt(x, 10)] += 1; });
    return CAP50.map(([a, b]) => c[a] + c[b]);
  });

  const label = ([a, b]) => `${pad2(a)}-${pad2(b)}`;
  const day = (r) => `${r.d.slice(8)}-${r.d.slice(5, 7)}`;

  const byDate = shown.map((r, i) => ({ d: r.d, t: day(r), c: per[i] })).reverse();
  const waiting = pendingDay(shown);
  if (waiting) {
    byDate.unshift({
      d: waiting, t: `${waiting.slice(8)}-${waiting.slice(5, 7)}`,
      c: new Array(CAP50.length).fill(null), pending: true,
    });
  }
  const verticalPair = ($("sp-orient") || {}).value === "Xem theo chiều dọc";
  const pendingAt = (y, i) => (verticalPair ? byDate[y] : byDate[i - 1]);
  const ganPair = new Array(CAP50.length).fill(byDate.length);
  const recentPair = new Array(CAP50.length).fill(0);
  for (let j = 0; j < CAP50.length; j += 1) {
    for (let k = 0; k < byDate.length; k += 1) {
      if (byDate[k].c[j]) { ganPair[j] = k; break; }
    }
    for (let k = 0; k < Math.min(30, byDate.length); k += 1) {
      recentPair[j] += byDate[k].c[j] || 0;
    }
  }
  const pairGan = (y, i) => {
    if (i === 0) return false;
    const day = verticalPair ? y : i - 1;
    const idx = verticalPair ? i - 1 : y;
    return day < ganPair[idx];
  };
  const pairTip = (y, i) => {
    if (i === 0) return "";
    const idx = verticalPair ? i - 1 : y;
    return `Cặp ${label(CAP50[idx])} — số ngày chưa ra tính đến ngày hiện tại: ${ganPair[idx]} ngày`;
  };
  if (($("sp-orient") || {}).value === "Xem theo chiều dọc") {
    table(grid, ["Ngày"].concat(CAP50.map(label)),
      byDate.map((r) => [mk("b", null, r.t)].concat(r.c.map((v) => v || ""))),
      { pending: pendingAt, gan: pairGan, title: pairTip,
        headKey: (i) => (i === 0 ? null : `p|c${label(CAP50[i - 1])}`),
        headExtra: (i) => (i === 0 ? "" : miniBar(recentPair[i - 1] / 2)),
        key: (y, i) => (i === 0
          ? `p|d${byDate[y].d}`
          : `p|c${label(CAP50[i - 1])}|d${byDate[y].d}`) });
  } else {
    table(grid, ["Cặp"].concat(byDate.map((r) => r.t)),
      CAP50.map((pair, j) => [mk("b", null, label(pair))]
        .concat(byDate.map((r) => r.c[j] || ""))),
      { pending: pendingAt, gan: pairGan, title: pairTip,
        headKey: (i) => (i === 0 ? null : `p|d${byDate[i - 1].d}`),
        cellExtra: (y, i) => (i === 0 ? miniBar(recentPair[y] / 2) : ""),
        key: (y, i) => (i === 0
          ? `p|c${label(CAP50[y])}`
          : `p|c${label(CAP50[y])}|d${byDate[i - 1].d}`) });
  }
}

function renderPairFrequency() {
  const rows = selected();
  setCount(rows);
  renderPairMatrix(rows);
  updateChanceNote(rows.length);
  const co = new Map();
  rows.forEach((r) => {
    const uniq = Array.from(new Set(r.n)).sort();
    for (let i = 0; i < uniq.length; i++)
      for (let j = i + 1; j < uniq.length; j++)
        co.set(uniq[i] + "-" + uniq[j], (co.get(uniq[i] + "-" + uniq[j]) || 0) + 1);
  });
  const expected = PAIR_BASELINE * rows.length;
  const top = Array.from(co.entries()).sort((a, b) => b[1] - a[1]).slice(0, 50);
  const topBody = top.map((p, k) => [
    k + 1, p[0], p[1], expected.toFixed(1),
    expected ? (p[1] / expected).toFixed(2) + "×" : "—",
  ]);
  table($("sp-grid"),
    ["Hạng", "Cặp số", "Số lần cùng về", "Kỳ vọng", "So kỳ vọng"],
    topBody, { numeric: [0, 2, 3, 4], pairOf: pairCols(topBody, 1) });
}

function renderHeadTail() {
  const rows = selected();
  setCount(rows);
  const shade = (value, max) => {
    if (!value) return "";
    const ratio = Math.min(1, value / Math.max(1, max));
    const ramp = (theme, low, high) => {
      const rgb = low.map((v, i) => Math.round(v + (high[i] - v) * ratio));
      const linear = rgb.map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
      const luminance = linear.reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
      const ink = luminance > .179 ? "#000000" : "#ffffff";
      return `--app-hit-bg-${theme}:rgb(${rgb.join(",")});--app-hit-ink-${theme}:${ink};`;
    };
    return ramp("light", [239,248,255], [7,89,133]) + ramp("dark", [85,120,148], [7,62,98]);
  };
  const paint = (cell, value, max, label) => {
    cell.classList.add("app-head-tail-heat");
    cell.dataset.appHitCount = String(value);
    cell.setAttribute("style", shade(value, max));
    cell.setAttribute("aria-label", `${label} · ${value} lượt`);
  };
  const legend = (id, max, daily) => {
    const host = $(id);
    if (!host) return;
    if (!rows.length) { fill(host, "Không có kỳ phù hợp với bộ lọc."); return; }
    const values = daily
      ? [...Array.from({length: Math.min(max, 5) + 1}, (_, i) => i), ...(max > 5 ? [max] : [])]
      : [...new Set([0, ...[.25,.5,.75,1].map(t => Math.ceil(max * t))])];
    fill(host, [mk("span", {class: "app-head-tail-legend-label"}, daily ? "Nháy trong một kỳ · ít → nhiều" : "Tổng lượt trong dải · ít → nhiều"),
      ...values.map(value => {
        const chip = mk("span", {class: "app-head-tail-swatch"}, value);
        paint(chip, value, max, daily ? "Nháy mỗi kỳ" : "Tổng lượt");
        return chip;
      }), mk("small", null, "Cùng thang màu cho Đầu và Đuôi.")]);
  };
  const head = new Array(10).fill(0);
  const tail = new Array(10).fill(0);
  rows.forEach((r) => r.n.forEach((x) => {
    head[parseInt(x[0], 10)] += 1;
    tail[parseInt(x[1], 10)] += 1;
  }));
  const total = rows.length * 27;
  const rangeMax = Math.max(1, ...head, ...tail);
  const build = (el, counts, label) => {
    const max = Math.max(...counts, 1);
    table(el, [label, "Số lần", "Tỉ lệ", "Biểu đồ"],
      counts.map((v, i) => [
        i, v, total ? ((v / total) * 100).toFixed(2) + "%" : "—",
        mk("span", { class: "sp-bar", style: `width:${(100 * v / max).toFixed(1)}%` }),
      ]), { numeric: [0, 1, 2] });
    el.prepend(mk("colgroup", null, [20,20,20,40].map(width => mk("col", {style: `width:${width}%`}))));
    counts.forEach((value, digit) => {
      const cells = el.tBodies[0].rows[digit].cells;
      paint(cells[0], value, rangeMax, `${label} ${digit}`);
      paint(cells[1], value, rangeMax, `${label} ${digit}`);
    });
  };
  build($("sp-head"), head, "Chữ số đầu");
  build($("sp-tail"), tail, "Chữ số đuôi");
  legend("app-head-tail-legend", rangeMax, false);

  const recent = rows.slice(-20).reverse();
  const daily = recent.map(r => {
    const counts = {head:new Array(10).fill(0), tail:new Array(10).fill(0), sum:new Array(10).fill(0)};
    r.n.forEach(x => {counts.head[+x[0]]++; counts.tail[+x[1]]++; counts.sum[(+x[0] + +x[1]) % 10]++;});
    return counts;
  });
  const dayMax = Math.max(1, ...daily.flatMap(day => [...day.head, ...day.tail]));
  const perDay = (kind, label, el) => {
    const headers = ["Ngày"].concat(
      Array.from({ length: 10 }, (_, d) => `${label} ${d}`));
    table(el, headers, recent.map((r, index) => {
      const count = daily[index][kind];
      return [viDate(r.d)].concat(
        count.map((v) => (v ? `${v} lần` : mk("span", { class: "sp-zero" }, "0"))));
    }), { numeric: Array.from({ length: 10 }, (_, i) => i + 1) });
    if (kind !== "sum") daily.forEach((day, index) => day[kind].forEach((value, digit) =>
      paint(el.tBodies[0].rows[index].cells[digit + 1], value, dayMax, `${label} ${digit} · ${recent[index].d}`)));
  };
  perDay("head", "Đầu", $("sp-day-head"));
  perDay("tail", "Đuôi", $("sp-day-tail"));
  perDay("sum", "Tổng", $("sp-day-sum"));
  legend("app-head-tail-day-legend", dayMax, true);
}

function specialGaps(rows = DRAWS) {
  const last = new Array(100).fill(-1);
  const maxGap = new Array(100).fill(0);
  const hits = new Array(100).fill(0);
  rows.forEach((r, t) => {
    const k = parseInt(lastTwo(r.s), 10);
    hits[k] += 1;
    if (last[k] >= 0) maxGap[k] = Math.max(maxGap[k], t - last[k]);
    last[k] = t;
  });
  const n = rows.length;
  return { last, maxGap, hits, current: last.map((t) => (t < 0 ? n : n - 1 - t)), n };
}

function lotoGaps(rows = DRAWS) {
  const last = new Array(100).fill(-1);
  const maxGap = new Array(100).fill(0);
  const hits = new Array(100).fill(0);
  rows.forEach((r, t) => {
    const seen = new Set(r.n.map((x) => parseInt(x, 10)));
    seen.forEach((k) => {
      hits[k] += 1;
      if (last[k] >= 0) maxGap[k] = Math.max(maxGap[k], t - last[k] - 1);
      last[k] = t;
    });
  });
  const n = rows.length;
  const current = last.map((t) => (t >= 0 ? n - 1 - t : n));
  return { last, maxGap, current, hits };
}

function pairGaps(rows = DRAWS) {
  const last = new Array(CAP50.length).fill(-1);
  const maxGap = new Array(CAP50.length).fill(0);
  const hits = new Array(CAP50.length).fill(0);
  rows.forEach((r, t) => {
    const seen = new Set(r.n.map((x) => parseInt(x, 10)));
    CAP50.forEach((pair, i) => {
      if (!seen.has(pair[0]) && !seen.has(pair[1])) return;
      hits[i] += 1;
      if (last[i] >= 0) maxGap[i] = Math.max(maxGap[i], t - last[i] - 1);
      last[i] = t;
    });
  });
  const n = rows.length;
  const current = last.map((t) => (t >= 0 ? n - 1 - t : n));
  return { last, maxGap, current, hits };
}

function viDate(d) {
  return `${d.slice(8)}-${d.slice(5, 7)}-${d.slice(0, 4)}`;
}

function drawDate(i, rows = DRAWS) {
  return i < 0 ? "chưa về trong dải" : viDate(rows[i].d);
}

function renderLoGan() {
  const rows = selected();
  const g = lotoGaps(rows);
  setCount(rows);

  const order = g.current.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  const ganBody = order.map((p) => [
    pad2(p[0]), drawDate(g.last[p[0]], rows), p[1], g.hits[p[0]] >= 2 ? g.maxGap[p[0]] : "—", g.hits[p[0]],
  ]);
  table($("sp-grid"),
    ["Bộ số", "Ngày ra cuối cùng", "Số kỳ gan", "Gan cực đại", "Tổng lần về"],
    ganBody, { numeric: [2, 3, 4], pairOf: pairCols(ganBody, 0) });
  const paint = (id, body, stats, prefix) => {
    const gapMax = Math.max(0, ...stats.current);
    const cycleMax = Math.max(0, ...stats.maxGap);
    const hitMax = Math.max(0, ...stats.hits);
    body.forEach((row, index) => {
      const cells = $(id).tBodies[0].rows[index].cells;
      specialMetricCell(cells[2], row[2], gapMax, "gap", `${row[0]} · Chưa về`, "kỳ");
      if (typeof row[3] === "number")
        specialMetricCell(cells[3], row[3], cycleMax, "cycle", `${row[0]} · Chu kỳ dài nhất`, "kỳ");
      specialMetricCell(cells[4], row[4], hitMax, "frequency", `${row[0]} · Số kỳ có mặt`, "kỳ");
    });
    specialMetricLegend(`${prefix}-gap-legend`, "gap", gapMax, "kỳ");
    specialMetricLegend(`${prefix}-cycle-legend`, "cycle", cycleMax, "kỳ", undefined, stats.hits.some(hits => hits >= 2));
    specialMetricLegend(`${prefix}-frequency-legend`, "frequency", hitMax, "kỳ", "Số kỳ có mặt");
  };
  paint("sp-grid", ganBody, g, "app-loto-current");

  const all = rows.length === DRAWS.length ? g : lotoGaps();
  const historyMax = Math.max(0, ...all.maxGap);
  const half = (el, from, to) => {
    const body = Array.from({ length: to - from }, (_, k) => {
      const i = from + k;
      return [pad2(i), all.hits[i] >= 2 ? `${all.maxGap[i]} kỳ` : "—"];
    });
    table(el, ["Bộ số", "Gan cực đại"], body,
      { numeric: [1], pairOf: pairCols(body, 0) });
    body.forEach((row, index) => {
      const value = all.maxGap[from + index];
      if (all.hits[from + index] >= 2) specialMetricCell(el.tBodies[0].rows[index].cells[1], value,
        historyMax, "cycle", `Số ${row[0]} · Chu kỳ dài nhất toàn bộ lịch sử`, "kỳ");
    });
  };
  half($("sp-max-lo"), 0, 50);
  half($("sp-max-hi"), 50, 100);
  specialMetricLegend("app-loto-history-cycle-legend", "cycle", historyMax, "kỳ", undefined, all.hits.some(hits => hits >= 2));

  const pg = pairGaps(rows);
  const pairOrder = pg.current.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  const pairBody = pairOrder.map((p) => [
    `${pad2(CAP50[p[0]][0])} - ${pad2(CAP50[p[0]][1])}`, drawDate(pg.last[p[0]], rows), p[1],
    pg.hits[p[0]] >= 2 ? pg.maxGap[p[0]] : "—", pg.hits[p[0]],
  ]);
  table($("sp-pair-gan"),
    ["Cặp số", "Ngày ra gần đây", "Số kỳ gan", "Gan cực đại", "Tổng lần về"],
    pairBody, { numeric: [2, 3, 4], pairOf: pairCols(pairBody, 0) });
  paint("sp-pair-gan", pairBody, pg, "app-loto-pair");
}

function specialMetricCell(cell, value, maximum, metric, label, unit) {
  const level = value > 0 && maximum > 0 ? Math.min(3, Math.ceil(3 * value / maximum)) : 0;
  cell.classList.add("app-stat-metric", `app-stat-${metric}`, `app-stat-level-${level}`);
  cell.dataset.statMetric = metric;
  cell.dataset.statValue = String(value);
  cell.dataset.statLevel = String(level);
  cell.setAttribute("aria-label", `${label}: ${value} ${unit}`);
}

function specialMetricLegend(id, metric, maximum, unit, label, hasCycle = maximum > 0) {
  const legend = $(id);
  if (!legend) return;
  const entries = [mk("strong", null, label || (metric === "gap" ? "Chưa về" : metric === "cycle" ? "Chu kỳ dài nhất" : "Số lượt"))];
  if (metric !== "cycle" || hasCycle) entries.push(
    mk("span", null, [mk("i", {class: `app-stat-${metric} app-stat-level-0`, "aria-hidden": "true"}), `0 ${unit}`]));
  if (metric === "cycle" && !hasCycle)
    entries.push(mk("span", null, "Chưa đủ hai lần xuất hiện để ghi nhận chu kỳ."));
  for (let level = 1; level <= 3; level++) {
    const low = Math.floor((level - 1) * maximum / 3) + 1;
    const high = Math.floor(level * maximum / 3);
    if (low > high) continue;
    const range = low === high ? String(low) : `${low}–${high}`;
    entries.push(mk("span", null, [mk("i", {class: `app-stat-${metric} app-stat-level-${level}`, "aria-hidden": "true"}), `${range} ${unit}`]));
  }
  fill(legend, entries);
}

function renderSpecialCycle() {
  const rows = selected();
  const s = specialGaps(rows);
  setCount(rows);
  const order = s.current.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  const body = order.map((p, k) => [k + 1, pad2(p[0]), p[1], s.maxGap[p[0]] || "—", s.hits[p[0]]]);
  table($("sp-grid"),
    ["Hạng", "Số", "Chưa về (kỳ)", "Chu kỳ dài nhất", "Tổng lần về"],
    body, { numeric: [0, 2, 3, 4], pairOf: pairCols(body, 1) });
  const maximum = Math.max(0, ...s.current);
  body.forEach((row, index) => specialMetricCell($("sp-grid").tBodies[0].rows[index].cells[2],
    row[2], maximum, "gap", `Số ${row[1]} · Chưa về`, "kỳ"));
  specialMetricLegend("app-special-gap-legend", "gap", maximum, "kỳ");
}

function renderSpecialBySet() {
  const draws = selected();
  const s = specialGaps(draws);
  setCount(draws);
  const rows = [];
  for (let i = 0; i < 100; i++) {
    const lastDate = s.last[i] >= 0 ? draws[s.last[i]].d : "chưa về trong dải";
    rows.push([pad2(i), lastDate, s.current[i], s.maxGap[i] || "—", s.hits[i]]);
  }
  rows.sort((a, b) => b[2] - a[2]);
  table($("sp-grid"),
    ["Bộ số", "Về gần nhất", "Chưa về (kỳ)", "Chu kỳ dài nhất", "Tổng lần về"],
    rows, { numeric: [2, 3, 4], pairOf: pairCols(rows, 0) });
  const maximum = Math.max(0, ...s.current);
  rows.forEach((row, index) => specialMetricCell($("sp-grid").tBodies[0].rows[index].cells[2],
    row[2], maximum, "gap", `Số ${row[0]} · Chưa về`, "kỳ"));
  specialMetricLegend("app-special-gap-legend", "gap", maximum, "kỳ");
}

function tomorrowLoto(draw, kind, date, missing) {
  const counts = new Map();
  for (const value of draw && Array.isArray(draw.n) ? draw.n : []) {
    const raw = String(value);
    if (!/^\d{1,2}$/.test(raw)) continue;
    const number = raw.padStart(2, "0");
    counts.set(number, (counts.get(number) || 0) + 1);
  }
  const total = [...counts.values()].reduce((sum, count) => sum + count, 0);
  return mk("div", {class: "app-tomorrow-loto", [`data-${kind}-loto`]: "true", "data-loto-date": date}, total ? [
    mk("small", {class: "app-tomorrow-loto-total"}, `${total} lượt`),
    mk("div", {class: "app-tomorrow-loto-numbers"}, [...counts].sort((a, b) => a[0].localeCompare(b[0])).map(([number, count]) =>
      mk("span", {"data-loto-number": number, "data-loto-count": count, "aria-label": `${number}, ${count} nháy`}, [
        mk("b", null, number), count > 1 ? mk("small", null, `×${count}`) : null,
      ]))),
  ] : mk("span", {class: "app-tomorrow-pending"}, missing || "Chưa có dữ liệu LOTO"));
}

function renderTomorrow() {
  const rows = selected();
  setCount(rows);
  const number = $("sp-tomorrow-number").value;
  const byDate = new Map(DRAWS.map(row => [row.d, row]));
  const latest = DRAWS.length ? DRAWS[DRAWS.length - 1].d : "";
  const matches = rows.filter(row => String(row.s).slice(-2) === number).slice().reverse();
  const format = value => value.split("-").reverse().join("/");
  const entries = matches.map(row => {
    const [y, m, d] = row.d.split("-").map(Number);
    const nextDate = new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
    return {row, nextDate, next: byDate.get(nextDate)};
  });
  const counts = new Map();
  for (const entry of entries) if (entry.next) {
    const suffix = String(entry.next.s).slice(-2);
    counts.set(suffix, (counts.get(suffix) || 0) + 1);
  }
  const known = entries.filter(entry => entry.next).length;
  $("sp-tomorrow-heading").textContent = `Những lần Đặc Biệt về ${number}`;
  $("sp-tomorrow-summary").textContent = `Đặc Biệt ${number}: ${matches.length} lần xuất hiện · ${known} lần có kết quả hôm sau.`;
  const body = entries.map(({row, nextDate, next}) => {
    const missing = nextDate > latest ? "Chờ kết quả" : "Chưa có dữ liệu";
    return [
      format(row.d),
      mk("span", {"data-trigger-special": "true"}, specialFull(row.s)),
      tomorrowLoto(row, "trigger", row.d),
      mk("span", {class: "app-tomorrow-result"}, [
        next ? mk("span", {"data-next-special": "true"}, specialFull(next.s))
          : mk("span", {class: "app-tomorrow-pending"}, missing),
        mk("small", {class: "app-tomorrow-next-date", "data-next-date": nextDate}, format(nextDate)),
      ]),
      tomorrowLoto(next, "next", nextDate, next ? null : missing),
    ];
  });
  const grid = $("sp-grid");
  table(grid, ["Ngày về", `Đặc Biệt về ${number}`, "LOTO cùng ngày", "Đặc Biệt hôm sau", "LOTO hôm sau"], body, {
    key: (y, x) => `tomorrow:${number}:${entries[y].row.d}:${[0, 1, "trigger-loto", 2, "next-loto"][x]}`,
    pairOf: (y, x) => x === 1 ? number : x === 3 && entries[y].next ? String(entries[y].next.s).slice(-2) : null,
  });
  Array.from(grid.tBodies[0].rows).forEach((row, index) => {
    if (entries[index]) row.setAttribute("data-trigger-date", entries[index].row.d);
  });
  if (!matches.length) grid.tBodies[0].rows[0].cells[0].textContent = `Chưa có lần Đặc Biệt về ${number} trong dải đang chọn.`;
  $("sp-tomorrow-frequency-note").textContent = `${known} kết quả hôm sau đã biết · Hai số cuối`;
  fill($("sp-tomorrow-frequencies"), [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([suffix, count]) =>
    mk("div", {"data-number": suffix, "data-count": count}, [mk("b", null, suffix), mk("span", null, `${count} lần`)])));
}

function groupSpecial(keyOf, label) {
  const rows = selected();
  setCount(rows);
  const groups = new Map();
  rows.forEach((r) => {
    const k = keyOf(r.d);
    if (!groups.has(k)) groups.set(k, new Array(100).fill(0));
    groups.get(k)[parseInt(lastTwo(r.s), 10)] += 1;
  });
  const keys = Array.from(groups.keys()).sort().reverse();
  const head = [label, "Số kỳ", "Về nhiều nhất", "Số lần", "Không về"];
  const body = keys.map((k) => {
    const c = groups.get(k);
    const total = c.reduce((a, b) => a + b, 0);
    const best = c.indexOf(Math.max(...c));
    const missing = c.filter((v) => v === 0).length;
    return [k, total, pad2(best), Math.max(...c), missing];
  });
  table($("sp-grid"), head, body, { numeric: [1, 3, 4] });
}

const WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"];

function mondayIndex(iso) {
  return (new Date(iso + "T00:00:00Z").getUTCDay() + 6) % 7;
}

function weekStart(iso) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - mondayIndex(iso));
  return d.toISOString().slice(0, 10);
}

function fillPicker(id, values, prefer) {
  const sel = $(id);
  if (!sel) return null;
  if (!sel.options.length) {
    fill(sel, values.map((v) => mk("option", null, v)));
    sel.value = prefer !== undefined ? prefer : values[values.length - 1];
  }
  return sel.value;
}

function weekGrid(rows) {
  const byDate = {};
  rows.forEach((r) => { byDate[r.d] = r.s; });

  const weeks = new Map();
  const pairs = new Map();
  rows.forEach((r) => {
    const w = weekStart(r.d);
    if (!weeks.has(w)) {
      weeks.set(w, new Array(7).fill(""));
      pairs.set(w, new Array(7).fill(null));
    }
    weeks.get(w)[mondayIndex(r.d)] = specialCell(byDate[r.d], r.d);
    pairs.get(w)[mondayIndex(r.d)] = lastTwo(byDate[r.d]);
  });
  const order = Array.from(weeks.keys()).sort();
  return {
    body: order.map((w) => weeks.get(w)),
    pairs: order.map((w) => pairs.get(w)),
    weeks: order,
  };
}

function renderSpecialByWeek() {
  const rows = selected();
  setCount(rows);
  const grid = weekGrid(rows);
  table($("sp-grid"), WEEKDAYS, grid.body,
    { rowHead: false, pairOf: (y, i) => (grid.pairs[y] || [])[i] || null,
      key: (y, i) => `special-week|week${grid.weeks[y]}|day${i}` });
}

function monthGrid(year) {
  const byDate = {};
  DRAWS.filter((r) => r.d.slice(0, 4) === year).forEach((r) => { byDate[r.d] = r.s; });

  const body = [];
  const pairs = [];
  for (let day = 1; day <= 31; day++) {
    const line = [mk("b", null, pad2(day))];
    const pline = [null];
    for (let m = 1; m <= 12; m++) {
      const de = byDate[`${year}-${pad2(m)}-${pad2(day)}`];
      line.push(de ? specialCell(de, null) : "");
      pline.push(de ? lastTwo(de) : null);
    }
    body.push(line);
    pairs.push(pline);
  }
  return { body, pairs };
}

const MONTH_HEAD = ["Ngày"].concat(
  Array.from({ length: 12 }, (_, m) => "Tháng " + (m + 1)));

function renderSpecialYearByDay() {
  const months = Array.from({ length: 12 }, (_, m) => "Tháng " + (m + 1));
  const today = todayInVietnam() || (DRAWS.length ? DRAWS[DRAWS.length - 1].d : "");
  const monthLabel = fillPicker("sp-month", months, months[(+today.slice(5, 7) || 1) - 1]);
  const month = months.indexOf(monthLabel) + 1;

  const inMonth = DRAWS.filter((r) => +r.d.slice(5, 7) === month);
  setCount(inMonth);

  const byYear = new Map();
  const pairByYear = new Map();
  inMonth.forEach((r) => {
    const year = r.d.slice(0, 4);
    if (!byYear.has(year)) {
      byYear.set(year, new Array(31).fill(""));
      pairByYear.set(year, new Array(31).fill(null));
    }
    byYear.get(year)[+r.d.slice(8) - 1] = specialCell(r.s, null);
    pairByYear.get(year)[+r.d.slice(8) - 1] = lastTwo(r.s);
  });

  const head = ["Năm"].concat(Array.from({ length: 31 }, (_, i) => String(i + 1)));
  const order = Array.from(byYear.keys()).sort().reverse();
  const body = order.map((year) => [mk("b", null, year)].concat(byYear.get(year)));
  const pairs = order.map((year) => [null].concat(pairByYear.get(year)));
  table($("sp-grid"), head, body,
    { pairOf: (y, i) => (pairs[y] || [])[i] || null });
}

function renderSpecialDayByMonth() {
  const years = Array.from(new Set(DRAWS.map((r) => r.d.slice(0, 4)))).sort();
  const year = fillPicker("sp-year", years) || years[years.length - 1];
  setCount(DRAWS.filter((r) => r.d.slice(0, 4) === year));
  const grid = monthGrid(year);
  table($("sp-grid"), MONTH_HEAD, grid.body,
    { pairOf: (y, i) => (grid.pairs[y] || [])[i] || null });
}

function renderOverview() {
  const rows = selected();
  setCount(rows);
  if ($("sp-count")) $("sp-count").textContent = rows.length
    ? `${rows.length} kỳ · ${viDate(rows[0].d)} → ${viDate(rows.at(-1).d)}`
    : "Không có kỳ phù hợp với bộ lọc";
  const counts = countLoto(rows);
  const expected = NHAY_PER_DRAW * rows.length;
  const total = rows.reduce((sum, row) => sum + row.n.length, 0);
  const s = specialGaps();
  const hottest = counts.indexOf(Math.max(...counts));
  const coldest = s.current.indexOf(Math.max(...s.current));
  const values = {};
  const scope = (list) => list.length
    ? `${list.length} kỳ · ${viDate(list[0].d)} → ${viDate(list.at(-1).d)}`
    : "0 kỳ · Không có kỳ phù hợp";
  const weekday = $("sp-weekday");
  const weekdayLabel = weekday && weekday.value !== "all"
    ? ` · ${weekday.options[weekday.selectedIndex].textContent}` : "";
  const filteredSources = [{
    title: "Các kỳ XSMB trong dải đang chọn",
    snippet: scope(rows) + weekdayLabel + ". Cộng đủ mọi nháy từ 27 kết quả LOTO mỗi kỳ.",
    url: "so-ket-qua-truyen-thong.html",
  }];
  const globalSources = [{
    title: "Giải Đặc Biệt trên toàn bộ lịch sử",
    snippet: scope(DRAWS) + ". Dùng hai số cuối giải Đặc Biệt; bộ lọc ngày và thứ không áp dụng.",
    url: "so-ket-qua-truyen-thong.html",
  }];
  const define = (id, title, sources, steps) => {
    values[id] = { title, sources, reasoningTrace: { steps } };
    return id;
  };
  const countSteps = (number) => [
    `Giữ đúng ${scope(rows)}${weekdayLabel} theo bộ lọc ngày và thứ.`,
    `Đếm đủ các lần xuất hiện của số ${pad2(number)} trong 27 kết quả LOTO của từng kỳ: ${counts[number]} nháy.`,
  ];
  const expectedStep = `Mốc cho mỗi số là 27/100 × ${rows.length} kỳ = ` +
    `${expected.toLocaleString("vi-VN", {maximumFractionDigits: 2})} nháy; đây là kỳ vọng số nháy.`;
  const ganSteps = (number) => [
    `Dùng toàn bộ lịch sử: ${scope(DRAWS)}, đến kỳ mới nhất đã có kết quả.`,
    "Bộ lọc ngày và thứ không áp dụng cho gan Đặc Biệt.",
    s.last[number] < 0
      ? `Số ${pad2(number)} chưa từng là hai số cuối giải Đặc Biệt; gan bằng ${s.current[number]} kỳ của toàn lịch sử.`
      : `Số ${pad2(number)} về Đặc Biệt gần nhất ngày ${viDate(DRAWS[s.last[number]].d)}. ` +
        `Đếm các kỳ sau lần ấy đến kỳ mới nhất: ${s.current[number]} kỳ gan.`,
  ];
  const cycleSteps = (number) => [
    `Dùng toàn bộ lịch sử: ${scope(DRAWS)}, đến kỳ mới nhất đã có kết quả.`,
    "Bộ lọc ngày và thứ không áp dụng cho chu kỳ Đặc Biệt.",
    s.maxGap[number]
      ? `Lấy khoảng cách lớn nhất theo kỳ giữa hai lần số ${pad2(number)} về Đặc Biệt liên tiếp: ${s.maxGap[number]} kỳ.`
      : `Số ${pad2(number)} chưa đủ hai lần về Đặc Biệt để có chu kỳ đã ghi nhận; hiển thị dấu gạch.`,
  ];
  const rangeId = define("overview-range", "Số kỳ trong dải đang chọn", filteredSources, [
    `Áp dụng bộ lọc ngày và thứ; dải có dữ liệu là ${scope(rows)}${weekdayLabel}.`,
  ]);
  const totalId = define("overview-total", "Tổng số nháy LOTO trong dải", filteredSources, [
    `Cộng toàn bộ kết quả LOTO của ${rows.length} kỳ trong dải: ${total} nháy.`,
    "Một số xuất hiện nhiều lần trong cùng kỳ được cộng đủ từng nháy.",
  ]);
  const expectedId = define("overview-expected", "Kỳ vọng số nháy LOTO", filteredSources, [
    expectedStep, "Cột «So kỳ vọng» lấy tổng nháy của từng số chia cho mốc này.",
  ]);
  const hotId = define("overview-hottest", "Số LOTO về nhiều nhất trong dải", filteredSources, [
    "Sắp xếp 100 số theo tổng nháy giảm dần trong dải đang chọn.",
    rows.length ? `Số ${pad2(hottest)} dẫn đầu với ${counts[hottest]} nháy.` : "Dải không có kỳ nào nên không có số dẫn đầu.",
  ]);
  const coldId = define("overview-coldest", "Số Đặc Biệt gan lâu nhất trên toàn lịch sử", globalSources, [
    "So sánh số kỳ chưa xuất hiện ở hai số cuối giải Đặc Biệt của 100 số trên toàn bộ lịch sử.",
    ...ganSteps(coldest),
  ]);

  const kpi = $("sp-kpi");
  if (kpi) {
    fill(kpi, [
      ["Kỳ đang phân tích", rows.length, rows.length ? `${viDate(rows[0].d)} → ${viDate(rows.at(-1).d)}` : "Không có kỳ phù hợp", rangeId],
      ["Tổng số nháy LOTO", total.toLocaleString("vi-VN"), "Cộng đủ mọi lần xuất hiện trong dải", totalId],
      ["LOTO về nhiều nhất", rows.length ? pad2(hottest) : "—", rows.length ? `${counts[hottest]} nháy trong dải đã chọn` : "Chọn lại dải dữ liệu", hotId],
      ["Gan Đặc Biệt lâu nhất", pad2(coldest), `${s.current[coldest]} kỳ · toàn bộ lịch sử`, coldId],
    ].map((p) => mk("div", { class: "sp-kpi-card bf-kpi" }, [
      mk("span", null, p[0]),
      mk("strong", { "data-evidence": p[3], "aria-label": p[0] }, p[1]),
      mk("small", { "data-evidence-split": "1", "data-evidence-row": p[3] }, p[2]),
    ])));
  }
  const matrix = $("sp-overview-matrix");
  if (matrix) {
    fill(matrix, rows.length ? counts.map((value, number) => mk("span", {
      class: "sp-cell", title: `Số ${pad2(number)}: ${value} nháy`,
    }, [mk("b", {
      "data-evidence": define(`overview-number-${pad2(number)}`, `Định danh số LOTO ${pad2(number)}`, filteredSources,
        [`${pad2(number)} là định danh của số LOTO; số nháy của số ấy nằm ngay dưới trong cùng ô.`]),
      "aria-label": `Số LOTO ${pad2(number)}`,
    }, pad2(number)), mk("i", {
      "data-evidence": define(`overview-count-${pad2(number)}`, `Số ${pad2(number)} · Tổng nháy LOTO`, filteredSources, countSteps(number)),
      "aria-label": `Số ${pad2(number)} · Tổng nháy LOTO`,
    }, value)])) :
      mk("p", { class: "sp-empty-row" }, "Không có kỳ phù hợp với dải ngày và thứ đang chọn."));
  }
  const totalLabel = $("sp-overview-total");
  if (totalLabel) {
    totalLabel.textContent = `${total.toLocaleString("vi-VN")} nháy · ${rows.length} kỳ`;
    totalLabel.setAttribute("data-evidence-row", totalId);
  }
  const expectedLabel = $("sp-overview-expected");
  if (expectedLabel) {
    expectedLabel.textContent = rows.length
      ? `Mốc trung bình là 27/100 × ${rows.length} kỳ = ${expected.toLocaleString("vi-VN", {maximumFractionDigits: 2})} nháy cho mỗi số. Cột “So kỳ vọng” lấy tổng nháy chia cho mốc này.`
      : "Chọn dải có kết quả để tính mốc so sánh theo số kỳ thực tế.";
    expectedLabel.setAttribute("data-evidence-row", expectedId);
  }
  const head = new Array(10).fill(0), tail = new Array(10).fill(0), sums = new Array(10).fill(0);
  counts.forEach((value, number) => {
    const tens = Math.floor(number / 10), units = number % 10;
    head[tens] += value; tail[units] += value; sums[(tens + units) % 10] += value;
  });
  for (const [id, values, label] of [
    ["sp-overview-head", head, "Đầu"], ["sp-overview-tail", tail, "Đuôi"], ["sp-overview-sum", sums, "Tổng"],
  ]) {
    const el = $(id);
    if (!el) continue;
    const max = Math.max(...values, 1);
    table(el, [label, "Nháy", "Tỉ lệ", "Phân bố"], rows.length ? values.map((value, digit) => [
      digit, value, total ? (100 * value / total).toFixed(1) + "%" : "—",
      mk("span", { class: "bf-distribution-track", "aria-hidden": "true" },
        mk("i", { style: `width:${(100 * value / max).toFixed(1)}%` })),
    ]) : [], { numeric: [0, 1, 2] });
    if (rows.length) Array.from(el.tBodies[0].rows).forEach((row, digit) => {
      row.setAttribute("data-evidence-row", define(`overview-${id}-${digit}`, `${label} ${digit} · Phân bố nháy LOTO`, filteredSources, [
        `Trong ${scope(rows)}${weekdayLabel}, gom các số LOTO có ${label.toLowerCase()} ${digit}: ${values[digit]} nháy.`,
        label === "Tổng" ? "Tổng là (đầu + đuôi) chia lấy dư 10." :
          `${label} là chữ số ${label === "Đầu" ? "hàng chục" : "hàng đơn vị"} của số LOTO.`,
        `Tỉ lệ = ${values[digit]} / ${total} × 100% = ${(100 * values[digit] / total).toFixed(1)}%.`,
      ]));
      row.setAttribute("data-evidence-cols", "1,2");
    });
  }
  const order = counts.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  const body = rows.length ? order.slice(0, 40).map((p, k) => [
    k + 1, pad2(p[0]), p[1],
    expected ? (p[1] / expected).toFixed(2) + "×" : "—",
    s.current[p[0]], s.maxGap[p[0]] || "—",
  ]) : [];
  const rank = $("sp-grid");
  table(rank,
    ["Hạng", "Số", "Nháy LOTO", "So kỳ vọng", "Gan Đặc Biệt (kỳ)", "Chu kỳ Đặc Biệt dài nhất (kỳ)"],
    body, { numeric: [0, 2, 3, 4, 5], pairOf: pairCols(body, 1) });
  if (body.length) Array.from(rank.tBodies[0].rows).forEach((row, index) => {
    const number = order[index][0];
    row.setAttribute("data-evidence-row", define(`overview-rank-${pad2(number)}`, `Số ${pad2(number)} · Nháy và kỳ vọng LOTO`, filteredSources, [
      ...countSteps(number), expectedStep,
      `So kỳ vọng = ${counts[number]} / ${expected.toLocaleString("vi-VN", {maximumFractionDigits: 2})} = ${body[index][3]}.`,
    ]));
    row.setAttribute("data-evidence-cols", "2,3");
    row.cells[4].setAttribute("data-evidence-row", define(`overview-gan-${pad2(number)}`,
      `Số ${pad2(number)} · Gan Đặc Biệt trên toàn lịch sử`, globalSources, ganSteps(number)));
    row.cells[5].setAttribute("data-evidence-row", define(`overview-cycle-${pad2(number)}`,
      `Số ${pad2(number)} · Chu kỳ Đặc Biệt trên toàn lịch sử`, globalSources, cycleSteps(number)));
  });
  const block = $("sp-stat-evidence");
  if (block) fill(block, JSON.stringify(values));
  if (window.appEvidence) Object.entries(values).forEach(([id, entry]) => window.appEvidence.register(id, entry));
}

function boot(renderName) {
  const render = window[renderName];
  if (typeof render !== "function") return;

  const tomorrowPick = $("sp-tomorrow-number");
  if (tomorrowPick) {
    const number = new URLSearchParams(location.search).get("number");
    const latest = DRAWS.length ? String(DRAWS[DRAWS.length - 1].s).slice(-2) : "00";
    tomorrowPick.value = number !== null && /^\d{1,2}$/.test(number) ? pad2(Number(number)) : latest;
    tomorrowPick.addEventListener("change", () => {
      const url = new URL(location.href);
      url.searchParams.set("number", tomorrowPick.value);
      history.replaceState(null, "", url);
      render();
    });
    $("sp-tomorrow-latest").addEventListener("click", () => {
      tomorrowPick.value = latest;
      tomorrowPick.dispatchEvent(new Event("change"));
    });
  }

  const from = $("sp-from"), to = $("sp-to");
  if (from && to && DRAWS.length) {
    from.min = to.min = DRAWS[0].d;
    from.max = to.max = DRAWS[DRAWS.length - 1].d;
    from.value = DRAWS[Math.max(0, DRAWS.length - 90)].d;
    to.value = DRAWS[DRAWS.length - 1].d;
  }
  const ganPick = $("sp-gan-pick");
  if (ganPick) {
    ganPick.addEventListener("change", () => {
      if (ganPick.value) { openGanPopup(ganPick.value); ganPick.value = ""; }
    });
  }

  const quick = $("sp-quick");
  if (quick) {
    quick.addEventListener("click", (ev) => {
      const days = ev.target.dataset.days;
      if (!days) return;
      const latest = DRAWS.length ? DRAWS[DRAWS.length - 1].d : "";
      if (!latest) return;
      const [y, m, d] = latest.split("-").map(Number);
      const start = new Date(Date.UTC(y, m - 1, d));
      start.setUTCDate(start.getUTCDate() - (Number(days) - 1));
      if (from) from.value = start.toISOString().slice(0, 10);
      if (to) to.value = latest;
      render();
    });
  }

  [from, to, $("sp-year"), $("sp-month"), $("sp-mode"), $("sp-orient"), $("sp-weekday"),
   $("sp-sort")].forEach(
    (el) => el && el.addEventListener("change", render));

  document.querySelectorAll(".sp-chips .sp-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sp-chips .sp-chip").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      const days = parseInt(btn.dataset.days, 10);
      if (from && to && DRAWS.length) {
        to.value = DRAWS[DRAWS.length - 1].d;
        from.value = days ? DRAWS[Math.max(0, DRAWS.length - days)].d : DRAWS[0].d;
      }
      render();
    });
  });
  bindMarking();
  bindGanPopup(render);
  bindColumnHint();
  renderLegend();
  bindFieldToggles(render);
  bindPicker(render);
  render();
}

function renderSpecialBridge() {
  const rows = selected();
  setCount(rows);

  const count = new Array(100).fill(0);
  rows.forEach((r) => { count[parseInt(lastTwo(r.s), 10)] += 1; });

  const head = ["Đầu / Đuôi"].concat(Array.from({ length: 10 }, (_, d) => `Đuôi ${d}`));
  const body = Array.from({ length: 10 }, (_, tens) =>
    [mk("b", null, `Đầu ${tens}`)].concat(Array.from({ length: 10 }, (_, ones) => {
      const n = tens * 10 + ones;
      return count[n]
        ? [mk("b", null, pad2(n)), mk("i", { class: "sp-times" }, `${count[n]} lần`)]
        : [mk("span", { class: "sp-none" }, pad2(n)), mk("i", {class: "sp-times"}, "0 lần")];
    })));
  table($("sp-grid"), head, body,
    { pairOf: (y, i) => (i === 0 ? null : pad2(y * 10 + (i - 1))) });
  $("sp-grid").prepend(mk("colgroup", null, [12,...Array(10).fill(8.8)].map(width => mk("col", {style: `width:${width}%`}))));
  const maximum = Math.max(0, ...count);
  Array.from($("sp-grid").tBodies[0].rows).forEach((row, tens) => {
    for (let ones = 0; ones < 10; ones++) {
      const number = tens * 10 + ones;
      specialMetricCell(row.cells[ones + 1], count[number], maximum, "frequency", `Số ${pad2(number)}`, "lần");
    }
  });
  specialMetricLegend("app-special-frequency-legend", "frequency", maximum, "lần");

  const lon = $("sp-lon");
  if (lon) {
    const pairs = reversePairs()
      .map(([a, b]) => [a, b, count[a] + count[b]])
      .filter((p) => p[2] > 0)
      .sort((x, y) => y[2] - x[2]);
    const lonBody = pairs.map((p, k) => [k + 1, `${pad2(p[0])} - ${pad2(p[1])}`, p[2]]);
    table(lon, ["Hạng", "Cặp lộn", "Số lần xuất hiện"], lonBody,
      { numeric: [0, 2], pairOf: pairCols(lonBody, 1),
        key: (y, i) => `special-reverse|pair${pad2(pairs[y][0])}-${pad2(pairs[y][1])}|field${i}` });
    const pairMaximum = Math.max(0, ...pairs.map(pair => pair[2]));
    pairs.forEach((pair, index) => specialMetricCell(lon.tBodies[0].rows[index].cells[2], pair[2], pairMaximum,
      "frequency", `Cặp ${pad2(pair[0])} - ${pad2(pair[1])}`, "lần"));
    specialMetricLegend("app-special-reverse-legend", "frequency", pairMaximum, "lần");
  }

  const recent = $("sp-recent");
  if (recent) {
    const last = DRAWS.slice(-3).reverse();
    fill(recent, last.map((r) => mk("div", { class: "sp-draw" }, [
      mk("h4", null,
        `Kết quả ngày ${r.d.slice(8)}-${r.d.slice(5, 7)}-${r.d.slice(0, 4)}`),
      mk("p", { class: "sp-db" }, ["Đặc Biệt ", mk("b", null, String(r.s).padStart(5, "0"))]),
      mk("div", { class: "sp-lolist" },
        r.n.map((x) => mk("span", { class: "sp-lo" }, x))),
    ])));
  }
}

function tongOf(special) {
  const two = lastTwo(special);
  return (+two[0] + +two[1]) % 10;
}

function renderSpecialByTong() {
  const rows = selected();
  setCount(rows);
  const fitColumns = () => Object.entries({
    "sp-grid": [20,32,24,24],
    "sp-parity": [20,20,30,30],
    "sp-trans": [18,18,14,18,16,16],
  }).forEach(([id, widths]) => $(id).prepend(mk("colgroup", null,
    widths.map(width => mk("col", {style: `width:${width}%`})))));
  if (!rows.length) {
    table($("sp-grid"), ["Tổng", "Ngày ra gần nhất", "Số kỳ chưa về", "Tổng số lần"], []);
    table($("sp-trans"), ["Tổng hôm trước", "Tổng hôm sau", "Số lần",
      "Trên tổng số kỳ", "Tỉ lệ", "Lệch chuẩn hoá"], []);
    table($("sp-parity"), ["Tổng hôm trước", "Số kỳ", "Hôm sau tổng chẵn",
      "Hôm sau tổng lẻ"], []);
    fitColumns();
    specialMetricLegend("app-special-gap-legend", "gap", 0, "kỳ");
    specialMetricLegend("app-special-total-frequency-legend", "frequency", 0, "lần");
    specialMetricLegend("app-special-transition-legend", "frequency", 0, "lần");
    return;
  }

  const lastSeen = new Array(10).fill(-1);
  const hits = new Array(10).fill(0);
  rows.forEach((r, i) => { const t = tongOf(r.s); lastSeen[t] = i; hits[t] += 1; });
  const gan = Array.from({ length: 10 }, (_, t) => [
    t,
    lastSeen[t] < 0 ? "—" : rows[lastSeen[t]].d,
    lastSeen[t] < 0 ? rows.length : rows.length - 1 - lastSeen[t],
    hits[t],
  ]).sort((a, b) => b[2] - a[2]);
  table($("sp-grid"), ["Tổng", "Ngày ra gần nhất", "Số kỳ chưa về", "Tổng số lần"],
    gan.map((g) => [mk("b", null, g[0]), g[1], g[2], g[3]]), { numeric: [0, 2, 3] });
  const gapMaximum = Math.max(0, ...gan.map(row => row[2]));
  const countMaximum = Math.max(0, ...hits);
  gan.forEach((row, index) => {
    const cells = $("sp-grid").tBodies[0].rows[index].cells;
    specialMetricCell(cells[2], row[2], gapMaximum, "gap", `Tổng ${row[0]} · Chưa về`, "kỳ");
    specialMetricCell(cells[3], row[3], countMaximum, "frequency", `Tổng ${row[0]} · Xuất hiện`, "lần");
  });
  specialMetricLegend("app-special-gap-legend", "gap", gapMaximum, "kỳ");
  specialMetricLegend("app-special-total-frequency-legend", "frequency", countMaximum, "lần");

  const trans = Array.from({ length: 10 }, () => new Array(10).fill(0));
  const fromTotal = new Array(10).fill(0);
  for (let i = 1; i < rows.length; i++) {
    const gap = (new Date(rows[i].d) - new Date(rows[i - 1].d)) / 86400000;
    if (gap !== 1) continue;
    const a = tongOf(rows[i - 1].s), b = tongOf(rows[i].s);
    trans[a][b] += 1; fromTotal[a] += 1;
  }

  const P0 = 0.1;
  const flat = [];
  for (let a = 0; a < 10; a++) {
    if (!fromTotal[a]) continue;
    for (let b = 0; b < 10; b++) {
      const n = fromTotal[a];
      const pct = 100 * trans[a][b] / n;
      const se = Math.sqrt(P0 * (1 - P0) / n) * 100;
      flat.push([a, b, trans[a][b], n, pct, se ? (pct - 10) / se : 0]);
    }
  }
  flat.sort((x, y) => Math.abs(y[5]) - Math.abs(x[5]));

  const tr = $("sp-trans");
  if (tr) {
    table(tr,
      ["Tổng hôm trước", "Tổng hôm sau", "Số lần", "Trên tổng số kỳ", "Tỉ lệ", "Lệch chuẩn hoá"],
      flat.slice(0, 40).map((f) => [
        mk("b", null, f[0]), mk("b", null, f[1]), f[2], f[3],
        f[4].toFixed(2).replace(".", ",") + " %",
        (f[5] > 0 ? "+" : "") + f[5].toFixed(2).replace(".", ","),
      ]), { numeric: [0, 1, 2, 3, 4, 5] });
    const shown = flat.slice(0, 40);
    const maximum = Math.max(0, ...shown.map(row => row[2]));
    shown.forEach((row, index) => specialMetricCell(tr.tBodies[0].rows[index].cells[2],
      row[2], maximum, "frequency", `Tổng ${row[0]} → ${row[1]}`, "lần"));
    specialMetricLegend("app-special-transition-legend", "frequency", maximum, "lần");
  }

  const par = $("sp-parity");
  if (par) {
    const body = [];
    for (let a = 0; a < 10; a++) {
      if (!fromTotal[a]) continue;
      let even = 0;
      for (let b = 0; b < 10; b += 2) even += trans[a][b];
      const pct = 100 * even / fromTotal[a];
      body.push([mk("b", null, a), fromTotal[a],
        pct.toFixed(2).replace(".", ",") + " %",
        (100 - pct).toFixed(2).replace(".", ",") + " %"]);
    }
    table(par, ["Tổng hôm trước", "Số kỳ", "Hôm sau tổng chẵn", "Hôm sau tổng lẻ"],
      body, { numeric: [0, 1, 2, 3] });
    Array.from(par.tBodies[0].rows).filter(row => row.cells.length === 4).forEach(row => {
      for (const [column, parity] of [[2, "even"], [3, "odd"]]) {
        row.cells[column].dataset.statParity = parity;
        row.cells[column].classList.add(`app-stat-parity-${parity}`);
      }
    });
  }
  fitColumns();
}
