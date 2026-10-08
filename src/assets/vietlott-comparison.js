/* Đối chiếu hồi cứu trên thiết bị; không ghi vào sổ dự báo đã đăng ký. */
(() => {
  "use strict";

  // Mức giải và cơ chế số đặc biệt theo core/games.py của engine Vietlott.
  const games = {
    mega645: {
      name: "Mega 6/45", total: 6, maximum: 45, bonus: "none",
      tiers: [["jackpot1", 6], ["first", 5], ["second", 4], ["third", 3]],
    },
    power655: {
      name: "Power 6/55", total: 6, maximum: 55, bonus: "same_drum",
      tiers: [["jackpot1", 6], ["jackpot2", 5, true], ["first", 5], ["second", 4], ["third", 3]],
    },
    lotto535: {
      name: "Lotto 5/35", total: 5, maximum: 35, bonus: "separate",
      tiers: [["jackpot1", 5, true], ["first", 5], ["second", 4, true], ["third", 4],
        ["fourth", 3, true], ["fifth", 3], ["consolation", 0, true, 2]],
    },
  };
  const tierLabels = {
    jackpot1: "Jackpot", jackpot2: "Jackpot 2", first: "Giải nhất", second: "Giải nhì",
    third: "Giải ba", fourth: "Giải tư", fifth: "Giải năm", consolation: "Khuyến khích",
  };
  const format = number => String(number).padStart(2, "0");
  const percent = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

  function gameFor(product) {
    if (!Object.prototype.hasOwnProperty.call(games, product)) {
      throw new TypeError("Chỉ hỗ trợ Mega 6/45, Power 6/55 và Lotto 5/35.");
    }
    return games[product];
  }

  function integer(value, maximum, label) {
    if (typeof value === "string") {
      if (!/^\d+$/.test(value.trim())) throw new TypeError(`${label} phải là số nguyên từ 1 đến ${maximum}.`);
      value = Number(value.trim());
    }
    if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1 || value > maximum) {
      throw new RangeError(`${label} phải là số nguyên từ 1 đến ${maximum}.`);
    }
    return value;
  }

  function numbersFor(numbers, game, label) {
    if (!Array.isArray(numbers) || numbers.length !== game.total) {
      throw new TypeError(`${label} phải có đúng ${game.total} số khác nhau từ 1 đến ${game.maximum}.`);
    }
    const values = Array.from(numbers, value => integer(value, game.maximum, label));
    if (new Set(values).size !== game.total) {
      throw new RangeError(`${label} phải có ${game.total} số khác nhau; không lặp số.`);
    }
    return values.sort((a, b) => a - b);
  }

  function optionalBonus(value, maximum, label) {
    if (value === undefined || value === null || (typeof value === "string" && !value.trim())) return undefined;
    return integer(value, maximum, label);
  }

  function comparePrediction(product, predicted, actual, { predictedBonus, actualBonus } = {}) {
    const game = gameFor(product);
    const prediction = numbersFor(predicted, game, "Bộ số nhập");
    const result = numbersFor(actual, game, "Kết quả thực tế");
    let bonusMatched = false;
    let tierKnown = true;
    if (game.bonus === "same_drum") {
      if (predictedBonus !== undefined && predictedBonus !== null) {
        throw new TypeError("Power 6/55 chỉ chọn 6 số chính, không chọn số đặc biệt thứ bảy.");
      }
      const bonus = optionalBonus(actualBonus, game.maximum, "Số đặc biệt thực tế");
      if (result.includes(bonus)) throw new RangeError("Số đặc biệt Power phải khác 6 số chính của kết quả thực tế.");
      tierKnown = bonus !== undefined;
      bonusMatched = tierKnown ? prediction.includes(bonus) : null;
    } else if (game.bonus === "separate") {
      const chosen = optionalBonus(predictedBonus, 12, "Số đặc biệt của bộ số nhập");
      const drawn = optionalBonus(actualBonus, 12, "Số đặc biệt thực tế");
      tierKnown = chosen !== undefined && drawn !== undefined;
      bonusMatched = tierKnown ? chosen === drawn : null;
    } else if ((predictedBonus !== undefined && predictedBonus !== null)
      || (actualBonus !== undefined && actualBonus !== null)) {
      throw new TypeError("Mega 6/45 không có số đặc biệt riêng.");
    }
    const actualSet = new Set(result);
    const matchedNumbers = prediction.filter(number => actualSet.has(number));
    const hits = matchedNumbers.length;
    const prize = tierKnown && game.tiers.find(([, minimum, requiresBonus, maximum = minimum]) =>
      hits >= minimum && hits <= maximum && (!requiresBonus || bonusMatched));
    const tier = prize ? prize[0] : null;
    let tierLabel = tierKnown ? (tier ? tierLabels[tier] : "Không trúng giải") : "Chưa đủ số đặc biệt để phân hạng";
    if (tier === "jackpot1" && product === "power655") tierLabel = "Jackpot 1";
    if (tier === "jackpot1" && product === "lotto535") tierLabel = "Độc đắc";
    return { hits, total: game.total, accuracy: hits / game.total * 100, matchedNumbers, bonusMatched, tier, tierLabel, tierKnown };
  }

  window.vietlottComparison = Object.freeze({ comparePrediction });

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function sequence(label, numbers, matchedNumbers, bonus, bonusMatched, powerBonus) {
    const row = element("div", "vl-compare-sequence");
    row.appendChild(element("span", "vl-comparison-row-label", label));
    const balls = element("div", "vl-comparison-balls");
    const matched = new Set(matchedNumbers);
    numbers.forEach(number => {
      const hit = matched.has(number);
      const bonusHit = bonusMatched && powerBonus === number;
      const ball = element("span", "vl-ball", format(number));
      if (hit) ball.classList.add("vl-ball--match", "vl-ball--hit");
      if (bonusHit) ball.classList.add("vl-ball--bonus-hit");
      ball.setAttribute("aria-label", `Số ${format(number)}${hit ? ", khớp số chính" : bonusHit ? ", khớp số đặc biệt" : ", không khớp số chính"}`);
      balls.appendChild(ball);
    });
    if (bonus !== undefined) {
      const ball = element("span", "vl-ball vl-ball--bonus", format(bonus));
      if (bonusMatched) ball.classList.add("vl-ball--bonus-hit");
      const state = bonusMatched === null ? "chưa đủ dữ liệu đối chiếu" : bonusMatched ? "khớp" : "không khớp";
      ball.setAttribute("aria-label", `Số đặc biệt ${format(bonus)}, ${state}`);
      balls.appendChild(ball);
    }
    row.appendChild(balls);
    return row;
  }

  function parseInput(input) {
    return input.value.trim().split(/[\s,;·]+/);
  }

  document.querySelectorAll("[data-vl-comparison-widget]").forEach(widget => {
    const form = widget.matches("form") ? widget : widget.querySelector("form");
    const prediction = widget.querySelector("[data-vl-prediction]");
    const actual = widget.querySelector("[data-vl-actual]");
    const predictedBonus = widget.querySelector("[data-vl-predicted-bonus]");
    const actualBonus = widget.querySelector("[data-vl-actual-bonus]");
    const output = widget.querySelector("[data-vl-comparison-output]");
    const status = widget.querySelector("[data-vl-comparison-status]");
    if (!form || !prediction || !actual || !output || !status) return;
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    output.hidden = true;

    form.addEventListener("submit", event => {
      event.preventDefault();
      output.replaceChildren();
      output.hidden = true;
      if (!actual.value.trim()) {
        status.textContent = "Chưa có kết quả thực tế. Chờ kết quả để đối chiếu.";
        return;
      }
      try {
        const product = widget.dataset.vlComparisonWidget;
        const game = gameFor(product);
        const predicted = parseInput(prediction);
        const drawn = parseInput(actual);
        const options = {};
        if (game.bonus !== "none") options.actualBonus = actualBonus ? actualBonus.value : undefined;
        if (game.bonus === "separate") options.predictedBonus = predictedBonus ? predictedBonus.value : undefined;
        const comparison = comparePrediction(product, predicted, drawn, options);
        const ownBonus = game.bonus === "separate" ? optionalBonus(options.predictedBonus, 12, "Số đặc biệt của bộ số nhập") : undefined;
        const drawnBonus = game.bonus === "none" ? undefined : optionalBonus(options.actualBonus,
          game.bonus === "separate" ? 12 : game.maximum, "Số đặc biệt thực tế");
        output.appendChild(sequence("Bộ số nhập", numbersFor(predicted, game, "Bộ số nhập"), comparison.matchedNumbers,
          ownBonus, comparison.bonusMatched, game.bonus === "same_drum" ? drawnBonus : undefined));
        output.appendChild(sequence("Kết quả thực tế", numbersFor(drawn, game, "Kết quả thực tế"), comparison.matchedNumbers,
          drawnBonus, comparison.bonusMatched));
        const score = `${comparison.hits} / ${comparison.total} số chính · ${percent.format(comparison.accuracy)}%`;
        const scoreNode = element("p", "vl-comparison-score", score);
        scoreNode.setAttribute("data-vl-comparison-score", "");
        scoreNode.dataset.vlComparisonHits = String(comparison.hits);
        scoreNode.dataset.vlComparisonTotal = String(comparison.total);
        scoreNode.dataset.vlComparisonAccuracy = String(comparison.accuracy);
        output.appendChild(scoreNode);
        const tierNode = element("p", "vl-comparison-tier", comparison.tierLabel);
        tierNode.setAttribute("data-vl-comparison-tier", comparison.tierKnown ? (comparison.tier || "none") : "unknown");
        output.appendChild(tierNode);
        const bonusState = comparison.bonusMatched === null ? "chưa đủ dữ liệu" : comparison.bonusMatched ? "khớp" : "không khớp";
        if (game.bonus !== "none") output.appendChild(element("p", "vl-comparison-bonus-status",
          `Số đặc biệt: ${bonusState}. Tỷ lệ chỉ tính số chính.`));
        output.hidden = false;
        status.textContent = `${score}. ${comparison.tierLabel}. Đây là đối chiếu thủ công hồi cứu, không phải dự báo đã đăng ký.`;
      } catch (error) {
        output.replaceChildren();
        status.textContent = error.message;
      }
    });
  });

  document.addEventListener("pointerdown", event => {
    const button = event.target instanceof Element ? event.target.closest(".vl-button") : null;
    if (!button || button.disabled || button.getAttribute("aria-disabled") === "true"
      || (event.button !== undefined && event.button !== 0)
      || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
    button.querySelectorAll(".vl-button-ripple").forEach(ripple => ripple.remove());
    const bounds = button.getBoundingClientRect();
    const ripple = element("span", "vl-button-ripple");
    ripple.setAttribute("aria-hidden", "true");
    ripple.style.setProperty("--vl-ripple-x", `${event.clientX - bounds.left}px`);
    ripple.style.setProperty("--vl-ripple-y", `${event.clientY - bounds.top}px`);
    ripple.style.setProperty("--vl-ripple-size", `${Math.max(bounds.width, bounds.height, 80) * 2}px`);
    button.appendChild(ripple);
    const timeout = setTimeout(() => ripple.remove(), 700);
    ripple.addEventListener("animationend", () => { clearTimeout(timeout); ripple.remove(); }, { once: true });
  });
})();
