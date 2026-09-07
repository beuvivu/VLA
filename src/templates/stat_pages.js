// Bộ máy thống kê chạy phía trình duyệt.
// Toàn bộ lịch sử được nhúng vào trang nên mọi bộ lọc là tức thì, không gọi
// mạng. Xem docstring của src/build_stat_pages.py để biết vì sao.
"use strict";
const DRAWS = window.__VLA_DRAWS__ || [];
const LOTO_BASELINE = 1 - Math.pow(0.99, 27);
const PAIR_BASELINE = 1 - 2 * Math.pow(0.99, 27) + Math.pow(0.98, 27);

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

/** Dựng bảng từ tiêu đề và các hàng. */
function table(el, headers, rows, opts) {
  opts = opts || {};
  const thead = "<thead><tr>" + headers.map((h) => `<th>${h}</th>`).join("") + "</tr></thead>";
  const body = rows.map((r) =>
    "<tr>" + r.map((c, i) => {
      const cls = opts.numeric && opts.numeric.includes(i) ? ' class="num"' : "";
      return `<td${cls}>${c}</td>`;
    }).join("") + "</tr>"
  ).join("");
  el.innerHTML = thead + "<tbody>" + body + "</tbody>";
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

function renderPairFrequency() {
  const rows = selected();
  setCount(rows);
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
    const k = parseInt(r.s.slice(-2), 10);
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
  rows.forEach((r) => { cell[r.d.slice(5)] = r.s.slice(-2); });

  const head = ["Ngày"].concat(Array.from({ length: 12 }, (_, m) => "T" + (m + 1)));
  const body = [];
  for (let day = 1; day <= 31; day++) {
    const line = [String(day)];
    for (let m = 1; m <= 12; m++) {
      const v = cell[`${pad2(m)}-${pad2(day)}`];
      line.push(v ? `<b>${v}</b>` : "");
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
    groups.get(k)[parseInt(r.s.slice(-2), 10)] += 1;
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
function renderSpecialByMonth() { groupSpecial((d) => d.slice(0, 7), "Tháng"); }
function renderSpecialByYear() { groupSpecial((d) => d.slice(0, 4), "Năm"); }

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
  [from, to, $("sp-year")].forEach((el) => el && el.addEventListener("change", render));

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
  render();
}
