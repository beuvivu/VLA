(() => {
  "use strict";

  if (window.TraditionalResults) return;

  const PRIZES = [
    ["special", "Đặc Biệt", 1, 5],
    ["prize1", "Giải Nhất", 1, 5],
    ["prize2", "Giải Nhì", 2, 5],
    ["prize3", "Giải Ba", 6, 5],
    ["prize4", "Giải Tư", 4, 4],
    ["prize5", "Giải Năm", 6, 4],
    ["prize6", "Giải Sáu", 3, 3],
    ["prize7", "Giải Bảy", 4, 2],
  ];
  const DATE_WIDTH = 10;
  const ROW_WIDTH = DATE_WIDTH + PRIZES.reduce((sum, [, , n, w]) => sum + n * w, 0);

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function decode(row, metadata = {}) {
    if (typeof row !== "string" || row.length !== ROW_WIDTH) return null;
    const date = row.slice(0, DATE_WIDTH);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
    const digits = row.slice(DATE_WIDTH);
    if (!/^\d+$/.test(digits)) return null;
    const prizes = [];
    let cursor = 0;
    for (const [code, name, count, width] of PRIZES) {
      const values = [];
      for (let i = 0; i < count; i += 1) {
        values.push(digits.slice(cursor, cursor + width));
        cursor += width;
      }
      prizes.push({ code, name, width, values });
    }
    const details = metadata && (!metadata.date || metadata.date === date) ? metadata : {};
    return {
      date, prizes,
      station: typeof details.station === "string" ? details.station : "",
      special_codes: Array.isArray(details.special_codes)
        ? details.special_codes.filter((code) => typeof code === "string" && code.trim()) : [],
    };
  }

  function headTail(draw) {
    const heads = Array.from({ length: 10 }, () => []);
    const tails = Array.from({ length: 10 }, () => []);
    for (const prize of draw.prizes) {
      for (const value of prize.values) {
        const two = value.slice(-2);
        heads[Number(two[0])].push(two[1]);
        tails[Number(two[1])].push(two[0]);
      }
    }
    for (let i = 0; i < 10; i += 1) { heads[i].sort(); tails[i].sort(); }
    return { heads, tails };
  }

  function lotoNumbers(draw) {
    const out = [];
    for (const prize of draw.prizes) {
      for (const value of prize.values) out.push(value.slice(-2));
    }
    return out.sort();
  }

  function weekdayOf(value) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  }

  function formatDate(value, withWeekday = false) {
    const options = withWeekday
      ? { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }
      : { day: "2-digit", month: "2-digit", year: "numeric" };
    return new Intl.DateTimeFormat("vi-VN", { ...options, timeZone: "Asia/Ho_Chi_Minh" })
      .format(new Date(`${value}T12:00:00+07:00`));
  }

  function renderDigitList(draw, headDigit, tails) {
    const box = el("div", "tr-digit-list");
    if (!tails || tails.length === 0) {
      box.append(el("span", "tr-dash", "—"));
      return box;
    }
    tails.forEach((tail, index) => {
      const pair = `${headDigit}${tail}`;
      const mini = el("span", "tr-mini", pair);
      mini.dataset.value = pair;
      mini.dataset.cell = `${draw.date}|d${headDigit}|${index}`;
      mini.tabIndex = 0;
      mini.setAttribute("role", "button");
      mini.setAttribute("aria-pressed", "false");
      mini.setAttribute("aria-label", `Đánh dấu số ${pair}`);
      box.append(mini);
    });
    return box;
  }

  function renderHeadTail(draw) {
    const section = el("section", "tr-head-tail");
    section.append(el("h3", "", "Bảng LOTO theo đầu"));
    const scroll = el("div", "tr-head-tail-scroll");
    const table = el("table");
    const thead = el("thead");
    const headRow = el("tr");
    for (const label of ["Đầu", "LOTO"]) headRow.append(el("th", "", label));
    thead.append(headRow);
    table.append(thead);
    const tbody = el("tbody");
    const { heads } = headTail(draw);
    for (let digit = 0; digit <= 9; digit += 1) {
      const row = el("tr");
      row.append(el("td", "tr-digit", String(digit)));
      const cell = el("td", "tr-tails");
      cell.append(renderDigitList(draw, digit, heads[digit]));
      row.append(cell);
      tbody.append(row);
    }
    table.append(tbody);
    scroll.append(table);
    section.append(scroll);
    return section;
  }

  function renderLoto(draw) {
    const section = el("section", "tr-loto");
    section.append(el("h3", "", "Dãy LOTO (27 số)"));
    const list = el("div", "tr-loto-list");
    for (const value of lotoNumbers(draw)) list.append(el("span", "tr-loto-item", value));
    section.append(list);
    return section;
  }

  function renderPrizes(draw) {
    const section = el("section", "tr-prizes");
    for (const prize of draw.prizes) {
      const row = el("div", "tr-prize-row");
      row.dataset.prize = prize.code;
      row.append(el("div", "tr-prize-label", prize.name));
      const numbers = el("div", "tr-number-grid");
      numbers.style.setProperty("--count", String(prize.values.length));
      prize.values.forEach((value, index) => {
        const number = el("div", "tr-number");
        number.dataset.cell = `${draw.date}|${prize.code}|${index}`;
        number.tabIndex = 0;
        number.setAttribute("role", "button");
        number.setAttribute("aria-pressed", "false");
        number.setAttribute("aria-label", `Đánh dấu số ${value.slice(-2)}`);
        if (prize.code === "special") {
          number.append(document.createTextNode(value.slice(0, -2)));
          number.append(el("span", "tr-special-tail", value.slice(-2)));
        } else {
          number.textContent = value;
        }
        numbers.append(number);
      });
      row.append(numbers);
      section.append(row);
    }
    return section;
  }

  function renderDraw(draw, { includeLoto = true, extra = null } = {}) {
    const article = el("article", "tr-day");
    const header = el("header", "tr-day-head");
    const title = el("div", "tr-day-title");
    const station = draw.station ? ` (${draw.station})` : "";
    title.append(el("h2", "", `Xổ số Miền Bắc${station}`));
    const time = el("time", "", formatDate(draw.date, true));
    time.dateTime = draw.date;
    title.append(time);
    const codes = el("div", "tr-special-codes");
    codes.append(el("span", "tr-code-label", "Ký hiệu Đặc Biệt:"));
    if (Array.isArray(draw.special_codes) && draw.special_codes.length) {
      for (const code of draw.special_codes) codes.append(el("span", "tr-special-code", code));
    } else {
      codes.append(el("span", "tr-code-missing", "Chưa có dữ liệu ký hiệu cho kỳ này"));
    }
    title.append(codes);
    header.append(title);
    header.append(el("span", "tr-badge", "Đã đối chiếu"));
    article.append(header);
    const grid = el("div", "tr-day-grid");
    grid.append(renderPrizes(draw));
    const side = el("div", "tr-day-side");
    side.append(renderHeadTail(draw));
    if (includeLoto) side.append(renderLoto(draw));
    grid.append(side);
    if (extra) grid.append(extra);
    article.append(grid);
    return article;
  }

  function createMarks(resultsNode, options = {}) {
    const pairMode = options.pairMode || { checked: false };
    const clearButton = options.clearButton || null;
    const markedCells = new Map();
    const markedValues = new Set();

    function markValue(node) {
      if (node.dataset.value) return node.dataset.value;
      const text = (node.textContent || "").trim();
      return /^\d+$/.test(text) ? text.slice(-2) : null;
    }

    function markCell(node) {
      return node.dataset.cell || null;
    }

    function isMarked(node) {
      if (markedCells.has(markCell(node))) return true;
      const value = markValue(node);
      return value !== null && markedValues.has(value);
    }

    function paintMarks(root = resultsNode) {
      for (const node of root.querySelectorAll(".tr-number, .tr-mini")) {
        if (isMarked(node)) node.dataset.marked = "";
        else delete node.dataset.marked;
        node.setAttribute("aria-pressed", String(isMarked(node)));
      }
      const total = markedCells.size + markedValues.size;
      if (clearButton) {
        clearButton.hidden = total === 0;
        clearButton.textContent = `Bỏ đánh dấu (${total})`;
      }
    }

    function toggleMark(node) {
      const value = markValue(node);
      const cell = markCell(node);
      const clearPairCells = () => {
        for (const [key, ownValue] of markedCells) {
          if (ownValue === value) markedCells.delete(key);
        }
      };
      if (value !== null && markedValues.has(value)) {
        markedValues.delete(value);
        clearPairCells();
      }
      else if (cell !== null && markedCells.has(cell)) markedCells.delete(cell);
      else if (pairMode.checked && value !== null) {
        clearPairCells();
        markedValues.add(value);
      }
      else if (cell !== null) markedCells.set(cell, value);
      else return false;
      return true;
    }

    resultsNode.addEventListener("click", (event) => {
      const node = event.target.closest(".tr-number, .tr-mini");
      if (!node || !resultsNode.contains(node)) return;
      event.stopPropagation();
      if (toggleMark(node)) paintMarks();
    });

    resultsNode.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const node = event.target.closest(".tr-number, .tr-mini");
      if (!node || !resultsNode.contains(node)) return;
      event.preventDefault();
      event.stopPropagation();
      node.click();
    });

    if (pairMode.addEventListener) {
      pairMode.addEventListener("change", () => paintMarks());
    }

    function clear() {
      markedCells.clear();
      markedValues.clear();
      paintMarks();
    }
    if (clearButton) clearButton.addEventListener("click", clear);
    return { paintMarks, clear };
  }

  const SHORT = { special: "ĐB", prize1: "G1", prize2: "G2", prize3: "G3", prize4: "G4", prize5: "G5",
    prize6: "G6", prize7: "G7" };
  const POSITIONS = [];
  for (const [code, , count, width] of PRIZES) {
    for (let index = 0; index < count; index += 1) {
      for (let digit = 0; digit < width; digit += 1) POSITIONS.push({ code, index, digit, count });
    }
  }
  const BRIDGE = "data-bridge-mark";

  function positionLabel(pos) {
    const spec = POSITIONS[pos];
    if (!spec) return "";
    const prize = SHORT[spec.code] + (spec.count > 1 ? "." + (spec.index + 1) : "");
    return `${prize} · chữ số ${spec.digit + 1}`;
  }

  function paintCell(cell, roles) {
    const value = cell.dataset.bridgeValue || cell.textContent.trim();
    const digit = (k) => {
      if (!roles[k]) return document.createTextNode(value[k]);
      const span = el("span", `tr-bridge-src tr-bridge-src--${roles[k]}`, value[k]);
      span.setAttribute("aria-label", `vị trí cầu: ${value[k]}`);
      return span;
    };
    const kids = [];
    const special = Boolean(cell.querySelector(".tr-special-tail") || cell.dataset.bridgeTail);
    const tailFrom = special ? value.length - 2 : value.length;
    for (let k = 0; k < tailFrom; k += 1) kids.push(digit(k));
    if (tailFrom < value.length) {
      const tail = el("span", "tr-special-tail");
      for (let k = tailFrom; k < value.length; k += 1) tail.append(digit(k));
      kids.push(tail);
      cell.dataset.bridgeTail = "1";
    }
    cell.dataset.bridgeValue = value;
    cell.replaceChildren(...kids);
  }

  function clearBridge(root) {
    if (!root) return;
    for (const cell of root.querySelectorAll(`[${BRIDGE}]`)) {
      paintCell(cell, {});
      cell.removeAttribute(BRIDGE);
    }
  }

  function markBridge(root, date, a, b) {
    clearBridge(root);
    if (!root || !/^\d{4}-\d{2}-\d{2}$/.test(String(date))) return 0;
    const cells = new Map();
    for (const [pos, role] of [[a, "a"], [b, "b"]]) {
      const spec = POSITIONS[Number(pos)];
      if (!spec || !Number.isInteger(Number(pos))) return 0;
      const cell = root.querySelector(`.tr-number[data-cell="${date}|${spec.code}|${spec.index}"]`);
      if (!cell) return 0;
      if (!cells.has(cell)) cells.set(cell, {});
      cells.get(cell)[spec.digit] = role;
    }
    for (const [cell, roles] of cells) {
      paintCell(cell, roles);
      cell.setAttribute(BRIDGE, "");
    }
    return cells.size;
  }

  function bindBridgeChips(resultsNode, date) {
    const chipOf = (target) => target && target.closest && target.closest("[data-bridge-a][data-bridge-b]");
    const show = (event) => {
      const chip = chipOf(event.target);
      if (chip) markBridge(resultsNode, date, chip.dataset.bridgeA, chip.dataset.bridgeB);
    };
    const hide = (event) => {
      const chip = chipOf(event.target);
      if (chip && !chip.contains(event.relatedTarget)) clearBridge(resultsNode);
    };
    resultsNode.addEventListener("mouseover", show);
    resultsNode.addEventListener("focusin", show);
    resultsNode.addEventListener("mouseout", hide);
    resultsNode.addEventListener("focusout", hide);
  }

  function mount(resultsNode, draw, options = {}) {
    if (!resultsNode || !draw) return null;
    const extra = resultsNode.querySelector(".tr-day-extra");
    resultsNode.replaceChildren(renderDraw(draw, { ...options, extra }));
    const marks = createMarks(resultsNode, options);
    marks.paintMarks();
    if (resultsNode.querySelector("[data-bridge-a][data-bridge-b]")) bindBridgeChips(resultsNode, draw.date);
    return marks;
  }

  window.TraditionalResults = Object.freeze({
    decode, weekdayOf, formatDate, renderDraw, createMarks, mount, markBridge, clearBridge, positionLabel,
  });
})();
