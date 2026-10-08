/* Bộ số nháp chạy trên thiết bị, không ghi sổ dự báo hoặc gửi giao dịch. */
(() => {
  "use strict";
  document.querySelectorAll("[data-vl-picks]").forEach(board => {
    const buttons = [...board.querySelectorAll("[data-vl-number]")];
    const slots = [...board.querySelectorAll("[data-vl-slot]")];
    const count = board.querySelector("[data-vl-count]");
    const status = board.querySelector("[data-vl-status]");
    const review = board.querySelector("[data-vl-review]");
    const dialog = board.querySelector("dialog");
    const selected = new Set();
    const values = () => [...selected].sort((a, b) => a - b);
    const format = n => String(n).padStart(2, "0");

    function render(message) {
      const sorted = values();
      buttons.forEach(button => {
        const picked = selected.has(Number(button.dataset.vlNumber));
        button.setAttribute("aria-pressed", String(picked));
        button.setAttribute("aria-disabled", String(!picked && selected.size === 6));
      });
      slots.forEach((slot, i) => {
        slot.textContent = sorted[i] === undefined ? "—" : format(sorted[i]);
        slot.classList.toggle("is-filled", sorted[i] !== undefined);
      });
      count.textContent = `${selected.size} / 6`;
      review.disabled = selected.size !== 6;
      status.textContent = message || (selected.size === 6
        ? `Đã chọn 6 số: ${sorted.map(format).join(" · ")}. Bạn có thể xem trước.`
        : `Đã chọn ${selected.size} / 6 số. Chọn thêm ${6 - selected.size} số.`);
    }

    buttons.forEach((button, index) => {
      button.addEventListener("focus", () => {
        buttons.forEach(b => { b.tabIndex = b === button ? 0 : -1; });
      });
      button.addEventListener("click", event => {
        if (event.altKey) return;
        const number = Number(button.dataset.vlNumber);
        if (selected.has(number)) selected.delete(number);
        else if (selected.size < 6) selected.add(number);
        else { status.textContent = "Bạn đã chọn đủ 6 số. Bỏ chọn một số để đổi."; return; }
        render();
      });
      button.addEventListener("keydown", event => {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        const columns = parseInt(getComputedStyle(button.parentElement).getPropertyValue("--vl-grid-cols"), 10) || 9;
        const offsets = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -columns, ArrowDown: columns };
        let next;
        if (event.key === "Home") next = 0;
        else if (event.key === "End") next = buttons.length - 1;
        else if (event.key in offsets) next = Math.max(0, Math.min(buttons.length - 1, index + offsets[event.key]));
        else return;
        event.preventDefault();
        buttons[next].focus();
      });
    });

    board.querySelector("[data-vl-clear]").addEventListener("click", () => {
      selected.clear(); render("Đã xóa bộ số. Chọn 6 số khác nhau để xem trước.");
    });
    board.querySelector("[data-vl-random]").addEventListener("click", () => {
      const pool = buttons.map(button => Number(button.dataset.vlNumber));
      for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
      }
      selected.clear();
      pool.slice(0, 6).forEach(number => selected.add(number));
      render();
    });
    review.addEventListener("click", () => {
      if (selected.size !== 6) return;
      board.querySelector("[data-vl-preview]").textContent = values().map(format).join(" · ");
      dialog.showModal();
    });
    board.querySelector("[data-vl-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => review.focus());
    board.querySelector("[data-vl-download]").addEventListener("click", () => {
      if (selected.size !== 6) return;
      const content = `BỘ SỐ NHÁP — ${board.dataset.vlName}\n${values().map(format).join(" ")}\n\n`
        + "Chưa phải vé đã mua. Bộ số không được gửi đến hệ thống đặt vé.\n";
      const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${board.dataset.vlPicks}-bo-so-nhap.txt`;
      document.body.appendChild(link);
      link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    render();
  });
})();
