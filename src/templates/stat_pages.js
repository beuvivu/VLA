// Bộ máy thống kê chạy phía trình duyệt.
// Toàn bộ lịch sử được nhúng vào trang nên mọi bộ lọc là tức thì, không gọi
// mạng. Xem docstring của src/build_stat_pages.py để biết vì sao.
"use strict";
const DRAWS = window.__D_DEMO_DRAWS__ || window.__D_DRAWS__ || [];
const LOTO_BASELINE = 1 - Math.pow(0.99, 27);
const PAIR_BASELINE = 1 - 2 * Math.pow(0.99, 27) + Math.pow(0.98, 27);

// Mốc "cực đại do ngẫu nhiên" của 4950 cặp, tra theo số kỳ ĐANG CHỌN.
//
// Mốc này tăng theo độ dài lịch sử: 7,7 ở 30 kỳ, 39,9 ở 393, 177,2 ở 2442.
// Ghi chú cố định một con số là sai ngay khi người dùng bấm bộ lọc — chọn
// "30 kỳ" mà vẫn đọc mốc của toàn bộ lịch sử thì lệch tới 25 lần, và bảng
// tuyên bố "bất thường" cho dữ liệu hoàn toàn ngẫu nhiên.
//
// Công thức đóng cần hàm phân phối nhị thức, quá nặng để tính lại trong
// trình duyệt mỗi lần lọc. Thay vào đó dựng sẵn một lưới và nội suy tuyến
// tính: 22 điểm cho sai số tối đa 0,67% (dưới 0,15% với mọi N >= 30).
const PAIR_CHANCE_GRID = window.__D_PAIR_CHANCE__ || [];

/** Cực đại ngẫu nhiên và khoảng 90% cho ``n`` kỳ; null nếu chưa có lưới. */
function pairChanceMaximum(n) {
  const g = PAIR_CHANCE_GRID;
  if (!g.length || n <= 0) return null;
  if (n <= g[0][0]) return { mean: g[0][1], low: g[0][2], high: g[0][3] };
  const last = g[g.length - 1];
  if (n >= last[0]) return { mean: last[1], low: last[2], high: last[3] };
  for (let i = 0; i + 1 < g.length; i++) {
    const a = g[i], b = g[i + 1];
    if (n >= a[0] && n <= b[0]) {
      const t = (n - a[0]) / (b[0] - a[0]);
      return {
        mean: a[1] + t * (b[1] - a[1]),
        low: Math.round(a[2] + t * (b[2] - a[2])),
        high: Math.round(a[3] + t * (b[3] - a[3])),
      };
    }
  }
  return null;
}

/** Viết lại ghi chú mốc ngẫu nhiên theo số kỳ đang chọn. */
function updateChanceNote(nDraws) {
  const el = $("sp-chance");
  if (!el) return;
  const c = pairChanceMaximum(nDraws);
  if (!c) { el.textContent = "—"; return; }
  const fmt = (x) => x.toFixed(1).replace(".", ",");
  el.textContent =
    `Trên lịch sử ngẫu nhiên dài đúng ${nDraws} kỳ, cực đại trung bình là ` +
    `${fmt(c.mean)} lần (khoảng 90%: ${c.low}–${c.high}), trong khi kỳ vọng ` +
    `mỗi cặp chỉ ${fmt(PAIR_BASELINE * nDraws)}.`;
}

const $ = (id) => document.getElementById(id);
const pad2 = (n) => String(n).padStart(2, "0");

/** Các kỳ nằm trong dải đang chọn. */
/** Thứ trong tuần của nhãn ngày `YYYY-MM-DD`, chuẩn JS (Chủ nhật = 0).
 *
 *  KHÔNG dùng `new Date(d).getDay()`. `getDay()` đọc theo múi giờ MÁY NGƯỜI
 *  XEM, không phải múi giờ đã dựng nên mốc. Đã đo trong Chromium với
 *  2026-09-14 (thứ Hai ở Việt Nam): cả `new Date(d).getDay()` lẫn
 *  `new Date(d + "T12:00:00+07:00").getDay()` đều trả 0 (Chủ nhật) khi người
 *  xem ở America/Los_Angeles hoặc Pacific/Honolulu — bộ lọc "Thứ hai" khi ấy
 *  trả về toàn kỳ Chủ nhật, âm thầm, không báo lỗi.
 *
 *  Ngày quay là một NHÃN LỊCH chứ không phải một thời điểm. `Date.UTC` dựng
 *  mốc từ ba con số rời và `getUTCDay()` đọc lại cũng bằng UTC, nên múi giờ
 *  người xem không chen vào được ở cả hai đầu.
 */
function weekdayOf(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
}

function selected() {
  const from = $("sp-from") && $("sp-from").value;
  const to = $("sp-to") && $("sp-to").value;
  let rows = DRAWS;
  if (from) rows = rows.filter((r) => r.d >= from);
  if (to) rows = rows.filter((r) => r.d <= to);
  // Lọc thứ chạy SAU khi đã chốt khoảng, không phải trước: yêu cầu là "các
  // ngày Thứ 2 TRONG khoảng đã chọn".
  const weekday = $("sp-weekday");
  if (weekday && weekday.value !== "all") {
    const want = Number(weekday.value);
    if (Number.isInteger(want) && want >= 0 && want <= 6) {
      rows = rows.filter((r) => weekdayOf(r.d) === want);
    }
  }
  return rows;
}

/** Nhãn ngày hôm nay theo giờ Việt Nam, hoặc "" nếu không dựng được.
 *
 *  Phải quy về múi giờ Việt Nam chứ không dùng đồng hồ máy: người xem ở bờ
 *  Tây nước Mỹ lúc 19h ngày 14 đang là 09h ngày 15 ở Việt Nam, nên "hôm nay"
 *  của họ lệch một ngày so với lịch quay.
 */
function todayInVietnam() {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
  } catch (err) {
    return "";
  }
}

/** Kỳ hôm nay đã có kết quả chưa. Trả về nhãn ngày nếu CHƯA, "" nếu rồi.
 *
 *  Cột chờ phải TÔN TRỌNG bộ lọc thứ. Nó được chèn vào sau khi lọc xong, nên
 *  nếu không tự kiểm thì nó lách qua: đã đo, lọc "Thứ hai" và lọc "Chủ nhật"
 *  đều hiện cột 15-09, trong khi 15-09-2026 là thứ Ba. Một cột chờ nằm sai
 *  thứ thì phá đúng cái mục đích người ta bật bộ lọc lên.
 */
function pendingDay(rows) {
  const today = todayInVietnam();
  if (!today) return "";
  const latest = rows.length ? rows[rows.length - 1].d : "";
  if (today <= latest) return "";
  const weekday = $("sp-weekday");
  if (weekday && weekday.value !== "all" && weekdayOf(today) !== Number(weekday.value)) {
    return "";
  }
  return today;
}

function setCount(rows) {
  const el = $("sp-count");
  if (!el) return;
  const first = rows.length ? rows[0].d : "—";
  const last = rows.length ? rows[rows.length - 1].d : "—";
  el.textContent = `${rows.length} kỳ · ${first} → ${last}`;
}

/** Giải Đặc Biệt ĐỦ 5 CHỮ SỐ, nhấn hai số cuối.
 *
 * Trang gốc liệt kê trọn giải Đặc Biệt chứ không chỉ hai số cuối. Dữ liệu
 * nhúng vốn đã giữ đủ 5 chữ số; bản trước cắt bớt ngay lúc dựng bảng nên
 * người đọc mất phần đầu và không đối chiếu được với kết quả gốc.
 */
function specialFull(value) {
  const s = String(value).padStart(5, "0");
  return `<span class="sp-de">${s.slice(0, 3)}<b>${s.slice(3)}</b></span>`;
}

// --- Ô bảng Đặc Biệt: sáu trường ------------------------------------------
//
// Trang tham chiếu không hiện mỗi con số mà là sáu trường, và có sáu ô đánh
// dấu để bật/tắt từng trường. Giải mã từ dữ liệu thật của họ, kiểm trên 24 ô:
//
//   '570 68 4 6 8 C 13'
//    │   │  │ │ │ │ └─ Bộ
//    │   │  │ │ │ └─── Chẵn/Lẻ  (theo Đuôi)
//    │   │  │ │ └───── Đuôi     (chữ số hàng đơn vị)
//    │   │  │ └─────── Đầu      (chữ số hàng chục)
//    │   │  └───────── Tổng     ((Đầu + Đuôi) mod 10)
//    │   └──────────── hai số cuối
//    └──────────────── ba số đầu
//
// Bộ gom một con với bóng-dương và số lộn của nó: 68 thuộc bộ 13 vì 6 có
// bóng 1 và 8 có bóng 3. Bảng tra dựng sẵn phía Python từ
// number_reference.bo_family_id, không cài lại công thức ở đây — một bản chép
// thứ hai là một bản sẽ trôi khỏi bản gốc.
const BO_LOOKUP = window.__D_BO__ || [];

const DE_FIELDS = [
  { key: "ngay", label: "Ngày", hint: "Ngày quay, dạng ngày-tháng" },
  { key: "tong", label: "Tổng", hint: "(Đầu + Đuôi) chia lấy dư 10" },
  { key: "dau", label: "Đầu", hint: "Chữ số hàng chục của hai số cuối" },
  { key: "duoi", label: "Đuôi", hint: "Chữ số hàng đơn vị của hai số cuối" },
  {
    key: "chanle",
    label: "Chẵn lẻ",
    hint: "Hai ký tự: chẵn/lẻ của Đầu, rồi của Đuôi. 68 cho CC vì 6 và 8 đều chẵn",
  },
  {
    key: "bo",
    label: "Bộ",
    hint: "Họ bộ số: gom một con với bóng dương và số lộn của nó. " +
      "68 thuộc bộ 13 vì bóng của 6 là 1, bóng của 8 là 3. Có 15 họ",
  },
];

const FIELD_KEY = "sp.defields." + (location.pathname.split("/").pop() || "index");
let SHOWN = new Set(DE_FIELDS.map((f) => f.key));
try {
  const saved = localStorage.getItem(FIELD_KEY);
  if (saved) SHOWN = new Set(JSON.parse(saved));
} catch (e) { /* cửa sổ ẩn danh ném lỗi ngay ở lệnh đọc */ }

/** Ô bảng Đặc Biệt đầy đủ: giải 5 số cộng các trường đang bật. */
function specialCell(value, iso) {
  const s = String(value).padStart(5, "0");
  const two = s.slice(3);
  const dau = +two[0];
  const duoi = +two[1];

  // Mỗi trường mang title riêng: người đọc trỏ vào con số là biết nó là gì,
  // không phải đối chiếu ngược lên hàng chú giải rồi đếm cột.
  const tip = (key) => (DE_FIELDS.find((f) => f.key === key) || {}).hint || "";
  const parts = [];
  if (iso && SHOWN.has("ngay")) {
    parts.push(`<i class="sp-f sp-f-ngay" title="Ngày ${iso}">` +
      `${iso.slice(8)}-${iso.slice(5, 7)}</i>`);
  }
  if (SHOWN.has("tong")) {
    parts.push(`<i class="sp-f" title="Tổng — ${tip("tong")}">${(dau + duoi) % 10}</i>`);
  }
  if (SHOWN.has("dau")) parts.push(`<i class="sp-f" title="Đầu — ${tip("dau")}">${dau}</i>`);
  if (SHOWN.has("duoi")) parts.push(`<i class="sp-f" title="Đuôi — ${tip("duoi")}">${duoi}</i>`);
  if (SHOWN.has("chanle")) {
    // HAI ký tự: chẵn/lẻ của Đầu rồi của Đuôi. Hai trang tham chiếu khác nhau
    // ở chỗ này — hainhay chỉ ghi một ký tự theo Đuôi, thongkemienbac ghi cả
    // hai. Lấy bản hai ký tự vì nó chứa trọn thông tin của bản kia.
    // Kiểm trên 15 ô thật: 49 -> "CL" (Đầu 4 chẵn, Đuôi 9 lẻ).
    parts.push(`<i class="sp-f" title="Chẵn/Lẻ — ${tip("chanle")}">` +
      `${dau % 2 === 0 ? "C" : "L"}${duoi % 2 === 0 ? "C" : "L"}</i>`);
  }
  if (SHOWN.has("bo")) {
    parts.push(`<i class="sp-f" title="Bộ — ${tip("bo")}">${BO_LOOKUP[+two] || ""}</i>`);
  }

  // Gọi lại specialFull thay vì chép markup: hai bản dựng cùng một thứ là hai
  // bản sẽ lệch nhau khi ai đó sửa một bên.
  return specialFull(s) +
    (parts.length ? `<span class="sp-fields">${parts.join("")}</span>` : "");
}

/** Hàng chú giải sáu trường, dựng từ một ô THẬT của kỳ gần nhất.
 *
 * Câu hỏi đầu tiên người đọc đặt ra trước bảng này là "chữ nhỏ dưới mỗi ô
 * nghĩa là gì". Trước đây trang có sáu ô bật/tắt nhưng không nói trường nào
 * đứng ở đâu, nên muốn biết thì phải đoán. Chú giải lấy đúng kỳ mới nhất thay
 * vì một ví dụ bịa: số trong chú giải trùng với số ở hàng đầu bảng, đối chiếu
 * được ngay.
 */
function renderLegend() {
  const box = $("sp-legend");
  if (!box) return;
  const last = DRAWS.length ? DRAWS[DRAWS.length - 1] : null;
  if (!last) { box.innerHTML = ""; return; }

  const s = String(last.s).padStart(5, "0");
  const two = s.slice(3);
  const dau = +two[0];
  const duoi = +two[1];
  const iso = last.d;
  const val = {
    ngay: `${iso.slice(8)}-${iso.slice(5, 7)}`,
    tong: String((dau + duoi) % 10),
    dau: String(dau),
    duoi: String(duoi),
    chanle: `${dau % 2 === 0 ? "C" : "L"}${duoi % 2 === 0 ? "C" : "L"}`,
    bo: BO_LOOKUP[+two] || "—",
  };
  // Liệt kê đủ các con cùng bộ với ô mẫu. Ví dụ cố định kiểu "68 thuộc bộ 13"
  // vô dụng khi kỳ mới nhất ra 04 — bộ của 04 chính là 04, câu giải thích đọc
  // thành lặp lại. Đọc thẳng bảng tra ra danh sách thì ví dụ nào cũng nói được
  // điều gì đó, và vẫn chỉ có một nguồn duy nhất là bảng dựng phía Python.
  const bo = BO_LOOKUP[+two];
  const family = [];
  for (let n = 0; n < 100 && bo; n += 1) {
    if (BO_LOOKUP[n] === bo) family.push(pad2(n));
  }
  const items = DE_FIELDS.map((f) =>
    `<span class="sp-lg-item" title="${f.hint}">` +
    `<b class="sp-lg-val">${val[f.key]}</b>` +
    `<span class="sp-lg-lab">${f.label}</span>` +
    `<span class="sp-lg-hint">${f.hint}</span></span>`
  ).join("");

  box.innerHTML =
    '<div class="sp-legend-head">Đọc một ô: chữ nhỏ dưới mỗi giải là gì</div>' +
    `<div class="sp-legend-sample">${specialFull(s)}` +
    `<span class="sp-lg-src">giải Đặc Biệt kỳ ` +
    `${iso.slice(8)}-${iso.slice(5, 7)}-${iso.slice(0, 4)}, hai số cuối ` +
    `<b>${two}</b> — sáu trường dưới đây tách ra từ chính ô này</span></div>` +
    `<div class="sp-legend-items">${items}</div>` +
    '<p class="sp-legend-rule">' +
    `Tổng = (Đầu + Đuôi) chia lấy dư 10 = (${dau} + ${duoi}) mod 10 = <b>${val.tong}</b>. ` +
    (bo
      ? `Bộ gom một con với bóng dương (0↔5, 1↔6, 2↔7, 3↔8, 4↔9) và số lộn của nó: ` +
        `${two} nằm ở bộ <b>${bo}</b>, gồm ${family.join(" ")}. Cả thảy 15 bộ. `
      : "") +
    "Bật/tắt từng trường bằng các ô dưới đây; lựa chọn được nhớ lại cho lần sau." +
    "</p>";
}

/** Gắn sáu ô đánh dấu bật/tắt trường. */
function bindFieldToggles(render) {
  const box = $("sp-fields-toggle");
  if (!box) return;
  box.innerHTML = DE_FIELDS.map((f) =>
    `<label class="sp-fchk" title="${f.hint}">` +
    `<input type="checkbox" data-field="${f.key}"` +
    `${SHOWN.has(f.key) ? " checked" : ""}> ${f.label}</label>`
  ).join("");
  box.addEventListener("change", (ev) => {
    const key = ev.target.dataset.field;
    if (!key) return;
    if (ev.target.checked) SHOWN.add(key); else SHOWN.delete(key);
    try { localStorage.setItem(FIELD_KEY, JSON.stringify(Array.from(SHOWN))); } catch (e) {}
    render();
  });
}

/** Hai số cuối, dùng cho phép ĐẾM chứ không phải để hiển thị. */
function lastTwo(value) {
  return String(value).padStart(5, "0").slice(-2);
}

/** Dựng bảng từ tiêu đề và các hàng. */
function table(el, headers, rows, opts) {
  opts = opts || {};
  // Tiêu đề cột cũng phải ĐÁNH DẤU ĐƯỢC.
  //
  // Bố cục hai chiều là bất đối xứng: cùng một con số, ở chiều ngang nó là
  // NHÃN HÀNG (`<td class="cell">`, bấm được), còn ở chiều dọc nó là TIÊU ĐỀ
  // CỘT (`<th>` trần, không class, không khoá). Trình xử lý khớp
  // `closest("td.cell")` nên `<th>` không bao giờ trúng — và người dùng thấy
  // đúng thế: bấm vào số ở chiều ngang thì ăn, ở chiều dọc thì không.
  //
  // Khoá của tiêu đề dùng CÙNG lược đồ danh tính với nhãn hàng, nên một con
  // số đánh dấu ở chiều này vẫn sáng khi đổi sang chiều kia.
  const thead = "<thead><tr>" + headers.map((h, i) => {
    const headKey = opts.headKey && opts.headKey(i);
    const extra = opts.headExtra ? opts.headExtra(i) : "";
    if (!headKey) return `<th>${h}${extra}</th>`;
    const on = MARKS.has(headKey) ? " marked" : "";
    return `<th class="cell${on}" data-key="${headKey}">${h}${extra}</th>`;
  }).join("") + "</tr></thead>";
  const body = rows.map((r, y) =>
    "<tr>" + r.map((c, i) => {
      const cls = opts.numeric && opts.numeric.includes(i) ? " num" : "";
      // Khoá theo DANH TÍNH ô khi người gọi cung cấp được, chứ không theo vị trí.
      //
      // Bảng ma trận ĐỔI CHIỀU được, tức nó bị chuyển vị. Khoá vị trí
      // `id:hàng:cột` vì thế trỏ sang một ô hoàn toàn khác sau khi đổi chiều:
      // đã đo, một dấu đặt ở chiều dọc mang khoá `sp-matrix-grid:0:0` và sang
      // chiều ngang thì khoá ấy rơi vào ô nhãn "00".
      //
      // Hệ quả nhìn thấy được là bấm KHÔNG ĂN: cú bấm rơi trúng một ô đang
      // mang dấu lạc thì nó GỠ dấu thay vì thêm, nên người dùng thấy chiều
      // dọc "không bấm được" trong khi chiều ngang thì được.
      const key = opts.key ? opts.key(y, i) : `${el.id}:${y}:${i}`;
      const on = MARKS.has(key) ? " marked" : "";
      // Ô rỗng phải TỰ NÓI ra rằng ngày đó không có kỳ. Không đánh dấu thì một
      // vùng trống trông như lỗi hiển thị, và người đọc không phân biệt được
      // "không về" với "chưa tải xong".
      const blank = (c === "" || c === null || c === undefined) ? " is-empty" : "";
      // Ô CÓ VỀ phải nổi lên khỏi nền, không chỉ khác ở chỗ có chữ. Và khi
      // bảng mang nghĩa "số nháy" thì con số ấy còn quyết định cấp màu.
      let state = "";
      if (!blank && i > 0) {
        state = " sp-hit";
        if (opts.nhay) {
          const k = parseInt(c, 10);
          if (k >= 1) state += ` sp-n${Math.min(k, 5)}`;
        }
      }
      const waiting = opts.pending && (opts.pending(y, i) || {}).pending ? " sp-pending" : "";
      const gan = !waiting && blank && opts.gan && opts.gan(y, i) ? " sp-gan" : "";
      const de = !blank && opts.de && opts.de(y, i) ? " sp-de-hit" : "";
      const tip = opts.title ? opts.title(y, i) : "";
      const titleAttr = tip ? ` title="${tip}"` : "";
      const style = opts.style && opts.style(y, i) ? ` style="${opts.style(y, i)}"` : "";
      const extra = opts.cellExtra ? opts.cellExtra(y, i) : "";
      return `<td class="cell${cls}${on}${blank}${state}${waiting}${gan}${de}" data-key="${key}"${titleAttr}${style}>${c}${extra}</td>`;
    }).join("") + "</tr>"
  ).join("");

  // Dải rỗng phải nói ra là rỗng. Không có nhánh này thì bảng giữ nguyên số
  // liệu của dải TRƯỚC trong khi bộ đếm đã báo "0 kỳ" — số cũ được trình bày
  // như thể thuộc về dải mới. Tái hiện được: chọn Từ ngày 09-09-2026 đến
  // 01-01-2020 (dải ngược) thì bộ đếm ra "0 kỳ" mà ba bảng vẫn đủ 40 hàng.
  const empty = `<tbody><tr><td class="sp-empty-row" colspan="${headers.length}">` +
    "Không có kỳ nào trong dải đã chọn. Kiểm lại Từ ngày / Đến ngày — " +
    "chọn ngược thứ tự cũng cho dải rỗng.</td></tr></tbody>";
  el.innerHTML = thead + (rows.length ? "<tbody>" + body + "</tbody>" : empty);

  // Cột đầu chỉ được dính và tô nền khi nó là NHÃN HÀNG. Bảng lịch tuần có
  // cột đầu là Thứ 2 — dữ liệu thật — nên tô nó lên là bịa ra một cột tiêu đề
  // không tồn tại, và mắt đọc lệch ngay.
  el.classList.toggle("has-rowhead", opts.rowHead !== false);
  // Bảng mang mã màu số nháy tự khai ra, để sọc ngựa vằn và nền hover
  // tránh đường — chúng cụ thể hơn nên nếu không tránh thì chúng thắng.
  el.classList.toggle("sp-nhay", !!opts.nhay);
}

// --- Tô sáng ô để so sánh ---------------------------------------------------
//
// Các bảng này dài hàng chục hàng và người đọc thường muốn dõi theo vài ô rời
// rạc — chẳng hạn cùng một ngày qua nhiều tháng. Không có cách đánh dấu thì họ
// phải nhớ bằng mắt, và chỉ cần cuộn một cái là mất dấu.
//
// Lưu theo từng máy bằng localStorage: đây là tiện ích cá nhân, không phải dữ
// liệu chung. Bọc try/catch vì cửa sổ ẩn danh và trình duyệt chặn lưu trữ sẽ
// ném lỗi ngay ở lệnh đọc, và một trang trắng thì tệ hơn hẳn việc mất dấu.
// Đổi tên kho có CHỦ Ý. Dấu lưu theo lược đồ cũ là khoá vị trí, nên nếu nạp
// lại chúng vào lược đồ mới thì chúng rơi vào những ô ngẫu nhiên — đúng cái
// lỗi vừa sửa. Đổi tên kho tức là bỏ hẳn chúng, sạch hơn là cố chuyển đổi.
const MARK_KEY = "sp.marks.v2." + (window.__D_DEMO_DRAWS__ ? "demo." : "") + (location.pathname.split("/").pop() || "index");
// HAI kho, không phải một.
//
//   MARKS       khoá theo Ô CỤ THỂ. Đây là chế độ mặc định: bấm ô nào thì
//               đúng ô ấy đổi màu, không ô nào khác.
//   PAIR_MARKS  khoá theo CẶP SỐ. Chỉ dùng khi bật "tự động đánh dấu cặp
//               trùng".
//
// Vì sao tách đôi thay vì một kho có cờ: một ô có thể đang sáng vì chính nó
// được bấm, HOẶC vì cặp số của nó đang được đánh dấu. Gộp lại thì không phân
// biệt được hai trường hợp ấy và cú bấm tiếp theo xử lý sai.
let MARKS = new Set();
let PAIR_MARKS = new Set();
try {
  const saved = JSON.parse(localStorage.getItem(MARK_KEY) || "{}");
  if (Array.isArray(saved)) MARKS = new Set(saved);
  else {
    MARKS = new Set(saved.cells || []);
    PAIR_MARKS = new Set(saved.pairs || []);
  }
} catch (e) { MARKS = new Set(); PAIR_MARKS = new Set(); }

function saveMarks() {
  try {
    localStorage.setItem(MARK_KEY, JSON.stringify({
      cells: Array.from(MARKS), pairs: Array.from(PAIR_MARKS),
    }));
  } catch (e) {}
}

// Bảng ma trận rộng tới 120 cột; mắt lạc cột là chuyện thường. Trỏ vào ô nào
// thì làm nổi tiêu đề cột đó. Gắn MỘT trình xử lý trên document thay vì trên
// từng ô: 100 x 120 ô là 12 000 trình xử lý.
// Dóng CHỮ THẬP. Bản trước chỉ đánh dấu cột; trên ma trận 100 hàng thì dóng
// ngược lại theo hàng mới là việc khó hơn, và nó không hề có.
function bindColumnHint() {
  let lastTable = null, lastIndex = -1, lastRow = null, lastCell = null;
  const clear = () => {
    if (lastTable && lastIndex >= 0) {
      const th = lastTable.querySelectorAll("thead th")[lastIndex];
      if (th) th.classList.remove("col-hint");
    }
    if (lastRow) lastRow.classList.remove("row-hint");
    if (lastCell) lastCell.classList.remove("cell-hint");
    lastTable = null; lastIndex = -1; lastRow = null; lastCell = null;
  };
  document.addEventListener("mouseover", (ev) => {
    const td = ev.target.closest("td");
    const tb = td && td.closest("table");
    if (!td || !tb) { clear(); return; }
    const i = td.cellIndex;
    if (tb === lastTable && i === lastIndex && td === lastCell) return;
    clear();
    const th = tb.querySelectorAll("thead th")[i];
    if (th) { th.classList.add("col-hint"); lastTable = tb; lastIndex = i; }
    const tr = td.parentElement;
    if (tr) { tr.classList.add("row-hint"); lastRow = tr; }
    td.classList.add("cell-hint"); lastCell = td;
  });
  document.addEventListener("mouseleave", clear, true);
}

/** Cặp hai chữ số mà một ô đại diện, hoặc null nếu ô không mang cặp nào.
 *
 *  Đọc từ KHOÁ chứ không từ chữ trong ô: chữ trong ô là SỐ NHÁY ("1", "2"),
 *  không phải con lô. Lấy nhầm nó thì bấm ô "2" sẽ làm sáng mọi ô có 2 nháy
 *  — một tập hợp chẳng có nghĩa gì với người soi cầu.
 */
function markPair(td) {
  const found = /\|(?:n|c)([0-9]{2}(?:-[0-9]{2})?)/.exec(td.dataset.key || "");
  return found ? found[1] : null;
}

function pairModeOn() {
  const box = $("sp-pair-mode");
  return !!(box && box.checked);
}

function isMarked(td) {
  if (MARKS.has(td.dataset.key)) return true;
  const pair = markPair(td);
  return pair !== null && PAIR_MARKS.has(pair);
}

function paintMarks() {
  document.querySelectorAll("td.cell, th.cell").forEach((td) => {
    td.classList.toggle("marked", isMarked(td));
  });
  updateMarkCount();
}

/** Một cú bấm, bốn nhánh — và thứ tự giữa chúng là phần quan trọng.
 *
 *  Quy tắc bao trùm: bấm vào ô ĐANG SÁNG thì nó tắt, bất kể nó sáng vì lý do
 *  gì. Hai nhánh tắt phải đứng TRƯỚC hai nhánh bật; nếu không, một ô đang
 *  sáng theo cặp sẽ bị chồng thêm dấu ô và bấm mãi không tắt.
 */
function toggleMark(td) {
  const key = td.dataset.key;
  const pair = markPair(td);
  if (pair !== null && PAIR_MARKS.has(pair)) PAIR_MARKS.delete(pair);
  else if (MARKS.has(key)) MARKS.delete(key);
  else if (pairModeOn() && pair !== null) PAIR_MARKS.add(pair);
  else MARKS.add(key);
}

function bindMarking() {
  document.addEventListener("click", (ev) => {
    const td = ev.target.closest("td.cell, th.cell");
    if (!td || !td.dataset.key) return;
    toggleMark(td);
    saveMarks();
    paintMarks();
  });

  // Đổi chế độ KHÔNG xoá dấu đã có: người xem bật chế độ cặp, đánh vài dấu,
  // rồi tắt đi — những dấu ấy phải còn nguyên vì họ không hề bỏ chọn chúng.
  const pairBox = $("sp-pair-mode");
  if (pairBox) pairBox.addEventListener("change", paintMarks);

  const clear = $("sp-clear-marks");
  if (clear) {
    clear.addEventListener("click", () => {
      MARKS.clear();
      PAIR_MARKS.clear();
      saveMarks();
      paintMarks();
    });
  }
  updateMarkCount();
}

function updateMarkCount() {
  const el = $("sp-mark-count");
  const total = MARKS.size + PAIR_MARKS.size;
  if (el) {
    el.textContent = total
      ? (PAIR_MARKS.size
        ? `${MARKS.size} ô + ${PAIR_MARKS.size} cặp đang đánh dấu`
        : `${MARKS.size} ô đang đánh dấu`)
      : "";
  }
}

/** Màu nền heat-map: 0 = nhạt nhất, 1 = đậm nhất. */
function heat(value, max) {
  if (!max) return "";
  const t = Math.min(1, value / max);
  // Dừng ở 0.55 để chữ tối luôn còn tương phản trên nền.
  return `background:rgba(124,58,237,${(t * 0.55).toFixed(3)})`;
}

function countLoto(rows) {
  const c = new Array(100).fill(0);
  rows.forEach((r) => r.n.forEach((x) => { c[parseInt(x, 10)] += 1; }));
  return c;
}

// --- Từng trang ------------------------------------------------------------

// --- Ma trận tần suất: số × ngày -------------------------------------------
//
// Bố cục của trang tham chiếu: một chiều là 100 con lô, chiều kia là từng kỳ,
// ô là số lần con đó về trong kỳ đó. Đổi được chiều ngang/dọc, và có bộ chọn
// để chỉ hiện những con đang quan tâm.
//
// Trần cột là ràng buộc thật, không phải lười: chọn "Tất cả" trên kho 2392 kỳ
// cho 239 000 ô và trình duyệt nghẹn.
//
// Nhưng trần 120 cũ thận trọng quá mức — đã đo lại chi phí dựng thật trong
// Chromium, cùng máy, cùng trang:
//
//        30 ngày    3 030 ô    106 ms
//       120 ngày   12 120 ô    352 ms
//       300 ngày   30 300 ô    894 ms      <- vẫn dưới một giây
//       500 ngày   50 500 ô  4 113 ms      <- chỗ gãy thật
//
// Nên trần đặt ở 300: đủ cho mốc dài nhất người dùng hỏi tới, và còn cách xa
// điểm mà trình duyệt bắt đầu nghẹn.
const MATRIX_MAX_DAYS = 300;
let MATRIX_GAN = new Array(100).fill(0);
let MATRIX_RECENT = new Array(100).fill(0);

const PICK_KEY = "sp.picked." + (window.__D_DEMO_DRAWS__ ? "demo." : "") + (location.pathname.split("/").pop() || "index");
let PICKED = null;   // null = hiện tất cả
try {
  const saved = localStorage.getItem(PICK_KEY);
  if (saved) PICKED = new Set(JSON.parse(saved));
} catch (e) { PICKED = null; }

function savePicked() {
  try {
    if (PICKED) localStorage.setItem(PICK_KEY, JSON.stringify(Array.from(PICKED)));
    else localStorage.removeItem(PICK_KEY);
  } catch (e) {}
}

function isPicked(n) {
  return PICKED === null || PICKED.has(n);
}

/** Lưới 00-99 bấm để chọn, kèm bốn nút nhanh. */
function bindPicker(render) {
  const box = $("sp-picker");
  if (!box) return;
  const draw = () => {
    box.innerHTML =
      '<div class="sp-pick-quick">' +
      '<button type="button" data-pick="all">Tất cả</button>' +
      '<button type="button" data-pick="none">Bỏ hết</button>' +
      '<button type="button" data-pick="even">Số chẵn</button>' +
      '<button type="button" data-pick="odd">Số lẻ</button>' +
      "</div><div class='sp-pick-grid'>" +
      Array.from({ length: 100 }, (_, n) =>
        `<button type="button" class="sp-pick${isPicked(n) ? " on" : ""}" ` +
        `aria-pressed="${isPicked(n)}" data-num="${n}">${pad2(n)}</button>`).join("") + "</div>";
  };
  draw();

  box.addEventListener("click", (ev) => {
    const quick = ev.target.dataset.pick;
    if (quick) {
      if (quick === "all") PICKED = null;
      else if (quick === "none") PICKED = new Set();
      else {
        PICKED = new Set();
        for (let n = 0; n < 100; n++) {
          if ((n % 2 === 0) === (quick === "even")) PICKED.add(n);
        }
      }
      savePicked(); draw(); render();
      return;
    }
    const num = ev.target.dataset.num;
    if (num === undefined) return;
    // Bấm một con số 00-99 MỞ POPUP chu kỳ gan, không lọc ngay.
    //
    // Hai yêu cầu đụng nhau ở đây: "bấm số thì hiện popup" và "bấm ô thì đổi
    // màu, bấm lại thì bỏ". Chúng không thể cùng nằm trên một phần tử. Ô trên
    // MA TRẬN giữ việc đổi màu (đó là thứ vừa được sửa và người dùng đang
    // dùng); chip 00-99 nằm NGOÀI ma trận nên nhận việc mở popup.
    //
    // Việc lọc không mất đi — nó chuyển vào trong popup, sau khi người xem
    // đã thấy chu kỳ gan rồi mới quyết định có lọc hay không.
    openGanPopup(pad2(+num));
  });
}

/** Ma trận số × ngày; đổi chiều theo bộ chọn. */
function renderLotoMatrix(rows) {
  const grid = $("sp-matrix-grid");
  if (!grid) return;

  const shown = rows.slice(-MATRIX_MAX_DAYS);
  const nums = Array.from({ length: 100 }, (_, n) => n).filter(isPicked);

  const note = $("sp-matrix-note");
  if (note) {
    note.textContent = rows.length > shown.length
      ? `Ma trận hiện ${shown.length} kỳ gần nhất trong ${rows.length} kỳ đã chọn ` +
        `(trần ${MATRIX_MAX_DAYS} để trang không treo). Bảng xếp hạng bên dưới ` +
        "dùng trọn dải."
      : `${shown.length} kỳ × ${nums.length} con.`;
  }
  if (!nums.length) { grid.innerHTML = ""; return; }

  const per = shown.map((r) => {
    const c = new Array(100).fill(0);
    r.n.forEach((x) => { c[parseInt(x, 10)] += 1; });
    return c;
  });

  // Con số trong mỗi ô CHÍNH LÀ số nháy của con lô đó trong kỳ đó, nên bảng
  // này là chỗ duy nhất mà phân cấp màu theo nháy mang đúng nghĩa.
  const opts = { nhay: true };
  const vertical = ($("sp-orient") || {}).value === "Xem theo chiều dọc";
  // Danh tính một ô là CẶP (con số, ngày kỳ) — thứ không đổi khi chuyển vị.
  // Ô nhãn hàng (cột 0) mang danh tính của chính thực thể nó gán nhãn.
  // Đảo MỘT lần và giữ luôn chỉ số gốc. Bản đầu tôi viết `shown.indexOf(r)`
  // ngay trong vòng dựng ô — trên ma trận 100 ngày × 100 số thì đó là một
  // triệu phép quét tuyến tính, tức tự tạo ra một vấn đề hiệu năng khi đang
  // đi sửa lỗi khác.
  const byDate = shown.map((r, i) => ({ d: r.d, c: per[i] })).reverse();
  // Số kỳ GAN của mỗi con: đếm từ kỳ mới nhất lùi lại tới lần về gần nhất.
  // `byDate` đã xếp mới-nhất-trước nên chỉ cần quét tới lần đầu gặp giá trị > 0.
  const ganOf = new Array(100).fill(byDate.length);
  for (let n = 0; n < 100; n += 1) {
    for (let k = 0; k < byDate.length; k += 1) {
      if (byDate[k].c[n]) { ganOf[n] = k; break; }
    }
  }
  // Tổng lần về trong 30 kỳ gần nhất — nguồn cho biểu đồ cột mini.
  const recent30 = new Array(100).fill(0);
  for (let k = 0; k < Math.min(30, byDate.length); k += 1) {
    for (let n = 0; n < 100; n += 1) recent30[n] += byDate[k].c[n] || 0;
  }
  MATRIX_GAN = ganOf;
  MATRIX_RECENT = recent30;

  // Sắp xếp CON SỐ, không phải sắp xếp ngày. Ngày luôn theo trục thời gian;
  // đảo nó đi thì ma trận mất nghĩa. Thứ người ta muốn đổi thứ tự là dãy số.
  const sort = ($("sp-sort") || {}).value || "num";
  if (sort !== "num") {
    const totalOf = (n) => byDate.reduce((sum, r) => sum + (r.c[n] || 0), 0);
    const score = sort.startsWith("gan") ? (n) => ganOf[n] : totalOf;
    const dir = sort.endsWith("-asc") ? 1 : -1;
    // Hoà nhau thì giữ thứ tự 00 -> 99, để bảng không nhảy lung tung giữa các
    // lần dựng khi nhiều con cùng điểm.
    nums.sort((a, b) => (score(a) - score(b)) * dir || a - b);
  }
  // Kỳ hôm nay chưa quay thì vẫn CÓ MẶT trên bảng, dưới dạng ô chờ. Bỏ hẳn nó
  // đi thì bảng trông như hôm nay không tồn tại; để nó trắng như ô "không về"
  // thì tệ hơn, vì đó là một lời khẳng định SAI — chưa quay không phải là
  // không về. `opts.pending` khiến `table()` gắn lớp riêng cho hàng/cột ấy.
  const waiting = pendingDay(shown);
  if (waiting) byDate.unshift({ d: waiting, c: new Array(100).fill(null), pending: true });
  opts.pending = (y, i) => (vertical ? byDate[y] : byDate[i - 1]);
  // Ô nằm trong KHOẢNG GAN: chỉ số kỳ nhỏ hơn vị trí lần về gần nhất.
  // Ô mà con số ấy chính là hai số cuối GIẢI ĐẶC BIỆT của kỳ đó.
  const deOf = new Map();
  shown.forEach((r) => deOf.set(r.d, String(r.s || "").slice(-2)));
  opts.de = (y, i) => {
    if (i === 0) return false;
    const day = vertical ? byDate[y] : byDate[i - 1];
    const num = vertical ? nums[i - 1] : nums[y];
    return !!day && deOf.get(day.d) === pad2(num);
  };
  opts.gan = (y, i) => {
    if (i === 0) return false;
    const day = vertical ? y : i - 1;
    const num = vertical ? nums[i - 1] : nums[y];
    return day < ganOf[num];
  };
  // Tooltip: số ngày chưa ra tính tới hôm nay.
  opts.title = (y, i) => {
    if (i === 0) return "";
    const num = vertical ? nums[i - 1] : nums[y];
    return `Số ${pad2(num)} — số ngày chưa ra tính đến ngày hiện tại: ${ganOf[num]} ngày`;
  };
  if (vertical) {
    const head = ["Ngày"].concat(nums.map(pad2));
    const body = byDate.map((r) =>
      [`<b>${r.d.slice(8)}-${r.d.slice(5, 7)}</b>`]
        .concat(nums.map((n) => r.c[n] || "")));
    opts.key = (y, i) => (i === 0
      ? `m|d${byDate[y].d}`
      : `m|n${pad2(nums[i - 1])}|d${byDate[y].d}`);
    // Chiều dọc: tiêu đề cột LÀ con số. Cùng khoá với nhãn hàng ở chiều ngang.
    opts.headKey = (i) => (i === 0 ? null : `m|n${pad2(nums[i - 1])}`);
    // Cột mini phía trên con số: tổng lần về trong 30 kỳ gần nhất.
    opts.headExtra = (i) => (i === 0 ? "" : miniBar(recent30[nums[i - 1]]));
    table(grid, head, body, opts);
  } else {
    const head = ["Số"].concat(byDate.map((r) => `${r.d.slice(8)}-${r.d.slice(5, 7)}`));
    const body = nums.map((n) =>
      [`<b>${pad2(n)}</b>`].concat(byDate.map((r) => r.c[n] || "")));
    opts.key = (y, i) => (i === 0
      ? `m|n${pad2(nums[y])}`
      : `m|n${pad2(nums[y])}|d${byDate[i - 1].d}`);
    // Chiều ngang: tiêu đề cột là NGÀY. Cùng khoá với nhãn hàng ở chiều dọc.
    opts.headKey = (i) => (i === 0 ? null : `m|d${byDate[i - 1].d}`);
    // Chiều ngang, con số là NHÃN HÀNG nên cột mini đi kèm nhãn hàng.
    opts.cellExtra = (y, i) => (i === 0 ? miniBar(recent30[nums[y]]) : "");
    table(grid, head, body, opts);
  }
  renderNhayLegend(grid);
}

// --- Chu kỳ gan: tính, và popup chi tiết ------------------------------------

/** Mọi chu kỳ gan của một con, theo chế độ.
 *
 *  `mode`: "loto" đọc 27 con lô của kỳ; "de" chỉ đọc hai số cuối giải đặc
 *  biệt. Hai chế độ cho hai chuỗi hoàn toàn khác nhau, nên không tái dùng
 *  kết quả của nhau được.
 *
 *  Trả về `{hits, cycles, current, max}` — `cycles` là độ dài từng quãng
 *  trượt GIỮA hai lần về, `current` là quãng đang chạy tính tới kỳ mới nhất.
 */
function ganCycles(pair, mode) {
  const hits = [];
  for (let i = 0; i < DRAWS.length; i += 1) {
    const r = DRAWS[i];
    const on = mode === "de"
      ? String(r.s || "").slice(-2) === pair
      : (r.n || []).indexOf(pair) >= 0;
    if (on) hits.push(i);
  }
  const cycles = [];
  for (let k = 1; k < hits.length; k += 1) cycles.push(hits[k] - hits[k - 1] - 1);
  const current = hits.length ? DRAWS.length - 1 - hits[hits.length - 1] : DRAWS.length;
  return {
    hits, cycles, current,
    max: cycles.length ? Math.max(...cycles) : 0,
    dates: hits.slice(-8).reverse().map((i) => DRAWS[i].d),
  };
}

function openGanPopup(pair) {
  const host = $("sp-gan-modal");
  if (!host) return;
  const mode = (host.dataset.mode === "de") ? "de" : "loto";
  const g = ganCycles(pair, mode);
  const tab = (value, label) =>
    `<button type="button" class="sp-btn${mode === value ? " on" : ""}" data-gmode="${value}">${label}</button>`;
  host.querySelector(".sp-modal-body").innerHTML =
    `<div class="sp-modal-tabs">${tab("loto", "Lô tô")}${tab("de", "Giải Đặc Biệt")}</div>` +
    `<div class="sp-modal-kpi">` +
    `<div><span>Gan hiện tại</span><strong>${g.current}</strong></div>` +
    `<div><span>Gan cực đại</span><strong>${g.max}</strong></div>` +
    `<div><span>Số lần về</span><strong>${g.hits.length}</strong></div>` +
    `<div><span>Số chu kỳ</span><strong>${g.cycles.length}</strong></div>` +
    "</div>" +
    `<p class="sp-hint">Các kỳ về gần nhất</p>` +
    `<div class="sp-modal-days">${g.dates.map((d) => `<span>${d}</span>`).join("") || "<span>—</span>"}</div>` +
    `<p class="sp-hint">Độ dài 12 chu kỳ gan gần nhất (số kỳ trượt giữa hai lần về)</p>` +
    `<div class="sp-modal-days">${g.cycles.slice(-12).reverse().map((c) => `<span>${c}</span>`).join("") || "<span>—</span>"}</div>` +
    // Nút lọc CHỈ có nghĩa ở trang có lưới chọn 00-99. Trang tần suất cặp lọc
    // theo HỌ CẶP, nên một nút "chỉ xem số 07" ở đó bấm vào không đổi gì — và
    // một nút không làm gì thì tệ hơn hẳn việc không có nút.
    ($("sp-picker")
      ? `<div class="sp-modal-tabs"><button type="button" class="sp-btn" data-gfilter="${pair}">` +
        `Chỉ xem số ${pair} trên ma trận</button></div>`
      : "");
  host.querySelector(".sp-modal-title").textContent = `Chu kỳ gan · số ${pair}`;
  host.dataset.pair = pair;
  host.hidden = false;
}

function bindGanPopup(render) {
  const host = $("sp-gan-modal");
  if (!host) return;
  // `render` là THAM SỐ, không phải biến toàn cục. Bản đầu tôi gọi thẳng
  // `render()` trong đây và nó ném "render is not defined" — nút lọc trong
  // popup im lặng không làm gì, mà lỗi chỉ hiện trong console nên nhìn từ
  // giao diện thì y như nút hỏng vô cớ.
  const redraw = typeof render === "function" ? render : () => {};
  host.addEventListener("click", (ev) => {
    if (ev.target === host || ev.target.dataset.close !== undefined) { host.hidden = true; return; }
    const gmode = ev.target.dataset.gmode;
    if (gmode) { host.dataset.mode = gmode; openGanPopup(host.dataset.pair); return; }
    const only = ev.target.dataset.gfilter;
    if (only !== undefined) {
      PICKED = new Set([Number(only)]);
      savePicked(); host.hidden = true; redraw();
    }
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") host.hidden = true;
  });
}

/** Cột mini: một vạch cao theo tổng lần về trong 30 kỳ.
 *
 *  Vẽ bằng một `<i>` có chiều cao tính sẵn, KHÔNG dùng SVG hay canvas: bảng
 *  có tới 100 tiêu đề và mỗi tiêu đề một biểu đồ, nên mỗi nút thừa đều nhân
 *  lên trăm lần. Một phần tử một thuộc tính là đủ để đọc được xu hướng.
 *
 *  Trần 30: 30 kỳ × tối đa vài nháy, nhưng thực tế hiếm khi quá 12. Cắt ở 12
 *  để dải giữa còn phân biệt được, thay vì dồn hết vào một phần tư dưới.
 */
function miniBar(total) {
  const pct = Math.max(6, Math.min(100, Math.round((total / 12) * 100)));
  return `<i class="sp-mini-bar" style="--h:${pct}%" aria-hidden="true"></i>`;
}

/** Chú giải phân cấp số nháy.
 *
 * Bắt buộc phải có: xanh dương -> xanh lá -> cam không có trật tự tri giác,
 * nên nếu không nói ra ánh xạ thì người đọc chỉ thấy màu chứ không đọc được
 * thông tin. Đặt NGAY TRÊN ma trận, không giấu sau tooltip — điện thoại
 * không có chuột để trỏ vào.
 */
function renderNhayLegend(grid) {
  const host = grid && grid.parentElement;
  if (!host || host.querySelector(".sp-nhay-legend")) return;
  const tiers = [
    [1, "1 nháy"], [2, "2 nháy"], [3, "3 nháy"], [4, "4 nháy"], [5, "5 nháy trở lên"],
  ];
  const box = document.createElement("div");
  box.className = "sp-nhay-legend";
  box.innerHTML = "<b>Số nháy</b>" + tiers.map(([k, label]) =>
    `<span class="sp-nl"><i class="sp-n${k}">${k === 5 ? "5+" : k}</i>` +
    `<span>${label}</span></span>`).join("") +
    '<span class="sp-nl"><i class="sp-empty-key"></i><span>không về</span></span>';
  host.insertBefore(box, grid);
}

function renderLotoFrequency() {
  const rows = selected();
  setCount(rows);
  renderLotoMatrix(rows);
  const counts = countLoto(rows);
  const expected = LOTO_BASELINE * rows.length;
  const max = Math.max(...counts, 1);

  const m = $("sp-matrix");
  if (m) {
    m.innerHTML = counts.map((v, i) =>
      `<span class="sp-cell" style="${heat(v, max)}" title="Số ${pad2(i)}: ${v} lần">` +
      `<b>${pad2(i)}</b><i>${v}</i></span>`
    ).join("");
  }
  const order = counts.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Hạng", "Số", "Số lần về", "Kỳ vọng", "So kỳ vọng"],
    order.map((p, k) => [
      k + 1, pad2(p[0]), p[1], expected.toFixed(1),
      expected ? (p[1] / expected).toFixed(2) + "×" : "—",
    ]), { numeric: [0, 2, 3, 4] });
}

// --- Số lộn -----------------------------------------------------------------
//
// "Lộn" là đảo hai chữ số: 01 <-> 10, 27 <-> 72. Chỉ có 45 cặp như vậy, vì
// 10 số kép (00, 11, ... 99) đảo lại chính nó nên KHÔNG có số lộn.
//
// Kho từng gộp 10 số kép thành 5 họ "kép bóng" (00-55, 11-66, 22-77, 33-88,
// 44-99) cho tròn 50 cặp. Nhưng BÓNG (0<->5, 1<->6, ...) là khái niệm khác hẳn
// LỘN, nên bảng cũ trộn hai thứ và gọi chung là cặp lộn. Ở đây tách bạch: 45
// cặp lộn thật, còn số kép liệt kê riêng đúng bản chất của nó.

/** 45 cặp lộn thật, dạng [a, b] với a < b và b là a đảo chữ số. */
function reversePairs() {
  const out = [];
  for (let a = 0; a < 100; a++) {
    const b = (a % 10) * 10 + Math.floor(a / 10);
    if (a < b) out.push([a, b]);
  }
  return out;   // đúng 45 cặp
}

/** 10 số kép: đảo lại chính nó. */
function doubleNumbers() {
  return Array.from({ length: 10 }, (_, d) => d * 11);
}

function renderReversePairs() {
  const rows = selected();
  setCount(rows);

  const c = new Array(100).fill(0);
  rows.forEach((r) => r.n.forEach((x) => { c[parseInt(x, 10)] += 1; }));

  const pairs = reversePairs()
    .map(([a, b]) => [a, b, c[a], c[b], c[a] + c[b]])
    .sort((x, y) => y[4] - x[4]);

  table($("sp-grid"),
    ["Hạng", "Cặp lộn", "Về của số đầu", "Về của số lộn", "Tổng", "Lệch"],
    pairs.map((p, k) => [
      k + 1,
      `${pad2(p[0])} ↔ ${pad2(p[1])}`,
      p[2], p[3], p[4],
      // Lệch giữa hai chiều: cặp lộn "cân" thì gần 0. Cột này mới là thứ đáng
      // nhìn, vì tổng chỉ nói cặp đó gồm hai con hay về, không nói gì về LỘN.
      (p[2] - p[3] > 0 ? "+" : "") + (p[2] - p[3]),
    ]), { numeric: [0, 2, 3, 4, 5] });

  const kep = $("sp-kep");
  if (kep) {
    const ds = doubleNumbers().map((n) => [pad2(n), c[n]]).sort((a, b) => b[1] - a[1]);
    table(kep, ["Số kép", "Số lần về"],
      ds.map((d) => [d[0], d[1]]), { numeric: [1] });
  }
}

// --- Ma trận 50 họ cặp × ngày ----------------------------------------------
//
// Bộ 50 họ lấy từ number_reference.all_cap_loto_50 và nhúng sẵn: 45 cặp lộn
// thật cộng 5 cặp ghép hai số kép qua bóng (00-55, 11-66, 22-77, 33-88,
// 44-99). Đọc từ chính trang tham chiếu thấy họ dùng đúng bộ này, nên đây là
// bằng chứng chứ không phải suy đoán.
const CAP50 = window.__D_CAP50__ || [];

function renderPairMatrix(rows) {
  const grid = $("sp-matrix-grid");
  if (!grid || !CAP50.length) return;

  const shown = rows.slice(-MATRIX_MAX_DAYS);
  const note = $("sp-matrix-note");
  if (note) {
    note.textContent = rows.length > shown.length
      ? `Ma trận hiện ${shown.length} kỳ gần nhất trong ${rows.length} kỳ đã chọn ` +
        `(trần ${MATRIX_MAX_DAYS} để trang không treo).`
      : `${shown.length} kỳ × ${CAP50.length} họ cặp.`;
  }

  // Mỗi ô: số lần HAI con của họ đó về trong kỳ, cộng lại.
  const per = shown.map((r) => {
    const c = new Array(100).fill(0);
    r.n.forEach((x) => { c[parseInt(x, 10)] += 1; });
    return CAP50.map(([a, b]) => c[a] + c[b]);
  });

  const label = ([a, b]) => `${pad2(a)}-${pad2(b)}`;
  const day = (r) => `${r.d.slice(8)}-${r.d.slice(5, 7)}`;

  // Cùng lỗi với ma trận lô tô: bảng này cũng chuyển vị được, nên khoá đánh
  // dấu phải theo danh tính (họ cặp, ngày kỳ) chứ không theo vị trí ô.
  const byDate = shown.map((r, i) => ({ d: r.d, t: day(r), c: per[i] })).reverse();
  const waiting = pendingDay(shown);
  if (waiting) {
    byDate.unshift({
      d: waiting, t: `${waiting.slice(8)}-${waiting.slice(5, 7)}`,
      c: new Array(CAP50.length).fill(null), pending: true,
    });
  }
  const verticalPair = ($("sp-orient") || {}).value === "Xem theo chiều dọc";
  const pendingAt = (y, i) => (verticalPair ? byDate[y] : byDate[i - 1]);
  // Cùng hai thứ với ma trận lô tô, tính theo HỌ CẶP: số kỳ gan và tổng lần
  // về trong 30 kỳ gần nhất. Trần biểu đồ cao gấp đôi vì mỗi ô cộng lần về
  // của HAI con, nên giá trị điển hình cũng gấp đôi.
  const ganPair = new Array(CAP50.length).fill(byDate.length);
  const recentPair = new Array(CAP50.length).fill(0);
  for (let j = 0; j < CAP50.length; j += 1) {
    for (let k = 0; k < byDate.length; k += 1) {
      if (byDate[k].c[j]) { ganPair[j] = k; break; }
    }
    for (let k = 0; k < Math.min(30, byDate.length); k += 1) {
      recentPair[j] += byDate[k].c[j] || 0;
    }
  }
  const pairGan = (y, i) => {
    if (i === 0) return false;
    const day = verticalPair ? y : i - 1;
    const idx = verticalPair ? i - 1 : y;
    return day < ganPair[idx];
  };
  const pairTip = (y, i) => {
    if (i === 0) return "";
    const idx = verticalPair ? i - 1 : y;
    return `Cặp ${label(CAP50[idx])} — số ngày chưa ra tính đến ngày hiện tại: ${ganPair[idx]} ngày`;
  };
  if (($("sp-orient") || {}).value === "Xem theo chiều dọc") {
    table(grid, ["Ngày"].concat(CAP50.map(label)),
      byDate.map((r) => [`<b>${r.t}</b>`].concat(r.c.map((v) => v || ""))),
      { pending: pendingAt, gan: pairGan, title: pairTip,
        headKey: (i) => (i === 0 ? null : `p|c${label(CAP50[i - 1])}`),
        headExtra: (i) => (i === 0 ? "" : miniBar(recentPair[i - 1] / 2)),
        key: (y, i) => (i === 0
          ? `p|d${byDate[y].d}`
          : `p|c${label(CAP50[i - 1])}|d${byDate[y].d}`) });
  } else {
    table(grid, ["Cặp"].concat(byDate.map((r) => r.t)),
      CAP50.map((pair, j) => [`<b>${label(pair)}</b>`]
        .concat(byDate.map((r) => r.c[j] || ""))),
      { pending: pendingAt, gan: pairGan, title: pairTip,
        headKey: (i) => (i === 0 ? null : `p|d${byDate[i - 1].d}`),
        cellExtra: (y, i) => (i === 0 ? miniBar(recentPair[y] / 2) : ""),
        key: (y, i) => (i === 0
          ? `p|c${label(CAP50[y])}`
          : `p|c${label(CAP50[y])}|d${byDate[i - 1].d}`) });
  }
}

function renderPairFrequency() {
  const rows = selected();
  setCount(rows);
  renderPairMatrix(rows);
  updateChanceNote(rows.length);
  const co = new Map();
  rows.forEach((r) => {
    const uniq = Array.from(new Set(r.n)).sort();
    for (let i = 0; i < uniq.length; i++)
      for (let j = i + 1; j < uniq.length; j++)
        co.set(uniq[i] + "-" + uniq[j], (co.get(uniq[i] + "-" + uniq[j]) || 0) + 1);
  });
  const expected = PAIR_BASELINE * rows.length;
  const top = Array.from(co.entries()).sort((a, b) => b[1] - a[1]).slice(0, 50);
  table($("sp-grid"),
    ["Hạng", "Cặp số", "Số lần cùng về", "Kỳ vọng", "So kỳ vọng"],
    top.map((p, k) => [
      k + 1, p[0], p[1], expected.toFixed(1),
      expected ? (p[1] / expected).toFixed(2) + "×" : "—",
    ]), { numeric: [0, 2, 3, 4] });
}

function renderHeadTail() {
  const rows = selected();
  setCount(rows);
  const head = new Array(10).fill(0);
  const tail = new Array(10).fill(0);
  rows.forEach((r) => r.n.forEach((x) => {
    head[parseInt(x[0], 10)] += 1;
    tail[parseInt(x[1], 10)] += 1;
  }));
  const total = rows.length * 27;
  const build = (el, counts, label) => {
    const max = Math.max(...counts, 1);
    table(el, [label, "Số lần", "Tỉ lệ", ""],
      counts.map((v, i) => [
        i, v, total ? ((v / total) * 100).toFixed(2) + "%" : "—",
        `<span class="sp-bar" style="width:${(100 * v / max).toFixed(1)}%"></span>`,
      ]), { numeric: [0, 1, 2] });
  };
  build($("sp-head"), head, "Chữ số đầu");
  build($("sp-tail"), tail, "Chữ số đuôi");

  // Ba ma trận NGÀY x chữ số, đúng bố cục trang tham chiếu. Bảng gộp phía
  // trên trả lời "chữ số nào hay ra", ma trận trả lời "hôm nào ra bao nhiêu
  // lần" — hai câu hỏi khác nhau, và bản trước chỉ có câu đầu.
  //
  // Tổng ở đây là (Đầu + Đuôi) mod 10 của từng con lô, giống ô bảng Đặc Biệt.
  const perDay = (pick, label, el) => {
    const recent = rows.slice(-20).reverse();
    const headers = ["Ngày"].concat(
      Array.from({ length: 10 }, (_, d) => `${label} ${d}`));
    table(el, headers, recent.map((r) => {
      const count = new Array(10).fill(0);
      r.n.forEach((x) => { count[pick(+x[0], +x[1])] += 1; });
      return [viDate(r.d)].concat(
        count.map((v) => (v ? `${v} lần` : '<span class="sp-zero">0</span>')));
    }), { numeric: Array.from({ length: 10 }, (_, i) => i + 1) });
  };
  perDay((d) => d, "Đầu", $("sp-day-head"));
  perDay((_, u) => u, "Đuôi", $("sp-day-tail"));
  perDay((d, u) => (d + u) % 10, "Tổng", $("sp-day-sum"));
}

function specialGaps() {
  // Số kỳ chưa về, và chu kỳ dài nhất trong lịch sử, cho từng con 00-99.
  const last = new Array(100).fill(-1);
  const maxGap = new Array(100).fill(0);
  const hits = new Array(100).fill(0);
  DRAWS.forEach((r, t) => {
    const k = parseInt(lastTwo(r.s), 10);
    hits[k] += 1;
    if (last[k] >= 0) maxGap[k] = Math.max(maxGap[k], t - last[k]);
    last[k] = t;
  });
  const n = DRAWS.length;
  return { last, maxGap, hits, current: last.map((t) => (t < 0 ? n : n - 1 - t)), n };
}

// --- Lô gan -----------------------------------------------------------------
//
// Bố cục đọc được từ trang tham chiếu (thongkemienbac, thong-ke-lo-gan):
//   1. Lô gan hiện tại: Bộ số | Ngày ra cuối cùng | Số kỳ gan | Gan cực đại
//   2. Gan cực đại của cả 00-99, tách hai bảng 00-49 và 50-99
//   3. Cặp lô gan: Cặp số | Ngày ra gần đây | Số kỳ gan | Gan cực đại
//
// "Gan" đếm theo KỲ chứ không theo ngày lịch. Hai cách này chỉ trùng nhau khi
// ngày nào cũng quay; XSMB nghỉ Tết và nghỉ 01-22/04/2020, nên đếm theo ngày
// lịch sẽ thổi phồng gan của mọi con ngay sau mỗi đợt nghỉ.

/** Gan của từng con 00-99 trên LOTO (27 con mỗi kỳ). */
function lotoGaps() {
  const last = new Array(100).fill(-1);
  const maxGap = new Array(100).fill(0);
  const hits = new Array(100).fill(0);
  DRAWS.forEach((r, t) => {
    // Một con có thể về nhiều lần trong cùng một kỳ. Với gan thì kỳ đó tính
    // MỘT lần — về hai nháy không làm con số bớt gan hơn về một nháy.
    const seen = new Set(r.n.map((x) => parseInt(x, 10)));
    seen.forEach((k) => {
      hits[k] += 1;
      if (last[k] >= 0) maxGap[k] = Math.max(maxGap[k], t - last[k]);
      last[k] = t;
    });
  });
  const n = DRAWS.length;
  const current = last.map((t) => (t >= 0 ? n - 1 - t : n));
  return { last, maxGap, current, hits };
}

/** Gan của 50 cặp LOTO: cặp về khi MỘT TRONG HAI con có mặt trong kỳ.
 *
 * Định nghĩa này đọc ra từ chính số liệu trang tham chiếu, không phải đoán.
 * Bản đầu tôi lấy "cả hai con cùng về", và nó sai:
 *
 *   cặp     họ in          "cả hai"        "một trong hai"
 *   24-42   02-09, gan 7   23-08, gan 17   02-09, gan 7   <- khớp
 *   23-32   04-09, gan 5   04-09, gan 5    04-09, gan 5
 *   29-92   05-09, gan 4   18-08, gan 22   05-09, gan 4   <- khớp
 *
 * Cách "cả hai" trùng đúng một dòng, và trùng là do tình cờ. Nó cũng mâu thuẫn
 * với thống kê: hai con cùng về một kỳ có xác suất 5,49% nên gan cực đại phải
 * cỡ 100 kỳ, trong khi họ in 11-17. Đánh cặp lộn là đánh cả hai con nên trúng
 * một con là trúng — "một trong hai" mới là nghĩa người chơi dùng.
 *
 * CAP50 chứa SỐ NGUYÊN, còn ``r.n`` chứa chuỗi hai ký tự. So thẳng hai kiểu đó
 * thì 0 không bao giờ bằng "00": bản đầu báo cả 50 cặp "chưa từng về" trên
 * 2394 kỳ — kết quả vô lý mà bảng vẫn dựng ra bình thường, không lỗi nào.
 */
function pairGaps() {
  const last = new Array(CAP50.length).fill(-1);
  const maxGap = new Array(CAP50.length).fill(0);
  const hits = new Array(CAP50.length).fill(0);
  DRAWS.forEach((r, t) => {
    const seen = new Set(r.n.map((x) => parseInt(x, 10)));
    CAP50.forEach((pair, i) => {
      if (!seen.has(pair[0]) && !seen.has(pair[1])) return;
      hits[i] += 1;
      if (last[i] >= 0) maxGap[i] = Math.max(maxGap[i], t - last[i]);
      last[i] = t;
    });
  });
  const n = DRAWS.length;
  const current = last.map((t) => (t >= 0 ? n - 1 - t : n));
  return { last, maxGap, current, hits };
}

/** Ngày dạng dd-mm-yyyy như trang tham chiếu, từ chuỗi ISO. */
function viDate(d) {
  return `${d.slice(8)}-${d.slice(5, 7)}-${d.slice(0, 4)}`;
}

/** Ngày của một kỳ theo chỉ số. */
function drawDate(i) {
  return i < 0 ? "chưa từng" : viDate(DRAWS[i].d);
}

function renderLoGan() {
  const g = lotoGaps();
  setCount(DRAWS);

  // 1. Gan hiện tại, giảm dần.
  const order = g.current.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Bộ số", "Ngày ra cuối cùng", "Số kỳ gan", "Gan cực đại", "Tổng lần về"],
    order.map((p) => [
      pad2(p[0]), drawDate(g.last[p[0]]), p[1], g.maxGap[p[0]] || "—", g.hits[p[0]],
    ]), { numeric: [2, 3, 4] });

  // 2. Gan cực đại, tách đôi để đọc cạnh nhau như trang tham chiếu.
  const half = (el, from, to) => table(el, ["Bộ số", "Gan cực đại"],
    Array.from({ length: to - from }, (_, k) => {
      const i = from + k;
      return [pad2(i), g.maxGap[i] ? `${g.maxGap[i]} kỳ` : "—"];
    }), { numeric: [1] });
  half($("sp-max-lo"), 0, 50);
  half($("sp-max-hi"), 50, 100);

  // 3. Cặp lô gan.
  const pg = pairGaps();
  const pairOrder = pg.current.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  table($("sp-pair-gan"),
    ["Cặp số", "Ngày ra gần đây", "Số kỳ gan", "Gan cực đại", "Tổng lần về"],
    pairOrder.map((p) => [
      `${pad2(CAP50[p[0]][0])} - ${pad2(CAP50[p[0]][1])}`, drawDate(pg.last[p[0]]), p[1],
      pg.maxGap[p[0]] || "—", pg.hits[p[0]],
    ]), { numeric: [2, 3, 4] });
}

function renderSpecialCycle() {
  const s = specialGaps();
  setCount(DRAWS);
  const order = s.current.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Hạng", "Số", "Chưa về (kỳ)", "Chu kỳ dài nhất", "Tổng lần về"],
    order.map((p, k) => [k + 1, pad2(p[0]), p[1], s.maxGap[p[0]] || "—", s.hits[p[0]]]),
    { numeric: [0, 2, 3, 4] });
}

function renderSpecialBySet() {
  const s = specialGaps();
  setCount(DRAWS);
  const rows = [];
  for (let i = 0; i < 100; i++) {
    const lastDate = s.last[i] >= 0 ? DRAWS[s.last[i]].d : "chưa từng";
    rows.push([pad2(i), lastDate, s.current[i], s.maxGap[i] || "—", s.hits[i]]);
  }
  rows.sort((a, b) => b[2] - a[2]);
  table($("sp-grid"),
    ["Bộ số", "Về gần nhất", "Chưa về (kỳ)", "Chu kỳ dài nhất", "Tổng lần về"],
    rows, { numeric: [2, 3, 4] });
}

function renderTomorrow() {
  const s = specialGaps();
  setCount(DRAWS);
  // Điểm tham khảo: số kỳ chưa về chuẩn hoá theo chu kỳ dài nhất của chính
  // con đó. Đây là mô tả lịch sử, KHÔNG phải xác suất đã hiệu chuẩn.
  const scored = [];
  for (let i = 0; i < 100; i++) {
    const ceiling = Math.max(s.maxGap[i], 1);
    scored.push([i, s.current[i] / ceiling, s.current[i], s.maxGap[i]]);
  }
  scored.sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Hạng", "Số", "Chưa về / chu kỳ dài nhất", "Chưa về", "Chu kỳ dài nhất"],
    scored.slice(0, 30).map((p, k) => [
      k + 1, pad2(p[0]), p[1].toFixed(2), p[2], p[3] || "—",
    ]), { numeric: [0, 2, 3, 4] });
}


function groupSpecial(keyOf, label) {
  const rows = selected();
  setCount(rows);
  const groups = new Map();
  rows.forEach((r) => {
    const k = keyOf(r.d);
    if (!groups.has(k)) groups.set(k, new Array(100).fill(0));
    groups.get(k)[parseInt(lastTwo(r.s), 10)] += 1;
  });
  const keys = Array.from(groups.keys()).sort().reverse();
  const head = [label, "Số kỳ", "Về nhiều nhất", "Số lần", "Không về"];
  const body = keys.map((k) => {
    const c = groups.get(k);
    const total = c.reduce((a, b) => a + b, 0);
    const best = c.indexOf(Math.max(...c));
    const missing = c.filter((v) => v === 0).length;
    return [k, total, pad2(best), Math.max(...c), missing];
  });
  table($("sp-grid"), head, body, { numeric: [1, 3, 4] });
}

// Khai báo bằng `function`, KHÔNG dùng `const`: boot() tra hàm qua
// window[renderName], mà `const` ở cấp cao nhất của script cổ điển không tạo
// thuộc tính trên window. Dùng const thì hai trang này im lặng không vẽ gì.
// --- Ba bảng Đặc Biệt ------------------------------------------------------
//
// Bố cục lấy theo trang tham chiếu, đọc được cấu trúc thật bằng
// .github/workflows/inspect-reference-pages.yml:
//
//   bang-dac-biet        53 hàng x 7 cột, hàng = tuần ISO, cột = Thứ 2..CN
//   bang-dac-biet-thang  31 x 12 cho một năm, cộng bảng "cùng tháng nhiều năm"
//   bang-dac-biet-nam    chọn Kiểu tuần (53x7) hoặc Kiểu tháng (31x12)

const WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"];

/** Chỉ số thứ trong tuần, 0 = Thứ 2 (không phải Chủ nhật như getDay). */
function mondayIndex(iso) {
  return (new Date(iso + "T00:00:00Z").getUTCDay() + 6) % 7;
}

/** Thứ Hai của tuần chứa ``iso``, dạng ISO. */
function weekStart(iso) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - mondayIndex(iso));
  return d.toISOString().slice(0, 10);
}

function fillPicker(id, values, prefer) {
  const sel = $(id);
  if (!sel) return null;
  if (!sel.options.length) {
    sel.innerHTML = values.map((v) => `<option>${v}</option>`).join("");
    sel.value = prefer !== undefined ? prefer : values[values.length - 1];
  }
  return sel.value;
}

/** Lưới tuần: hàng = tuần, cột = thứ. Dùng cho cả trang tuần và Kiểu tuần. */
function weekGrid(rows) {
  const byDate = {};
  rows.forEach((r) => { byDate[r.d] = r.s; });

  const weeks = new Map();
  rows.forEach((r) => {
    const w = weekStart(r.d);
    if (!weeks.has(w)) weeks.set(w, new Array(7).fill(""));
    weeks.get(w)[mondayIndex(r.d)] = specialCell(byDate[r.d], r.d);
  });
  return Array.from(weeks.keys()).sort().map((w) => weeks.get(w));
}

function renderSpecialByWeek() {
  const rows = selected();
  setCount(rows);
  table($("sp-grid"), WEEKDAYS, weekGrid(rows), { rowHead: false });
}

/** Lưới tháng: hàng = ngày 1..31, cột = 12 tháng của một năm. */
function monthGrid(year) {
  const byDate = {};
  DRAWS.filter((r) => r.d.slice(0, 4) === year).forEach((r) => { byDate[r.d] = r.s; });

  const body = [];
  for (let day = 1; day <= 31; day++) {
    const line = [`<b>${pad2(day)}</b>`];
    for (let m = 1; m <= 12; m++) {
      const de = byDate[`${year}-${pad2(m)}-${pad2(day)}`];
      line.push(de ? specialCell(de, null) : "");
    }
    body.push(line);
  }
  return body;
}

const MONTH_HEAD = ["Ngày"].concat(
  Array.from({ length: 12 }, (_, m) => "Tháng " + (m + 1)));

function renderSpecialYearByDay() {
  // Hàng là NĂM, cột là ngày 1-31, cho MỘT tháng đã chọn. Tên hàm nói theo BỐ
  // CỤC chứ không theo tên trang: hai trang này từng hiện đúng cùng một bảng
  // và tên trang thì ngược với nội dung, nên đặt tên theo trục mà bảng trải ra
  // là cách duy nhất để lần sau không lẫn lại.
  const months = Array.from({ length: 12 }, (_, m) => "Tháng " + (m + 1));
  const monthLabel = fillPicker("sp-month", months, months[new Date().getMonth()]);
  const month = months.indexOf(monthLabel) + 1;

  const inMonth = DRAWS.filter((r) => +r.d.slice(5, 7) === month);
  setCount(inMonth);

  const byYear = new Map();
  inMonth.forEach((r) => {
    const year = r.d.slice(0, 4);
    if (!byYear.has(year)) byYear.set(year, new Array(31).fill(""));
    byYear.get(year)[+r.d.slice(8) - 1] = specialCell(r.s, null);
  });

  const head = ["Năm"].concat(Array.from({ length: 31 }, (_, i) => String(i + 1)));
  const body = Array.from(byYear.keys()).sort().reverse()
    .map((year) => [`<b>${year}</b>`].concat(byYear.get(year)));
  table($("sp-grid"), head, body);
}

function renderSpecialDayByMonth() {
  // Hàng là ngày 1-31, cột là THÁNG 1-12, cho MỘT năm đã chọn.
  const years = Array.from(new Set(DRAWS.map((r) => r.d.slice(0, 4)))).sort();
  const year = fillPicker("sp-year", years) || years[years.length - 1];
  setCount(DRAWS.filter((r) => r.d.slice(0, 4) === year));
  table($("sp-grid"), MONTH_HEAD, monthGrid(year));
}

function renderOverview() {
  const rows = selected();
  setCount(rows);
  const counts = countLoto(rows);
  const expected = LOTO_BASELINE * rows.length;
  const s = specialGaps();
  const hottest = counts.indexOf(Math.max(...counts));
  const coldest = s.current.indexOf(Math.max(...s.current));

  const kpi = $("sp-kpi");
  if (kpi) {
    kpi.innerHTML = [
      ["Số kỳ trong dải", rows.length],
      ["Kỳ vọng mỗi con", expected.toFixed(1) + " lần"],
      ["Về nhiều nhất", pad2(hottest) + " (" + counts[hottest] + ")"],
      ["Gan Đặc Biệt lâu nhất", pad2(coldest) + " (" + s.current[coldest] + " kỳ)"],
    ].map((p) => `<div class="sp-kpi-card"><span>${p[0]}</span><strong>${p[1]}</strong></div>`).join("");
  }
  const order = counts.map((v, i) => [i, v]).sort((a, b) => b[1] - a[1]);
  table($("sp-grid"),
    ["Hạng", "Số", "Lần về", "So kỳ vọng", "Gan Đặc Biệt (kỳ)", "Chu kỳ Đặc Biệt dài nhất"],
    order.slice(0, 40).map((p, k) => [
      k + 1, pad2(p[0]), p[1],
      expected ? (p[1] / expected).toFixed(2) + "×" : "—",
      s.current[p[0]], s.maxGap[p[0]] || "—",
    ]), { numeric: [0, 2, 3, 4, 5] });
}

// --- Khởi động -------------------------------------------------------------

function boot(renderName) {
  const render = window[renderName];
  if (typeof render !== "function") return;

  const from = $("sp-from"), to = $("sp-to");
  if (from && to && DRAWS.length) {
    from.min = to.min = DRAWS[0].d;
    from.max = to.max = DRAWS[DRAWS.length - 1].d;
    from.value = DRAWS[Math.max(0, DRAWS.length - 90)].d;
    to.value = DRAWS[DRAWS.length - 1].d;
  }
  // Trang tần suất CẶP không có lưới chọn 00-99, nên popup chu kỳ gan không
  // có đường vào. Một ô chọn nhỏ đưa tính năng ấy tới cả hai trang mà không
  // phải nhét lưới 100 nút vào trang vốn làm việc theo họ cặp.
  const ganPick = $("sp-gan-pick");
  if (ganPick) {
    ganPick.addEventListener("change", () => {
      if (ganPick.value) { openGanPopup(ganPick.value); ganPick.value = ""; }
    });
  }

  const quick = $("sp-quick");
  if (quick) {
    quick.addEventListener("click", (ev) => {
      const days = ev.target.dataset.days;
      if (!days) return;
      // Đặt mốc bằng cách lùi từ KỲ MỚI NHẤT CÓ DỮ LIỆU, không lùi từ hôm nay:
      // lùi từ hôm nay sẽ hụt mất mấy kỳ mỗi khi kho chưa cập nhật tới hôm nay.
      const latest = DRAWS.length ? DRAWS[DRAWS.length - 1].d : "";
      if (!latest) return;
      const [y, m, d] = latest.split("-").map(Number);
      const start = new Date(Date.UTC(y, m - 1, d));
      start.setUTCDate(start.getUTCDate() - (Number(days) - 1));
      if (from) from.value = start.toISOString().slice(0, 10);
      if (to) to.value = latest;
      render();
    });
  }

  [from, to, $("sp-year"), $("sp-month"), $("sp-mode"), $("sp-orient"), $("sp-weekday"),
   $("sp-sort")].forEach(
    (el) => el && el.addEventListener("change", render));

  // Chỉ nút BÊN TRONG .sp-chips. "Xoá đánh dấu" từng dùng chung lớp .sp-chip
  // nên nó cũng dính bộ xử lý này: dataset.days là undefined -> parseInt ra
  // NaN -> nhánh "Tất cả" -> bấm xoá đánh dấu thì dải ngày âm thầm nhảy từ
  // 90 kỳ lên 2 396 kỳ. Người dùng không hề yêu cầu điều đó.
  document.querySelectorAll(".sp-chips .sp-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sp-chips .sp-chip").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      const days = parseInt(btn.dataset.days, 10);
      if (from && to && DRAWS.length) {
        to.value = DRAWS[DRAWS.length - 1].d;
        from.value = days ? DRAWS[Math.max(0, DRAWS.length - days)].d : DRAWS[0].d;
      }
      render();
    });
  });
  bindMarking();
  bindGanPopup(render);
  bindColumnHint();
  renderLegend();
  bindFieldToggles(render);
  bindPicker(render);
  render();
}


// --- Cầu giải Đặc Biệt -------------------------------------------------------
//
// Ba khối, theo đúng bố cục đọc được từ trang tham chiếu:
//   1. Ma trận 10x10 tần suất hai số cuối giải Đặc Biệt, xếp theo Đầu 0-9.
//   2. Cặp lộn thật kèm số lần, sắp giảm dần.
//   3. Kết quả ba kỳ gần nhất, đủ các giải.

function renderSpecialBridge() {
  const rows = selected();
  setCount(rows);

  const count = new Array(100).fill(0);
  rows.forEach((r) => { count[parseInt(lastTwo(r.s), 10)] += 1; });

  // 1. Ma trận Đầu 0-9 x Đuôi 0-9.
  const head = ["Đầu"].concat(Array.from({ length: 10 }, (_, d) => String(d)));
  const body = Array.from({ length: 10 }, (_, tens) =>
    [`<b>Đầu ${tens}</b>`].concat(Array.from({ length: 10 }, (_, ones) => {
      const n = tens * 10 + ones;
      return count[n]
        ? `<b>${pad2(n)}</b><i class="sp-times">${count[n]} lần</i>`
        : `<span class="sp-none">${pad2(n)}</span>`;
    })));
  table($("sp-grid"), head, body);

  // 2. Cặp lộn kèm số lần. Số kép đảo lại chính nó nên không nằm ở đây.
  const lon = $("sp-lon");
  if (lon) {
    const pairs = reversePairs()
      .map(([a, b]) => [a, b, count[a] + count[b]])
      .filter((p) => p[2] > 0)
      .sort((x, y) => y[2] - x[2]);
    table(lon, ["Hạng", "Cặp lộn", "Số lần xuất hiện"],
      pairs.map((p, k) => [k + 1, `${pad2(p[0])} - ${pad2(p[1])}`, p[2]]),
      { numeric: [0, 2] });
  }

  // 3. Ba kỳ gần nhất, đủ giải.
  const recent = $("sp-recent");
  if (recent) {
    const last = DRAWS.slice(-3).reverse();
    recent.innerHTML = last.map((r) => {
      const cells = r.n.map((x) => `<span class="sp-lo">${x}</span>`).join("");
      return `<div class="sp-draw"><h4>Kết quả ngày ${r.d.slice(8)}-` +
        `${r.d.slice(5, 7)}-${r.d.slice(0, 4)}</h4>` +
        `<p class="sp-db">Đặc Biệt <b>${String(r.s).padStart(5, "0")}</b></p>` +
        `<div class="sp-lolist">${cells}</div></div>`;
    }).join("");
  }
}


// --- Giải Đặc Biệt theo TỔNG ------------------------------------------------
//
// Tổng = (Đầu + Đuôi) mod 10, nên có 10 giá trị 0-9. Ba bảng, theo bố cục đọc
// được từ trang tham chiếu:
//   1. Gan theo tổng: tổng nào lâu chưa về nhất.
//   2. Chuyển tổng: hôm qua tổng X thì hôm nay tổng Y với xác suất bao nhiêu.
//   3. Chẵn/lẻ hôm sau, theo tổng hôm qua.
//
// Bảng 2 và 3 là thống kê MÔ TẢ trên lịch sử, không phải dự báo đã hiệu
// chuẩn. Ghi chú mốc ngẫu nhiên đi kèm nói rõ điều đó: với 10 giá trị, mức
// ngẫu nhiên là 10% mỗi ô, và lệch vài phần trăm trên vài trăm kỳ là chuyện
// thường.

function tongOf(special) {
  const two = lastTwo(special);
  return (+two[0] + +two[1]) % 10;
}

function renderSpecialByTong() {
  const rows = selected();
  setCount(rows);
  if (!rows.length) {
    // Không return trắng: bảng sẽ giữ số liệu của dải trước. Dựng lại cả ba
    // với đúng tiêu đề của chúng để table() gắn dòng "dải rỗng".
    table($("sp-grid"), ["Tổng", "Ngày ra gần nhất", "Số kỳ chưa về", "Tổng số lần"], []);
    table($("sp-trans"), ["Tổng hôm trước", "Tổng hôm sau", "Số lần",
      "Trên tổng số kỳ", "Tỉ lệ", "Lệch chuẩn hoá"], []);
    table($("sp-parity"), ["Tổng hôm trước", "Số kỳ", "Hôm sau tổng chẵn",
      "Hôm sau tổng lẻ"], []);
    return;
  }

  // 1. Gan theo tổng.
  const lastSeen = new Array(10).fill(-1);
  const hits = new Array(10).fill(0);
  rows.forEach((r, i) => { const t = tongOf(r.s); lastSeen[t] = i; hits[t] += 1; });
  const gan = Array.from({ length: 10 }, (_, t) => [
    t,
    lastSeen[t] < 0 ? "—" : rows[lastSeen[t]].d,
    lastSeen[t] < 0 ? rows.length : rows.length - 1 - lastSeen[t],
    hits[t],
  ]).sort((a, b) => b[2] - a[2]);
  table($("sp-grid"), ["Tổng", "Ngày ra gần nhất", "Số kỳ chưa về", "Tổng số lần"],
    gan.map((g) => [`<b>${g[0]}</b>`, g[1], g[2], g[3]]), { numeric: [0, 2, 3] });

  // 2. Chuyển tổng: đếm cặp (hôm qua, hôm nay) trên các kỳ LIỀN KỀ thật.
  //    Bỏ qua ranh giới ngày nghỉ quay — nối hai kỳ cách nhau nhiều ngày lại
  //    thành "hôm sau" là bịa ra một chuyển tiếp không tồn tại.
  const trans = Array.from({ length: 10 }, () => new Array(10).fill(0));
  const fromTotal = new Array(10).fill(0);
  for (let i = 1; i < rows.length; i++) {
    const gap = (new Date(rows[i].d) - new Date(rows[i - 1].d)) / 86400000;
    if (gap !== 1) continue;
    const a = tongOf(rows[i - 1].s), b = tongOf(rows[i].s);
    trans[a][b] += 1; fromTotal[a] += 1;
  }

  // Xếp theo TỈ LỆ là cách chắc chắn đẩy nhiễu lên đầu: một ô 3/9 cho 33 %
  // và đứng trên mọi ô khác, dù ba lần thì chẳng nói lên điều gì. Xếp theo
  // độ lệch CHUẨN HOÁ so với mức ngẫu nhiên 10 %, tức chia cho sai số chuẩn
  // sqrt(p(1-p)/n) — cùng một độ lệch phần trăm trên mẫu lớn mới đáng kể.
  const P0 = 0.1;
  const flat = [];
  for (let a = 0; a < 10; a++) {
    if (!fromTotal[a]) continue;
    for (let b = 0; b < 10; b++) {
      const n = fromTotal[a];
      const pct = 100 * trans[a][b] / n;
      const se = Math.sqrt(P0 * (1 - P0) / n) * 100;
      flat.push([a, b, trans[a][b], n, pct, se ? (pct - 10) / se : 0]);
    }
  }
  flat.sort((x, y) => Math.abs(y[5]) - Math.abs(x[5]));

  const tr = $("sp-trans");
  if (tr) {
    table(tr,
      ["Tổng hôm trước", "Tổng hôm sau", "Số lần", "Trên tổng số kỳ", "Tỉ lệ", "Lệch chuẩn hoá"],
      flat.slice(0, 40).map((f) => [
        `<b>${f[0]}</b>`, `<b>${f[1]}</b>`, f[2], f[3],
        f[4].toFixed(2).replace(".", ",") + " %",
        (f[5] > 0 ? "+" : "") + f[5].toFixed(2).replace(".", ","),
      ]), { numeric: [0, 1, 2, 3, 4, 5] });
  }

  // 3. Chẵn/lẻ của tổng hôm sau, theo tổng hôm trước.
  const par = $("sp-parity");
  if (par) {
    const body = [];
    for (let a = 0; a < 10; a++) {
      if (!fromTotal[a]) continue;
      let even = 0;
      for (let b = 0; b < 10; b += 2) even += trans[a][b];
      const pct = 100 * even / fromTotal[a];
      body.push([`<b>${a}</b>`, fromTotal[a],
        pct.toFixed(2).replace(".", ",") + " %",
        (100 - pct).toFixed(2).replace(".", ",") + " %"]);
    }
    table(par, ["Tổng hôm trước", "Số kỳ", "Hôm sau tổng chẵn", "Hôm sau tổng lẻ"],
      body, { numeric: [0, 1, 2, 3] });
  }
}
