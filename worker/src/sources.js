// Danh mục nguồn, khớp `src/ingest/sources.py`.
//
// Thứ tự mảng CHÍNH LÀ thứ tự ưu tiên khi các nguồn bất đồng. Đổi thứ tự ở
// đây mà không đổi bên Python là làm hai bên chọn khác nhau lúc chưa đủ đồng
// thuận — `tests/test_worker_sources_parity.py` chặn chuyện đó.

function pad(value) {
  return String(value).padStart(2, "0");
}

function dmy(date, sep) {
  return [pad(date.day), pad(date.month), String(date.year)].join(sep);
}

// Chính sách nguồn từ 13-10-2026, khớp `src/ingest/sources.py`: MỘT nguồn chính; hai nguồn dự
// phòng chỉ được gọi khi nguồn chính gặp sự cố (`primaryHasFailed` trong snapshot.js).
// Năm nguồn cũ đã nghỉ — xem chú thích `PRIMARY_SOURCE_NAMES` bên Python để biết vì sao.
export const PRIMARY_SOURCES = [
  {
    name: "xoso.com.vn",
    tier: "primary",
    dateUrls: (d) => [`https://xoso.com.vn/xsmb-${dmy(d, "-")}.html`],
    liveUrls: () => ["https://xoso.com.vn/tuong-thuat-mien-bac/xsmb-tructiep.html"],
  },
];

export const FALLBACK_SOURCES = [
  {
    name: "mketqua.net",
    tier: "fallback",
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
