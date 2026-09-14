// Danh mục nguồn và cách cắt phần trang, khớp `src/sources.py`.
//
// Thứ tự mảng CHÍNH LÀ thứ tự ưu tiên khi các nguồn bất đồng. Đổi thứ tự ở
// đây mà không đổi bên Python là làm hai bên chọn khác nhau lúc chưa đủ đồng
// thuận — `tests/test_worker_sources_parity.py` chặn chuyện đó.

import { htmlToLines } from "./prize_map.js";

function pad(value) {
  return String(value).padStart(2, "0");
}

function dmy(date, sep) {
  return [pad(date.day), pad(date.month), String(date.year)].join(sep);
}

// hainhay.net là một sổ cái cuộn: nhiều kỳ nằm chồng trên cùng một trang.
// Không cắt thì bộ bóc rất dễ vớ phải kỳ hôm trước. Bản Python cắt trên VĂN
// BẢN (không phải HTML) từ lần xuất hiện đầu của ngày cần lấy tới mốc kỳ kế
// tiếp, hoặc 5 000 ký tự.
function hainhaySection(html, date) {
  const text = htmlToLines(html).join("\n");
  const starts = [];
  for (const token of [dmy(date, "/"), dmy(date, "-")]) {
    let from = 0;
    for (;;) {
      const at = text.indexOf(token, from);
      if (at === -1) break;
      starts.push(at);
      from = at + 1;
    }
  }
  if (starts.length === 0) return html;
  const start = Math.min(...starts);
  const tail = text.slice(start + 80);
  const markers = [];
  for (const pattern of [/XSMB\s*[>\-]/i, /Kết Quả Miền Bắc\s*\(/i]) {
    const m = tail.match(pattern);
    if (m && m.index !== undefined) markers.push(start + 80 + m.index);
  }
  const end = markers.length > 0
    ? Math.min(...markers)
    : Math.min(text.length, start + 5000);
  return text.slice(start, end);
}

// xskt.vn cũng là sổ cái cuộn. Cắt từ đúng ngày được yêu cầu; trả chuỗi rỗng
// khi trang không có ngày ấy để bộ bóc không rơi ngược về kỳ mới nhất.
function xsktSection(html, date) {
  const text = htmlToLines(html).join("\n");
  const tokens = [
    dmy(date, "-"),
    `${date.day}-${date.month}-${date.year}`,
    dmy(date, "/"),
  ];
  const starts = tokens.map((token) => text.indexOf(token)).filter((at) => at >= 0);
  if (starts.length === 0) return "";
  const start = Math.min(...starts);
  return text.slice(start, Math.min(text.length, start + 8000));
}

export const SOURCES = [
  {
    name: "xoso.com.vn",
    dateUrl: (d) => `https://xoso.com.vn/xsmb-${dmy(d, "-")}.html`,
    liveUrl: () => "https://xoso.com.vn/tuong-thuat-mien-bac/xsmb-tructiep.html",
  },
  {
    name: "mketqua.net",
    // Trang theo NGÀY xác định hơn sổ cái cuộn, nên phải nối ngày vào — bản
    // đầu tôi viết thiếu đoạn ấy và phép kiểm đối chiếu danh mục bắt được.
    dateUrl: (d) => "https://mketqua.net/x%E1%BB%95-s%E1%BB%91-Truy%E1%BB%81n-Th%E1%BB%91ng/"
      + `${dmy(d, "-")}.html`,
    liveUrl: () => "https://mketqua.net/xo-so-truyen-thong.php",
  },
  {
    name: "www.minhngoc.net.vn",
    dateUrl: (d) => `https://www.minhngoc.net.vn/ket-qua-xo-so/mien-bac/${dmy(d, "-")}.html`,
    liveUrl: () => "https://www.minhngoc.net.vn/xo-so-truc-tiep/mien-bac.html",
  },
  {
    name: "xosominhngoc.com",
    dateUrl: (d) => `https://www.xosominhngoc.com/kqxs/mien-bac/${dmy(d, "-")}.html`,
    liveUrl: () => "https://www.xosominhngoc.com/xo-so-truc-tiep/mien-bac.html",
  },
  {
    name: "xosodaiphat.com",
    dateUrl: (d) => `https://xosodaiphat.com/xsmb-${dmy(d, "-")}.html`,
    liveUrl: (d) => `https://xosodaiphat.com/xsmb-${dmy(d, "-")}.html`,
  },
  {
    name: "hainhay.net",
    dateUrl: () => "https://www.hainhay.net/so-ket-qua-truyen-thong/300",
    liveUrl: () => "https://www.hainhay.net/",
    selectSection: hainhaySection,
  },
  {
    name: "xskt.vn",
    dateUrl: () => "https://xskt.vn/xsmb-500-ngay/",
    liveUrl: () => "https://xskt.vn/",
    selectSection: xsktSection,
  },
];

export const SOURCE_NAMES = SOURCES.map((s) => s.name);
