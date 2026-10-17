/* Lớp trình bày cho hai trang tần suất. Bộ máy thống kê cung cấp phép đếm,
   bộ lọc và danh tính ô. Các hàm mk, put, fill nằm cùng phạm vi script. */
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
    document.querySelectorAll(".bf-tabs a").forEach(a => {
      const target = new URL(a.href, location.href);
      if (target.pathname.endsWith("/thong-ke-tong-hop.html")) {
        fill(a, "Tổng hợp · Dữ liệu thật");
      } else {
        target.searchParams.set("demo", "1");
        a.href = target.href;
      }
    });
    // Minh họa lịch sử không thêm kỳ chờ của hôm nay.
    pendingDay = () => "";
  }
  const orientation = $("sp-orient");
  const orientationKey = "sp.orientation.v1." + (demo ? "demo." : "") + location.pathname.split("/").pop();
  const narrow = window.matchMedia?.("(max-width: 700px)");
  let manualOrientation = "";
  try { manualOrientation = localStorage.getItem(orientationKey) || ""; } catch (e) {}
  if (!["vertical", "horizontal"].includes(manualOrientation)) manualOrientation = "";
  const setOrientation = value => {
    orientation.value = value === "vertical" ? "Xem theo chiều dọc" : "Xem theo chiều ngang";
  };
  setOrientation(manualOrientation || (narrow?.matches ? "vertical" : "horizontal"));
  orientation.closest("label").hidden = true;
  orientation.closest(".sp-controls").classList.add("app-frequency-controls");
  function syncOrientation() {
    const vertical = orientation.value === "Xem theo chiều dọc";
    $("app-frequency-cards").classList.toggle("app-frequency-vertical", vertical);
    grid.parentElement.hidden = vertical;
    document.querySelectorAll("[data-app-orientation]").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.appOrientation === (vertical ? "vertical" : "horizontal")));
    });
    $("app-frequency-view-help").textContent = vertical
      ? "Mỗi thẻ là một số hoặc họ cặp. Mở lịch sử để đối chiếu và đánh dấu từng kỳ."
      : "Ma trận theo kỳ ở dưới các biểu đồ. Cuộn ngang; dùng phím mũi tên trong vùng bảng.";
  }
  orientation.addEventListener("change", () => {
    manualOrientation = orientation.value === "Xem theo chiều dọc" ? "vertical" : "horizontal";
    try { localStorage.setItem(orientationKey, manualOrientation); } catch (e) {}
    syncOrientation();
  });
  document.querySelectorAll("[data-app-orientation]").forEach(button => {
    button.addEventListener("click", () => {
      setOrientation(button.dataset.appOrientation);
      orientation.dispatchEvent(new Event("change", {bubbles: true}));
    });
  });
  narrow?.addEventListener?.("change", () => {
    if (!manualOrientation) {
      setOrientation(narrow.matches ? "vertical" : "horizontal");
      window[renderName]();
    }
  });
  if (demo) $("app-frequency-onboarding").hidden = false;

  let matrixChartMember = null, matrixChartGroups = [];
  function drawMatrixChartLabels() {
    if (!matrixChartMember || orientation.value === "Xem theo chiều dọc") return;
    const cells = new Map(Array.from(grid.querySelectorAll("tbody td:first-child[data-key]"), cell => [cell.dataset.key, cell]));
    matrixChartGroups.forEach(group => {
      const family = group.map(pad2).join("-");
      const key = pairPage ? `p|c${family}` : `m|n${family}`;
      const cell = cells.get(key);
      if (cell) fill(cell, [pairPage ? mk("b", null, family.replace("-", "–")) : null, ...group.map(matrixChartMember)]);
    });
  }
  /** Một đường cho mỗi số, gộp tối đa 24 nhóm kỳ và dùng chung trần lượt/kỳ. */
  function drawRangeCards(rows, counts) {
    const host = $("app-frequency-cards");
    syncOrientation();
    if (!rows.length) {
      fill(host, mk("p", {class: "sp-empty-row"}, "Không có kỳ trong dải đã chọn. Hãy chọn lại ngày hoặc thứ."));
      return;
    }
    const daily = rows.map(row => {
      const values = new Array(100).fill(0);
      row.n.forEach(number => {values[Number(number)]++;});
      return values;
    });
    const bins = Math.min(24, rows.length);
    const samples = Array.from({length: 100}, (_, number) => Array.from({length: bins}, (_, bin) => {
      const start = Math.floor(bin * rows.length / bins), end = Math.floor((bin + 1) * rows.length / bins);
      let sum = 0;
      for (let day = start; day < end; day++) sum += daily[day][number];
      return sum / (end - start);
    }));
    const scale = Math.max(1, ...samples.flat());
    const member = number => {
      const values = samples[number];
      const split = Math.floor(rows.length / 2);
      const before = split ? daily.slice(0, split).reduce((sum, day) => sum + day[number], 0) / split : 0;
      const after = split ? daily.slice(split).reduce((sum, day) => sum + day[number], 0) / (rows.length - split) : 0;
      const falling = split > 0 && after < before;
      const points = values.map((value, index) => `${index ? "L" : "M"}${values.length === 1 ? 0 : (index * 120 / (values.length - 1)).toFixed(2)},${(31 - value * 28 / scale).toFixed(2)}`);
      if (values.length === 1) points.push(`L120,${(31 - values[0] * 28 / scale).toFixed(2)}`);
      return mk("div", {class: "app-frequency-member", "data-app-number": pad2(number)}, [
        mk("div", {class: "app-frequency-member-heading"}, [
          mk("b", null, pad2(number)),
          mk("span", {class: "app-frequency-count"}, `${counts[number]} lượt`),
        ]),
        mk("svg", {class: "app-frequency-spark" + (falling ? " app-frequency-falling" : ""), viewBox: "0 0 120 36", role: "img",
          "aria-label": `Số ${pad2(number)}: ${counts[number]} lượt trong ${rows.length} kỳ; ${rows.length < 2 ? "chưa đủ kỳ so xu hướng" : falling ? "mức lượt/kỳ nửa sau giảm" : "mức lượt/kỳ nửa sau bằng hoặc tăng"}`,
          "data-total": counts[number], "data-scale": scale}, mk("path", {d: points.join(" "), fill: "none", "vector-effect": "non-scaling-stroke"})),
        mk("small", null, `${rows.length} kỳ · ${rows.length < 2 ? "Cần ≥ 2 kỳ để so xu hướng" : falling ? "↓ Mức lượt/kỳ giảm" : "→ Mức lượt/kỳ bằng hoặc tăng"}`),
      ]);
    };
    let groups = pairPage ? CAP50.filter(pair => pickedPairs.has(pair.map(pad2).join("-"))) : Array.from({length: 100}, (_, i) => [i]).filter(([number]) => isPicked(number));
    const sort = $("sp-sort")?.value || "num";
    const gan = group => {
      let distance = 0;
      for (let i = daily.length - 1; i >= 0 && !group.some(number => daily[i][number]); i--) distance++;
      return distance;
    };
    if (sort !== "num") {
      const score = group => sort.startsWith("gan") ? gan(group) : group.reduce((sum, number) => sum + counts[number], 0);
      const direction = sort.endsWith("-asc") ? 1 : -1;
      groups.sort((a, b) => (score(a) - score(b)) * direction || a[0] - b[0]);
    }
    if (orientation.value !== "Xem theo chiều dọc") {
      fill(host, []);
      grid.classList.add("app-frequency-chart-matrix");
      matrixChartMember = member;
      matrixChartGroups = groups;
      drawMatrixChartLabels();
      return;
    }
    matrixChartMember = null;
    grid.classList.remove("app-frequency-chart-matrix");
    fill(host, groups.length ? groups.map(group => {
      const family = group.map(pad2).join("-");
      const content = mk("div", {class: "app-frequency-history-content"});
      const details = mk("details", {class: "app-frequency-history"}, [mk("summary", null, "Lịch sử từng kỳ · bấm ô để đánh dấu"), content]);
      details.addEventListener("toggle", () => {
        if (!details.isConnected) return;
        if (!details.open) { fill(content, []); return; }
        host.querySelectorAll("details[open]").forEach(other => { if (other !== details) { other.open = false; fill(other.lastElementChild, []); } });
        let limit = 60;
        const drawHistory = () => {
          const shown = rows.slice(-limit).reverse();
          const tableNode = mk("table", {class: "sp-table sp-nhay", "aria-label": `Lịch sử ${family}`}, [
            mk("thead", null, mk("tr", null, [mk("th", {scope: "col"}, "Kỳ quay"), mk("th", {scope: "col"}, "Lượt về")])),
            mk("tbody", null, shown.map(row => {
              const count = row.n.filter(number => group.includes(Number(number))).length;
              const key = pairPage ? `p|c${family}|d${row.d}` : `m|n${family}|d${row.d}`;
              const special = group.includes(Number(String(row.s).slice(-2)));
              return mk("tr", null, [mk("th", {scope: "row"}, viDate(row.d)), mk("td", {
                class: `cell ${count ? "sp-hit sp-n" + Math.min(count, 5) : "is-empty"}${special && count ? " sp-de-hit" : ""}`,
                "data-key": key, tabindex: "-1", "aria-label": `${family} · ${row.d} · ${count} lượt${special && count ? " · Đặc Biệt" : ""}`,
              }, count)]);
            })),
          ]);
          const region = mk("div", {class: "app-frequency-history-scroll", role: "region", tabindex: "0", "aria-label": `Lịch sử ${family}, phím mũi tên để di chuyển`}, tableNode);
          region.addEventListener("keydown", event => {
            const cells = Array.from(tableNode.querySelectorAll("td[data-key]"));
            const current = event.target.closest("td[data-key]");
            if (["Enter", " "].includes(event.key) && current) { event.preventDefault(); current.click(); }
            if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const at = cells.indexOf(current);
            const next = event.key === "Home" ? 0 : event.key === "End" ? cells.length - 1 : Math.max(0, Math.min(cells.length - 1, at + (event.key === "ArrowUp" ? -1 : 1)));
            cells[next]?.focus({preventScroll: true});
            cells[next]?.scrollIntoView({block: "nearest"});
          });
          const more = mk("button", {type: "button", class: "app-frequency-more"}, `Xem thêm kỳ (${Math.min(limit, rows.length)}/${rows.length})`);
          more.addEventListener("click", () => { limit += 60; drawHistory(); });
          fill(content, [region, limit < rows.length ? more : null]);
          paintMarks();
        };
        drawHistory();
      });
      return mk("article", {class: "app-frequency-card", "data-app-family": family}, [
        pairPage ? mk("h3", null, [`Họ ${family.replace("-", "–")}`, mk("span", {class: "app-frequency-family-total"}, `${group.reduce((sum, number) => sum + counts[number], 0)} lượt`)]) : null,
        mk("div", {class: "app-frequency-members"}, group.map(member)), details,
      ]);
    }) : mk("p", {class: "sp-empty-row"}, "Chưa chọn số nào. Mở phần lựa chọn để thêm số."));
  }

  const dateOf = cell => /\|d(\d{4}-\d{2}-\d{2})/.exec(cell.dataset.key || "")?.[1];
  const numberOf = cell => /\|n(\d{2})/.exec(cell.dataset.key || "")?.[1];
  let currentRows = [], currentSpecials = new Map(), scoredRows = null, pairScores = null;
  function decorate() {
    clearCrosshair.run();
    const rows = selected();
    const specials = new Map(rows.map(r => [r.d, String(r.s).slice(-2)]));
    currentRows = rows;
    currentSpecials = specials;
    const counts = countLoto(rows);
    const total = rows.reduce((n, r) => n + r.n.length, 0);
    const hot = counts.indexOf(Math.max(...counts));
    const last = rows.at(-1);
    $("sp-count").textContent = rows.length
      ? `${rows.length} kỳ · ${viDate(rows[0].d)} → ${viDate(last.d)}`
      : "Không có kỳ phù hợp với bộ lọc";
    fill($("bf-kpis"), [
      ["Kỳ đang phân tích", rows.length, rows.length ? `${viDate(rows[0].d)} → ${viDate(last.d)}` : "Không có kỳ phù hợp", "◷", ""],
      ["Tổng số nháy", total.toLocaleString("vi-VN"), "27 kết quả trong mỗi kỳ XSMB", "▥", ""],
      ["Đặc Biệt gần nhất", last ? String(last.s).slice(-2) : "—", last ? `Giải ${last.s} · ${viDate(last.d)}` : "Chưa có kết quả", "★", "1"],
      ["Lô tô xuất hiện nhiều nhất", rows.length ? pad2(hot) : "—", rows.length ? `${counts[hot]} nháy trên trọn dải` : "Chọn lại khoảng thời gian", "↗", "1"],
    ].map(([label, value, hint, icon, computed]) => mk("div", {class: "bf-kpi"}, [
      mk("span", {class: "bf-kpi-icon", "aria-hidden": "true"}, icon),
      mk("span", {class: "bf-kpi-label"}, label),
      mk("strong", null, value),
      // Dòng phụ in kết quả tính được thì khai để số trong câu có bằng chứng.
      mk("small", {"data-evidence-split": computed}, hint),
    ])));
    drawRangeCards(rows, counts);
    decorateCells(rows, specials);
    document.querySelectorAll("[title]").forEach(node => node.removeAttribute("title"));
    if (pairPage) {
      const totals = $("bf-pair-totals");
      fill(totals, rows.length ? CAP50.map(([a, b]) => mk("span", {
        class: "sp-cell", "aria-label": `Họ ${pad2(a)}–${pad2(b)}: ${counts[a] + counts[b]} lượt trong ${rows.length} kỳ`,
      }, [mk("b", null, `${pad2(a)}–${pad2(b)}`), mk("i", null, counts[a] + counts[b])])) :
        mk("p", {class: "sp-empty-row"}, "Không có kỳ phù hợp với dải ngày và thứ đang chọn."));
    }
    document.querySelectorAll(".bf-totals .sp-cell").forEach(cell => {
      cell.setAttribute("aria-label", `${cell.querySelector("b").textContent}: ${cell.querySelector("i").textContent} lượt trong ${rows.length} kỳ`);
    });
    $("bf-selection-count").textContent = pairPage ? `${pickedPairs.size}/50 họ cặp` : `${Array.from({length:100},(_,i)=>i).filter(isPicked).length}/100 số`;
    $("sp-matrix-note").textContent = `${rows.length} kỳ · mới nhất trước`;
    if (!pairPage) {
      // Bảng xếp hạng đếm tổng số nháy trên trọn dải đã chọn.
      const expected = rows.length * 27 / 100;
      $("sp-grid").querySelectorAll("tbody tr").forEach(tr => {
        if (tr.cells.length !== 5) return;
        tr.cells[3].textContent = expected.toFixed(1);
        tr.cells[4].textContent = expected ? (Number(tr.cells[2].textContent) / expected).toFixed(2) + "×" : "—";
      });
    }
    paintMarks();
  }
  function decorateCells(rows, specials) {
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
      cell.removeAttribute("title");
      cell.setAttribute("aria-label", label);
      cell.tabIndex = -1;
    }
    if (pairPage && rows.length) filterPairs(rows);
    const first = Array.from(dataCells).find(c => c.cellIndex > 0 && !c.hidden && !c.parentElement.hidden);
    if (first) first.tabIndex = -1;
    // Dải không có kỳ không đồng nghĩa với những lần không về.
    if (!rows.length || !first) {
      if (grid._spWindow) grid._spWindow.destroy();
      fill(grid, mk("tbody", null, mk("tr", null, mk("td", {class: "sp-empty-row"},
        !rows.length
          ? 'Không có kỳ trong dải đã chọn. Hãy kiểm tra khoảng ngày và bộ lọc thứ.'
          : 'Chưa chọn số nào. Mở phần lựa chọn để thêm số vào ma trận.'))));
    }
  }
  grid.addEventListener('sp:matrix-window', () => {
    clearCrosshair.run();
    decorateCells(currentRows, currentSpecials);
    drawMatrixChartLabels();
    paintMarks();
  });
  function filterPairs(rows) {
    const vertical = $("sp-orient").value === "Xem theo chiều dọc";
    const pairs = CAP50.map(p => p.map(pad2).join("-"));
    if (scoredRows !== rows) {
      const byDate = rows.slice().reverse();
      pairScores = new Map(pairs.map(pair => {
        const ns = pair.split("-");
        const daily = byDate.map(r => r.n.filter(n => ns.includes(n)).length);
        const hit = daily.findIndex(n => n > 0);
        return [pair, {total:daily.reduce((a,b)=>a+b,0), gan:hit < 0 ? daily.length : hit}];
      }));
      scoredRows = rows;
    }
    const score = pairScores;
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
        if (tr.classList.contains('sp-virtual-gap')) continue;
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
  // Hàm khởi động gắn bộ xử lý này riêng cho hai trang tần suất.
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
    grid.parentElement.addEventListener("keydown",ev=>{
      const cell = ev.target.closest("td") || (ev.target === grid.parentElement
        ? Array.from(grid.querySelectorAll("td[data-key]")).find(candidate =>
          candidate.cellIndex > 0 && !candidate.hidden && !candidate.parentElement.hidden &&
          !candidate.classList.contains("sp-virtual-gap"))
        : null);
      if (!cell) return;
      if(ev.key==="Escape"){clear();return;}
      if(ev.key==="Enter" || ev.key===" "){ev.preventDefault();cell.click();return;}
      if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(ev.key))return;
      ev.preventDefault();
      if (ev.target === grid.parentElement) {
        cell.focus({preventScroll:true});
        cell.scrollIntoView({block:"nearest",inline:"nearest"});
        return;
      }
      const rows=Array.from(grid.tBodies[0].rows).filter(r=>!r.hidden && !r.classList.contains('sp-virtual-gap'));
      let rowIndex=rows.indexOf(cell.parentElement);
      const cells=Array.from(cell.parentElement.cells).filter(c=>!c.hidden && c.cellIndex>0 && c.hasAttribute('data-key'));
      let colIndex=cells.indexOf(cell);
      if(ev.key==="ArrowUp")rowIndex--;if(ev.key==="ArrowDown")rowIndex++;
      if(ev.key==="ArrowLeft")colIndex--;if(ev.key==="ArrowRight")colIndex++;
      if (grid._spWindow && (rowIndex < 0 || rowIndex >= rows.length || colIndex < 0 || colIndex >= cells.length)) {
        grid._spWindow.move(cell, ev.key);
        return;
      }
      const row=rows[Math.max(0,Math.min(rows.length-1,rowIndex))];
      const target=Array.from(row.cells).filter(c=>!c.hidden && c.cellIndex>0 && c.hasAttribute('data-key'))[Math.max(0,Math.min(cells.length-1,colIndex))];
      if(target){cell.tabIndex=-1;target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({block:"nearest",inline:"nearest"});}
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
