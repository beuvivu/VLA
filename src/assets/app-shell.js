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
    body.classList.toggle("app-panel-open", mo);
    if (hep()) { body.classList.toggle("app-nav-open", mo); }
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
    if (ev.key === "Escape" && dangMo() && hep()) { datTrangThai(false); }
  });

  /* Khôi phục lựa chọn cũ. Ở màn hẹp luôn bắt đầu ở trạng thái đóng: mở sẵn
     một tấm phủ toàn màn khi vừa vào trang là chặn ngay nội dung người đọc
     vừa bấm vào. */
  var luu = null;
  try { luu = localStorage.getItem(KHOA_PANEL); } catch (e) { luu = null; }
  datTrangThai(!hep() && luu === "1");

  /* Đổi bề ngang qua mốc thì trạng thái phủ không còn nghĩa cũ. */
  window.addEventListener("resize", function () {
    if (!hep()) { body.classList.remove("app-nav-open"); if (scrim) { scrim.hidden = true; } }
    else if (dangMo()) { body.classList.add("app-nav-open"); if (scrim) { scrim.hidden = false; } }
  });

  /* --- Chọn nhóm cấp một ------------------------------------------------ */

  var nutNhom = [].slice.call(doc.querySelectorAll(".app-rail-btn"));
  var nhomPanel = [].slice.call(doc.querySelectorAll(".app-panel-group"));

  function moNhom(chiSo) {
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

  function loc(tu) {
    var q = (tu || "").trim().toLowerCase();
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
      var nhan = (a.getAttribute("data-app-label") || a.textContent || "").toLowerCase();
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
      if (ev.key === "Escape") { search.value = ""; loc(""); }
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
  var NHAN = { auto: "◐", light: "☀", dark: "☾" };
  var TEN = { auto: "Theo hệ thống", light: "Sáng", dark: "Tối" };

  function datTheme(che) {
    if (che === "auto") { doc.documentElement.removeAttribute("data-ui-theme"); }
    else { doc.documentElement.setAttribute("data-ui-theme", che); }
    if (themeBtn) {
      var ic = themeBtn.querySelector(".app-theme-ic");
      if (ic) { ic.textContent = NHAN[che]; }
      themeBtn.setAttribute("title", "Chế độ màu: " + TEN[che]);
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
})();
