/*! Enable non-blocking stylesheets without inline onload (CSP-safe) */
(function () {
  function activate() {
    var links = document.querySelectorAll(
      'link[rel="stylesheet"][media="print"][data-async-css], link[rel="stylesheet"][media="print"][data-ui-visual-system], link[rel="stylesheet"][media="print"][data-ui-css]'
    );
    for (var i = 0; i < links.length; i++) {
      links[i].media = "all";
      links[i].removeAttribute("data-async-css");
    }
    var more = document.querySelectorAll(
      'link[rel="stylesheet"][media="print"][href*="ui.css"], link[rel="stylesheet"][media="print"][href*="ui-visual"]'
    );
    for (var j = 0; j < more.length; j++) {
      more[j].media = "all";
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", activate);
  } else {
    activate();
  }
})();
