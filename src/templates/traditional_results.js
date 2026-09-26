(() => {
  "use strict";

  const shared = window.TraditionalResults;
  const { decode, weekdayOf, formatDate, renderDraw } = shared;

  const embedded = JSON.parse(document.getElementById("tr-embedded-data").textContent);
  const form = document.getElementById("tr-form");
  const period = document.getElementById("tr-period");
  const weekday = document.getElementById("tr-weekday");
  const customDates = document.getElementById("tr-custom-dates");
  const fromInput = document.getElementById("tr-from");
  const toInput = document.getElementById("tr-to");
  const resultsNode = document.getElementById("tr-results");
  const emptyNode = document.getElementById("tr-empty");
  const emptyDetail = document.getElementById("tr-empty-detail");
  const statusNode = document.getElementById("tr-source-status");
  const submit = form.querySelector('button[type="submit"]');
  const pairMode = document.getElementById("tr-pair-mode");
  const clearButton = document.getElementById("tr-mark-clear");
  const moreNode = document.getElementById("tr-more");
  const moreButton = document.getElementById("tr-more-btn");
  const toggleHeadTail = document.getElementById("tr-toggle-headtail");
  const toggleLoto = document.getElementById("tr-toggle-loto");
  const toggleTail = document.getElementById("tr-toggle-tail");

  let current = [];
  let shown = 0;

  // Dựng dần thay vì dựng hết một lượt.
  //
  // Đo trên Chromium máy bàn: 2 399 kỳ sinh 545 060 nút DOM và mất 2 622 ms
  // để dựng — trên điện thoại tầm trung con số ấy còn tệ hơn nhiều lần. Bộ
  // lọc vẫn chọn TRỌN khoảng (và xuất file vẫn xuất trọn), chỉ phần hiển thị
  // là dựng theo lô.
  //
  //     30 kỳ      6 811 nút     68 ms
  //    300 kỳ     68 178 nút    347 ms
  //  1 000 kỳ    227 227 nút  1 091 ms
  //  2 399 kỳ    545 060 nút  2 622 ms
  const PAGE_SIZE = 100;

  const ALL = embedded.rows.map((row) => decode(row,
    typeof row === "string" ? embedded.draw_metadata?.[row.slice(0, 10)] : undefined))
    .filter((draw) => draw !== null);
  const { paintMarks } = shared.createMarks(resultsNode, { pairMode, clearButton });

  // ---- Chọn khoảng ------------------------------------------------------
  //
  // Mốc nhanh đếm theo SỐ KỲ chứ không theo ngày lịch. XSMB nghỉ quay dịp Tết
  // và đợt giãn cách 2020, nên "lùi 30 ngày lịch" có thể chỉ ra 27 kỳ — và
  // người xem không hiểu vì sao chọn 30 lại được 27. Đếm theo kỳ thì luôn ra
  // đúng số đã chọn, chừng nào lịch sử còn đủ.

  function selectRange() {
    if (period.value === "custom") {
      if (!fromInput.value || !toInput.value) {
        throw new Error("Vui lòng chọn đủ từ ngày và đến ngày.");
      }
      if (fromInput.value > toInput.value) {
        throw new Error("Từ ngày không được sau đến ngày.");
      }
      return ALL.filter((d) => d.date >= fromInput.value && d.date <= toInput.value);
    }
    if (period.value === "all") return ALL.slice();
    const amount = Number(period.value);
    return Number.isFinite(amount) && amount > 0 ? ALL.slice(0, amount) : ALL.slice(0, 30);
  }

  /** Lọc thứ CHẠY SAU khi đã chốt khoảng, không phải trước.
   *
   *  Thứ tự này là một lựa chọn có hệ quả thấy được, nên nói rõ: yêu cầu là
   *  "hiển thị sổ kết quả của riêng các ngày Thứ 2 TRONG KHOẢNG THỜI GIAN ĐÃ
   *  CHỌN". Vậy khoảng là cái được chốt trước, thứ lọc bên trong nó.
   *
   *  Hệ quả: chọn "30 kỳ gần nhất" + "Thứ hai" thì ra khoảng 4 kỳ, không phải
   *  30 kỳ thứ Hai. Con số ấy đúng theo định nghĩa trên nhưng dễ làm người xem
   *  ngỡ ngàng, nên dòng trạng thái phải nói rõ đã lọc từ bao nhiêu kỳ —
   *  xem `statusLine()`. Im lặng ở đây mới là cái sai.
   */
  function selectRows() {
    const rows = selectRange();
    if (weekday.value === "all") return rows;
    const want = Number(weekday.value);
    if (!Number.isInteger(want) || want < 0 || want > 6) return rows;
    return rows.filter((draw) => weekdayOf(draw.date) === want);
  }

  /** Nhãn của thứ đang chọn, lấy thẳng từ ô chọn để không phải chép danh sách
   *  tên thứ lần thứ hai ở đây. */
  function weekdayLabel() {
    return weekday.options[weekday.selectedIndex]?.textContent || "";
  }

  function emptyMessage() {
    const first = ALL.at(-1)?.date;
    const last = ALL[0]?.date;
    if (!first) return "Chưa nạp được dữ liệu nào.";
    // Rỗng vì lọc thứ là chuyện khác hẳn với rỗng vì khoảng sai, và phải nói
    // khác nhau. `selectRange()` có kỳ mà kết quả rỗng thì thủ phạm là ô thứ.
    if (weekday.value !== "all") {
      let inRange = 0;
      try { inRange = selectRange().length; } catch { inRange = 0; }
      if (inRange > 0) {
        return `Khoảng đã chọn có ${inRange} kỳ nhưng không kỳ nào rơi vào `
          + `${weekdayLabel()}. Hãy mở rộng khoảng hoặc chọn thứ khác.`;
      }
    }
    if (period.value !== "custom") return "Hãy chọn khoảng khác.";
    // Nói rõ vì sao rỗng. Bản trước chỉ hiện "Chưa có kết quả trong khoảng đã
    // chọn", đọc như thể hôm ấy không quay — trong khi thật ra ngày đã chọn
    // nằm ngoài dải dữ liệu.
    if (toInput.value < first || fromInput.value > last) {
      return `Khoảng đã chọn nằm ngoài dải dữ liệu. Sổ hiện có từ `
        + `${formatDate(first)} đến ${formatDate(last)}.`;
    }
    return `Không có kỳ nào trong khoảng này. Sổ hiện có từ `
      + `${formatDate(first)} đến ${formatDate(last)}.`;
  }

  function appendPage(count) {
    const fragment = document.createDocumentFragment();
    const until = Math.min(shown + count, current.length);
    for (let i = shown; i < until; i += 1) fragment.append(renderDraw(current[i]));
    shown = until;
    moreNode.before(fragment);
    paintMarks();
    moreNode.hidden = shown >= current.length;
    moreButton.textContent = `Xem thêm ${Math.min(PAGE_SIZE, current.length - shown)} kỳ`
      + ` (còn ${current.length - shown})`;
  }

  /** Dựng nốt phần còn lại — dùng trước khi in, vì trình duyệt chỉ in thứ đã có. */
  function renderEverything() {
    if (shown < current.length) appendPage(current.length - shown);
  }

  function render(rows, message) {
    current = rows;
    shown = 0;
    resultsNode.replaceChildren(moreNode);
    appendPage(PAGE_SIZE);
    emptyNode.hidden = current.length !== 0;
    if (current.length === 0) emptyDetail.textContent = emptyMessage();
    document.getElementById("tr-result-count").textContent = String(current.length);
    document.getElementById("tr-latest").textContent =
      current[0] ? formatDate(current[0].date) : "—";
    document.getElementById("tr-oldest").textContent =
      current.at(-1) ? formatDate(current.at(-1).date) : "—";
    document.getElementById("tr-total-count").textContent = String(ALL.length);
    statusNode.textContent = message || statusLine();
    statusNode.dataset.state = "ready";
  }

  /** Khi có lọc thứ, nói luôn đã lọc từ bao nhiêu kỳ — nếu không, "4 kỳ"
   *  sau khi chọn "30 kỳ gần nhất" trông như trang bị hỏng. */
  function statusLine() {
    if (weekday.value === "all") {
      return `Đang hiển thị ${current.length} kỳ trong tổng số ${ALL.length} kỳ đã lưu.`;
    }
    let inRange = current.length;
    try { inRange = selectRange().length; } catch { /* giữ nguyên */ }
    return `Đang hiển thị ${current.length} kỳ ${weekdayLabel()}, lọc từ `
      + `${inRange} kỳ của khoảng đã chọn (tổng kho ${ALL.length} kỳ).`;
  }

  function refresh() {
    submit.disabled = true;
    try {
      render(selectRows());
    } catch (error) {
      render([], error.message);
      statusNode.dataset.state = "error";
    } finally {
      submit.disabled = false;
    }
  }

  // ---- Tuỳ chọn hiển thị ------------------------------------------------

  function applyLayout() {
    const picked = form.parentElement.querySelector('input[name="tr-layout"]:checked');
    resultsNode.dataset.layout = picked ? picked.value : "1";
  }

  function applyToggles() {
    resultsNode.dataset.headtail = toggleHeadTail.checked ? "on" : "off";
    resultsNode.dataset.loto = toggleLoto.checked ? "on" : "off";
    resultsNode.dataset.tail = toggleTail.checked ? "on" : "off";
  }

  // ---- Xuất dữ liệu -----------------------------------------------------

  function exportRows() {
    const rows = [["Ngày", "Khu vực", "Giải", "Thứ tự", "Kết quả"]];
    for (const draw of current) {
      for (const prize of draw.prizes) {
        prize.values.forEach((value, index) => rows.push([
          draw.date, "Miền Bắc", prize.name, String(index + 1), value,
        ]));
      }
    }
    return rows;
  }

  function download(blob, extension) {
    const first = current.at(-1)?.date || "khong-co-du-lieu";
    const last = current[0]?.date || "khong-co-du-lieu";
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `so-ket-qua-${first}-${last}.${extension}`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function exportCsv() {
    const text = "﻿" + exportRows().map((row) => row.map(csvCell).join(",")).join("\r\n");
    download(new Blob([text], { type: "text/csv;charset=utf-8" }), "csv");
  }

  // Trình tạo ZIP tối thiểu (store/no compression) để xuất một tệp OOXML
  // .xlsx thật, không dùng CDN và không vi phạm CSP của GitHub Pages.
  const encoder = new TextEncoder();
  const crcTable = (() => {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n += 1) {
      let c = n;
      for (let k = 0; k < 8; k += 1) c = (c & 1) ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }

  function write16(view, offset, value) { view.setUint16(offset, value, true); }
  function write32(view, offset, value) { view.setUint32(offset, value >>> 0, true); }
  function joinBytes(parts) {
    const size = parts.reduce((sum, part) => sum + part.length, 0);
    const output = new Uint8Array(size);
    let offset = 0;
    for (const part of parts) { output.set(part, offset); offset += part.length; }
    return output;
  }

  function zip(entries) {
    const locals = [];
    const centrals = [];
    let offset = 0;
    for (const [name, content] of entries) {
      const nameBytes = encoder.encode(name);
      const data = encoder.encode(content);
      const crc = crc32(data);
      const local = new Uint8Array(30 + nameBytes.length);
      const localView = new DataView(local.buffer);
      write32(localView, 0, 0x04034b50); write16(localView, 4, 20); write16(localView, 6, 0x0800);
      write16(localView, 8, 0); write32(localView, 14, crc); write32(localView, 18, data.length);
      write32(localView, 22, data.length); write16(localView, 26, nameBytes.length);
      local.set(nameBytes, 30);
      locals.push(local, data);

      const central = new Uint8Array(46 + nameBytes.length);
      const centralView = new DataView(central.buffer);
      write32(centralView, 0, 0x02014b50); write16(centralView, 4, 20); write16(centralView, 6, 20);
      write16(centralView, 8, 0x0800); write16(centralView, 10, 0); write32(centralView, 16, crc);
      write32(centralView, 20, data.length); write32(centralView, 24, data.length);
      write16(centralView, 28, nameBytes.length); write32(centralView, 42, offset);
      central.set(nameBytes, 46);
      centrals.push(central);
      offset += local.length + data.length;
    }
    const centralSize = centrals.reduce((sum, part) => sum + part.length, 0);
    const end = new Uint8Array(22);
    const endView = new DataView(end.buffer);
    write32(endView, 0, 0x06054b50); write16(endView, 8, entries.length);
    write16(endView, 10, entries.length); write32(endView, 12, centralSize); write32(endView, 16, offset);
    return joinBytes([...locals, ...centrals, end]);
  }

  function xml(value) {
    return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");
  }

  function exportXlsx() {
    const rows = exportRows();
    const columns = rows[0].length;
    const lastColumn = String.fromCharCode(64 + columns);
    const sheetRows = rows.map((row, rowIndex) => `<row r="${rowIndex + 1}">${row.map((value, columnIndex) => (
      `<c r="${String.fromCharCode(65 + columnIndex)}${rowIndex + 1}" t="inlineStr"${rowIndex === 0 ? ' s="1"' : ""}><is><t>${xml(value)}</t></is></c>`
    )).join("")}</row>`).join("");
    const files = [
      ["[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + '<Default Extension="xml" ContentType="application/xml"/>'
        + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + '</Types>'],
      ["_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        + '</Relationships>'],
      ["xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        + 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        + '<sheets><sheet name="Sổ kết quả" sheetId="1" r:id="rId1"/></sheets></workbook>'],
      ["xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        + '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        + '</Relationships>'],
      ["xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + '<fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Arial"/></font></fonts>'
        + '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2946F3"/><bgColor indexed="64"/></patternFill></fill></fills>'
        + '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        + '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        + '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        + '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        + '</styleSheet>'],
      ["xl/worksheets/sheet1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + `<dimension ref="A1:${lastColumn}${rows.length}"/>`
        + '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        + `<cols><col min="1" max="1" width="14" customWidth="1"/><col min="2" max="${columns}" width="18" customWidth="1"/></cols>`
        + `<sheetData>${sheetRows}</sheetData><autoFilter ref="A1:${lastColumn}${rows.length}"/>`
        + '</worksheet>'],
    ];
    download(new Blob([zip(files)], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }), "xlsx");
  }

  // ---- Nối sự kiện ------------------------------------------------------

  period.addEventListener("change", () => {
    customDates.hidden = period.value !== "custom";
    refresh();
  });
  weekday.addEventListener("change", refresh);
  form.addEventListener("submit", (event) => { event.preventDefault(); refresh(); });
  for (const input of [fromInput, toInput]) {
    input.addEventListener("change", () => { if (period.value === "custom") refresh(); });
  }
  for (const radio of document.querySelectorAll('input[name="tr-layout"]')) {
    radio.addEventListener("change", applyLayout);
  }
  for (const toggle of [toggleHeadTail, toggleLoto, toggleTail]) {
    toggle.addEventListener("change", applyToggles);
  }
  document.getElementById("tr-export-csv").addEventListener("click", exportCsv);
  document.getElementById("tr-export-xlsx").addEventListener("click", exportXlsx);
  moreButton.addEventListener("click", () => appendPage(PAGE_SIZE));
  document.getElementById("tr-print").addEventListener("click", () => {
    // In thì phải có đủ. Không dựng nốt thì bản in chỉ có lô đầu tiên, mà
    // trên giấy thì không ai thấy được là đang thiếu.
    renderEverything();
    window.print();
  });

  if (embedded.schema_version !== 2 || ALL.length === 0) {
    statusNode.textContent = "Dữ liệu nhúng không hợp lệ; vui lòng dựng lại trang.";
    statusNode.dataset.state = "error";
    return;
  }
  applyLayout();
  applyToggles();
  refresh();
})();
