(function () {
  if (window.__matrixVirt) return;
  window.__matrixVirt = true;

  // --- config (tuned for many 10x10 matrices on a long landing page) ---
  var PRELOAD_PX = 320;          // hydrate slightly before visible
  var UNLOAD_PX = 1200;          // dehydrate when far away (recycle DOM)
  var MAX_HYDRATE_PER_FRAME = 2; // avoid long tasks when several enter at once
  var payloadCache = null;
  var hydrated = new WeakSet();
  var pending = [];
  var rafScheduled = false;
  var ioIn = null;
  var ioOut = null;

  function prefersReducedWork() {
    try {
      if (navigator.connection && navigator.connection.saveData) return true;
      if (navigator.deviceMemory && navigator.deviceMemory <= 2) return true;
    } catch (e) {}
    return false;
  }

  function getAllPayloads() {
    if (payloadCache) return payloadCache;
    var box = document.getElementById('virt-matrix-data');
    if (!box) { payloadCache = {}; return payloadCache; }
    try { payloadCache = JSON.parse(box.textContent); }
    catch (e) { payloadCache = {}; }
    return payloadCache;
  }

  function loadPayload(grid) {
    var raw = grid.getAttribute('data-virt-payload');
    if (raw) {
      try { return JSON.parse(raw); } catch (e) { return null; }
    }
    var id = grid.getAttribute('data-virt-id');
    if (!id) return null;
    return getAllPayloads()[id] || null;
  }

  function cellButton(p) {
    var b = document.createElement('button');
    b.className = p.c;
    b.setAttribute('data-number', p.n);
    if (p.m) b.setAttribute('data-mode', p.m);
    if (p.v != null && p.v !== '') b.setAttribute('data-value', p.v);
    if (p.s) b.setAttribute('style', p.s);
    if (p.t) b.title = p.t;
    b.textContent = p.n;
    // no per-cell listener — delegated on document
    return b;
  }

  // Event delegation: one listener for all current + future matrix cells
  if (!window.__matrixVirtClick) {
    window.__matrixVirtClick = true;
    document.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t) return;
      var btn = t.closest ? t.closest('button[data-number]') : null;
      if (!btn) return;
      if (typeof showNumber === 'function') {
        showNumber(btn.getAttribute('data-mode') || 'loto', btn.getAttribute('data-number'));
      }
    });
  }

  function buildGridFragment(payload, tiny) {
    var axis = tiny ? 'matrix-head' : 'matrix-axis';
    var frag = document.createDocumentFragment();
    frag.appendChild(document.createElement('div'));
    var i, head, tail, h, ax, p;
    for (i = 0; i < 10; i++) {
      h = document.createElement('div');
      h.className = axis;
      h.textContent = String(i);
      frag.appendChild(h);
    }
    for (head = 0; head < 10; head++) {
      ax = document.createElement('div');
      ax.className = axis;
      ax.textContent = String(head);
      frag.appendChild(ax);
      for (tail = 0; tail < 10; tail++) {
        p = payload[head * 10 + tail];
        if (p) frag.appendChild(cellButton(p));
        else {
          var empty = document.createElement('div');
          empty.className = 'virt-slot';
          frag.appendChild(empty);
        }
      }
    }
    return frag;
  }

  function placeholder(tiny) {
    var el = document.createElement('div');
    el.className = 'virt-placeholder';
    el.setAttribute('data-virt-kind', tiny ? 'tiny' : 'grid');
    el.style.cssText = 'grid-column:1/-1;min-height:' + (tiny ? '220px' : '320px') +
      ';display:grid;place-items:center;color:#64748b;font-size:12px;font-weight:700';
    el.textContent = 'Ma tr\u1eadn 00\u201399';
    return el;
  }

  function hydrate(grid) {
    if (hydrated.has(grid) || grid.getAttribute('data-virt-hydrated') === '1') return;
    var payload = loadPayload(grid);
    if (!payload || !payload.length) return;
    var tiny = grid.classList.contains('tiny-matrix');
    grid.replaceChildren(buildGridFragment(payload, tiny));
    grid.setAttribute('data-virt-hydrated', '1');
    grid.classList.remove('is-dehydrated');
    hydrated.add(grid);
  }

  function dehydrate(grid) {
    // Do not unload the first tiny matrix (above-fold LCP)
    if (grid.getAttribute('data-virt-keep') === '1') return;
    if (!hydrated.has(grid) && grid.getAttribute('data-virt-hydrated') !== '1') return;
    // Must have payload id to restore later
    if (!grid.getAttribute('data-virt-id') && !grid.getAttribute('data-virt-payload')) return;
    var tiny = grid.classList.contains('tiny-matrix');
    grid.replaceChildren(placeholder(tiny));
    grid.removeAttribute('data-virt-hydrated');
    grid.classList.add('is-dehydrated');
    hydrated.delete(grid);
  }

  function flushPending() {
    rafScheduled = false;
    var budget = prefersReducedWork() ? 1 : MAX_HYDRATE_PER_FRAME;
    var n = 0;
    while (pending.length && n < budget) {
      var g = pending.shift();
      hydrate(g);
      n++;
    }
    if (pending.length) {
      rafScheduled = true;
      requestAnimationFrame(flushPending);
    }
  }

  function queueHydrate(grid) {
    if (hydrated.has(grid) || grid.getAttribute('data-virt-hydrated') === '1') return;
    if (pending.indexOf(grid) !== -1) return;
    pending.push(grid);
    if (!rafScheduled) {
      rafScheduled = true;
      requestAnimationFrame(flushPending);
    }
  }

  function observe() {
    var grids = document.querySelectorAll('[data-virt-payload], [data-virt-id]');
    if (!grids.length) return;

    if (!('IntersectionObserver' in window)) {
      for (var i = 0; i < grids.length; i++) hydrate(grids[i]);
      return;
    }

    var reduced = prefersReducedWork();
    var preload = reduced ? 120 : PRELOAD_PX;
    var unload = reduced ? 600 : UNLOAD_PX;

    ioIn = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) queueHydrate(entries[i].target);
      }
    }, { rootMargin: preload + 'px 0px', threshold: 0.01 });

    // Separate observer with large margin → fires when far off-screen
    ioOut = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (!entries[i].isIntersecting) dehydrate(entries[i].target);
      }
    }, { rootMargin: unload + 'px 0px', threshold: 0 });

    for (var j = 0; j < grids.length; j++) {
      ioIn.observe(grids[j]);
      ioOut.observe(grids[j]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', observe);
  } else {
    observe();
  }
})();
