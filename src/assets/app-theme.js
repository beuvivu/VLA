/* Khôi phục màu ngay trong head, trước stylesheet và trước khung vẽ đầu. */
(function () {
  "use strict";
  var root = document.documentElement;
  if (root.hasAttribute("data-app-theme-ready")) { return; }
  root.setAttribute("data-app-theme-ready", "true");
  var key = "app-theme";
  var media = null;
  try {
    if (typeof window.matchMedia === "function") { media = window.matchMedia("(prefers-color-scheme: dark)"); }
  } catch (error) { /* Khôi phục lựa chọn đã lưu kể cả khi truy vấn OS bị chặn. */ }
  var choice = "auto";
  var bound = false;

  function valid(value) { return value === "light" || value === "dark" ? value : "auto"; }
  try { choice = valid(localStorage.getItem(key)); } catch (error) { /* Dùng hệ thống khi storage bị chặn. */ }

  function render() {
    var dark = choice === "dark" || (choice === "auto" && !!(media && media.matches));
    root.classList.toggle("dark", dark);
    if (choice === "auto" && media) { root.removeAttribute("data-ui-theme"); }
    else {
      // Không đọc được OS: giữ CSS cùng màu dự phòng, không lưu thành lựa chọn.
      root.setAttribute("data-ui-theme", choice === "auto" ? "light" : choice);
    }
    /* color-scheme thuộc CSS để bản in có thể khôi phục bảng màu sáng. */
    var button = document.getElementById("app-theme");
    if (button) {
      var label = dark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối";
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.setAttribute("aria-pressed", dark ? "true" : "false");
      var icon = button.querySelector(".app-theme-ic");
      if (icon) { icon.setAttribute("data-theme-state", dark ? "dark" : "light"); }
    }
  }

  function bind() {
    if (bound) { return; }
    var button = document.getElementById("app-theme");
    if (!button) { return; }
    bound = true;
    button.addEventListener("click", function () {
      choice = root.classList.contains("dark") ? "light" : "dark";
      try { localStorage.setItem(key, choice); } catch (error) { /* Vẫn đổi màu trong tab hiện tại. */ }
      render();
    });
    render();
  }

  render();
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", bind, { once: true }); }
  else { bind(); }
  function changed() { if (choice === "auto") { render(); } }
  try {
    if (media && media.addEventListener) { media.addEventListener("change", changed); }
    else if (media && media.addListener) { media.addListener(changed); }
  } catch (error) { /* Nút đổi màu và đồng bộ tab vẫn hoạt động. */ }
  window.addEventListener("storage", function (event) {
    if (event.key !== key && event.key !== null) { return; }
    choice = valid(event.newValue);
    render();
  });
})();
