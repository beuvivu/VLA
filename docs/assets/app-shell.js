/* Hành vi khung ứng dụng: thu/mở điều hướng, đổi nhóm, lọc sidebar và tìm
   chức năng toàn ứng dụng. Chế độ màu do app-theme.js quản lý.

   KHÔNG dùng bất kỳ cách ghi DOM nào nhận chuỗi rồi tự phân tích thành thẻ.
   Mọi thay đổi ở đây là bật/tắt lớp, đặt thuộc tính, hoặc gán textContent.
   Kho có phép kiểm dò việc này, và luật đứng ngay cả khi phép kiểm không phủ
   tới tệp này. */
(function () {
  "use strict";

  var doc = document;
  var body = doc.body;
  var KHOA_PANEL = "app-panel-open";

  function lay(id) { return doc.getElementById(id); }

  var rail = lay("app-rail");
  var panel = lay("app-panel");
  var toggle = lay("app-toggle");
  var scrim = lay("app-scrim");
  var search = lay("app-sidebar-filter");
  var searchEmpty = lay("app-sidebar-filter-empty");
  var searchOpen = lay("app-search-open");
  var panelTitle = lay("app-panel-title");
  var globalDialog = lay("app-global-search");
  var globalInput = lay("app-global-search-input");
  var globalClose = lay("app-global-search-close");
  if (!rail || !panel || body.dataset.appShellReady) { return; }
  body.dataset.appShellReady = "true";
  var dropdowns = [].slice.call(doc.querySelectorAll(".app-dropdown"));

  function closeDropdowns(restoreFocus) {
    dropdowns.forEach(function (container) {
      var button = container.querySelector("button[aria-controls]");
      var menu = lay(button.getAttribute("aria-controls"));
      if (!menu.hidden && restoreFocus) { button.focus(); }
      menu.hidden = true;
      button.setAttribute("aria-expanded", "false");
    });
  }
  dropdowns.forEach(function (container) {
    var button = container.querySelector("button[aria-controls]");
    var menu = lay(button.getAttribute("aria-controls"));
    button.addEventListener("click", function () {
      var open = menu.hidden;
      closeDropdowns(false);
      menu.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    button.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowDown") { return; }
      event.preventDefault(); closeDropdowns(false);
      menu.hidden = false; button.setAttribute("aria-expanded", "true");
      menu.querySelector("a, button:not([hidden])").focus();
    });
  });
  doc.addEventListener("click", function (event) {
    if (!event.target.closest(".app-dropdown")) { closeDropdowns(false); }
  });
  doc.addEventListener("focusin", function (event) {
    if (!event.target.closest(".app-dropdown")) { closeDropdowns(false); }
  });

  var hep = function () {
    try {
      if (typeof window.matchMedia === "function") { return window.matchMedia("(max-width:1199.98px)").matches; }
    } catch (error) { /* Dùng chiều rộng thực khi truy vấn media bị chặn. */ }
    return window.innerWidth < 1200;
  };

  /* --- Thu / mở --------------------------------------------------------- */

  function datTrangThai(mo) {
    /* Trả focus ra trước khi ẩn hoặc khóa vùng đang chứa nó. */
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
    scrim.addEventListener("click", function () {
      /* Nhấn chuột xuống nền phủ có thể đã bỏ focus khỏi menu trước click. */
      if (toggle) { toggle.focus(); }
      datTrangThai(false);
    });
  }
  doc.addEventListener("keydown", function (ev) {
    if (ev.isComposing) { return; }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault(); openGlobalSearch(); return;
    }
    if (globalDialog && globalDialog.open) { globalKeydown(ev); return; }
    if (ev.key === "Escape" && dropdowns.some(function (c) { return !c.querySelector(".app-dropdown-menu").hidden; })) {
      ev.preventDefault(); closeDropdowns(true); return;
    }
    if (ev.key === "Escape" && dangMo()) {
      datTrangThai(false); if (toggle) { toggle.focus(); }
    }
    if (ev.key === "Tab" && hep() && dangMo()) {
      var focusables = [].slice.call(doc.querySelectorAll(
        '.app-header a, .app-header button, .app-rail button, .app-rail a, .app-panel input, .app-panel a, .app-panel summary'
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

  /* --- Lọc chức năng trong nhóm đang chọn ------------------------------ */

  /* Lọc trên chính các mục điều hướng có thật. Không có ô tìm kiếm nào nhận
     chữ rồi không trả về gì: mỗi kết quả là một trang tồn tại trong kho. */
  var mucNav = [].slice.call(doc.querySelectorAll(".app-nav-item"));

  function chuanHoa(tu) {
    return (tu || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[đĐ]/g, "d").trim().toLowerCase();
  }

  function loc(tu) {
    var q = chuanHoa(tu);
    var selected = nutNhom.filter(function (b) { return b.getAttribute("aria-selected") === "true"; })[0];
    var khop = 0;
    nhomPanel.forEach(function (g) {
      g.hidden = !selected || g.getAttribute("aria-labelledby") !== selected.id;
      [].slice.call(g.querySelectorAll(".app-nav-item")).forEach(function (a) {
        var nhan = chuanHoa(a.getAttribute("data-app-label") || a.textContent);
        a.hidden = nhan.indexOf(q) === -1;
        if (!g.hidden && !a.hidden) { khop += 1; }
      });
    });
    if (searchEmpty) { searchEmpty.hidden = khop !== 0; }
  }

  if (search) {
    search.addEventListener("input", function () { loc(search.value); });
    search.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !ev.isComposing && search.value) { ev.stopPropagation(); search.value = ""; loc(""); }
    });
  }

  /* --- Tìm kiếm toàn ứng dụng: trạng thái riêng, không mở/lọc sidebar. --- */
  var globalResults = globalDialog ? Array.from(globalDialog.querySelectorAll(".app-global-result")) : [];
  var globalMatches = [];
  var globalSelected = -1;
  var previousFocus = null;

  function selectGlobal(index) {
    globalSelected = globalMatches.length ? Math.max(0, Math.min(index, globalMatches.length - 1)) : -1;
    globalResults.forEach(function (link) {
      var selected = link === globalMatches[globalSelected];
      link.classList.toggle("app-global-result--active", selected);
      link.setAttribute("aria-selected", selected ? "true" : "false");
    });
    var active = globalMatches[globalSelected];
    if (active) {
      globalInput.setAttribute("aria-activedescendant", active.id);
      if (active.scrollIntoView) { active.scrollIntoView({ block: "nearest" }); }
    } else { globalInput.removeAttribute("aria-activedescendant"); }
  }

  function filterGlobal() {
    var query = chuanHoa(globalInput.value);
    var words = query.split(/\s+/);
    globalMatches = globalResults.filter(function (link) {
      var label = chuanHoa(link.getAttribute("data-app-search"));
      link.hidden = !words.every(function (word) { return label.indexOf(word) !== -1; });
      return !link.hidden;
    });
    lay("app-global-search-empty").hidden = globalMatches.length !== 0;
    lay("app-global-search-status").textContent = globalMatches.length + " chức năng";
    selectGlobal(0);
  }

  function openGlobalSearch() {
    if (!globalDialog || !globalInput) { return; }
    closeDropdowns(false);
    if (!globalDialog.open) {
      previousFocus = doc.activeElement;
      globalDialog.showModal();
      body.classList.add("app-global-search-open");
    }
    globalInput.setAttribute("aria-expanded", "true");
    filterGlobal();
    globalInput.focus();
    globalInput.select();
  }

  function restoreGlobalFocus() {
    /* close có thể đến muộn sau một lần mở mới; không lấy focus khỏi modal ấy. */
    if (globalDialog.open || !previousFocus) { return; }
    body.classList.remove("app-global-search-open");
    globalInput.setAttribute("aria-expanded", "false");
    var target = previousFocus.isConnected && previousFocus !== body ? previousFocus : searchOpen;
    for (var node = target; node; node = node.parentElement) {
      if (node.inert || node.hidden) { target = searchOpen; break; }
    }
    previousFocus = null;
    if (target) { target.focus(); }
  }

  function closeGlobalSearch() {
    if (globalDialog && globalDialog.open) {
      globalDialog.close();
      restoreGlobalFocus();
    }
  }

  function globalKeydown(event) {
    if (event.key === "Escape") { event.preventDefault(); closeGlobalSearch(); return; }
    if (event.key === "Tab") {
      event.preventDefault();
      (doc.activeElement === globalInput ? globalClose : globalInput).focus();
      return;
    }
    if (event.target !== globalInput || event.isComposing) { return; }
    var index = globalSelected;
    if (event.key === "ArrowDown") { index += 1; }
    else if (event.key === "ArrowUp") { index -= 1; }
    else if (event.key === "Home") { index = 0; }
    else if (event.key === "End") { index = globalMatches.length - 1; }
    else if (event.key === "Enter") {
      event.preventDefault();
      if (globalMatches[index]) { globalMatches[index].click(); }
      return;
    } else { return; }
    event.preventDefault();
    selectGlobal(index);
  }

  if (globalDialog && globalInput) {
    globalInput.addEventListener("input", filterGlobal);
    globalClose.addEventListener("click", closeGlobalSearch);
    globalDialog.addEventListener("close", restoreGlobalFocus);
    globalDialog.addEventListener("cancel", function (event) { event.preventDefault(); closeGlobalSearch(); });
    globalDialog.addEventListener("click", function (event) {
      if (event.target.closest(".app-global-result")) {
        datTrangThai(false);
        closeGlobalSearch();
      } else if (event.target === globalDialog) { closeGlobalSearch(); }
    });
    if (searchOpen) { searchOpen.addEventListener("click", openGlobalSearch); }
    if (lay("app-rail-add")) { lay("app-rail-add").addEventListener("click", openGlobalSearch); }
  }
  if (lay("app-rail-exit")) {
    lay("app-rail-exit").addEventListener("click", function () {
      if (toggle) { toggle.focus(); }
      datTrangThai(false);
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
    var previousGroup = nutNhom.filter(function (b) { return b.getAttribute("aria-selected") === "true"; })[0];
    if (search && previousGroup && previousGroup.getAttribute("data-app-group") !== group) { search.value = ""; }
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
    if (search) { loc(search.value); }
  }
  dongBoDuongDan();
  window.addEventListener("hashchange", dongBoDuongDan);
  mucNav.forEach(function (a) { a.addEventListener("click", function () { datTrangThai(false); }); });
  [].slice.call(doc.querySelectorAll('.app-header a[href]')).forEach(function (a) {
    a.addEventListener('click', function () {
      closeDropdowns(true);
      datTrangThai(false);
    });
  });

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
      var caption = full.querySelector("span");
      if (caption) { caption.textContent = label; }
    });
  }
})();
