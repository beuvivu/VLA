/* Hành vi khung ứng dụng: thu/mở điều hướng, đổi nhóm, tìm chức năng, đổi
   chế độ màu.

   KHÔNG dùng bất kỳ cách ghi DOM nào nhận chuỗi rồi tự phân tích thành thẻ.
   Mọi thay đổi ở đây là bật/tắt lớp, đặt thuộc tính, hoặc gán textContent.
   Kho có phép kiểm dò việc này, và luật đứng ngay cả khi phép kiểm không phủ
   tới tệp này. */
(function () {
  "use strict";

  var doc = document;
  var body = doc.body;
  var KHOA_PANEL = "app-panel-open";
  var KHOA_THEME = "app-theme";

  function lay(id) { return doc.getElementById(id); }

  var rail = lay("app-rail");
  var panel = lay("app-panel");
  var toggle = lay("app-toggle");
  var scrim = lay("app-scrim");
  var search = lay("app-search");
  var searchEmpty = lay("app-search-empty");
  var searchOpen = lay("app-search-open");
  var themeBtn = lay("app-theme");
  var panelTitle = lay("app-panel-title");

  if (!rail || !panel) { return; }

  var hep = function () { return window.matchMedia("(max-width:1199.98px)").matches; };

  /* --- Thu / mở --------------------------------------------------------- */

  function datTrangThai(mo) {
    /* Trả focus trước khi khóa panel; scrim và resize cũng đi qua đây. */
    if (!mo && toggle && (panel.contains(doc.activeElement) || (hep() && rail.contains(doc.activeElement)))) {
      toggle.focus();
    }
    body.classList.toggle("app-panel-open", mo);
    body.classList.toggle("app-nav-open", mo && hep());
    panel.inert = !mo;
    panel.setAttribute("aria-hidden", mo ? "false" : "true");
    rail.inert = hep() && !mo;
    var main = lay("app-main");
    if (main) { main.inert = mo && hep(); }
    if (toggle) { toggle.setAttribute("aria-expanded", mo ? "true" : "false"); }
    if (scrim) { scrim.hidden = !(mo && hep()); }
    try { localStorage.setItem(KHOA_PANEL, mo ? "1" : "0"); } catch (e) { /* chế độ riêng tư */ }
  }

  function dangMo() { return body.classList.contains("app-panel-open"); }

  if (toggle) {
    toggle.addEventListener("click", function () { datTrangThai(!dangMo()); });
  }
  if (scrim) {
    scrim.addEventListener("click", function () { datTrangThai(false); });
  }
  doc.addEventListener("keydown", function (ev) {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault(); datTrangThai(true); if (search) { search.focus(); }
    }
    if (ev.key === "Escape" && dangMo()) {
      datTrangThai(false); if (toggle) { toggle.focus(); }
    }
    if (ev.key === "Tab" && hep() && dangMo()) {
      var focusables = [].slice.call(doc.querySelectorAll(
        '.app-header a, .app-header button, .app-rail button, .app-panel input, .app-panel a, .app-panel summary'
      )).filter(function (e) { return e.getClientRects().length && !e.closest('[hidden]'); });
      var first = focusables[0], last = focusables[focusables.length - 1];
      if (ev.shiftKey && doc.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && doc.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
  });

  /* Khôi phục lựa chọn cũ. Ở màn hẹp luôn bắt đầu ở trạng thái đóng: mở sẵn
     một tấm phủ toàn màn khi vừa vào trang là chặn ngay nội dung người đọc
     vừa bấm vào. */
  var luu = null;
  try { luu = localStorage.getItem(KHOA_PANEL); } catch (e) { luu = null; }
  datTrangThai(!hep() && luu === "1");

  /* Đổi bề ngang qua mốc thì trạng thái phủ không còn nghĩa cũ. */
  var narrowBefore = hep();
  window.addEventListener("resize", function () {
    var narrowNow = hep();
    if (narrowNow !== narrowBefore) {
      narrowBefore = narrowNow;
      datTrangThai(false);
    }
  });

  /* --- Chọn nhóm cấp một ------------------------------------------------ */

  var nutNhom = [].slice.call(doc.querySelectorAll(".app-rail-btn"));
  var nhomPanel = [].slice.call(doc.querySelectorAll(".app-panel-group"));

  function moNhom(chiSo) {
    if (search) { search.value = ""; }
    [].slice.call(doc.querySelectorAll(".app-nav-item")).forEach(function (a) { a.hidden = false; });
    if (searchEmpty) { searchEmpty.hidden = true; }
    nutNhom.forEach(function (b) {
      b.setAttribute("aria-selected", b.getAttribute("data-app-group") === chiSo ? "true" : "false");
    });
    nhomPanel.forEach(function (g) {
      g.hidden = g.getAttribute("data-app-group") !== chiSo;
    });
    var nut = nutNhom.filter(function (b) { return b.getAttribute("data-app-group") === chiSo; })[0];
    if (nut && panelTitle) { panelTitle.textContent = nut.getAttribute("title") || ""; }
    datTrangThai(true);
  }

  nutNhom.forEach(function (b) {
    b.addEventListener("click", function () { moNhom(b.getAttribute("data-app-group")); });
    b.addEventListener("keydown", function (ev) {
      var i = nutNhom.indexOf(b);
      var ke = ev.key === "ArrowDown" ? i + 1 : (ev.key === "ArrowUp" ? i - 1 : -1);
      if (ke >= 0 && ke < nutNhom.length) { ev.preventDefault(); nutNhom[ke].focus(); }
    });
  });

  /* --- Tìm chức năng ---------------------------------------------------- */

  /* Lọc trên chính các mục điều hướng có thật. Không có ô tìm kiếm nào nhận
     chữ rồi không trả về gì: mỗi kết quả là một trang tồn tại trong kho. */
  var mucNav = [].slice.call(doc.querySelectorAll(".app-nav-item"));

  function chuanHoa(tu) {
    return (tu || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[đĐ]/g, "d").trim().toLowerCase();
  }

  function loc(tu) {
    var q = chuanHoa(tu);
    if (!q) {
      nhomPanel.forEach(function (g) {
        g.hidden = g.getAttribute("aria-labelledby") !==
          (nutNhom.filter(function (b) { return b.getAttribute("aria-selected") === "true"; })[0] || {}).id;
      });
      mucNav.forEach(function (a) { a.hidden = false; });
      if (searchEmpty) { searchEmpty.hidden = true; }
      return;
    }
    var khop = 0;
    nhomPanel.forEach(function (g) { g.hidden = false; });
    mucNav.forEach(function (a) {
      var nhan = chuanHoa(a.getAttribute("data-app-label") || a.textContent);
      var hien = nhan.indexOf(q) !== -1;
      a.hidden = !hien;
      if (hien) { khop += 1; }
    });
    nhomPanel.forEach(function (g) {
      var con = [].slice.call(g.querySelectorAll(".app-nav-item")).some(function (a) { return !a.hidden; });
      g.hidden = !con;
    });
    if (searchEmpty) { searchEmpty.hidden = khop !== 0; }
  }

  if (search) {
    search.addEventListener("input", function () { loc(search.value); });
    search.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && search.value) { ev.stopPropagation(); search.value = ""; loc(""); }
    });
  }
  if (searchOpen && search) {
    searchOpen.addEventListener("click", function () {
      datTrangThai(true);
      search.focus();
      search.select();
    });
  }

  /* --- Chế độ màu ------------------------------------------------------- */

  /* Ba trạng thái, không phải hai. Trạng thái "theo hệ" KHÔNG được đặt
     data-ui-theme: đặt vào là đè mất prefers-color-scheme, và người dùng mất
     khả năng đi theo cài đặt máy. */
  var VONG = ["auto", "light", "dark"];
  var TEN = { auto: "Theo hệ thống", light: "Sáng", dark: "Tối" };

  function datTheme(che) {
    if (che === "auto") { doc.documentElement.removeAttribute("data-ui-theme"); }
    else { doc.documentElement.setAttribute("data-ui-theme", che); }
    if (themeBtn) {
      var ic = themeBtn.querySelector(".app-theme-ic");
      if (ic) { ic.setAttribute("data-theme-state", che); }
      themeBtn.setAttribute("title", "Chế độ màu: " + TEN[che]);
      themeBtn.setAttribute("aria-label", "Chế độ màu: " + TEN[che] + ". Bấm để chuyển.");
    }
    try { localStorage.setItem(KHOA_THEME, che); } catch (e) { /* chế độ riêng tư */ }
  }

  var themeLuu = null;
  try { themeLuu = localStorage.getItem(KHOA_THEME); } catch (e) { themeLuu = null; }
  datTheme(VONG.indexOf(themeLuu) === -1 ? "auto" : themeLuu);

  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var hien = doc.documentElement.getAttribute("data-ui-theme") || "auto";
      datTheme(VONG[(VONG.indexOf(hien) + 1) % VONG.length]);
    });
  }
  /* Đường dẫn neo phải phản ánh đúng phần đang xem và đóng menu trên điện thoại. */
  function dongBoDuongDan() {
    var file = location.pathname.split("/").pop() || "index.html";
    if (file === "landing.html" || file === "landing_desktop.html") { file = "index.html"; }
    var target = file + location.hash;
    var currentLink = mucNav.filter(function (a) { return a.getAttribute("href") === target; })[0] ||
      mucNav.filter(function (a) { return a.getAttribute("href") === file; })[0];
    mucNav.forEach(function (a) {
      var active = a === currentLink;
      a.classList.toggle("app-nav-item--active", active);
      if (active) { a.setAttribute("aria-current", "page"); } else { a.removeAttribute("aria-current"); }
    });
    if (!currentLink) { return; }
    var group = currentLink.closest(".app-panel-group").getAttribute("data-app-group");
    nutNhom.forEach(function (b) {
      var active = b.getAttribute("data-app-group") === group;
      b.setAttribute("aria-selected", active ? "true" : "false");
      if (active) {
        if (panelTitle) { panelTitle.textContent = b.title; }
        var crumb = doc.querySelector(".app-crumb:not(.app-crumb--now)");
        if (crumb) { crumb.textContent = b.title; }
      }
    });
    nhomPanel.forEach(function (g) { g.hidden = g.getAttribute("data-app-group") !== group; });
    var pageCrumb = doc.querySelector(".app-crumb--now");
    if (pageCrumb) { pageCrumb.textContent = currentLink.getAttribute("data-app-label"); }
    if (search && search.value) { loc(search.value); }
  }
  dongBoDuongDan();
  window.addEventListener("hashchange", dongBoDuongDan);
  mucNav.forEach(function (a) { a.addEventListener("click", function () { datTrangThai(false); }); });

  [].slice.call(doc.querySelectorAll(".app-section-link")).forEach(function (a) {
    a.addEventListener("click", function () { datTrangThai(false); });
  });

  var full = lay("app-fullscreen");
  if (full) {
    full.hidden = !doc.fullscreenEnabled;
    full.addEventListener("click", function () {
      var action = doc.fullscreenElement ? doc.exitFullscreen() : doc.documentElement.requestFullscreen();
      if (action && action.catch) { action.catch(function () { full.hidden = true; }); }
    });
    doc.addEventListener("fullscreenchange", function () {
      var label = doc.fullscreenElement ? "Thoát toàn màn hình" : "Toàn màn hình";
      full.setAttribute("aria-label", label);
      full.setAttribute("title", label);
      full.setAttribute("aria-pressed", doc.fullscreenElement ? "true" : "false");
    });
  }
})();
