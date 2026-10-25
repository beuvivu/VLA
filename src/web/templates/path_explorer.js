(() => {
  "use strict";
  // Phần đối chiếu chỉ đọc dữ liệu đã công bố, không sửa xác suất hay điều kiện quét.
  function node(tag, cls, text) {
    const item = document.createElement(tag);
    if (cls) item.className = cls;
    if (text !== undefined) item.textContent = text;
    return item;
  }
  const dateLabel = value => String(value).split("-").reverse().join("/");
  function sourceLine(source, cls, label) {
    const line = node("div", `path-source ${cls}`);
    if (!source) {
      line.append(node("span", "", `${label}: chưa có dữ liệu nguồn`));
      return line;
    }
    line.append(node("span", "", `${label} · ${source.label}`));
    const value = node("span", "path-raw-value");
    [...source.value].forEach((digit, index) => value.append(node(index === source.offset ? "mark" : "span", "", digit)));
    line.append(value);
    return line;
  }
  function evidenceCard(cell, mode) {
    const card = node("li", "path-evidence");
    const state = mode === "de" && cell.state === "hit" ? "hit-de" : cell.state;
    card.dataset.state = state;
    card.dataset.targetDate = cell.target_date;
    card.dataset.sourceDate = cell.source_date;
    card.append(node("h4", "", `${state === "future" ? "Kỳ tới" : "Kỳ đối chiếu"} · ${dateLabel(cell.target_date)}`),
      node("p", "path-source-day", `Lấy chữ số từ ngày ${dateLabel(cell.source_date)}`));
    const flow = node("div", "path-flow");
    const sources = node("div", "path-sources");
    sources.append(sourceLine(cell.source_a, "path-source-a", "A"), sourceLine(cell.source_b, "path-source-b", "B"));
    const candidate = node("div", "path-candidate");
    candidate.append(node("span", "", "Ghép A → B"), node("b", "", cell.num ?? "—"));
    const outcome = node("div", "path-outcome");
    const label = state === "future" ? "Chờ kết quả" : state === "unknown" ? "Chưa đủ dữ liệu đối chiếu"
      : state === "hit-de" ? "Về Đặc Biệt" : state === "hit" ? `Về LOTO${cell.count !== null ? ` · ${cell.count} nháy` : ""}` : "Không về";
    outcome.append(node("strong", "", label));
    if (state !== "future" && cell.actual_special) {
      outcome.append(node("span", "", "Đặc Biệt thực tế"), node("span", "path-actual-special", cell.actual_special));
    }
    flow.append(sources, candidate, outcome);
    card.append(flow);
    if (mode === "loto" && cell.actual_numbers?.length && state !== "future") {
      const details = node("details", "path-actual-list");
      details.append(node("summary", "", "Xem các số LOTO thực tế"), node("p", "", cell.actual_numbers.join(" · ")));
      card.append(details);
    }
    return card;
  }
  function mount() {
    const dataNode = document.getElementById("path-data");
    if (!dataNode) return;
    let data;
    try { data = JSON.parse(dataNode.textContent); } catch { return; }
    if (!Array.isArray(data.rows)) return;
    const state = { data, selected: null, number: "", visible: [] };
    window.PathExplorer = { state, evidenceCard };
    if (!data.rows.length) return;
    const panel = document.getElementById("path-detail");
    const input = document.getElementById("path-number-filter");
    const days = document.getElementById("path-days-filter");
    const status = document.getElementById("path-status");
    function syncUrl() {
      const url = new URL(location.href);
      if (state.number) url.searchParams.set("number", state.number); else url.searchParams.delete("number");
      if (state.selected !== null) url.searchParams.set("path", data.rows[state.selected].id); else url.searchParams.delete("path");
      history.replaceState(null, "", url);
    }
    function renderDetail(index) {
      state.selected = index;
      panel.replaceChildren();
      for (const button of document.querySelectorAll("[data-path-index]")) button.setAttribute("aria-pressed", String(Number(button.dataset.pathIndex) === index));
      if (index === null) {
        const emptyTitle = node("h3", "", "Không có đường cầu trong danh sách đang hiển thị");
        emptyTitle.id = "path-detail-title";
        panel.append(emptyTitle,
          node("p", "", "Số hỗ trợ ở phía trên được tính trên toàn bộ đường cầu đủ điều kiện. Bỏ lọc để xem lại danh sách đã xuất."));
        return;
      }
      const row = data.rows[index];
      const title = node("h3", "", `Đường cầu ${index + 1} · trễ ${row.lag} ngày`);
      title.id = "path-detail-title";
      panel.append(title, node("p", "", `${row.i_label} → ${row.j_label}`));
      const meta = node("div", "path-detail-meta");
      meta.append(node("span", "", `Chuỗi hiện tại ${row.current_streak} kỳ`), node("span", "", `Dài nhất ${row.max_streak} kỳ`),
        node("span", "", `Dự báo kỳ tới ${row.p_next === null ? "chưa có" : `${(row.p_next * 100).toFixed(2)}%`}`));
      const legend = node("div", "path-legend");
      legend.append(node("span", "path-source-a", "A: chữ số hàng chục"), node("span", "path-source-b", "B: chữ số hàng đơn vị"));
      panel.append(meta, legend);
      const list = node("ol", "path-timeline");
      if (row.forecast) list.append(evidenceCard(row.forecast, data.mode));
      const limit = days.value === "all" ? row.cells.length : Number(days.value);
      for (const cell of row.cells.slice(-limit).reverse()) list.append(evidenceCard(cell, data.mode));
      panel.append(list);
    }
    function filter(number, preferred = null) {
      state.number = /^\d{1,2}$/.test(number.trim()) ? number.trim().padStart(2, "0") : "";
      input.value = state.number;
      state.visible = [];
      for (const [index, row] of data.rows.entries()) {
        const show = !state.number || row.next_num === state.number;
        document.querySelector(`[data-path-row="${index}"]`).hidden = !show;
        if (show) state.visible.push(index);
      }
      for (const button of document.querySelectorAll("[data-path-number]")) button.setAttribute("aria-pressed", String(button.dataset.pathNumber === state.number));
      status.textContent = `${state.visible.length}/${data.rows.length} đường cầu đang hiển thị${state.number ? ` báo số ${state.number} cho kỳ ${dateLabel(data.target_date)}` : ""}.`;
      renderDetail(preferred !== null && state.visible.includes(preferred) ? preferred : state.visible[0] ?? null);
      syncUrl();
    }
    function revealDetail() {
      const heading = document.getElementById("path-detail-title");
      heading.tabIndex = -1;
      heading.focus({preventScroll: true});
      heading.scrollIntoView?.({block: "start"});
    }
    for (const button of document.querySelectorAll("[data-path-number]")) button.addEventListener("click", () => {
      filter(button.dataset.pathNumber);
      revealDetail();
    });
    for (const button of document.querySelectorAll("[data-path-index]")) button.addEventListener("click", () => {
      renderDetail(Number(button.dataset.pathIndex));
      syncUrl();
      revealDetail();
    });
    input.addEventListener("input", () => { if (input.value.length === 2 || !input.value) filter(input.value); });
    input.addEventListener("change", () => filter(input.value));
    days.addEventListener("change", () => renderDetail(state.selected));
    document.getElementById("path-reset").addEventListener("click", () => filter(""));
    const params = new URLSearchParams(location.search);
    const selected = data.rows.findIndex(row => row.id === params.get("path"));
    filter(params.get("number") || "", selected < 0 ? null : selected);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
