(() => {
  "use strict";

  const EXPECTED = {
    special: [1, 5], prize1: [1, 5], prize2: [2, 5], prize3: [6, 5],
    prize4: [4, 4], prize5: [6, 4], prize6: [3, 3], prize7: [4, 2],
  };
  const embedded = JSON.parse(document.getElementById("tr-embedded-data").textContent);
  const form = document.getElementById("tr-form");
  const period = document.getElementById("tr-period");
  const customDates = document.getElementById("tr-custom-dates");
  const fromInput = document.getElementById("tr-from");
  const toInput = document.getElementById("tr-to");
  const resultsNode = document.getElementById("tr-results");
  const emptyNode = document.getElementById("tr-empty");
  const statusNode = document.getElementById("tr-source-status");
  const submit = form.querySelector('button[type="submit"]');
  let current = [];

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function validDraw(draw) {
    if (!draw || !/^\d{4}-\d{2}-\d{2}$/.test(draw.draw_date || "")) return false;
    if (!Array.isArray(draw.prizes) || draw.prizes.length !== 8) return false;
    const seen = new Set();
    for (const prize of draw.prizes) {
      const shape = EXPECTED[prize?.code];
      if (!shape || seen.has(prize.code) || prize.width !== shape[1]) return false;
      seen.add(prize.code);
      if (!Array.isArray(prize.values) || prize.values.length !== shape[0]) return false;
      if (prize.values.some((value) => !new RegExp(`^[0-9]{${shape[1]}}$`).test(value))) return false;
    }
    return seen.size === Object.keys(EXPECTED).length;
  }

  function validPayload(payload) {
    return payload && payload.schema_version === 1 && Array.isArray(payload.data)
      && payload.data.every(validDraw);
  }

  function sourceText(source) {
    return source?.kind === "xskt_fallback" ? "Bù từ xskt.vn" : "CSDL VLA";
  }

  function formatDate(value, withWeekday = false) {
    const options = withWeekday
      ? { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }
      : { day: "2-digit", month: "2-digit", year: "numeric" };
    return new Intl.DateTimeFormat("vi-VN", { ...options, timeZone: "Asia/Ho_Chi_Minh" })
      .format(new Date(`${value}T12:00:00+07:00`));
  }

  function renderDigitList(values) {
    const box = el("div", "tr-digit-list");
    if (!Array.isArray(values) || values.length === 0) {
      box.append(el("span", "", "—"));
      return box;
    }
    for (const value of values) box.append(el("span", "tr-mini", value));
    return box;
  }

  function renderHeadTail(draw) {
    const section = el("section", "tr-head-tail");
    section.append(el("h3", "", "Lô tô đầu / đuôi"));
    const scroll = el("div", "tr-head-tail-scroll");
    const table = el("table");
    const thead = el("thead");
    const headRow = el("tr");
    for (const label of ["Đầu", "Đuôi tương ứng", "Đuôi", "Đầu tương ứng"]) {
      headRow.append(el("th", "", label));
    }
    thead.append(headRow);
    table.append(thead);
    const tbody = el("tbody");
    for (let digit = 0; digit <= 9; digit += 1) {
      const key = String(digit);
      const row = el("tr");
      row.append(el("td", "tr-digit", key));
      const headValues = el("td");
      headValues.append(renderDigitList(draw.head_tail?.heads?.[key] || []));
      row.append(headValues);
      row.append(el("td", "tr-digit", key));
      const tailValues = el("td");
      tailValues.append(renderDigitList(draw.head_tail?.tails?.[key] || []));
      row.append(tailValues);
      tbody.append(row);
    }
    table.append(tbody);
    scroll.append(table);
    section.append(scroll);
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
      for (const value of prize.values) {
        const number = el("div", "tr-number");
        if (prize.code === "special") {
          number.append(document.createTextNode(value.slice(0, -2)));
          number.append(el("span", "tr-special-tail", value.slice(-2)));
        } else {
          number.textContent = value;
        }
        numbers.append(number);
      }
      row.append(numbers);
      section.append(row);
    }
    return section;
  }

  function renderDraw(draw) {
    const article = el("article", "tr-day");
    const header = el("header", "tr-day-head");
    const title = el("div", "tr-day-title");
    title.append(el("h2", "", `Xổ số ${draw.province?.name || "Hà Nội"}`));
    const time = el("time", "", formatDate(draw.draw_date, true));
    time.dateTime = draw.draw_date;
    title.append(time);
    header.append(title);
    const badge = el("span", "tr-badge", sourceText(draw.source));
    badge.dataset.source = draw.source?.kind || "vla_db";
    header.append(badge);
    article.append(header);
    const grid = el("div", "tr-day-grid");
    grid.append(renderPrizes(draw));
    grid.append(renderHeadTail(draw));
    article.append(grid);
    return article;
  }

  function counts(rows) {
    return rows.reduce((out, draw) => {
      if (draw.source?.kind === "xskt_fallback") out.xskt += 1;
      else out.vla += 1;
      return out;
    }, { vla: 0, xskt: 0 });
  }

  function render(rows, message = "") {
    current = rows.filter(validDraw).sort((a, b) => b.draw_date.localeCompare(a.draw_date));
    resultsNode.replaceChildren();
    const fragment = document.createDocumentFragment();
    for (const draw of current) fragment.append(renderDraw(draw));
    resultsNode.append(fragment);
    emptyNode.hidden = current.length !== 0;
    const sourceCounts = counts(current);
    document.getElementById("tr-result-count").textContent = String(current.length);
    document.getElementById("tr-latest").textContent = current[0]
      ? formatDate(current[0].draw_date) : "—";
    document.getElementById("tr-vla-count").textContent = String(sourceCounts.vla);
    document.getElementById("tr-xskt-count").textContent = String(sourceCounts.xskt);
    statusNode.textContent = message || "Đang dùng dữ liệu chuẩn đã nhúng từ VLA.";
    statusNode.dataset.state = "ready";
  }

  function rangeForLocal() {
    if (period.value === "custom") {
      if (!fromInput.value || !toInput.value) throw new Error("Vui lòng chọn đủ từ ngày và đến ngày.");
      if (fromInput.value > toInput.value) throw new Error("Từ ngày không được sau đến ngày.");
      return embedded.data.filter((draw) => draw.draw_date >= fromInput.value && draw.draw_date <= toInput.value);
    }
    const amount = Number(period.value);
    const latest = embedded.data[0]?.draw_date;
    if (!latest) return [];
    const from = new Date(`${latest}T00:00:00Z`);
    from.setUTCDate(from.getUTCDate() - amount + 1);
    const lower = from.toISOString().slice(0, 10);
    return embedded.data.filter((draw) => draw.draw_date >= lower && draw.draw_date <= latest);
  }

  function apiUrl() {
    const configured = String(window.VLA_RESULTS_API_URL || "").trim();
    if (!configured) return null;
    const url = new URL(configured, window.location.href);
    url.searchParams.set("region", "north");
    url.searchParams.set("province", document.getElementById("tr-province").value);
    if (period.value === "custom") {
      if (!fromInput.value || !toInput.value) throw new Error("Vui lòng chọn đủ từ ngày và đến ngày.");
      url.searchParams.set("from", fromInput.value);
      url.searchParams.set("to", toInput.value);
      url.searchParams.delete("days");
    } else {
      url.searchParams.set("days", period.value);
      url.searchParams.delete("from");
      url.searchParams.delete("to");
    }
    return url;
  }

  async function refresh() {
    submit.disabled = true;
    statusNode.textContent = "Đang kiểm tra CSDL VLA và các ngày còn thiếu…";
    statusNode.dataset.state = "loading";
    try {
      const url = apiUrl();
      if (!url) {
        render(rangeForLocal(), "Worker chưa cấu hình; đang dùng CSDL VLA đã nhúng trong trang.");
        return;
      }
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || `HTTP ${response.status}`);
      if (!validPayload(payload)) throw new Error("API trả dữ liệu sai hợp đồng schema_version=1.");
      const vla = payload.meta?.source_counts?.vla_db || 0;
      const xskt = payload.meta?.source_counts?.xskt_fallback || 0;
      render(payload.data, `Đã tải ${payload.data.length} kỳ: ${vla} từ VLA, ${xskt} kỳ bù từ xskt.vn.`);
    } catch (error) {
      render(rangeForLocal(), `Không kết nối được API; đã chuyển sang dữ liệu VLA nhúng. ${error.message}`);
      statusNode.dataset.state = "error";
    } finally {
      submit.disabled = false;
    }
  }

  function exportRows() {
    const rows = [["Ngày", "Khu vực", "Tỉnh/Thành", "Giải", "Thứ tự", "Kết quả", "Nguồn"]];
    for (const draw of current) {
      for (const prize of draw.prizes) {
        prize.values.forEach((value, index) => rows.push([
          draw.draw_date,
          draw.region?.name || "Miền Bắc",
          draw.province?.name || "Hà Nội",
          prize.name,
          String(index + 1),
          value,
          sourceText(draw.source),
        ]));
      }
    }
    return rows;
  }

  function download(blob, extension) {
    const first = current.at(-1)?.draw_date || "khong-co-du-lieu";
    const last = current[0]?.draw_date || "khong-co-du-lieu";
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
    const text = "\ufeff" + exportRows().map((row) => row.map(csvCell).join(",")).join("\r\n");
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
        + '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF4F46E5"/><bgColor indexed="64"/></patternFill></fill></fills>'
        + '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        + '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        + '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        + '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        + '</styleSheet>'],
      ["xl/worksheets/sheet1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + `<dimension ref="A1:G${rows.length}"/>`
        + '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        + '<cols><col min="1" max="1" width="14" customWidth="1"/><col min="2" max="7" width="18" customWidth="1"/></cols>'
        + `<sheetData>${sheetRows}</sheetData><autoFilter ref="A1:G${rows.length}"/>`
        + '</worksheet>'],
    ];
    download(new Blob([zip(files)], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }), "xlsx");
  }

  period.addEventListener("change", () => {
    customDates.hidden = period.value !== "custom";
    if (period.value === "custom" && !toInput.value) {
      toInput.value = embedded.data[0]?.draw_date || "";
      const from = embedded.data[Math.min(29, embedded.data.length - 1)];
      fromInput.value = from?.draw_date || toInput.value;
    }
  });
  form.addEventListener("submit", (event) => { event.preventDefault(); refresh(); });
  document.getElementById("tr-export-csv").addEventListener("click", exportCsv);
  document.getElementById("tr-export-xlsx").addEventListener("click", exportXlsx);

  if (!validPayload(embedded)) {
    statusNode.textContent = "Dữ liệu nhúng không hợp lệ; vui lòng dựng lại trang.";
    statusNode.dataset.state = "error";
    return;
  }
  render(rangeForLocal());
  if (window.VLA_RESULTS_API_URL) refresh();
})();
