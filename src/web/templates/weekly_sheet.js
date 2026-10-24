(() => {
  "use strict";

  // Tạo phôi tuần: bảng giải Đặc Biệt theo tuần (Thứ Hai → Chủ Nhật), tách 3 chữ
  // số đầu và 2 chữ số cuối, cỡ chữ và màu do người xem chọn rồi in.
  // Dựng DOM bằng createElement + textContent; màu và cỡ chữ đặt qua CSSOM.

  const DATA = document.getElementById("app-phoi-data");
  if (!DATA) return;
  const SPECIALS = JSON.parse(DATA.textContent).specials;
  const DAYS = ["Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật"];
  const COLOR = /^#[0-9a-f]{6}$/i;

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const dayIndex = (iso) => (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7;
  const mondayOf = (iso) => {
    const t = new Date(`${iso}T00:00:00Z`);
    t.setUTCDate(t.getUTCDate() - dayIndex(iso));
    return t.toISOString().slice(0, 10);
  };

  /** Các tuần (theo Thứ Hai), cũ trước; mỗi tuần 7 ô, ô trống khi kỳ ấy chưa có. */
  function weeks(specials, count) {
    const byWeek = new Map();
    for (const [date, value] of specials) {
      const key = mondayOf(date);
      if (!byWeek.has(key)) byWeek.set(key, new Array(7).fill(null));
      byWeek.get(key)[dayIndex(date)] = { date, value };
    }
    return [...byWeek.entries()].sort((u, v) => (u[0] < v[0] ? -1 : 1)).slice(-count);
  }

  function clamp(raw, lo, hi, fallback) {
    const n = Number.parseInt(raw, 10);
    return Number.isInteger(n) ? Math.min(hi, Math.max(lo, n)) : fallback;
  }

  function readForm(form) {
    return {
      count: clamp(form.elements.count.value, 5, 80, 50),
      headsize: clamp(form.elements.headsize.value, 15, 35, 20),
      tailsize: clamp(form.elements.tailsize.value, 15, 35, 20),
      bg: COLOR.test(form.elements.bgcolour.value) ? form.elements.bgcolour.value : "#ffffff",
      head: COLOR.test(form.elements.headcolour.value) ? form.elements.headcolour.value : "#000000",
      tail: COLOR.test(form.elements.tailcolour.value) ? form.elements.tailcolour.value : "#d11a1a",
    };
  }

  function render(host, options) {
    const table = el("table", "app-phoi");
    table.style.backgroundColor = options.bg;
    const thead = el("thead");
    const headRow = el("tr");
    for (const label of ["Tuần", ...DAYS]) {
      const th = el("th", "", label);
      th.scope = "col";
      headRow.append(th);
    }
    thead.append(headRow);
    table.append(thead);
    const body = el("tbody");
    const list = weeks(SPECIALS, options.count);
    list.forEach(([monday, cells], i) => {
      const row = el("tr");
      const no = el("th", "", String(list.length - i));
      no.scope = "row";
      no.title = `Tuần bắt đầu ${monday.split("-").reverse().join("/")}`;
      row.append(no);
      for (const cell of cells) {
        const td = el("td", "app-phoi-cell");
        if (cell) {
          td.title = cell.date.split("-").reverse().join("/");
          const head = el("span", "app-phoi-head", cell.value.slice(0, 3));
          head.style.fontSize = `${options.headsize}px`;
          head.style.color = options.head;
          const tail = el("span", "app-phoi-tail", cell.value.slice(3));
          tail.style.fontSize = `${options.tailsize}px`;
          tail.style.color = options.tail;
          td.append(head, tail);
        }
        row.append(td);
      }
      body.append(row);
    });
    table.append(body);
    host.replaceChildren(table);
    return table;
  }

  function mount() {
    const form = document.getElementById("app-phoi-form");
    const host = document.getElementById("app-phoi");
    if (!form || !host) return;
    const draw = () => {
      const options = readForm(form);
      const table = render(host, options);
      const status = document.getElementById("app-phoi-status");
      if (status) status.textContent = `${table.tBodies[0].rows.length} tuần · Mỗi hàng một tuần, từ cũ đến mới. `
        + "Cuộn ngang nếu cần để xem đủ bảy ngày.";
    };
    form.addEventListener("input", draw);
    form.addEventListener("submit", (event) => { event.preventDefault(); draw(); });
    const print = document.getElementById("app-phoi-print");
    if (print) print.addEventListener("click", () => window.print());
    draw();
  }

  window.WeeklySheet = { weeks, readForm, render, mondayOf };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
