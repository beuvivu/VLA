/* Hiệu ứng trang trí độc lập với nội dung và điều hướng. Không giấu con trỏ
   gốc; chỉ cập nhật vị trí khi thật sự có thao tác chuột. */
(function () {
  "use strict";

  var doc = document;
  var body = doc.body;
  if (!body || body.dataset.appDesign !== "crafto" || body.dataset.appMotionReady) { return; }
  body.dataset.appMotionReady = "true";

  var button = doc.getElementById("app-motion-toggle");
  var cursor = doc.querySelector("[data-app-effects] .app-cursor");
  var decorations = Array.from(doc.querySelectorAll("[data-app-parallax]"));
  var reveals = Array.from(doc.querySelectorAll("[data-app-reveal]"));
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var precise = window.matchMedia("(hover: hover) and (pointer: fine)");
  var preference = "on";
  var enabled = false;
  var frame = null;
  var pointer = null;
  var observer = null;

  try {
    if (window.localStorage.getItem("app-motion") === "off") { preference = "off"; }
  } catch (error) { /* Chế độ riêng tư vẫn cho phép đổi hiệu ứng trong phiên này. */ }

  function revealAll() {
    reveals.forEach(function (node) { node.classList.add("app-is-revealed"); });
    if (observer) { observer.disconnect(); }
  }

  function resetPointer() {
    if (frame !== null) { window.cancelAnimationFrame(frame); }
    frame = null;
    pointer = null;
    if (cursor) {
      cursor.classList.remove("app-cursor--visible", "app-cursor--active");
      cursor.style.removeProperty("--app-pointer-x");
      cursor.style.removeProperty("--app-pointer-y");
    }
    decorations.forEach(function (node) {
      node.style.setProperty("--app-parallax-x", "0px");
      node.style.setProperty("--app-parallax-y", "0px");
    });
  }

  function canTrackPointer() { return enabled && precise.matches && !doc.hidden; }

  function syncState() {
    enabled = preference === "on" && !reduced.matches;
    body.dataset.appMotion = enabled ? "on" : "off";
    if (doc.hidden) { body.dataset.appHidden = "true"; }
    else { delete body.dataset.appHidden; }
    resetPointer();
    if (!enabled) { revealAll(); }
    if (button) {
      button.hidden = false;
      button.disabled = reduced.matches;
      button.setAttribute("aria-pressed", enabled ? "true" : "false");
      button.textContent = reduced.matches ? "Giảm chuyển động" : enabled ? "Hiệu ứng: Bật" : "Hiệu ứng: Tắt";
      button.title = reduced.matches ? "Hiệu ứng đã tắt theo thiết lập giảm chuyển động của hệ điều hành" :
        enabled ? "Tắt hiệu ứng chuyển động" : "Bật hiệu ứng chuyển động";
    }
  }

  function updatePointer() {
    frame = null;
    if (!canTrackPointer() || !pointer) { return; }
    if (cursor) {
      cursor.style.setProperty("--app-pointer-x", pointer.x + "px");
      cursor.style.setProperty("--app-pointer-y", pointer.y + "px");
      cursor.classList.add("app-cursor--visible");
      var interactive = pointer.target && pointer.target.closest &&
        pointer.target.closest("a[href], button, [role='button']");
      cursor.classList.toggle("app-cursor--active", Boolean(interactive));
    }
    /* Giới hạn độ lệch ở 6px; không dịch chuyển bảng hoặc nội dung số liệu. */
    var x = Math.max(-1, Math.min(1, pointer.x / Math.max(1, window.innerWidth) * 2 - 1)) * 6;
    var y = Math.max(-1, Math.min(1, pointer.y / Math.max(1, window.innerHeight) * 2 - 1)) * 6;
    decorations.forEach(function (node) {
      node.style.setProperty("--app-parallax-x", Number(x.toFixed(2)) + "px");
      node.style.setProperty("--app-parallax-y", Number(y.toFixed(2)) + "px");
    });
  }

  doc.addEventListener("pointermove", function (event) {
    if (!canTrackPointer()) { return; }
    if (event.pointerType === "touch") { resetPointer(); return; }
    pointer = { x: event.clientX, y: event.clientY, target: event.target };
    if (frame === null) { frame = window.requestAnimationFrame(updatePointer); }
  }, { passive: true });
  doc.addEventListener("pointerleave", resetPointer);
  doc.addEventListener("pointerout", function (event) {
    if (!event.relatedTarget) { resetPointer(); }
  });
  window.addEventListener("blur", resetPointer);
  doc.addEventListener("visibilitychange", syncState);

  function watchMedia(media) {
    if (media.addEventListener) { media.addEventListener("change", syncState); }
    else if (media.addListener) { media.addListener(syncState); }
  }
  watchMedia(reduced);
  watchMedia(precise);

  if (button) {
    button.addEventListener("click", function () {
      if (reduced.matches) { return; }
      preference = preference === "on" ? "off" : "on";
      try { window.localStorage.setItem("app-motion", preference); }
      catch (error) { /* Lựa chọn trong phiên vẫn có hiệu lực khi bộ nhớ bị chặn. */ }
      syncState();
    });
  }

  syncState();
  if (enabled && "IntersectionObserver" in window) {
    observer = new window.IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("app-is-revealed");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    reveals.forEach(function (node) { observer.observe(node); });
  } else { revealAll(); }
})();
