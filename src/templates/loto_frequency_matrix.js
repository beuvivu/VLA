// Included only on tan-suat-loto. Reuses the canonical embedded DRAWS and MARKS.
function lfmDraw(draw) {
  const counts = Array(100).fill(0);
  (draw.n || []).forEach(n => { if (/^\d{2}$/.test(n)) counts[+n]++; });
  const special = /^\d{5}$/.test(draw.s) ? draw.s.slice(-2) : null;
  return {date:draw.d, counts, special};
}
function lfmState(count, special) { return special ? "special" : count ? `hit${Math.min(count,5)}` : "miss"; }
function lfmCard(number, count, special) {
  return `<span class="lfm-card lfm-${lfmState(count,special)}">${count || special ? number : ""}` +
    `${special || count > 1 ? `<small>${special ? "★ " : ""}${count > 1 ? count + "×" : ""}</small>` : ""}</span>`;
}
let lfmActive = null, lfmLocked = false, lfmAxes = [], lfmColumns = [];
function lfmClear() {
  lfmAxes.forEach(el => el.classList.remove("lfm-axis", "lfm-active"));
  lfmAxes = []; lfmActive = null; lfmLocked = false;
  $("lfm-detail").textContent = "Chọn ô để xem chi tiết.";
}
function lfmSelect(cell) {
  if (!cell || cell === lfmActive) return;
  const locked = lfmLocked;
  lfmClear(); lfmLocked = locked; lfmActive = cell;
  lfmAxes = [...cell.parentElement.children, ...(lfmColumns[+cell.dataset.column] || [])];
  lfmAxes.forEach(el => el.classList.add("lfm-axis"));
  cell.classList.add("lfm-active");
  const old = $("sp-matrix-grid").querySelector('[tabindex="0"]');
  if (old) old.tabIndex = -1;
  cell.tabIndex = 0;
  $("lfm-detail").textContent = cell.getAttribute("aria-label");
}
renderLotoMatrix = function(rows) {
  const grid = $("sp-matrix-grid");
  lfmClear();
  const shown = rows.slice(-MATRIX_MAX_DAYS).reverse().map(lfmDraw);
  $("sp-matrix-note").textContent = `${shown.length} / ${rows.length} kỳ · 100 số · ngày mới nhất bên trái.`;
  grid.innerHTML = `<caption>Nháy lô tô theo ngày · ${shown.length} kỳ</caption><thead><tr><th scope="col">Số</th>` +
    shown.map(d => `<th scope="col" title="${d.date}">${d.date.slice(8)}/${d.date.slice(5,7)}<br>${d.date.slice(0,4)}</th>`).join("") +
    '</tr></thead><tbody>' + Array.from({length:100}, (_,n) => `<tr><th scope="row"${isPicked(n) ? '' : ' class="lfm-unpicked"'}>${pad2(n)}</th>` +
      shown.map((d,c) => {
        const number = pad2(n), count = d.counts[n], special = d.special === number;
        const label = `Số ${number} · ${d.date.split("-").reverse().join("/")} · ${count} nháy${special ? " · ★ Giải Đặc Biệt" : " · Không phải giải đặc biệt"}`;
        const key = `lfm:${number}:${d.date}`;
        return `<td class="lfm-cell${MARKS.has(key) ? " marked" : ""}" tabindex="${n===0 && c===0 ? 0 : -1}" ` +
          `data-row="${n}" data-column="${c}" data-number="${number}" data-date="${d.date}" data-hit-count="${count}" ` +
          `data-is-special="${special}" data-key="${key}" aria-label="${label}" title="${label}">` +
          lfmCard(number,count,special) + '</td>';
      }).join("") + '</tr>').join("") + '</tbody>';
  lfmColumns = shown.map((_,c) => Array.from(grid.rows, row => row.cells[c+1]));
};
function lfmInit() {
  const grid = $("sp-matrix-grid");
  $("lfm-legend").innerHTML = [["Đặc biệt",1,true],["Không về",0,false],...[1,2,3,4,5].map(n=>[n===5?"≥5 nháy":`${n} nháy`,n,false])]
    .map(([label,count,special])=>`<span>${lfmCard("",count,special)}${label}</span>`).join("");
  const theme = value => {
    document.documentElement.dataset.theme = value;
    document.querySelectorAll('[data-lfm-theme]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.lfmTheme===value)));
  };
  theme(document.documentElement.dataset.theme || "light");
  document.querySelectorAll('[data-lfm-theme]').forEach(b=>b.addEventListener('click',()=>{
    theme(b.dataset.lfmTheme); try { localStorage.setItem('vla.theme',b.dataset.lfmTheme); } catch(e) {}
  }));
  grid.addEventListener('pointerover',ev=>{ if(ev.pointerType!=="touch" && !lfmLocked) lfmSelect(ev.target.closest('.lfm-cell')); });
  grid.addEventListener('pointerleave',()=>{ if(!lfmLocked) lfmClear(); });
  grid.addEventListener('focusin',ev=>{ if(!lfmLocked) lfmSelect(ev.target.closest('.lfm-cell')); });
  grid.addEventListener('click',ev=>{
    const cell = ev.target.closest('.lfm-cell'); if(!cell) return;
    if(lfmLocked && cell===lfmActive) lfmClear(); else { lfmSelect(cell); lfmLocked=true; }
  });
  grid.addEventListener('keydown',ev=>{
    const cell = ev.target.closest('.lfm-cell'); if(!cell) return;
    const moves = {ArrowLeft:[0,-1],ArrowRight:[0,1],ArrowUp:[-1,0],ArrowDown:[1,0]};
    if(moves[ev.key]) {
      ev.preventDefault(); const [r,c]=moves[ev.key];
      const next = grid.tBodies[0].rows[+cell.dataset.row+r]?.cells[cell.cellIndex+c];
      if(next?.classList.contains('lfm-cell')) { lfmLocked=false; lfmSelect(next); next.focus(); }
    } else if(ev.key==='Enter' || ev.key===' ') { ev.preventDefault(); cell.click(); }
  });
  document.addEventListener('keydown',ev=>{if(ev.key==='Escape') lfmClear();});
  $("lfm-clear").addEventListener('click',lfmClear);
  $("lfm-mark").addEventListener('click',()=>{
    if(!lfmActive) return;
    const key=lfmActive.dataset.key;
    if(MARKS.has(key)) MARKS.delete(key); else MARKS.add(key);
    lfmActive.classList.toggle('marked',MARKS.has(key)); saveMarks(); updateMarkCount();
  });
}
lfmInit();
