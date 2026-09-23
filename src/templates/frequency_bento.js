/* Frequency-only presentation layer. Counts, filters and cell identities are
   supplied by the existing statistics engine. No network or external assets.

   `mk`, `put` and `fill` are the DOM builders declared at the top of
   stat_pages.js. Both files are emitted into the SAME <script> element by
   src/build_stat_pages.py, so they share one scope. Nothing here may assign a
   string to the DOM: tests/test_security_hardening.py scans this file. */
function installFrequencyBento(renderName) {
  const pairPage = renderName === "renderPairFrequency";
  const demo = !!window.__D_DEMO_DRAWS__;
  const original = window[renderName];
  const grid = $("sp-matrix-grid");
  const pickedPairs = new Set(CAP50.map(([a, b]) => `${pad2(a)}-${pad2(b)}`));
  const pairOf = (cell) => /\|c(\d{2}-\d{2})/.exec(cell.dataset.key || "")?.[1];
  const clearCrosshair = {run: () => {}};
  if (demo) {
    $("bf-demo-banner").hidden = false;
    $("bf-source").textContent = "Dữ liệu giả lập · Không phải kết quả thật";
    $("bf-demo-link").textContent = "Quay về dữ liệu XSMB ↗";
    $("bf-demo-link").href = location.pathname;
    document.querySelectorAll(".bf-tabs a").forEach(a => {a.href += "?demo=1";});
    // A historical demonstration must not add today's real pending draw.
    pendingDay = () => "";
  }
  const dateOf = cell => /\|d(\d{4}-\d{2}-\d{2})/.exec(cell.dataset.key || "")?.[1];
  const numberOf = cell => /\|n(\d{2})/.exec(cell.dataset.key || "")?.[1];
  function decorate() {
    clearCrosshair.run();
    const rows = selected();
    const specials = new Map(rows.map(r => [r.d, String(r.s).slice(-2)]));
    const counts = countLoto(rows);
    const total = rows.reduce((n, r) => n + r.n.length, 0);
    const hot = counts.indexOf(Math.max(...counts));
    const last = rows.at(-1);
    fill($("bf-kpis"), [
      ["Kỳ đang phân tích", rows.length, rows.length ? `${rows[0].d} → ${last.d}` : "Không có kỳ phù hợp", "◷"],
      ["Tổng số nháy", total.toLocaleString("vi-VN"), "27 kết quả trong mỗi kỳ XSMB", "▥"],
      ["Đặc Biệt gần nhất", last ? String(last.s).slice(-2) : "—", last ? `Giải ${last.s} · ${last.d}` : "Chưa có kết quả", "★"],
      ["Lô tô xuất hiện nhiều nhất", rows.length ? pad2(hot) : "—", rows.length ? `${counts[hot]} nháy trên trọn dải` : "Chọn lại khoảng thời gian", "↗"],
    ].map(([label, value, hint, icon]) => mk("div", {class: "bf-kpi"}, [
      mk("span", {class: "bf-kpi-icon", "aria-hidden": "true"}, icon),
      mk("span", {class: "bf-kpi-label"}, label),
      mk("strong", null, value),
      mk("small", null, hint),
    ])));
    grid.classList.add("sp-nhay");
    grid.querySelectorAll("th").forEach(th => {th.scope = "col";});
    const dataCells = grid.querySelectorAll("td[data-key]");
    for (const cell of dataCells) {
      if (cell.cellIndex === 0) continue;
      const date = dateOf(cell);
      const number = pairPage ? pairOf(cell) : numberOf(cell);
      const count = Number.parseInt(cell.textContent, 10) || 0;
      const isSpecial = count > 0 && (pairPage ? number?.split("-").includes(specials.get(date)) : number === specials.get(date));
      cell.classList.toggle("sp-de-hit", isSpecial);
      if (count > 0) cell.classList.add("sp-hit", `sp-n${Math.min(count, 5)}`);
      const waiting = cell.classList.contains("sp-pending");
      const label = `${pairPage ? "Cặp" : "Số"} ${number} · ${date} · ${waiting ? "Chờ kết quả" : count + " nháy"}${isSpecial ? " · Đặc Biệt" : ""}`;
      cell.title = label;
      cell.setAttribute("aria-label", label);
      cell.tabIndex = -1;
    }
    if (pairPage && rows.length) filterPairs(rows);
    const first = Array.from(dataCells).find(c => c.cellIndex > 0 && !c.hidden && !c.parentElement.hidden);
    if (first) first.tabIndex = 0;
    // A date range with no draws is not evidence of misses.
    if (!rows.length || !first) {
      fill(grid, mk("tbody", null, mk("tr", null, mk("td", {class: "sp-empty-row"},
        !rows.length
          ? 'Không có kỳ trong dải đã chọn. Hãy kiểm tra khoảng ngày và bộ lọc thứ.'
          : 'Chưa chọn số nào. Mở phần lựa chọn để thêm số vào ma trận.'))));
    }
    $("bf-selection-count").textContent = pairPage ? `${pickedPairs.size}/50 họ cặp` : `${Array.from({length:100},(_,i)=>i).filter(isPicked).length}/100 số`;
    $("sp-matrix-note").textContent = `${Math.min(rows.length, MATRIX_MAX_DAYS)} kỳ${rows.length > MATRIX_MAX_DAYS ? " gần nhất · xếp hạng dùng trọn dải" : " · mới nhất trước"}`;
    if (!pairPage) {
      // The ranking counts occurrences, not the number of draws with a hit.
      const expected = rows.length * 27 / 100;
      $("sp-grid").querySelectorAll("tbody tr").forEach(tr => {
        if (tr.cells.length !== 5) return;
        tr.cells[3].textContent = expected.toFixed(1);
        tr.cells[4].textContent = expected ? (Number(tr.cells[2].textContent) / expected).toFixed(2) + "×" : "—";
      });
    }
    paintMarks();
  }
  function filterPairs(rows) {
    const vertical = $("sp-orient").value === "Xem theo chiều dọc";
    const pairs = CAP50.map(p => p.map(pad2).join("-"));
    const byDate = rows.slice(-MATRIX_MAX_DAYS).slice().reverse();
    const score = new Map(pairs.map(pair => {
      const ns = pair.split("-");
      const daily = byDate.map(r => r.n.filter(n => ns.includes(n)).length);
      const hit = daily.findIndex(n => n > 0);
      return [pair, {total:daily.reduce((a,b)=>a+b,0), gan:hit < 0 ? daily.length : hit}];
    }));
    const sort = $("sp-sort")?.value || "num";
    const compare = (a,b) => {
      if (sort === "num") return a.localeCompare(b);
      const field = sort.startsWith("gan") ? "gan" : "total";
      const sign = sort.endsWith("-asc") ? 1 : -1;
      return (score.get(a)[field] - score.get(b)[field]) * sign || a.localeCompare(b);
    };
    if (vertical) {
      const head = Array.from(grid.tHead.rows[0].cells);
      const order = head.slice(1).map((c, i) => ({pair:pairOf(c),index:i+1})).sort((a,b)=>compare(a.pair,b.pair));
      for (const tr of grid.rows) {
        const cells = Array.from(tr.cells);
        for (const item of order) {const c=cells[item.index];c.hidden=!pickedPairs.has(item.pair);tr.append(c);}
      }
    } else {
      const trs = Array.from(grid.tBodies[0].rows);
      trs.sort((a,b)=>compare(pairOf(a.cells[0]),pairOf(b.cells[0])));
      for (const tr of trs) {tr.hidden=!pickedPairs.has(pairOf(tr.cells[0]));grid.tBodies[0].append(tr);}
    }
  }
  const render = () => {original();decorate();};
  window[renderName] = render;
  // Existing boot binds this handler. It remains unchanged on all other pages.
  bindColumnHint = () => {
    let tracked = [], active = null, touch = false;
    function clear() {
      tracked.forEach(c=>c.classList.remove("bf-track"));tracked=[];
      if(active) active.classList.remove("bf-active");active=null;
    }
    clearCrosshair.run = clear;
    function highlight(cell) {
      if(!cell || cell.cellIndex===0 || cell.classList.contains("sp-empty-row")) return;
      if(cell===active) return;
      clear();active=cell;cell.classList.add("bf-active");
      const row=cell.parentElement;
      const column=Array.from(grid.rows).map(r=>r.cells[cell.cellIndex]).filter(Boolean);
      tracked=Array.from(new Set([...row.cells,...column]));
      tracked.forEach(c=>c.classList.add("bf-track"));
      $("bf-cell-status").textContent=cell.getAttribute("aria-label") || "";
    }
    grid.addEventListener("pointerover", ev=>{if(ev.pointerType!=="touch") highlight(ev.target.closest("td"));});
    grid.addEventListener("pointerdown", ev=>{touch=ev.pointerType==="touch";highlight(ev.target.closest("td"));});
    grid.addEventListener("pointerleave",()=>{if(!touch)clear();});
    grid.addEventListener("focusin",ev=>highlight(ev.target.closest("td")));
    grid.addEventListener("keydown",ev=>{
      const cell=ev.target.closest("td");if(!cell)return;
      if(ev.key==="Escape"){clear();return;}
      if(ev.key==="Enter" || ev.key===" "){ev.preventDefault();cell.click();return;}
      if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(ev.key))return;
      ev.preventDefault();
      const rows=Array.from(grid.tBodies[0].rows).filter(r=>!r.hidden);
      let rowIndex=rows.indexOf(cell.parentElement);
      const cells=Array.from(cell.parentElement.cells).filter(c=>!c.hidden && c.cellIndex>0);
      let colIndex=cells.indexOf(cell);
      if(ev.key==="ArrowUp")rowIndex--;if(ev.key==="ArrowDown")rowIndex++;
      if(ev.key==="ArrowLeft")colIndex--;if(ev.key==="ArrowRight")colIndex++;
      const row=rows[Math.max(0,Math.min(rows.length-1,rowIndex))];
      const target=Array.from(row.cells).filter(c=>!c.hidden && c.cellIndex>0)[Math.max(0,Math.min(cells.length-1,colIndex))];
      if(target){cell.tabIndex=-1;target.tabIndex=0;target.focus({preventScroll:true});target.scrollIntoView({block:"nearest",inline:"nearest"});}
    });
  };
  if (pairPage) {
    const host=$("bf-pair-picker");
    const drawPicker=()=>{
      fill(host, [
        mk("div", {class: "sp-pick-quick"}, [
          mk("button", {type: "button", "data-bf-pick": "all"}, "Tất cả"),
          mk("button", {type: "button", "data-bf-pick": "none"}, "Bỏ hết"),
        ]),
        mk("div", {class: "bf-pair-grid"}, CAP50.map(p => {
          const label = p.map(pad2).join("-");
          return mk("button", {
            type: "button",
            "data-bf-pair": label,
            "aria-pressed": String(pickedPairs.has(label)),
          }, label);
        })),
      ]);
    };
    drawPicker();
    host.addEventListener("click",ev=>{
      const btn=ev.target.closest("button");if(!btn)return;
      if(btn.dataset.bfPick){pickedPairs.clear();if(btn.dataset.bfPick==="all")CAP50.forEach(p=>pickedPairs.add(p.map(pad2).join("-")));}
      else if(btn.dataset.bfPair){const p=btn.dataset.bfPair;if(pickedPairs.has(p))pickedPairs.delete(p);else pickedPairs.add(p);}
      drawPicker();render();
    });
  }
}
