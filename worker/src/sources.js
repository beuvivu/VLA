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

// xosothudo.com.vn là nguồn ưu tiên số một. Mẫu đường dẫn CHƯA kiểm chứng
// được từ môi trường phát triển (sandbox chặn toàn bộ HTTP ra ngoài), nên nguồn
// này khai báo nhiều ứng viên và thử lần lượt thay vì chốt cứng một phỏng đoán.
const THU_DO_DATE_URLS = (d) => [
  `https://xosothudo.com.vn/xsmb-${dmy(d, "-")}.html`,
  `https://xosothudo.com.vn/ket-qua-xo-so-mien-bac/${dmy(d, "-")}.html`,
  `https://xosothudo.com.vn/xsmb/${dmy(d, "-")}.html`,
];

// Tầng ưu tiên MỘT. Chỉ hai nguồn này được gọi ở lượt đầu.
export const PRIMARY_SOURCES = [
  {
    name: "xosothudo.com.vn",
    tier: "primary",
    dateUrls: THU_DO_DATE_URLS,
    liveUrls: (d) => [
      "https://xosothudo.com.vn/tuong-thuat-truc-tiep-xsmb.html",
      "https://xosothudo.com.vn/xsmb-truc-tiep.html",
      ...THU_DO_DATE_URLS(d),
    ],
  },
  {
    name: "xoso.com.vn",
    tier: "primary",
    dateUrls: (d) => [`https://xoso.com.vn/xsmb-${dmy(d, "-")}.html`],
    liveUrls: () => ["https://xoso.com.vn/tuong-thuat-mien-bac/xsmb-tructiep.html"],
  },
];

// Tầng DỰ PHÒNG. Chỉ chạm tới khi tầng chính không đủ để xác minh.
export const FALLBACK_SOURCES = [
  {
    name: "xskt.vn",
    tier: "fallback",
    dateUrls: () => ["https://xskt.vn/xsmb-500-ngay/"],
    liveUrls: () => ["https://xskt.vn/"],
    selectSection: xsktSection,
  },
  {
    name: "mketqua.net",
    tier: "fallback",
    // Trang theo NGÀY xác định hơn sổ cái cuộn, nên phải nối ngày vào — bản
    // đầu tôi viết thiếu đoạn ấy và phép kiểm đối chiếu danh mục bắt được.
    dateUrls: (d) => ["https://mketqua.net/x%E1%BB%95-s%E1%BB%91-Truy%E1%BB%81n-Th%E1%BB%91ng/"
      + `${dmy(d, "-")}.html`],
    liveUrls: () => ["https://mketqua.net/xo-so-truyen-thong.php"],
  },
  {
    name: "www.minhngoc.net.vn",
    tier: "fallback",
    dateUrls: (d) => [`https://www.minhngoc.net.vn/ket-qua-xo-so/mien-bac/${dmy(d, "-")}.html`],
    liveUrls: () => ["https://www.minhngoc.net.vn/xo-so-truc-tiep/mien-bac.html"],
  },
  {
    name: "xosominhngoc.com",
    tier: "fallback",
    dateUrls: (d) => [`https://www.xosominhngoc.com/kqxs/mien-bac/${dmy(d, "-")}.html`],
    liveUrls: () => ["https://www.xosominhngoc.com/xo-so-truc-tiep/mien-bac.html"],
  },
  {
    name: "xosodaiphat.com",
    tier: "fallback",
    dateUrls: (d) => [`https://xosodaiphat.com/xsmb-${dmy(d, "-")}.html`],
    liveUrls: (d) => [`https://xosodaiphat.com/xsmb-${dmy(d, "-")}.html`],
  },
  {
    name: "hainhay.net",
    tier: "fallback",
    dateUrls: () => ["https://www.hainhay.net/so-ket-qua-truyen-thong/300"],
    liveUrls: () => ["https://www.hainhay.net/"],
    selectSection: hainhaySection,
  },
];

export const SOURCES = [...PRIMARY_SOURCES, ...FALLBACK_SOURCES];

export const SOURCE_NAMES = SOURCES.map((s) => s.name);

// Mã công khai thay cho tên miền. Mọi thứ ra tới trình duyệt phải dùng mã này.
export const SOURCE_PUBLIC_CODE = Object.fromEntries([
  ...PRIMARY_SOURCES.map((s, i) => [s.name, `P${i + 1}`]),
  ...FALLBACK_SOURCES.map((s, i) => [s.name, `F${i + 1}`]),
]);

export function publicSourceCode(name) {
  return Object.prototype.hasOwnProperty.call(SOURCE_PUBLIC_CODE, name)
    ? SOURCE_PUBLIC_CODE[name]
    : "?";
}
