function pad(value) {
  return String(value).padStart(2, "0");
}

function dmy(date, sep) {
  return [pad(date.day), pad(date.month), String(date.year)].join(sep);
}

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

export const SOURCE_PUBLIC_CODE = Object.fromEntries([
  ...PRIMARY_SOURCES.map((s, i) => [s.name, `P${i + 1}`]),
  ...FALLBACK_SOURCES.map((s, i) => [s.name, `F${i + 1}`]),
]);

export function publicSourceCode(name) {
  return Object.prototype.hasOwnProperty.call(SOURCE_PUBLIC_CODE, name)
    ? SOURCE_PUBLIC_CODE[name]
    : "?";
}
