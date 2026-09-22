/*! UI dock — external (CSP: script-src 'self') */
(function () {
  function boot(root) {
    if (!root || root.getAttribute("data-dock-ready") === "1") return;
    root.setAttribute("data-dock-ready", "1");
    var prefix =
      root.getAttribute("data-ui-dock") ||
      (root.classList.contains("dock") ? "dock" : "ui-dock");
    var groupSel = "." + prefix + "-group";
    var btnSel = "." + prefix + "-btn";
    document.documentElement.classList.add("ui-js");
    var groups = Array.prototype.slice.call(root.querySelectorAll(groupSel));

    function set(g, open) {
      g.classList.toggle("ui-open", open);
      var b = g.querySelector(btnSel);
      if (b) b.setAttribute("aria-expanded", open ? "true" : "false");
    }
    function shut(except) {
      for (var i = 0; i < groups.length; i++) {
        if (groups[i] !== except) set(groups[i], false);
      }
    }

    root.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest(btnSel);
      if (!b) return;
      var g = b.closest(groupSel);
      if (!g) return;
      var open = !g.classList.contains("ui-open");
      shut(g);
      set(g, open);
    });
    document.addEventListener("click", function (e) {
      if (!(e.target.closest && e.target.closest("." + prefix))) shut(null);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      var g = root.querySelector(groupSel + ".ui-open");
      if (!g) return;
      var b = g.querySelector(btnSel);
      shut(null);
      if (b) b.focus();
    });
    root.addEventListener("focusout", function (e) {
      if (!e.relatedTarget || !root.contains(e.relatedTarget)) shut(null);
    });
  }

  function run() {
    var nodes = document.querySelectorAll(
      "[data-ui-dock], nav.dock, nav.ui-dock, .ui-dock, .dock"
    );
    for (var i = 0; i < nodes.length; i++) boot(nodes[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
