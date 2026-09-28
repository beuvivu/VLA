/** Dựng vùng ngày đang xem khi dải lớn; khoảng cuộn vẫn bao phủ toàn bộ lịch sử. */
function renderFrequencyWindow(el, headers, rows, opts) {
  if (el.id !== 'sp-matrix-grid' || Math.max(headers.length, rows.length) <= 400) return false;
  const horizontal = headers.length > 400;
  const scroller = el.parentElement;
  const cellWidth = 54, rowHeight = 36, buffer = 8;
  let queued = 0, previous = '', stopped = false;

  function draw(anchor) {
    queued = 0;
    if (stopped) return;
    const rect = el.getBoundingClientRect();
    const count = Math.ceil((horizontal ? scroller.clientWidth : innerHeight) /
      (horizontal ? cellWidth : rowHeight)) + 2 * buffer;
    const total = horizontal ? headers.length - 1 : rows.length;
    const position = horizontal ? scroller.scrollLeft / cellWidth :
      (80 - rect.top - (el.tHead?.offsetHeight || 44)) / rowHeight;
    const start = Math.max(0, Math.min(total - count, Math.floor(anchor ?? position) - buffer));
    const end = Math.min(total, start + count);
    const signature = `${start}:${end}`;
    if (signature === previous) return;
    const firstDraw = !previous;
    previous = signature;
    const focused = el.contains(document.activeElement) ? document.activeElement : null;
    const focusRow = focused?.parentElement.getAttribute('aria-rowindex');
    const focusCol = focused?.getAttribute('aria-colindex');
    const rowOffset = horizontal ? 0 : start;
    const column = i => horizontal && i > 0 ? start + i : i;
    const mapped = {...opts, windowed: true};
    for (const name of ['key', 'pairOf', 'pending', 'gan', 'de', 'title', 'style', 'cellExtra']) {
      if (opts[name]) mapped[name] = (y, i) => opts[name](y + rowOffset, column(i));
    }
    for (const name of ['headKey', 'headExtra', 'headPairOf']) {
      if (opts[name]) mapped[name] = i => opts[name](column(i));
    }
    const visibleRows = horizontal ? rows.map(r => [r[0], ...r.slice(start + 1, end + 1)]) : rows.slice(start, end);
    table(el, horizontal ? [headers[0], ...headers.slice(start + 1, end + 1)] : headers, visibleRows, mapped);
    if (horizontal) el.dataset.spColumns = headers.length;
    el.setAttribute('aria-rowcount', rows.length + 1);
    el.setAttribute('aria-colcount', headers.length);
    Array.from(el.rows).forEach((tr, y) => {
      tr.setAttribute('aria-rowindex', y ? rowOffset + y + 1 : 1);
      Array.from(tr.cells).forEach((cell, i) => cell.setAttribute('aria-colindex', column(i) + 1));
    });
    if (horizontal) {
      for (const tr of el.rows) {
        const gap = size => mk(tr.parentElement === el.tHead ? 'th' : 'td', {
          class: 'sp-virtual-gap', 'aria-hidden': 'true', style: `width:${size * cellWidth}px`,
        });
        if (start) tr.cells[0].after(gap(start));
        if (end < total) tr.append(gap(total - end));
      }
    } else {
      const gap = size => mk('tr', {class: 'sp-virtual-gap', 'aria-hidden': 'true'},
        mk('td', {class: 'sp-virtual-gap', colspan: headers.length, style: `height:${size * rowHeight}px`}));
      if (start) el.tBodies[0].prepend(gap(start));
      if (end < total) el.tBodies[0].append(gap(total - end));
    }
    // Lần đầu do bộ render chính trang trí; các lần cuộn chỉ cập nhật ô mới.
    if (!firstDraw) el.dispatchEvent(new Event('sp:matrix-window'));
    if (focusRow && focusCol) {
      const target = el.querySelector(`[aria-rowindex="${focusRow}"] [aria-colindex="${focusCol}"]`);
      if (target) {
        el.querySelector('[tabindex="0"]')?.setAttribute('tabindex', '-1');
        target.tabIndex = 0;
        target.focus({preventScroll: true});
      }
    }
  }

  function schedule() {
    if (!queued) queued = requestAnimationFrame(() => draw());
  }
  scroller.addEventListener('scroll', schedule, {passive: true});
  window.addEventListener('scroll', schedule, {passive: true});
  window.addEventListener('resize', schedule, {passive: true});
  el._spWindow = {
    move(cell, key) {
      // Chỉ ngày mới trải qua nhiều vùng; trục số/cặp có thể đã sắp xếp hoặc ẩn.
      if (horizontal ? !['ArrowLeft', 'ArrowRight'].includes(key) : !['ArrowUp', 'ArrowDown'].includes(key)) return;
      const row = Number(cell.parentElement.getAttribute('aria-rowindex')) - 2;
      const col = Number(cell.getAttribute('aria-colindex')) - 1;
      const nextRow = row + (key === 'ArrowDown' ? 1 : key === 'ArrowUp' ? -1 : 0);
      const nextCol = col + (key === 'ArrowRight' ? 1 : key === 'ArrowLeft' ? -1 : 0);
      if (nextRow < 0 || nextRow >= rows.length || nextCol < 1 || nextCol >= headers.length) return;
      draw(horizontal ? nextCol - 1 : nextRow);
      const target = el.querySelector(`[aria-rowindex="${nextRow + 2}"] [aria-colindex="${nextCol + 1}"]`);
      if (target) {
        cell.tabIndex = -1;
        target.tabIndex = 0;
        target.focus({preventScroll: true});
        target.scrollIntoView({block: 'nearest', inline: 'nearest'});
      }
    },
    destroy() {
      stopped = true;
      cancelAnimationFrame(queued);
      scroller.removeEventListener('scroll', schedule);
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      delete el._spWindow;
      delete el.dataset.spColumns;
      el.removeAttribute('aria-rowcount');
      el.removeAttribute('aria-colcount');
    },
  };
  draw();
  return true;
}
