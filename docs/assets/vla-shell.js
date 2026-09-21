/*
 * App Shell của VLA: chọn chủ đề và drawer điều hướng trên điện thoại.
 *
 * Ba ràng buộc định hình tệp này, cả ba đều do bộ kiểm của kho cưỡng chế:
 *
 * 1. KHÔNG dùng bất kỳ cách ghi DOM nào nhận chuỗi rồi phân tích nó thành
 *    thẻ. Mọi chữ hiển thị đã có sẵn trong HTML; JavaScript chỉ đổi thuộc
 *    tính, lớp và `textContent`. Ba nhãn của nút chủ đề nằm sẵn trong DOM và
 *    CSS chọn nhãn nào hiện, nên không cần viết thẻ vào DOM lúc chạy.
 *    Tên các cách ghi bị cấm được liệt kê ở `tests/test_security_hardening.py`
 *    — không nhắc lại ở đây để chính tệp này không khớp bộ dò của phép kiểm.
 * 2. CSP `script-src 'self'` nên tệp này là tệp riêng, không nội tuyến.
 * 3. Chạy trước khi vẽ để không nháy chủ đề, nên nó được nạp CHẶN trong
 *    `<head>` chứ không `defer`. Phần cần DOM thì chờ `DOMContentLoaded`.
 *
 * Mọi lần đọc/ghi localStorage đều bọc try/catch: ở chế độ riêng tư hoặc khi
 * site data bị chặn, chính lệnh truy cập NÉM LỖI, và một ngoại lệ ở đây sẽ
 * chặn luôn phần còn lại của tệp.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "vla.theme.v1";
  var STATES = ["system", "light", "dark"];

  function readStored() {
    try {
      var value = window.localStorage.getItem(STORAGE_KEY);
      return STATES.indexOf(value) === -1 ? "system" : value;
    } catch (err) {
      return "system";
    }
  }

  function writeStored(state) {
    try {
      if (state === "system") {
        window.localStorage.removeItem(STORAGE_KEY);
      } else {
        window.localStorage.setItem(STORAGE_KEY, state);
      }
    } catch (err) {
      /* Không lưu được thì lựa chọn chỉ sống trong phiên này. Đó là mất mát
         chấp nhận được; làm hỏng cái nút thì không. */
    }
  }

  /*
   * `data-theme` điều khiển màu, `data-theme-state` điều khiển nhãn nào hiện.
   * Hai thuộc tính riêng biệt là CỐ Ý: ở trạng thái "system" không được đặt
   * `data-theme`, vì đặt nó là ghi đè `prefers-color-scheme` — tức mất luôn
   * khả năng theo hệ điều hành.
   */
  function apply(state) {
    var root = document.documentElement;
    if (state === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", state);
    }
    root.setAttribute("data-theme-state", state);
  }

  apply(readStored());

  function resolved(state) {
    if (state !== "system") {
      return state;
    }
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch (err) {
      return "light";
    }
  }

  function setupTheme() {
    var button = document.querySelector("[data-vla-theme-toggle]");
    if (!button) {
      return;
    }

    function sync() {
      var state = document.documentElement.getAttribute("data-theme-state") || "system";
      /* Nút này KHÔNG phải công tắc hai trạng thái nên không dùng
         `aria-pressed` — nó xoay ba trạng thái. Trình đọc màn hình nhận
         trạng thái qua nhãn đang hiện, và `aria-live` thông báo khi đổi. */
      button.setAttribute("data-state", state);
    }

    sync();
    button.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme-state") || "system";
      var next = STATES[(STATES.indexOf(current) + 1) % STATES.length];
      apply(next);
      writeStored(next);
      sync();
      var live = document.getElementById("vla-theme-live");
      if (live) {
        var labels = { system: "theo hệ thống", light: "sáng", dark: "tối" };
        live.textContent = "Chủ đề: " + labels[next] + " (đang áp dụng: " + (resolved(next) === "dark" ? "tối" : "sáng") + ")";
      }
    });
  }

  function setupDrawer() {
    var sidebar = document.getElementById("vla-sidebar");
    var backdrop = document.getElementById("vla-backdrop");
    var toggle = document.querySelector("[data-vla-nav-toggle]");
    var closeButton = document.querySelector("[data-vla-nav-close]");
    if (!sidebar || !backdrop || !toggle) {
      return;
    }

    var lastFocused = null;

    function focusables() {
      return Array.prototype.filter.call(
        sidebar.querySelectorAll("a[href], button, summary, [tabindex]:not([tabindex='-1'])"),
        function (node) {
          return node.offsetParent !== null || node === document.activeElement;
        }
      );
    }

    function setOpen(open) {
      sidebar.setAttribute("data-open", open ? "true" : "false");
      backdrop.setAttribute("data-open", open ? "true" : "false");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      /* `inert` giữ cho nội dung phía sau không nhận được Tab khi drawer mở.
         Thiếu nó, người dùng bàn phím Tab ra khỏi drawer vào một vùng đang bị
         nền mờ che — focus ở chỗ không thấy được là lỗi nặng hơn cả không có
         drawer. */
      var main = document.getElementById("vla-main");
      if (main) {
        if (open) {
          main.setAttribute("inert", "");
        } else {
          main.removeAttribute("inert");
        }
      }
      document.body.style.overflow = open ? "hidden" : "";
      if (open) {
        lastFocused = document.activeElement;
        var first = focusables()[0];
        if (first) {
          first.focus();
        }
      } else if (lastFocused && typeof lastFocused.focus === "function") {
        lastFocused.focus();
        lastFocused = null;
      }
    }

    function isOpen() {
      return sidebar.getAttribute("data-open") === "true";
    }

    toggle.addEventListener("click", function () {
      setOpen(!isOpen());
    });
    backdrop.addEventListener("click", function () {
      setOpen(false);
    });
    if (closeButton) {
      closeButton.addEventListener("click", function () {
        setOpen(false);
      });
    }

    document.addEventListener("keydown", function (event) {
      if (!isOpen()) {
        return;
      }
      if (event.key === "Escape") {
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      /* Vòng focus trong drawer. Không có nó, Tab thoát ra khỏi drawer đang
         mở và người dùng bàn phím mất dấu con trỏ. */
      var nodes = focusables();
      if (nodes.length === 0) {
        return;
      }
      var first = nodes[0];
      var last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    /* Kéo cửa sổ rộng ra thì sidebar thành cố định; phải nhả `inert` và
       `overflow` của body, nếu không trang bị khoá cuộn ở kích thước mà
       drawer không còn tồn tại. */
    try {
      window.matchMedia("(min-width: 1024px)").addEventListener("change", function (event) {
        if (event.matches && isOpen()) {
          setOpen(false);
        }
      });
    } catch (err) {
      /* Trình duyệt cũ không có addEventListener trên MediaQueryList. */
    }
  }

  function boot() {
    setupTheme();
    setupDrawer();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
