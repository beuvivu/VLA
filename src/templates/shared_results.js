(() => {
  "use strict";

  // Các trang tự chứa dùng cùng một bộ dựng và cùng hành vi đánh dấu.
  if (window.TraditionalResults) return;

  // Bản sao của PRIZE_SPEC bên Python: mã, nhãn, số lượng, độ rộng.
  // `tests/test_traditional_results_page.py` buộc hai bản khớp nhau — lệch
  // nhau thì trang vẫn dựng được nhưng cắt sai chuỗi và hiện số rác.
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

  // ---- Giải mã một dòng nén -------------------------------------------
  // Một dòng là `YYYY-MM-DD` + 107 chữ số. Cắt theo đúng bảng độ rộng ở
  // trên, và từ chối mọi dòng sai độ dài thay vì cắt bừa.

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
    // Không mang ký hiệu của kỳ trước sang ngày đang xem.
    const details = metadata && (!metadata.date || metadata.date === date) ? metadata : {};
    return {
      date, prizes,
      station: typeof details.station === "string" ? details.station : "",
      special_codes: Array.isArray(details.special_codes)
        ? details.special_codes.filter((code) => typeof code === "string" && code.trim()) : [],
    };
  }

  /** Bảng đầu/đuôi tính TẠI TRÌNH DUYỆT thay vì nhúng sẵn — 20 mảng mỗi kỳ
   *  nhân 2 399 kỳ là phần lớn dung lượng của bản trước. */
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

  /** Toàn bộ 27 số LOTO của một kỳ, tăng dần. */
  function lotoNumbers(draw) {
    const out = [];
    for (const prize of draw.prizes) {
      for (const value of prize.values) out.push(value.slice(-2));
    }
    return out.sort();
  }

  /** Thứ trong tuần của một ngày `YYYY-MM-DD`, theo chuẩn JS (Chủ nhật = 0).
   *
   *  ĐỌC KỸ CHỖ NÀY. Hai cách viết hiển nhiên đều SAI:
   *
   *      new Date(value).getDay()                     // sai
   *      new Date(value + "T12:00:00+07:00").getDay() // cũng sai
   *
   *  `getDay()` trả về thứ theo múi giờ CỦA MÁY NGƯỜI XEM, không phải theo
   *  múi giờ đã dựng nên mốc thời gian. Đã đo trong Chromium với ngày
   *  2026-09-14 (thứ Hai ở Việt Nam):
   *
   *      múi giờ người xem      +07 trưa   new Date(d)   Date.UTC
   *      Asia/Ho_Chi_Minh          1 ✓         1 ✓          1 ✓
   *      Europe/London             1 ✓         1 ✓          1 ✓
   *      America/Los_Angeles       0 ✗         0 ✗          1 ✓
   *      Pacific/Honolulu          0 ✗         0 ✗          1 ✓
   *      Australia/Sydney          1 ✓         1 ✓          1 ✓
   *
   *  Người xem ở bờ Tây nước Mỹ sẽ thấy mọi kỳ lệch một ngày, và bộ lọc
   *  "Thứ hai" trả về toàn các kỳ Chủ nhật — sai âm thầm, không báo lỗi.
   *
   *  `Date.UTC` dựng mốc từ ba con số rời, và `getUTCDay()` đọc lại cũng
   *  bằng UTC, nên múi giờ người xem không chen vào được ở cả hai đầu. Ngày
   *  quay XSMB vốn là một NHÃN LỊCH, không phải một thời điểm — đối xử với
   *  nó như nhãn mới đúng.
   */
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

  // ---- Dựng giao diện ---------------------------------------------------

  /** Dãy đuôi của một chữ số đầu.
   *
   *  Ô hiển thị MỘT chữ số đuôi, nhưng giá trị để đánh dấu là cả CẶP
   *  ``đầu + đuôi``. Bản trước lấy chính nội dung ô làm khoá, tức một chữ số
   *  đơn lẻ — bấm ô "2" làm sáng 159 ô mini ở mọi hàng đầu khác nhau và
   *  KHÔNG ô giải nào. Đó không phải cặp LOTO, nên nó vô nghĩa với người
   *  soi cầu.
   */
  function renderDigitList(draw, headDigit, tails) {
    const box = el("div", "tr-digit-list");
    if (!tails || tails.length === 0) {
      box.append(el("span", "tr-dash", "—"));
      return box;
    }
    tails.forEach((tail, index) => {
      // Hiện TRỌN cặp hai chữ số, không phải mỗi chữ số đuôi.
      //
      // Đã đọc cấu trúc bảng loto của trang tham chiếu: hai cột `['Đầu',
      // 'LOTO']`, và ô nội dung là `'02; 08;'` — tức cặp đầy đủ.
      //
      // Việc này còn chữa một chỗ vô lý sẵn có của trang ta: ô mini vốn đã
      // mang cặp đầy đủ trong `data-value` để đánh dấu, nhưng người xem chỉ
      // THẤY một chữ số. Bấm vào ô hiện chữ "2" rồi thấy các ô giải chứa
      // "32" sáng lên thì không cách nào đoán ra vì sao. Nay cái thấy và cái
      // được đánh dấu là một.
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
    // Khối phụ dựng sẵn phía máy chủ (ô cầu vị trí) được CHUYỂN sang, không dựng lại.
    if (extra) grid.append(extra);
    article.append(grid);
    return article;
  }

  function createMarks(resultsNode, options = {}) {
    const pairMode = options.pairMode || { checked: false };
    const clearButton = options.clearButton || null;
    // ---- Đánh dấu số bằng cú nhấp (soi cầu) -------------------------------
    //
    // Dùng MỘT bộ bắt sự kiện đặt trên vùng kết quả, không gắn từng ô. Vùng này
    // có tới hàng chục nghìn ô số và danh sách được dựng lại mỗi lần đổi bộ lọc;
    // gắn từng ô sẽ tốn bằng đó lượt đăng ký mỗi lần dựng.
    //
    // HAI kho đánh dấu, không phải một:
    //
    //   markedCells   khoá theo Ô CỤ THỂ — "ngày | giải | vị trí". Đây là chế
    //                 độ mặc định: bấm ô nào thì đúng ô ấy đổi màu.
    //   markedValues  khoá theo CẶP SỐ hai chữ số. Chỉ dùng khi người xem bật
    //                 ô "Tự động đánh dấu cặp trùng".
    //
    // Vì sao tách đôi thay vì một kho có cờ: một ô có thể đang sáng vì chính nó
    // được bấm, HOẶC vì cặp số của nó đang được đánh dấu. Gộp vào một kho thì
    // không phân biệt được hai trường hợp ấy, và cú bấm tiếp theo sẽ xử lý sai.
    //
    // Cả hai đều khoá theo DỮ LIỆU chứ không theo phần tử, nên dựng lại danh
    // sách — đổi bố cục, xem thêm, đổi khoảng — không làm mất dấu.
    const markedCells = new Set();
    const markedValues = new Set();

    /** Cặp hai chữ số của một ô. Ô giải lấy hai số cuối; ô mini đã mang sẵn. */
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

    /** Một cú bấm, bốn nhánh — và thứ tự giữa chúng là phần quan trọng.
     *
     *  Quy tắc bao trùm: **bấm vào ô đang sáng thì nó tắt**, bất kể nó sáng vì
     *  lý do gì. Nếu nó sáng theo cặp thì cả cặp cùng tắt — đúng như lúc nó
     *  sáng lên. Hai nhánh tắt phải đứng TRƯỚC hai nhánh bật, nếu không một ô
     *  đang sáng theo cặp sẽ bị thêm dấu ô chồng lên và bấm mãi không tắt.
     */
    function toggleMark(node) {
      const value = markValue(node);
      const cell = markCell(node);
      if (value !== null && markedValues.has(value)) markedValues.delete(value);
      else if (cell !== null && markedCells.has(cell)) markedCells.delete(cell);
      else if (pairMode.checked && value !== null) markedValues.add(value);
      else if (cell !== null) markedCells.add(cell);
      else return false;
      return true;
    }

    resultsNode.addEventListener("click", (event) => {
      const node = event.target.closest(".tr-number, .tr-mini");
      if (!node || !resultsNode.contains(node)) return;
      event.stopPropagation();
      if (toggleMark(node)) paintMarks();
    });

    // Bàn phím: ô số phải bấm được bằng Enter/Space, không chỉ bằng chuột.
    resultsNode.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const node = event.target.closest(".tr-number, .tr-mini");
      if (!node || !resultsNode.contains(node)) return;
      event.preventDefault();
      event.stopPropagation();
      node.click();
    });

    // Đổi chế độ KHÔNG xoá dấu đã có. Người xem bật chế độ cặp, đánh vài dấu,
    // rồi tắt đi — những dấu ấy phải còn nguyên, vì họ không hề bỏ chọn chúng.
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

  function mount(resultsNode, draw, options = {}) {
    if (!resultsNode || !draw) return null;
    const extra = resultsNode.querySelector(".tr-day-extra");
    resultsNode.replaceChildren(renderDraw(draw, { ...options, extra }));
    const marks = createMarks(resultsNode, options);
    marks.paintMarks();
    return marks;
  }

  window.TraditionalResults = Object.freeze({
    decode, weekdayOf, formatDate, renderDraw, createMarks, mount,
  });
})();
