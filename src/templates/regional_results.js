(() => {
  "use strict";

  const results = document.getElementById("rg-results");
  const date = document.getElementById("rg-date");
  const province = document.getElementById("rg-province");
  const reset = document.getElementById("rg-reset");
  const empty = document.getElementById("rg-filter-empty");
  if (!results || !date || !province || !reset) return;

  // Chính bộ đánh dấu của Miền Bắc; khóa ô đã bao gồm tỉnh để không lẫn đài.
  const marks = window.TraditionalResults.createMarks(results, {
    pairMode: document.getElementById("rg-pair-mode"),
    clearButton: document.getElementById("rg-mark-clear"),
  });
  marks.paintMarks();
  const cards = [...results.querySelectorAll(".rg-draw")];

  function apply() {
    let visible = 0;
    for (const card of cards) {
      const stationHeaders = [...card.querySelectorAll("thead th[data-province]")];
      const stations = stationHeaders.filter((node) => !province.value || node.dataset.province === province.value);
      for (const node of card.querySelectorAll("[data-province]")) {
        node.hidden = Boolean(province.value && node.dataset.province !== province.value);
      }
      card.hidden = Boolean((date.value && card.dataset.date !== date.value) || !stations.length);
      if (!card.hidden) visible += 1;
      card.querySelector("table").style.setProperty("--rg-visible-provinces", String(stations.length));
      card.querySelector(".rg-station-count").textContent = `${stations.length} đài`;
    }
    if (empty) empty.hidden = visible > 0 || cards.length === 0;
    marks.paintMarks();
  }

  date.addEventListener("change", apply);
  province.addEventListener("change", apply);
  reset.addEventListener("click", () => {
    date.value = "";
    province.value = "";
    apply();
  });
})();
