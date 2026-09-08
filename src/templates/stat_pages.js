// Bộ máy thống kê chạy phía trình duyệt.
// Toàn bộ lịch sử được nhúng vào trang nên mọi bộ lọc là tức thì, không gọi
// mạng. Xem docstring của src/build_stat_pages.py để biết vì sao.
"use strict";
const DRAWS = window.__VLA_DRAWS__ || [];
const LOTO_BASELINE = 1 - Math.pow(0.99, 27);
const PAIR_BASELINE = 1 - 2 * Math.pow(0.99, 27) + Math.pow(0.98, 27);

// Mốc "cực đại do ngẫu nhiên" của 4950 cặp, tra theo số kỳ ĐANG CHỌN.
//
// Mốc này tăng theo độ dài lịch sử: 7,7 ở 30 kỳ, 39,9 ở 393, 177,2 ở 2442.
// Ghi chú cố định một con số là sai ngay khi người dùng bấm bộ lọc — chọn
// "30 kỳ" mà vẫn đọc mốc của toàn bộ lịch sử thì lệch tới 25 lần, và bảng
// tuyên bố "bất thường" cho dữ liệu hoàn toàn ngẫu nhiên.
//
// Công thức đóng cần hàm phân phối nhị thức, quá nặng để tính lại trong
// trình duyệt mỗi lần lọc. Thay vào đó dựng sẵn một lưới và nội suy tuyến
// tính: 22 điểm cho sai số tối đa 0,67% (dưới 0,15% với mọi N >= 30).
const PAIR_CHANCE_GRID = window.__VLA_PAIR_CHANCE__ || [];

/** Cực đại ngẫu nhiên và khoảng 90% cho ``n`` kỳ; null nếu chưa có lưới. */
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

/** Viết lại ghi chú mốc ngẫu nhiên theo số kỳ đang chọn. */
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

/** Các kỳ nằm trong dải đang chọn. */
function selected() {
  const from = $("sp-from") && $("sp-from").value;
  const to = $("sp-to") && $("sp-to").value;
  let rows = DRAWS;
  if (from) rows = rows.filter((r) => r.d >= from);
  if (to) rows = rows.filter((r) => r.d <= to);
  return rows;
}

function setCount(rows) {
  const el = $("sp-count");
  if (!el) return;
  const first = rows.length ? rows[0].d : "—";
  const last = rows.length ? rows[rows.length - 1].d : "—";
  el.textContent = `${rows.length} kỳ · ${first} → ${last}`;
}

/** Giải đặc biệt ĐỦ 5 CHỮ SỐ, nhấn hai số cuối.
 *
 * Trang gốc liệt kê trọn giải đặc biệt chứ không chỉ hai số cuối. Dữ liệu
 * nhúng vốn đã giữ đủ 5 chữ số; bản trước cắt bớt ngay lúc dựng bảng nên
 * người đọc mất phần đầu và không đối chiếu được với kết quả gốc.
 */
function specialFull(value) {
  const s = String(value).padStart(5, "0");
  return `<span class="sp-de">${s.slice(0, 3)}<b>${s.slice(3)}</b></span>`;
}

/** Hai số cuối, dùng cho phép ĐẾM chứ không phải để hiển thị. */
function lastTwo(value) {
  return String(value).padStart(5, "0").slice(-2);
}

/** Dựng bảng từ tiêu đề và các hàng. */
function table(el, headers, rows, opts) {
  opts = opts || {};
  const thead = "<thead><tr>" + headers.map((h) => `<th>${h}</th>`).join("") + "</tr></thead>";
  const body = rows.map((r, y) =>
    "<tr>" + r.map((c, i) => {
      const cls = opts.numeric && opts.numeric.includes(i) ? " num" : "";
      const key = `${el.id}:${y}:${i}`;
      const on = MARKS.has(key) ? " marked" : "";
      const style = opts.style && opts.style(y, i) ? ` style="${opts.style(y, i)}"` : "";
      return `<td class="cell${cls}${on}" data-key="${key}"${style}>${c}</td>`;
    }).join("") + "</tr>"
  ).join("");
  el.innerHTML = thead + "<tbody>" + body + "</tbody>";
}

// --- Tô sáng ô để so sánh ---------------------------------------------------
//
// Các bảng này dài hàng chục hàng và người đọc thường muốn dõi theo vài ô rời
// rạc — chẳng hạn cùng một ngày qua nhiều tháng. Không có cách đánh dấu thì họ
// phải nhớ bằng mắt, và chỉ cần cuộn một cái là mất dấu.
//
// Lưu theo từng máy bằng localStorage: đây là tiện ích cá nhân, không phải dữ
// liệu chung. Bọc try/catch vì cửa sổ ẩn danh và trình duyệt chặn lưu trữ sẽ
// ném lỗi ngay ở lệnh đọc, và một trang trắng thì tệ hơn hẳn việc mất dấu.
const MARK_KEY = "vla.marks." + (location.pathname.split("/").pop() || "index");
let MARKS = new Set();
try {
  MARKS = new Set(JSON.parse(localStorage.getItem(MARK_KEY) || "[]"));
} catch (e) { MARKS = new Set(); }

function saveMarks() {
  try { localStorage.setItem(MARK_KEY, JSON.stringify(Array.from(MARKS))); } catch (e) {}
}

function bindMarking() {
  document.addEventListener("click", (ev) => {
    const td = ev.target.closest("td.cell");
    if (!td || !td.dataset.key) return;
    const key = td.dataset.key;
    if (MARKS.has(key)) { MARKS.delete(key); td.classList.remove("marked"); }
    else { MARKS.add(key); td.classList.add("marked"); }
    saveMarks();
    updateMarkCount();
  });

  const clear = $("sp-clear-marks");
  if (clear) {
    clear.addEventListener("click", () => {
      MARKS.clear();
      saveMarks();
      document.querySelectorAll("td.marked").forEach((td) => td.classList.remove("marked"));
      updateMarkCount();
    });
  }
  updateMarkCount();
}

function updateMarkCount() {
  const el = $("sp-mark-count");
  if (el) el.textContent = MARKS.size ? `${MARKS.size} ô đang đánh dấu` : "";
}

/** Màu nền heat-map: 0 = nhạt nhất, 1 = đậm nhất. */
function heat(value, max) {
  if (!max) return "";
  const t = Math.min(1, value / max);
  // Dừng ở 0.55 để chữ tối luôn còn tương phản trên nền.
  return `background:rgba(124,58,237,${(t * 0.55).toFixed(3)})`;
}

function countLoto(rows) {
  const c = new Array(100).fill(0);
  rows.forEach((r) => r.n.forEach((x) => { c[parseInt(x, 10)] += 1; }));
  return c;
}

// --- Từng trang ------------------------------------------------------------

function renderLotoFrequency() {
  const rows = selected();
  setCount(rows);
  const counts = countLoto(rows);
  const expected = LOTO_BASELINE * rows.length;
  const max = Math.max(...counts, 1);

  const m = $("sp-matrix");
  if (m) {
    m.innerHTML = counts.map((v, i) =>
      `<span class="sp-cell" style="${heat(v, max)}" title="Số ${pad2(i)}: ${v} lần">` +
      `<b>${pad2(i)}</b><i>${v}</i></span>`
    ).join("");
  }
  const order = counts.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Hạng", "Số", "Số lần về", "Kỳ vọng", "So kỳ vọng"],
    order.map((p, k) => [
      k + 1, pad2(p[0]), p[1], expected.toFixed(1),
      expected ? (p[1] / expected).toFixed(2) + "×" : "—",
    ]), { numeric: [0, 2, 3, 4] });
}

// --- Số lộn -----------------------------------------------------------------
//
// "Lộn" là đảo hai chữ số: 01 <-> 10, 27 <-> 72. Chỉ có 45 cặp như vậy, vì
// 10 số kép (00, 11, ... 99) đảo lại chính nó nên KHÔNG có số lộn.
//
// Kho từng gộp 10 số kép thành 5 họ "kép bóng" (00-55, 11-66, 22-77, 33-88,
// 44-99) cho tròn 50 cặp. Nhưng BÓNG (0<->5, 1<->6, ...) là khái niệm khác hẳn
// LỘN, nên bảng cũ trộn hai thứ và gọi chung là cặp lộn. Ở đây tách bạch: 45
// cặp lộn thật, còn số kép liệt kê riêng đúng bản chất của nó.

/** 45 cặp lộn thật, dạng [a, b] với a < b và b là a đảo chữ số. */
function reversePairs() {
  const out = [];
  for (let a = 0; a < 100; a++) {
    const b = (a % 10) * 10 + Math.floor(a / 10);
    if (a < b) out.push([a, b]);
  }
  return out;   // đúng 45 cặp
}

/** 10 số kép: đảo lại chính nó. */
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

  table($("sp-grid"),
    ["Hạng", "Cặp lộn", "Về của số đầu", "Về của số lộn", "Tổng", "Lệch"],
    pairs.map((p, k) => [
      k + 1,
      `${pad2(p[0])} ↔ ${pad2(p[1])}`,
      p[2], p[3], p[4],
      // Lệch giữa hai chiều: cặp lộn "cân" thì gần 0. Cột này mới là thứ đáng
      // nhìn, vì tổng chỉ nói cặp đó gồm hai con hay về, không nói gì về LỘN.
      (p[2] - p[3] > 0 ? "+" : "") + (p[2] - p[3]),
    ]), { numeric: [0, 2, 3, 4, 5] });

  const kep = $("sp-kep");
  if (kep) {
    const ds = doubleNumbers().map((n) => [pad2(n), c[n]]).sort((a, b) => b[1] - a[1]);
    table(kep, ["Số kép", "Số lần về"],
      ds.map((d) => [d[0], d[1]]), { numeric: [1] });
  }
}

function renderPairFrequency() {
  const rows = selected();
  setCount(rows);
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
  table($("sp-grid"),
    ["Hạng", "Cặp số", "Số lần cùng về", "Kỳ vọng", "So kỳ vọng"],
    top.map((p, k) => [
      k + 1, p[0], p[1], expected.toFixed(1),
      expected ? (p[1] / expected).toFixed(2) + "×" : "—",
    ]), { numeric: [0, 2, 3, 4] });
}

function renderHeadTail() {
  const rows = selected();
  setCount(rows);
  const head = new Array(10).fill(0);
  const tail = new Array(10).fill(0);
  rows.forEach((r) => r.n.forEach((x) => {
    head[parseInt(x[0], 10)] += 1;
    tail[parseInt(x[1], 10)] += 1;
  }));
  const total = rows.length * 27;
  const build = (el, counts, label) => {
    const max = Math.max(...counts, 1);
    table(el, [label, "Số lần", "Tỉ lệ", ""],
      counts.map((v, i) => [
        i, v, total ? ((v / total) * 100).toFixed(2) + "%" : "—",
        `<span class="sp-bar" style="width:${(100 * v / max).toFixed(1)}%"></span>`,
      ]), { numeric: [0, 1, 2] });
  };
  build($("sp-head"), head, "Chữ số đầu");
  build($("sp-tail"), tail, "Chữ số đuôi");
}

function specialGaps() {
  // Số kỳ chưa về, và chu kỳ dài nhất trong lịch sử, cho từng con 00-99.
  const last = new Array(100).fill(-1);
  const maxGap = new Array(100).fill(0);
  const hits = new Array(100).fill(0);
  DRAWS.forEach((r, t) => {
    const k = parseInt(lastTwo(r.s), 10);
    hits[k] += 1;
    if (last[k] >= 0) maxGap[k] = Math.max(maxGap[k], t - last[k]);
    last[k] = t;
  });
  const n = DRAWS.length;
  return { last, maxGap, hits, current: last.map((t) => (t < 0 ? n : n - 1 - t)), n };
}

function renderSpecialCycle() {
  const s = specialGaps();
  setCount(DRAWS);
  const order = s.current.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Hạng", "Số", "Chưa về (kỳ)", "Chu kỳ dài nhất", "Tổng lần về"],
    order.map((p, k) => [k + 1, pad2(p[0]), p[1], s.maxGap[p[0]] || "—", s.hits[p[0]]]),
    { numeric: [0, 2, 3, 4] });
}

function renderSpecialBySet() {
  const s = specialGaps();
  setCount(DRAWS);
  const rows = [];
  for (let i = 0; i < 100; i++) {
    const lastDate = s.last[i] >= 0 ? DRAWS[s.last[i]].d : "chưa từng";
    rows.push([pad2(i), lastDate, s.current[i], s.maxGap[i] || "—", s.hits[i]]);
  }
  rows.sort((a, b) => b[2] - a[2]);
  table($("sp-grid"),
    ["Bộ số", "Về gần nhất", "Chưa về (kỳ)", "Chu kỳ dài nhất", "Tổng lần về"],
    rows, { numeric: [2, 3, 4] });
}

function renderTomorrow() {
  const s = specialGaps();
  setCount(DRAWS);
  // Điểm tham khảo: số kỳ chưa về chuẩn hoá theo chu kỳ dài nhất của chính
  // con đó. Đây là mô tả lịch sử, KHÔNG phải xác suất đã hiệu chuẩn.
  const scored = [];
  for (let i = 0; i < 100; i++) {
    const ceiling = Math.max(s.maxGap[i], 1);
    scored.push([i, s.current[i] / ceiling, s.current[i], s.maxGap[i]]);
  }
  scored.sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Hạng", "Số", "Chưa về / chu kỳ dài nhất", "Chưa về", "Chu kỳ dài nhất"],
    scored.slice(0, 30).map((p, k) => [
      k + 1, pad2(p[0]), p[1].toFixed(2), p[2], p[3] || "—",
    ]), { numeric: [0, 2, 3, 4] });
}

function renderSpecialByDay() {
  const sel = $("sp-year");
  const years = Array.from(new Set(DRAWS.map((r) => r.d.slice(0, 4)))).sort();
  if (sel && !sel.options.length) {
    sel.innerHTML = years.map((y) => `<option>${y}</option>`).join("");
    sel.value = years[years.length - 1];
  }
  const year = sel ? sel.value : years[years.length - 1];
  const rows = DRAWS.filter((r) => r.d.slice(0, 4) === year);
  setCount(rows);
  const cell = {};
  rows.forEach((r) => { cell[r.d.slice(5)] = r.s; });

  const head = ["Ngày"].concat(Array.from({ length: 12 }, (_, m) => "T" + (m + 1)));
  const body = [];
  for (let day = 1; day <= 31; day++) {
    const line = [String(day)];
    for (let m = 1; m <= 12; m++) {
      const v = cell[`${pad2(m)}-${pad2(day)}`];
      line.push(v ? specialFull(v) : "");
    }
    body.push(line);
  }
  table($("sp-grid"), head, body);
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

// Khai báo bằng `function`, KHÔNG dùng `const`: boot() tra hàm qua
// window[renderName], mà `const` ở cấp cao nhất của script cổ điển không tạo
// thuộc tính trên window. Dùng const thì hai trang này im lặng không vẽ gì.
// --- Bảng đặc biệt theo THÁNG: lịch theo tuần ------------------------------
//
// Trang gốc liệt kê trọn giải đặc biệt của từng ngày, không phải bảng thống
// kê tổng hợp. Xếp theo lịch tuần (hàng = tuần, cột = thứ) vì người soi cầu
// đối chiếu theo thứ trong tuần, và dạng này cho thấy ngay ngày nào khuyết.

const WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"];

/** Chỉ số thứ trong tuần, 0 = Thứ 2 (không phải Chủ nhật như getDay). */
function mondayIndex(iso) {
  return (new Date(iso + "T00:00:00Z").getUTCDay() + 6) % 7;
}

function fillPicker(id, values) {
  const sel = $(id);
  if (!sel) return null;
  if (!sel.options.length) {
    sel.innerHTML = values.map((v) => `<option>${v}</option>`).join("");
    sel.value = values[values.length - 1];
  }
  return sel.value;
}

function renderSpecialByMonth() {
  const months = Array.from(new Set(DRAWS.map((r) => r.d.slice(0, 7)))).sort();
  const month = fillPicker("sp-month", months) || months[months.length - 1];
  const rows = DRAWS.filter((r) => r.d.slice(0, 7) === month);
  setCount(rows);

  const byDate = {};
  rows.forEach((r) => { byDate[r.d] = r.s; });

  const [y, m] = month.split("-").map(Number);
  const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();

  const body = [];
  let week = new Array(7).fill("");
  for (let day = 1; day <= daysInMonth; day++) {
    const iso = `${month}-${pad2(day)}`;
    const idx = mondayIndex(iso);
    const de = byDate[iso];
    week[idx] = `<span class="sp-daynum">${day}</span>` +
      (de ? specialFull(de) : '<span class="sp-none">—</span>');
    if (idx === 6 || day === daysInMonth) {
      body.push(week.slice());
      week = new Array(7).fill("");
    }
  }
  table($("sp-grid"), WEEKDAYS, body);
}

// --- Bảng đặc biệt theo NĂM: liệt kê theo tháng ----------------------------

function renderSpecialByYear() {
  const years = Array.from(new Set(DRAWS.map((r) => r.d.slice(0, 4)))).sort();
  const year = fillPicker("sp-year", years) || years[years.length - 1];
  const rows = DRAWS.filter((r) => r.d.slice(0, 4) === year);
  setCount(rows);

  const byDate = {};
  rows.forEach((r) => { byDate[r.d] = r.s; });

  // Hàng = ngày 1..31, cột = 12 tháng. Mỗi ô là TRỌN giải đặc biệt.
  const head = ["Ngày"].concat(Array.from({ length: 12 }, (_, m) => "Tháng " + (m + 1)));
  const body = [];
  for (let day = 1; day <= 31; day++) {
    const line = [`<b>${day}</b>`];
    for (let m = 1; m <= 12; m++) {
      const de = byDate[`${year}-${pad2(m)}-${pad2(day)}`];
      line.push(de ? specialFull(de) : "");
    }
    body.push(line);
  }
  table($("sp-grid"), head, body);
}

function renderOverview() {
  const rows = selected();
  setCount(rows);
  const counts = countLoto(rows);
  const expected = LOTO_BASELINE * rows.length;
  const s = specialGaps();
  const hottest = counts.indexOf(Math.max(...counts));
  const coldest = s.current.indexOf(Math.max(...s.current));

  const kpi = $("sp-kpi");
  if (kpi) {
    kpi.innerHTML = [
      ["Số kỳ trong dải", rows.length],
      ["Kỳ vọng mỗi con", expected.toFixed(1) + " lần"],
      ["Về nhiều nhất", pad2(hottest) + " (" + counts[hottest] + ")"],
      ["Gan ĐB lâu nhất", pad2(coldest) + " (" + s.current[coldest] + " kỳ)"],
    ].map((p) => `<div class="sp-kpi-card"><span>${p[0]}</span><strong>${p[1]}</strong></div>`).join("");
  }
  const order = counts.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Hạng", "Số", "Lần về", "So kỳ vọng", "Gan ĐB (kỳ)", "Chu kỳ ĐB dài nhất"],
    order.slice(0, 40).map((p, k) => [
      k + 1, pad2(p[0]), p[1],
      expected ? (p[1] / expected).toFixed(2) + "×" : "—",
      s.current[p[0]], s.maxGap[p[0]] || "—",
    ]), { numeric: [0, 2, 3, 4, 5] });
}

// --- Khởi động -------------------------------------------------------------

function boot(renderName) {
  const render = window[renderName];
  if (typeof render !== "function") return;

  const from = $("sp-from"), to = $("sp-to");
  if (from && to && DRAWS.length) {
    from.min = to.min = DRAWS[0].d;
    from.max = to.max = DRAWS[DRAWS.length - 1].d;
    from.value = DRAWS[Math.max(0, DRAWS.length - 90)].d;
    to.value = DRAWS[DRAWS.length - 1].d;
  }
  [from, to, $("sp-year"), $("sp-month")].forEach(
    (el) => el && el.addEventListener("change", render));

  document.querySelectorAll(".sp-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sp-chip").forEach((b) => b.classList.remove("on"));
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
  render();
}
