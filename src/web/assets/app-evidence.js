(function () {
  "use strict";

  var doc = document;
  var win = window;
  var homeEvidence = /(?:^|\/)(?:index\.html|landing\.html|landing_desktop\.html)?$/.test(win.location.pathname);
  if (!doc.body || doc.body.dataset.appEvidenceReady) { return; }
  doc.body.dataset.appEvidenceReady = "true";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var NUM = /^[+\-\u2212\u00b1]?\s?(?:\d{1,3}(?:[ \u00a0\u202f.,]\d{3})+|\d+)(?:[.,]\d+)?(?:[eE][+\-]?\d+)?\s?(?:%|\u2030|\u00d7|x|k\u1ef3|l\u1ea7n|ng\u00e0y|nh\u00e1y|c\u1ea7u|con|s\u1ed1|tu\u1ea7n|th\u00e1ng|n\u0103m)?$/;
  var MAX_LEN = 24;
  var KNOWN_VALUE = ".tr-number, .tr-mini, .sp-de, [data-evidence-value]";
  var EXCLUDE = [
    ".app-rail", ".app-panel", ".app-header", ".app-global-search", ".app-evidence-tip",
    ".app-evidence-drawer", "input", "textarea", "select", "option", "[contenteditable]",
    "[data-no-evidence]", "[hidden]", "[aria-hidden='true']", "script", "style", "noscript", "code", "pre",
  ].join(",");
  var INTERACTIVE = [
    "a[href]", "button", "label", "summary", "[role='button']", "[role='link']", "[role='tab']",
    "[role='checkbox']", "[role='switch']", "[role='option']", "[onclick]", "[data-key]",
    ".tr-number", ".tr-mini",
  ].join(",");
  var STOP_AT = { TD: 1, TH: 1, LI: 1, DT: 1, DD: 1, P: 1, H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1, CAPTION: 1 };
  var NEVER = { TR: 1, THEAD: 1, TBODY: 1, TFOOT: 1, TABLE: 1, UL: 1, OL: 1, DL: 1, SECTION: 1,
    ARTICLE: 1, MAIN: 1, NAV: 1, FORM: 1, HEADER: 1, FOOTER: 1, ASIDE: 1, FIGURE: 1 };
  var TOUCH_GRACE = 700;

  var root = doc.getElementById("app-main") || doc.body;
  var registry = readRegistry();

  function readRegistry() {
    var empty = { page: { sources: [], reasoningTrace: { steps: [] } }, sections: [], values: {} };
    var node = doc.getElementById("app-evidence-data");
    if (!node) { return empty; }
    try {
      var data = JSON.parse(node.textContent || "{}");
      return {
        page: data.page || empty.page,
        sections: Array.isArray(data.sections) ? data.sections : [],
        values: data.values && typeof data.values === "object" ? data.values : {},
      };
    } catch (error) {
      return empty;
    }
  }

  function mergeValueBlocks() {
    [].slice.call(doc.querySelectorAll("script[type='application/json'][data-app-evidence-values]"))
      .forEach(function (node) {
        try {
          var values = JSON.parse(node.textContent || "{}");
          Object.keys(values).forEach(function (id) { registry.values[id] = values[id]; });
        } catch (error) {   }
      });
  }
  mergeValueBlocks();

  function norm(text) { return String(text || "").replace(/\s+/g, " ").trim(); }
  function short(text, max) {
    var t = norm(text);
    if (!t) { return ""; }
    return t.length > max ? t.slice(0, max - 1) + "…" : t;
  }
  function isNumber(text) { return text.length > 0 && text.length <= MAX_LEN && NUM.test(text); }

  function isVisible(el, styles) {
    if (!el || !root.contains(el) || el.closest(EXCLUDE)) { return false; }
    for (var ancestor = el; ancestor; ancestor = ancestor.parentElement) {
      if (ancestor.tagName === "DETAILS" && !ancestor.open) {
        var summary = ancestor.querySelector(":scope > summary");
        if (!summary || !summary.contains(el)) { return false; }
      }
    }
    if (typeof el.checkVisibility === "function") { return el.checkVisibility({ checkVisibilityCSS: true }); }
    for (var node = el; node; node = node.parentElement) {
      var style = styles && styles.get(node);
      if (!style) {
        style = win.getComputedStyle(node);
        if (styles) { styles.set(node, style); }
      }
      if (style.display === "none" || (node === el && /^(hidden|collapse)$/.test(style.visibility))) { return false; }
    }
    return true;
  }

  function svgLabel(el) {
    var title = el.querySelector ? el.querySelector(":scope > title") : null;
    return norm(title ? title.textContent : el.getAttribute("aria-label"));
  }

  function valueTarget(node) {
    var el = node && node.nodeType === 1 ? node : node && node.parentElement;
    if (!el || !root.contains(el) || el.closest(EXCLUDE)) { return null; }
    var explicit = el.closest("[data-evidence]");
    if (explicit && root.contains(explicit)) { return explicit; }
    var known = el.closest(KNOWN_VALUE);
    if (known && root.contains(known) && isNumber(norm(known.textContent))) { return known; }
    if (el.namespaceURI === SVG_NS) {
      var label = svgLabel(el);
      if (label && /\d/.test(label)) { return el; }
    }
    for (var depth = 0; el && depth < 4; depth += 1, el = el.parentElement) {
      if (el === root || el === doc.body || NEVER[el.tagName]) { return null; }
      var text = norm(el.textContent);
      if (text.length > MAX_LEN) { return null; }
      if (isNumber(text) && singleNumber(el)) { return el; }
      if (STOP_AT[el.tagName]) { return null; }
    }
    return null;
  }

  function singleNumber(el) {
    var parts = 0;
    for (var node = el.firstChild; node; node = node.nextSibling) {
      if ((node.nodeType === 1 || node.nodeType === 3) && /\d/.test(node.textContent || "")) { parts += 1; }
    }
    return parts <= 1;
  }

  function isInteractive(el) {
    if (el.hasAttribute("data-evidence")) { return false; }
    if (el.matches("[tabindex]:not([tabindex='-1'])") && !el.hasAttribute("data-evidence-region")) { return true; }
    var hit = el.closest(INTERACTIVE);
    return Boolean(hit && root.contains(hit) && !hit.hasAttribute("data-evidence"));
  }

  function valueText(el) {
    if (el.hasAttribute("data-evidence-value")) { return norm(el.getAttribute("data-evidence-value")); }
    if (el.namespaceURI === SVG_NS && !isNumber(norm(el.textContent))) { return svgLabel(el); }
    return norm(el.textContent);
  }

  function pageTitle() {
    var h1 = root.querySelector("h1");
    return h1 ? short(h1.textContent, 90) : short(doc.title, 90);
  }

  var HEADINGS = ":scope > h2, :scope > h3, :scope > h4, :scope > header h2, :scope > header h3, " +
    ":scope > .ui-card-head h2, :scope > .ui-card-head h3, :scope > div > h2, :scope > div > h3";

  function headingOf(container) {
    var h = container.querySelector(HEADINGS);
    return h ? short(h.textContent, 80) : "";
  }

  function headingBefore(container, el) {
    var found = "";
    var all = container.querySelectorAll(HEADINGS);
    for (var i = 0; i < all.length; i += 1) {
      if (all[i].compareDocumentPosition(el) & 4) { found = short(all[i].textContent, 80); }
    }
    return found;
  }

  function sectionTitle(el) {
    for (var anc = el.parentElement; anc && anc !== root && anc !== doc.body; anc = anc.parentElement) {
      if (anc.namespaceURI === SVG_NS) { continue; }
      var title = headingOf(anc);
      if (title) { return title; }
    }
    return "";
  }

  function columnIndex(cell) {
    var i = 0;
    for (var c = cell.parentElement.firstElementChild; c && c !== cell; c = c.nextElementSibling) {
      i += c.colSpan || 1;
    }
    return i;
  }

  function columnHeader(cell, table) {
    if (!table || !table.tHead || cell.closest("thead")) { return ""; }
    var rows = table.tHead.rows;
    var idx = columnIndex(cell);
    for (var r = rows.length - 1; r >= 0; r -= 1) {
      var start = 0;
      for (var k = 0; k < rows[r].cells.length; k += 1) {
        var head = rows[r].cells[k];
        var span = head.colSpan || 1;
        if (idx >= start && idx < start + span) {
          var text = short(head.textContent, 50);
          if (text) { return text; }
          break;
        }
        start += span;
      }
    }
    return "";
  }

  function rowLabel(cell, table) {
    var row = cell.parentElement;
    if (!row || cell.closest("thead")) { return ""; }
    var th = row.querySelector(":scope > th[scope='row']");
    if (th && th !== cell) { return short(th.textContent, 50); }
    var picks = [];
    for (var c = row.firstElementChild; c && c !== cell && picks.length < 2; c = c.nextElementSibling) {
      if (norm(c.textContent)) { picks.push(c); }
    }
    if (!picks.length && cell.nextElementSibling && norm(cell.nextElementSibling.textContent)) {
      picks.push(cell.nextElementSibling);
    }
    return picks.map(function (c) {
      var text = short(c.textContent, 24);
      var head = columnHeader(c, table);
      if (!head || head === text) { return text; }
      return head === "#" ? "#" + text : head + ": " + text;
    }).join(" · ");
  }

  function labelText(node, value) {
    var text = short(node.textContent, 61);
    return text && text.length <= 60 && !isNumber(text) && text.indexOf(value) < 0 ? text : "";
  }

  function nearbyLabel(el, value) {
    var own = norm(el.getAttribute("aria-label") || el.getAttribute("aria-description") || el.getAttribute("title"));
    if (own && !isNumber(own)) { return short(own, 60); }
    for (var node = el, depth = 0; node && node !== root && depth < 3; depth += 1, node = node.parentElement) {
      var prev = node.previousElementSibling;
      var next = node.nextElementSibling;
      var text = (prev && labelText(prev, value)) || (next && labelText(next, value));
      if (text) { return text; }
    }
    return "";
  }

  function context(el, value) {
    var ctx = { page: pageTitle(), section: sectionTitle(el), table: "", row: "", column: "", label: "" };
    if (el.namespaceURI === SVG_NS) {
      var label = svgLabel(el);
      if (label && label !== value) { ctx.label = short(label, 90); }
      return ctx;
    }
    var cell = el.closest("td, th");
    if (cell) {
      var table = cell.closest("table");
      if (table) {
        ctx.table = short((table.caption && table.caption.textContent) || table.getAttribute("aria-label"), 80);
      }
      ctx.column = columnHeader(cell, table);
      ctx.row = rowLabel(cell, table);
      if (!ctx.column && !ctx.row) { ctx.label = nearbyLabel(cell, value); }
    } else {
      ctx.label = nearbyLabel(el, value);
    }
    return ctx;
  }

  function entryAnchor(entry, el) {
    try {
      if (entry.match) { return el.closest(entry.match); }
    } catch (error) { return null; }
    if (!entry.heading) { return null; }
    for (var anc = el.parentElement; anc && anc !== root && anc !== doc.body; anc = anc.parentElement) {
      if (anc.namespaceURI !== SVG_NS && headingBefore(anc, el).indexOf(entry.heading) === 0) { return anc; }
    }
    return null;
  }

  function sectionEntry(el) {
    var best = null;
    var bestAnchor = null;
    for (var i = 0; i < registry.sections.length; i += 1) {
      var entry = registry.sections[i];
      var anchor = entry ? entryAnchor(entry, el) : null;
      if (anchor && root.contains(anchor) && (!bestAnchor || (bestAnchor !== anchor && bestAnchor.contains(anchor)))) {
        best = entry;
        bestAnchor = anchor;
      }
    }
    return best;
  }

  function whereStep(ctx, value) {
    var parts = [];
    if (ctx.table) { parts.push("bảng «" + ctx.table + "»"); }
    if (ctx.row) { parts.push("hàng «" + ctx.row + "»"); }
    if (ctx.column) { parts.push("cột «" + ctx.column + "»"); }
    if (!parts.length && ctx.label) { parts.push("mục «" + ctx.label + "»"); }
    if (!parts.length) { return ""; }
    return "Giá trị đọc tại " + parts.join(", ") + ": " + value + ".";
  }

  function idFor(el, ctx) {
    var bits = [location.pathname.split("/").pop() || "index.html", ctx.section, ctx.table, ctx.row, ctx.column, ctx.label];
    return bits.filter(Boolean).join(" › ").slice(0, 160);
  }

  function rowCovers(row, el) {
    var cols = row.getAttribute("data-evidence-cols");
    if (!cols) { return true; }
    var cell = el.closest("td, th");
    return Boolean(cell) && cols.split(",").indexOf(String(cell.cellIndex)) >= 0;
  }

  var IDENT_COLUMN = /^(?:số|con|cặp|cặp số|bộ số|số loto|số đặc biệt|2 số cuối)$/i;
  var RANK_COLUMN = /^(?:#|stt|top|(?:thứ )?hạng(?: .*)?)$/i;

  function cellScoped(section, el) {
    var cell = el.closest("td, th");
    var anchor = section && cell ? entryAnchor(section, el) : null;
    return Boolean(anchor && cell.contains(anchor));
  }

  function columnRole(column, section) {
    var name = norm(column);
    var sources = ((section || registry.page || {}).sources) || [];
    if (IDENT_COLUMN.test(name)) {
      return { title: "Định danh của hàng", sources: sources, reasoningTrace: { steps: [
        "Cột «" + name + "» là định danh của hàng: số 00–99 (hoặc cặp số) mà các cột còn lại mô tả — không phải giá trị đo.",
        "Giá trị của số ấy nằm ở các cột khác của cùng hàng; mỗi cột có cách tính của bảng.",
      ] } };
    }
    if (RANK_COLUMN.test(name)) {
      return { title: "Thứ hạng trong bảng", sources: sources, reasoningTrace: { steps: [
        "Cột «" + name + "» là thứ tự của hàng sau khi bảng được sắp xếp theo cột giá trị chính — vị trí trong danh sách, không phải một phép tính riêng.",
        "Giá trị dùng để xếp nằm ở các cột khác của cùng hàng.",
      ] } };
    }
    return null;
  }

  function evidenceFor(el) {
    var value = valueText(el);
    var explicitId = el.getAttribute("data-evidence") || "";
    if (!explicitId) {
      var row = el.closest("[data-evidence-row]");
      if (row && root.contains(row) && rowCovers(row, el)) { explicitId = row.getAttribute("data-evidence-row") || ""; }
    }
    var own = explicitId ? registry.values[explicitId] || null : null;
    var section = sectionEntry(el);
    var ctx = context(el, value);
    if (!own && !cellScoped(section, el)) { own = columnRole(ctx.column, section); }
    var base = own || section || registry.page || {};
    var trace = base.reasoningTrace || {};
    var steps = (trace.steps || []).slice();
    var where = whereStep(ctx, value);
    if (where) { steps.push(where); }
    var out = {
      id: explicitId || idFor(el, ctx),
      value: value,
      sources: (base.sources || []).slice(),
      reasoningTrace: { steps: steps },
      context: ctx,
      scope: (own && own.title) || (section && section.title) || "",
    };
    if (typeof trace.confidenceScore === "number" && isFinite(trace.confidenceScore)) {
      out.reasoningTrace.confidenceScore = trace.confidenceScore;
    }
    if (trace.promptUsed) { out.reasoningTrace.promptUsed = String(trace.promptUsed); }
    return out;
  }

  function mk(tag, cls, text) {
    var node = doc.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null && text !== "") { node.textContent = String(text); }
    return node;
  }

  function safeUrl(url) {
    var u = String(url || "");
    return /^[a-z0-9][a-z0-9._\-/]*(?:\.html)?(?:#[a-z0-9._\-]*)?$/i.test(u) ? u : "";
  }

  var tip = mk("div", "app-evidence-tip");
  tip.id = "app-evidence-tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  doc.body.appendChild(tip);
  var tipFor = null;
  var lastTouch = 0;

  function fillTip(ev, interactive, viaKeyboard) {
    var src = ev.sources[0];
    var lines = [];
    var head = mk("p", "app-evidence-tip-source");
    head.appendChild(mk("strong", "", "Nguồn: "));
    head.appendChild(doc.createTextNode(src ? src.title : "Dữ liệu của trang"));
    if (ev.sources.length > 1) { head.appendChild(doc.createTextNode(" · +" + (ev.sources.length - 1) + " nguồn")); }
    lines.push(head);
    var where = ev.context.column || ev.context.label || ev.scope || ev.context.section;
    lines.push(mk("p", "app-evidence-tip-meta",
      "Suy luận qua " + ev.reasoningTrace.steps.length + " bước" + (where ? " · " + where : "")));
    lines.push(mk("p", "app-evidence-tip-hint", viaKeyboard === "region"
      ? "Enter để xem chi tiết bằng chứng suy luận · mũi tên để chọn số khác"
      : viaKeyboard && interactive
        ? "Alt + Enter để xem chi tiết bằng chứng suy luận (Enter giữ chức năng sẵn có)"
        : viaKeyboard
          ? "Enter để xem chi tiết bằng chứng suy luận"
          : interactive
            ? (homeEvidence ? "Nhấp đúp (hoặc nhấn giữ) để xem chi tiết bằng chứng suy luận" : "Alt + nhấp (hoặc nhấn giữ) để xem chi tiết bằng chứng suy luận")
            : (homeEvidence ? "Nhấp đúp để xem chi tiết bằng chứng suy luận" : "Click để xem chi tiết bằng chứng suy luận")));
    tip.replaceChildren.apply(tip, lines);
  }

  function placeTip(el) {
    var rect = el.getBoundingClientRect();
    var vw = win.innerWidth || doc.documentElement.clientWidth;
    var vh = win.innerHeight || doc.documentElement.clientHeight;
    var w = tip.offsetWidth;
    var h = tip.offsetHeight;
    var top = rect.top - h - 8;
    if (top < 8) { top = Math.min(rect.bottom + 8, vh - h - 8); }
    var left = Math.max(8, Math.min(rect.left + rect.width / 2 - w / 2, vw - w - 8));
    tip.style.top = Math.max(8, top) + "px";
    tip.style.left = left + "px";
  }

  function showTip(el, viaKeyboard) {
    if (tipFor && tipFor !== el) { unmark(tipFor); }
    var interactive = isInteractive(el);
    fillTip(evidenceFor(el), interactive, viaKeyboard);
    tip.hidden = false;
    placeTip(el);
    tipFor = el;
    if (!interactive) { el.classList.add("app-evidence-hot"); }
    if (el.matches(":focus")) { el.setAttribute("aria-describedby", tip.id); }
  }

  function unmark(el) {
    el.classList.remove("app-evidence-hot");
    if (el.getAttribute("aria-describedby") === tip.id) { el.removeAttribute("aria-describedby"); }
  }

  function hideTip() {
    tip.hidden = true;
    if (tipFor) { unmark(tipFor); }
    tipFor = null;
  }

  doc.addEventListener("pointerdown", function (event) {
    if (event.pointerType === "touch") { lastTouch = Date.now(); }
    hideTip();
  }, true);

  doc.addEventListener("focusin", function (event) {
    if (event.target.hasAttribute && event.target.hasAttribute("data-evidence-region")) {
      if (keyboard && !drawerOpen()) {
        var region = event.target;
        var keep = currentItem(region);
        var start = keep || firstItem(region);
        if (start) { setActive(region, start); }
      }
      return;
    }
    var el = valueTarget(event.target);
    if (keyboard && el && el === event.target && !drawerOpen()) { showTip(el, "self"); return; }
    var inner = keyboard && !drawerOpen() ? controlNumber(event.target) : null;
    if (inner) {
      showTip(inner, "self");
      event.target.setAttribute("aria-describedby", tip.id);
    }
  });
  doc.addEventListener("focusout", function (event) {
    if (event.target === tipFor || (tipFor && event.target.contains && event.target.contains(tipFor))) { hideTip(); }
    if (event.target.getAttribute && event.target.getAttribute("aria-describedby") === tip.id) {
      event.target.removeAttribute("aria-describedby");
    }
    if (event.target === activeRegion && !(event.relatedTarget && activeRegion.contains(event.relatedTarget))) {
      deactivate();
    }
  });
  win.addEventListener("scroll", function () {
    if (!tipFor) { return; }
    if (tipFor === active) { placeTip(active); } else { hideTip(); }
  }, { passive: true, capture: true });

  var drawer = null;
  var lastFocus = null;

  function drawerOpen() { return Boolean(drawer && drawer.open); }

  function buildDrawer() {
    drawer = mk("dialog", "app-evidence-drawer");
    drawer.id = "app-evidence-drawer";
    drawer.setAttribute("aria-labelledby", "app-evidence-title");
    drawer.addEventListener("click", function (event) {
      if (event.target === drawer) { closeDrawer(); }
    });
    drawer.addEventListener("cancel", function (event) { event.preventDefault(); closeDrawer(); });
    drawer.addEventListener("close", restoreFocus);
    doc.body.appendChild(drawer);
  }

  function section(title, child) {
    var box = mk("section", "app-evidence-section");
    box.appendChild(mk("h3", "", title));
    box.appendChild(child);
    return box;
  }

  function contextList(ctx) {
    var rows = [["Trang", ctx.page], ["Khối", ctx.section], ["Bảng", ctx.table],
      ["Hàng", ctx.row], ["Cột", ctx.column], ["Mục", ctx.label]];
    var dl = mk("dl", "app-evidence-context");
    rows.forEach(function (pair) {
      if (!pair[1]) { return; }
      dl.appendChild(mk("dt", "", pair[0]));
      dl.appendChild(mk("dd", "", pair[1]));
    });
    return dl;
  }

  function sourceList(sources) {
    var list = mk("ol", "app-evidence-sources");
    if (!sources.length) {
      list.appendChild(mk("li", "", "Dữ liệu hiển thị trên chính trang này."));
      return list;
    }
    sources.forEach(function (src) {
      var item = mk("li", "app-evidence-source");
      var url = safeUrl(src.url);
      var title;
      if (url) {
        title = mk("a", "app-evidence-source-title", src.title);
        title.href = url;
      } else {
        title = mk("strong", "app-evidence-source-title", src.title);
      }
      item.appendChild(title);
      if (src.snippet) { item.appendChild(mk("p", "app-evidence-snippet", src.snippet)); }
      if (typeof src.page === "number") { item.appendChild(mk("small", "app-evidence-page", "Trang " + src.page)); }
      list.appendChild(item);
    });
    return list;
  }

  function confidenceBlock(score) {
    var pct = Math.round((score > 1 ? score : score * 100));
    pct = Math.max(0, Math.min(100, pct));
    var box = mk("div", "app-evidence-confidence");
    var bar = mk("div", "app-evidence-meter");
    bar.setAttribute("role", "meter");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(pct));
    bar.setAttribute("aria-label", "Độ tin cậy");
    var fill = mk("span", "app-evidence-meter-fill");
    fill.style.width = pct + "%";
    bar.appendChild(fill);
    box.appendChild(bar);
    box.appendChild(mk("p", "app-evidence-meter-text", "Độ tin cậy: " + pct + "%"));
    return box;
  }

  function fillDrawer(ev) {
    var surface = mk("div", "app-evidence-surface");
    var head = mk("header", "app-evidence-head");
    var titles = mk("div", "app-evidence-titles");
    titles.appendChild(mk("p", "app-evidence-eyebrow", "Nguồn & bằng chứng suy luận"));
    titles.appendChild(mk("p", "app-evidence-value", ev.value));
    var title = mk("h2", "", ev.scope || ev.context.column || ev.context.label || ev.context.section || ev.context.page || "Con số trên trang");
    title.id = "app-evidence-title";
    titles.appendChild(title);
    var close = mk("button", "app-evidence-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Đóng bằng chứng");
    close.addEventListener("click", closeDrawer);
    head.appendChild(titles);
    head.appendChild(close);
    surface.appendChild(head);

    var body = mk("div", "app-evidence-body");
    body.appendChild(section("Ngữ cảnh", contextList(ev.context)));
    body.appendChild(section("Nguồn dữ liệu", sourceList(ev.sources)));
    var steps = mk("ol", "app-evidence-steps");
    ev.reasoningTrace.steps.forEach(function (step) { steps.appendChild(mk("li", "", step)); });
    var trace = section("Bằng chứng suy luận", steps);
    if (typeof ev.reasoningTrace.confidenceScore === "number") {
      trace.appendChild(confidenceBlock(ev.reasoningTrace.confidenceScore));
    }
    body.appendChild(trace);
    body.appendChild(mk("p", "app-evidence-id", "Mã bằng chứng: " + ev.id));
    surface.appendChild(body);
    drawer.replaceChildren(surface);
    return close;
  }

  function openFor(el) {
    if (!isVisible(el)) { return null; }
    var ev = evidenceFor(el);
    hideTip();
    if (!drawer) { buildDrawer(); }
    lastFocus = doc.activeElement && doc.activeElement !== doc.body ? doc.activeElement : el;
    var close = fillDrawer(ev);
    if (typeof drawer.showModal === "function") { drawer.showModal(); } else { drawer.setAttribute("open", ""); }
    doc.body.classList.add("app-evidence-open");
    close.focus();
    return ev;
  }

  function closeDrawer() {
    if (!drawer) { return; }
    if (typeof drawer.close === "function") { drawer.close(); } else { drawer.removeAttribute("open"); restoreFocus(); }
  }

  function restoreFocus() {
    doc.body.classList.remove("app-evidence-open");
    if (lastFocus && typeof lastFocus.focus === "function" && doc.contains(lastFocus)) {
      try { lastFocus.focus({ preventScroll: true }); } catch (error) { lastFocus.focus(); }
    }
    lastFocus = null;
  }

  function hasSelection() {
    var sel = win.getSelection ? win.getSelection() : null;
    return Boolean(sel && !sel.isCollapsed && norm(String(sel)));
  }

  doc.addEventListener("click", function (event) {
    if (homeEvidence || !event.altKey || event.button !== 0) { return; }
    var el = valueTarget(event.target);
    if (!el) { return; }
    event.preventDefault();
    event.stopPropagation();
    openFor(el);
  }, true);

  doc.addEventListener("dblclick", function (event) {
    if (!homeEvidence || event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) { return; }
    var el = valueTarget(event.target);
    if (!el) { return; }
    event.preventDefault();
    event.stopPropagation();
    openFor(el);
  }, true);

  doc.addEventListener("click", function (event) {
    if (homeEvidence || event.defaultPrevented || event.button !== 0 || event.altKey || event.ctrlKey ||
        event.metaKey || event.shiftKey) { return; }
    var el = valueTarget(event.target);
    if (!el || isInteractive(el) || hasSelection()) { return; }
    openFor(el);
  });

  doc.addEventListener("contextmenu", function (event) {
    if (Date.now() - lastTouch > TOUCH_GRACE * 2) { return; }
    var el = valueTarget(event.target);
    if (!el) { return; }
    event.preventDefault();
    openFor(el);
  });

  var REGION_OF = "section, article, aside, figure, .ui-card";
  var SHOW_TEXT = 4;
  var SHOW_ELEMENT = 1;
  var keyboard = false;
  var active = null;
  var activeRegion = null;
  var hint = mk("p", "app-evidence-sr",
    "Dùng phím mũi tên để chọn con số, Enter để xem nguồn và bằng chứng suy luận.");
  hint.id = "app-evidence-kbd";
  var live = mk("p", "app-evidence-sr");
  live.id = "app-evidence-live";
  live.setAttribute("aria-live", "polite");
  doc.body.appendChild(hint);
  doc.body.appendChild(live);

  doc.addEventListener("keydown", function () { keyboard = true; }, true);
  doc.addEventListener("pointerdown", function () { keyboard = false; }, true);

  function selfFocusable(el) {
    return !el.hasAttribute("data-evidence-region") &&
      el.matches("a[href], button, input, select, textarea, summary, [tabindex]:not([tabindex='-1'])");
  }

  function regionFor(el) {
    var table = el.closest("table");
    if (table && root.contains(table)) { return table; }
    var box = el.closest(REGION_OF);
    return box && root.contains(box) ? box : el;
  }

  function markRegion(region) {
    if (region.hasAttribute("data-evidence-region") || region.closest(EXCLUDE)) { return; }
    var tab = region.getAttribute("tabindex");
    if (tab !== null && tab !== "0") { return; }
    region.setAttribute("data-evidence-region", "");
    region.setAttribute("tabindex", "0");
    var described = region.getAttribute("aria-describedby");
    region.setAttribute("aria-describedby", described ? described + " " + hint.id : hint.id);
  }

  function svgPoint(el) {
    return el.namespaceURI === SVG_NS && /\d/.test(svgLabel(el)) && valueTarget(el) === el;
  }

  function eachItem(scope, region, visit, includeInvisible) {
    var walker = doc.createTreeWalker(scope, SHOW_TEXT | SHOW_ELEMENT, null);
    var styles = new WeakMap();
    var last = null;
    for (var node = walker.nextNode(); node; node = walker.nextNode()) {
      var el;
      if (node.nodeType === 1) {
        if (!svgPoint(node)) { continue; }
        el = node;
      } else {
        var holder = node.parentElement;
        if (!/\d/.test(node.nodeValue) || (holder && holder.namespaceURI === SVG_NS && /^(title|desc)$/.test(holder.localName))) { continue; }
        el = valueTarget(node);
      }
      if (!el || el === last || selfFocusable(el) || (region && regionFor(el) !== region) ||
          (!includeInvisible && !isVisible(el, styles))) { continue; }
      last = el;
      if (visit(el) === false) { return; }
    }
  }

  function controlNumber(control) {
    if (!control || control.nodeType !== 1 || !root.contains(control) || control.closest(EXCLUDE)) { return null; }
    if (!selfFocusable(control) || control.hasAttribute("data-evidence-region")) { return null; }
    var found = null;
    var primary = control.querySelector("[data-evidence-primary]");
    if (primary) {
      eachItem(primary, null, function (el) { if (control.contains(el) && el !== control) { found = el; return false; } });
      if (found) { return found; }
    }
    eachItem(control, null, function (el) { if (control.contains(el) && el !== control) { found = el; return false; } });
    return found;
  }

  function firstItem(region) {
    var found = null;
    eachItem(region, region, function (el) { found = el; return false; });
    return found;
  }

  function itemsIn(region) {
    var out = [];
    eachItem(region, region, function (el) { if (out[out.length - 1] !== el) { out.push(el); } });
    return out;
  }

  function itemInCell(cell, region, fromEnd) {
    var found = null;
    if (cell) { eachItem(cell, region, function (el) { found = el; return fromEnd ? undefined : false; }); }
    return found;
  }

  function cellStep(cell, region, dRow, dCol) {
    var rows = region.rows;
    var r = cell.parentElement.rowIndex;
    var c = cell.cellIndex;
    for (var guard = 0; guard < 2000; guard += 1) {
      if (dCol) {
        c += dCol;
        if (c < 0 || c >= rows[r].cells.length) { return null; }
      } else {
        r += dRow;
        if (r < 0 || r >= rows.length) { return null; }
        c = Math.min(cell.cellIndex, rows[r].cells.length - 1);
      }
      var next = itemInCell(rows[r].cells[c], region, dCol < 0);
      if (next) { return next; }
    }
    return null;
  }

  function stepInCell(cell, region, cur, dir) {
    var items = [];
    eachItem(cell, region, function (el) { items.push(el); });
    var i = items.indexOf(cur);
    return i < 0 ? null : items[i + dir] || null;
  }

  function deactivate() {
    if (active) { active.classList.remove("app-evidence-active"); }
    if (tipFor === active) { hideTip(); }
  }

  function setActive(region, el) {
    deactivate();
    active = el;
    activeRegion = region;
    el.classList.add("app-evidence-active");
    if (el.scrollIntoView) { el.scrollIntoView({ block: "nearest", inline: "nearest" }); }
    showTip(el, "region");
    var ev = evidenceFor(el);
    var where = ev.context.column || ev.context.label || ev.context.section;
    live.textContent = ev.value + (where ? ", " + where : "");
  }

  function currentItem(region) {
    return activeRegion === region && active && region.contains(active) &&
      regionFor(active) === region && !selfFocusable(active) && valueTarget(active) === active && isVisible(active)
      ? active : null;
  }

  function regionKey(event, region) {
    var key = event.key;
    if (key === "Escape") { deactivate(); return; }
    var moves = ["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Home", "End"];
    var open = key === "Enter" || key === " ";
    if (!open && moves.indexOf(key) < 0) { return; }
    event.preventDefault();
    var cur = currentItem(region);
    if (!cur && activeRegion === region) { deactivate(); active = null; }
    if (open) {
      var target = cur || firstItem(region);
      if (target) { event.stopPropagation(); openFor(target); }
      return;
    }
    var next = null;
    var cell = cur && region.tagName === "TABLE" ? cur.closest("td, th") : null;
    if (!cur) {
      next = firstItem(region);
    } else if (key === "Home") {
      next = firstItem(region);
    } else if (key === "End") {
      var all = itemsIn(region);
      next = all[all.length - 1];
    } else if (cell) {
      var dir = key === "ArrowRight" ? 1 : key === "ArrowLeft" ? -1 : 0;
      next = (dir && stepInCell(cell, region, cur, dir)) ||
        (dir ? cellStep(cell, region, 0, dir) : cellStep(cell, region, key === "ArrowDown" ? 1 : -1, 0));
    } else {
      var items = itemsIn(region);
      var i = items.indexOf(cur);
      next = key === "ArrowRight" || key === "ArrowDown" ? items[i + 1] : items[i - 1];
    }
    if (next) { setActive(region, next); }
  }

  var COMPOUND = /^[\d\s.,%\u2030\u00d7()\/+\-\u2212\u2013\u2014\u00b1\u2248~=\u2192\u2190]+$/;
  var DATE_PART = /(?<!\d[.,]?)(?:(?:0[1-9]|[12]\d|3[01])\/(?:0[1-9]|1[0-2])(?!\/)|\d{1,2}\/\d{1,2}\/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}:\d{2}(?::\d{2})?)(?![.,]?\d)/g;
  var TOKEN = /(?<![\p{L}\d.,])(?:[+\-\u2212](?=\d)|\u00b1\s?(?=\d))?(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?![.,]?\d)|\d+(?:[.,]\d+)*)(?:[eE][+\-]?\d+)?(?:\s?(?:%|\u2030|\u00d7))?(?![\p{L}\d])/gu;
  var CELLISH = "td, th, dd, li";
  var CONTROL = "a[href], button, label, summary, [role='button'], [role='link'], [role='tab'], " +
    "[role='checkbox'], [role='switch'], [role='option'], [onclick]";
  var MONTH_DAY = /^(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$/;
  var BRACKET_LIST = /\[(\d+(?:,\s?\d+)+)\]/g;

  function tokenRanges(value) {
    var taken = [];
    DATE_PART.lastIndex = 0;
    for (var d = DATE_PART.exec(value); d; d = DATE_PART.exec(value)) { taken.push([d.index, d.index + d[0].length]); }
    var out = [];
    BRACKET_LIST.lastIndex = 0;
    for (var g = BRACKET_LIST.exec(value); g; g = BRACKET_LIST.exec(value)) {
      taken.push([g.index, g.index + g[0].length]);
      var digits = /\d+/g;
      for (var n = digits.exec(g[1]); n; n = digits.exec(g[1])) {
        var at = g.index + 1 + n.index;
        out.push([at, at + n[0].length]);
      }
    }
    TOKEN.lastIndex = 0;
    for (var m = TOKEN.exec(value); m; m = TOKEN.exec(value)) {
      var a = m.index;
      var b = a + m[0].length;
      var covered = taken.some(function (r) { return a < r[1] && b > r[0]; });
      if (!covered) { out.push([a, b]); }
    }
    return out.sort(function (x, y) { return x[0] - y[0]; });
  }

  function splittable(parent, whole) {
    var marked = parent.closest("[data-evidence-split]");
    if (marked && root.contains(marked)) { return whole.length <= 600; }
    if (whole.length > 120) { return false; }
    if (COMPOUND.test(whole)) { return true; }
    var cell = parent.closest(CELLISH);
    return Boolean(cell && root.contains(cell) && norm(cell.textContent).length <= 80);
  }

  function splitCompound() {
    var walker = doc.createTreeWalker(root, SHOW_TEXT, null);
    var todo = [];
    for (var node = walker.nextNode(); node; node = walker.nextNode()) {
      var parent = node.parentElement;
      if (!parent || !/\d/.test(node.nodeValue) || valueTarget(node)) { continue; }
      if (parent.closest(EXCLUDE) || parent.closest(".app-evidence-token") || parent.closest(CONTROL)) { continue; }
      if (parent.namespaceURI === SVG_NS) { continue; }
      var whole = norm(parent.textContent);
      if (parent.closest("th") && MONTH_DAY.test(whole)) { continue; }
      if (!splittable(parent, whole)) { continue; }
      var ranges = tokenRanges(node.nodeValue);
      if (ranges.length) { todo.push([node, ranges]); }
    }
    todo.forEach(function (job) {
      var text = job[0];
      var value = text.nodeValue;
      var parts = doc.createDocumentFragment();
      var at = 0;
      job[1].forEach(function (r) {
        if (r[0] > at) { parts.appendChild(doc.createTextNode(value.slice(at, r[0]))); }
        parts.appendChild(mk("span", "app-evidence-token", value.slice(r[0], r[1])));
        at = r[1];
      });
      if (at < value.length) { parts.appendChild(doc.createTextNode(value.slice(at))); }
      text.parentNode.replaceChild(parts, text);
    });
  }

  var scanTimer = 0;
  function scan() {
    scanTimer = 0;
    splitCompound();
    var seen = [];
    eachItem(root, null, function (el) {
      var region = regionFor(el);
      if (seen.indexOf(region) < 0) { seen.push(region); markRegion(region); }
    }, true);
  }
  function scheduleScan() { if (!scanTimer) { scanTimer = setTimeout(scan, 250); } }
  scan();
  if (win.MutationObserver) { new win.MutationObserver(scheduleScan).observe(root, { childList: true, subtree: true }); }

  doc.addEventListener("keydown", function (event) {
    var region = event.target && event.target.hasAttribute && event.target.hasAttribute("data-evidence-region")
      ? event.target : null;
    if (region && !drawerOpen()) { regionKey(event, region); return; }
    if (event.key === "Escape" && tipFor && !drawerOpen()) { hideTip(); return; }
    if (event.key !== "Enter" && event.key !== " ") { return; }
    var el = valueTarget(event.target);
    if (!el || el !== event.target) { el = event.key === "Enter" && event.altKey ? controlNumber(event.target) : null; }
    if (!el) { return; }
    var own = el === event.target && el.hasAttribute("data-evidence") && !isInteractive(el);
    if (own || (event.key === "Enter" && event.altKey)) {
      event.preventDefault();
      event.stopPropagation();
      openFor(el);
    }
  }, true);

  win.appEvidence = {
    register: function (id, entry) { if (id && entry) { registry.values[String(id)] = entry; } },
    evidenceFor: function (el) { return el ? evidenceFor(el) : null; },
    open: function (el) { return el ? openFor(el) : null; },
    close: closeDrawer,
    find: valueTarget,
  };
})();
