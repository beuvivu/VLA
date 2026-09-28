/** Giữ nguyên bảng thật: co giãn theo dữ liệu, đồng bộ cuộn và ghim tiêu đề. */
function installStatTableLayout() {
  const layouts = [];
  let frame = 0;
  let needsMeasure = true;

  function schedule(measure = false) {
    needsMeasure = needsMeasure || measure;
    if (!frame) frame = requestAnimationFrame(update);
  }

  function update() {
    frame = 0;
    const header = document.querySelector('.app-header');
    const top = header ? Math.max(0, header.getBoundingClientRect().bottom) : 0;
    for (const {table, scroller, pan, track} of layouts) {
      const head = table.tHead;
      if (needsMeasure) {
        const columns = Number(table.dataset.spColumns) ||
          (head ? Array.from(head.rows[0].cells).filter(c => !c.hidden).length : 1);
        table.style.setProperty('--sp-columns', columns);
        table.style.setProperty('--sp-data-columns', Math.max(0, columns - 1));
        pan.hidden = table.offsetWidth <= scroller.clientWidth + 1;
        // Hai viền của khung không thuộc clientWidth; hai thanh phải có cùng biên cuộn.
        track.style.width = `${table.offsetWidth + pan.clientWidth - scroller.clientWidth}px`;
        pan.scrollLeft = scroller.scrollLeft;
      }
      const rect = table.getBoundingClientRect();
      const headHeight = head ? head.offsetHeight : 0;
      const panHeight = pan.hidden ? 0 : pan.offsetHeight;
      // overflow-x tạo vùng cuộn riêng nên sticky CSS không theo cuộn trang.
      // Dịch chính hàng tiêu đề, không nhân bản ô hay làm mất khoá đánh dấu.
      const offset = Math.min(Math.max(0, top + panHeight - rect.top),
        Math.max(0, rect.height - headHeight));
      if (head) head.style.setProperty('--sp-head-offset', `${offset}px`);
      scroller.style.scrollPaddingTop = `${headHeight + panHeight + top}px`;
    }
    needsMeasure = false;
  }

  document.querySelectorAll('.sp-scroll > .sp-table').forEach(table => {
    const scroller = table.parentElement;
    scroller.classList.add('sp-table-layout');
    scroller.setAttribute('role', 'region');
    scroller.setAttribute('aria-label', table.getAttribute('aria-label') || 'Bảng thống kê');
    scroller.tabIndex = 0;
    const host = mk('div', {class: 'sp-table-frame'});
    const track = mk('div', {class: 'sp-table-pan-track'});
    const pan = mk('div', {class: 'sp-table-pan', role: 'region', tabindex: '0',
      'aria-label': 'Cuộn ngang bảng dữ liệu'}, track);
    scroller.before(host);
    host.append(pan, scroller);
    const sync = (source, target) => {
      if (target.scrollLeft !== source.scrollLeft) target.scrollLeft = source.scrollLeft;
    };
    pan.addEventListener('scroll', () => sync(pan, scroller), {passive: true});
    scroller.addEventListener('scroll', () => sync(scroller, pan), {passive: true});
    layouts.push({table, scroller, pan, track});
    // Mỗi lần lọc thay thead/tbody; không quan sát từng ô khi rê chuột/đánh dấu.
    new MutationObserver(() => schedule(true)).observe(table, {childList: true});
    const resize = new ResizeObserver(() => schedule(true));
    resize.observe(scroller);
    resize.observe(table);
  });
  window.addEventListener('scroll', () => schedule(), {passive: true});
  window.addEventListener('resize', () => schedule(true), {passive: true});
  schedule(true);
}
