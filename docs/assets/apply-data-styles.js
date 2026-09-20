/*! Apply data-bg / data-fg via element.style (allowed under CSP; style= attributes are not) */
(function () {
  function apply(root) {
    var scope = root || document;
    var nodes = scope.querySelectorAll("[data-bg], [data-fg], [data-style]");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var bg = el.getAttribute("data-bg");
      var fg = el.getAttribute("data-fg");
      var st = el.getAttribute("data-style");
      if (bg) el.style.background = bg;
      if (fg) el.style.color = fg;
      if (st) {
        var parts = st.split(";");
        for (var j = 0; j < parts.length; j++) {
          var kv = parts[j].split(":");
          if (kv.length < 2) continue;
          var k = kv[0].trim().toLowerCase();
          var v = kv.slice(1).join(":").trim();
          if (k === "background" || k === "background-color") el.style.background = v;
          else if (k === "color") el.style.color = v;
        }
      }
    }
  }
  function run() {
    apply(document);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
  window.__applyDataStyles = apply;
})();
