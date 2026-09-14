// REST API cho trang "Sổ kết quả truyền thống".
//
// Luồng dữ liệu có thứ tự cứng:
// 1. lịch sử chuẩn trong data/xsmb.json của VLA;
// 2. lớp bù đã lưu trong KV;
// 3. chỉ khi vẫn thiếu ngày mới gọi sổ cuộn xskt.vn đúng MỘT lần.
//
// Kết quả lấy từ xskt.vn được lưu vào KV ngay để các lượt xem sau không cào
// lại. Quy trình Python hằng ngày dùng cùng nguồn XsktVnSource và sẽ đưa kỳ
// hợp lệ vào data/xsmb.json sau bước đồng thuận/canonical validation.

import {
  EXPECTED_COUNTS,
  EXPECTED_WIDTHS,
  PRIZE_ORDER,
  extractPartialPrizeMap,
  validPrizeToken,
} from "./prize_map.js";
import { vietnamParts } from "./snapshot.js";

const DEFAULT_HISTORY_URL =
  "https://raw.githubusercontent.com/beuvivu/VLA/main/data/xsmb.json";
const DEFAULT_XSKT_URL = "https://xskt.vn/xsmb-500-ngay/";
const PRIMARY_FRESH_KEY = "traditional:primary:fresh:v1";
const PRIMARY_LAST_GOOD_KEY = "traditional:primary:last-good:v1";
const OVERLAY_KEY = "traditional:xskt-overlay:v1";
const RESPONSE_PREFIX = "traditional:response:v1:";
const ALLOWED_DAYS = new Set([30, 60, 90, 100]);
const MAX_RANGE_DAYS = 500;

const PRIZE_LABELS = {
  special: "Đặc Biệt",
  prize1: "Giải Nhất",
  prize2: "Giải Nhì",
  prize3: "Giải Ba",
  prize4: "Giải Tư",
  prize5: "Giải Năm",
  prize6: "Giải Sáu",
  prize7: "Giải Bảy",
  prize8: "Giải Tám",
};

const INTERNAL_FIELDS = {
  special: ["special"],
  prize1: ["prize1"],
  prize2: ["prize2_1", "prize2_2"],
  prize3: ["prize3_1", "prize3_2", "prize3_3", "prize3_4", "prize3_5", "prize3_6"],
  prize4: ["prize4_1", "prize4_2", "prize4_3", "prize4_4"],
  prize5: ["prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6"],
  prize6: ["prize6_1", "prize6_2", "prize6_3"],
  prize7: ["prize7_1", "prize7_2", "prize7_3", "prize7_4"],
};

function response(body, { status = 200, cacheControl = "no-store" } = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": cacheControl,
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, OPTIONS",
    },
  });
}

function cacheStore(env) {
  const kv = env?.RESULTS_CACHE ?? env?.LIVE;
  return kv && typeof kv.get === "function" && typeof kv.put === "function" ? kv : null;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function isoDate(date) {
  return `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())}`;
}

function parseDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
  if (!match) return null;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return isoDate(date) === value ? date : null;
}

function addDays(date, amount) {
  return new Date(date.getTime() + amount * 86_400_000);
}

function daysInclusive(from, to) {
  return Math.floor((to.getTime() - from.getTime()) / 86_400_000) + 1;
}

function latestEligibleDate(nowUtcMs) {
  const parts = vietnamParts(nowUtcMs);
  const today = new Date(Date.UTC(parts.year, parts.month - 1, parts.day));
  const afterCutoff = parts.hour > 18 || (parts.hour === 18 && parts.minute >= 35);
  return afterCutoff ? today : addDays(today, -1);
}

export function parseTraditionalQuery(url, { nowUtcMs = Date.now() } = {}) {
  const region = url.searchParams.get("region") || "north";
  const province = url.searchParams.get("province") || "hanoi";
  if (region !== "north" || province !== "hanoi") {
    throw new Error("Phiên bản hiện tại chỉ hỗ trợ Miền Bắc / Hà Nội.");
  }

  const fromRaw = url.searchParams.get("from");
  const toRaw = url.searchParams.get("to");
  let from;
  let to;
  let presetDays = null;
  if (fromRaw !== null || toRaw !== null) {
    if (!fromRaw || !toRaw) throw new Error("Khoảng tùy chọn phải có đủ từ ngày và đến ngày.");
    from = parseDate(fromRaw);
    to = parseDate(toRaw);
    if (!from || !to) throw new Error("Ngày phải đúng định dạng YYYY-MM-DD.");
  } else {
    const days = Number(url.searchParams.get("days") || 30);
    if (!Number.isInteger(days) || !ALLOWED_DAYS.has(days)) {
      throw new Error("Số ngày chỉ nhận 30, 60, 90 hoặc 100.");
    }
    presetDays = days;
    to = latestEligibleDate(nowUtcMs);
    from = addDays(to, -(days - 1));
  }

  if (from > to) throw new Error("Từ ngày không được sau đến ngày.");
  if (daysInclusive(from, to) > MAX_RANGE_DAYS) {
    throw new Error(`Khoảng tùy chọn tối đa ${MAX_RANGE_DAYS} ngày.`);
  }
  return {
    region,
    province,
    from: isoDate(from),
    to: isoDate(to),
    preset_days: presetDays,
    timezone: "Asia/Ho_Chi_Minh",
  };
}

function prizeMapFromInternal(row) {
  const prizes = {};
  for (const key of PRIZE_ORDER) {
    prizes[key] = INTERNAL_FIELDS[key].map((field) => {
      const value = row[field];
      if (value === null || value === undefined || value === "") return null;
      const token = String(value).trim().padStart(EXPECTED_WIDTHS[key], "0");
      return validPrizeToken(token, key);
    });
    if (prizes[key].some((value) => value === null)) return null;
  }
  return prizes;
}

function completePrizeMap(prizes) {
  return PRIZE_ORDER.every((key) => {
    const values = prizes?.[key];
    return Array.isArray(values)
      && values.length === EXPECTED_COUNTS[key]
      && values.every((value) => validPrizeToken(value, key) !== null);
  });
}

function normalizePrimary(payload) {
  if (!Array.isArray(payload)) throw new Error("Dữ liệu VLA không phải một danh sách.");
  const byDate = {};
  for (const row of payload) {
    const drawDate = String(row?.date || "").slice(0, 10);
    if (!parseDate(drawDate)) continue;
    const prizes = prizeMapFromInternal(row);
    if (prizes && completePrizeMap(prizes)) byDate[drawDate] = prizes;
  }
  if (Object.keys(byDate).length === 0) throw new Error("Dữ liệu VLA không có kỳ hợp lệ.");
  return byDate;
}

async function readJson(kv, key) {
  if (!kv) return null;
  const raw = await kv.get(key);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

async function loadPrimary(env, fetchImpl) {
  const kv = cacheStore(env);
  const fresh = await readJson(kv, PRIMARY_FRESH_KEY);
  if (fresh) return { rows: fresh, cache: "hit" };

  const historyUrl = env?.VLA_HISTORY_URL || DEFAULT_HISTORY_URL;
  try {
    const fetched = await fetchImpl(historyUrl, {
      headers: {
        "Accept": "application/json",
        "User-Agent": "VLA-traditional-results/1.0",
      },
      signal: AbortSignal.timeout(10_000),
    });
    if (!fetched.ok) throw new Error(`HTTP ${fetched.status}`);
    const rows = normalizePrimary(await fetched.json());
    if (kv) {
      await kv.put(PRIMARY_FRESH_KEY, JSON.stringify(rows), { expirationTtl: 300 });
      await kv.put(PRIMARY_LAST_GOOD_KEY, JSON.stringify(rows), { expirationTtl: 129_600 });
    }
    return { rows, cache: "miss" };
  } catch (error) {
    const stale = await readJson(kv, PRIMARY_LAST_GOOD_KEY);
    if (stale) return { rows: stale, cache: "stale", warning: String(error?.message || error) };
    throw new Error(`Không đọc được CSDL VLA: ${String(error?.message || error)}`);
  }
}

export function parseXsktLedger(html) {
  const rows = {};
  const tablePattern = /<table\b[^>]*class=["'][^"']*\bkqmb\b[^"']*["'][^>]*>[\s\S]*?<\/table\s*>/gi;
  for (const match of String(html || "").matchAll(tablePattern)) {
    const table = match[0];
    const dateMatch = /XSMB[\s\S]{0,180}?ngày\s*(\d{1,2})[-/]\s*(\d{1,2})[-/]\s*(\d{4})/i.exec(table);
    if (!dateMatch) continue;
    const drawDate = `${dateMatch[3]}-${pad2(dateMatch[2])}-${pad2(dateMatch[1])}`;
    if (!parseDate(drawDate)) continue;
    const prizes = extractPartialPrizeMap(table);
    if (completePrizeMap(prizes)) rows[drawDate] = prizes;
  }
  return rows;
}

async function loadXsktOverlay(env, fetchImpl, missingDates) {
  const kv = cacheStore(env);
  const overlay = (await readJson(kv, OVERLAY_KEY)) || {};
  let unresolved = missingDates.filter((day) => !completePrizeMap(overlay[day]?.prizes));
  let fetched = false;
  let warning = null;

  if (unresolved.length > 0) {
    const xsktUrl = env?.XSKT_HISTORY_URL || DEFAULT_XSKT_URL;
    try {
      const responseFromSource = await fetchImpl(xsktUrl, {
        headers: {
          "Accept": "text/html,application/xhtml+xml",
          "Accept-Language": "vi-VN,vi;q=0.9",
          "User-Agent": "VLA-traditional-results/1.0 (+https://github.com/beuvivu/VLA)",
        },
        signal: AbortSignal.timeout(12_000),
      });
      if (!responseFromSource.ok) {
        warning = `xskt.vn trả HTTP ${responseFromSource.status}`;
      } else {
        fetched = true;
        const parsed = parseXsktLedger(await responseFromSource.text());
        const fetchedAt = new Date().toISOString();
        for (const day of unresolved) {
          if (completePrizeMap(parsed[day])) {
            overlay[day] = { prizes: parsed[day], fetched_at_utc: fetchedAt };
          }
        }
        if (kv) await kv.put(OVERLAY_KEY, JSON.stringify(overlay), { expirationTtl: 2_592_000 });
      }
    } catch (error) {
      warning = `Không đọc được xskt.vn: ${String(error?.message || error)}`;
    }
    unresolved = missingDates.filter((day) => !completePrizeMap(overlay[day]?.prizes));
  }
  return { overlay, unresolved, fetched, warning };
}

function dateRange(from, to) {
  const start = parseDate(from);
  const end = parseDate(to);
  const out = [];
  for (let cursor = start; cursor <= end; cursor = addDays(cursor, 1)) out.push(isoDate(cursor));
  return out;
}

function headTail(prizes) {
  const heads = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(i), []]));
  const tails = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(i), []]));
  for (const key of PRIZE_ORDER) {
    for (const value of prizes[key]) {
      const two = value.slice(-2);
      heads[two[0]].push(two[1]);
      tails[two[1]].push(two[0]);
    }
  }
  for (let i = 0; i <= 9; i += 1) {
    heads[String(i)].sort();
    tails[String(i)].sort();
  }
  return { heads, tails };
}

function apiDraw(drawDate, prizes, source) {
  return {
    id: `north:hanoi:${drawDate}`,
    region: { code: "north", name: "Miền Bắc" },
    province: { code: "hanoi", name: "Hà Nội" },
    draw_date: drawDate,
    status: "official",
    source,
    prizes: PRIZE_ORDER.map((key) => ({
      code: key,
      name: PRIZE_LABELS[key],
      width: EXPECTED_WIDTHS[key],
      values: prizes[key],
    })),
    head_tail: headTail(prizes),
  };
}

function sourceCounts(data) {
  const counts = { vla_db: 0, xskt_fallback: 0 };
  for (const draw of data) counts[draw.source.kind] += 1;
  return counts;
}

export async function buildTraditionalResults(
  query,
  env,
  { fetchImpl = fetch, nowUtcMs = Date.now() } = {},
) {
  const primary = await loadPrimary(env, fetchImpl);
  const requestedDates = dateRange(query.from, query.to);
  const missing = requestedDates.filter((day) => !completePrizeMap(primary.rows[day]));
  const fallback = missing.length
    ? await loadXsktOverlay(env, fetchImpl, missing)
    : { overlay: {}, unresolved: [], fetched: false, warning: null };

  const data = [];
  for (const day of requestedDates) {
    if (completePrizeMap(primary.rows[day])) {
      data.push(apiDraw(day, primary.rows[day], {
        kind: "vla_db",
        provider: "VLA canonical database",
        canonical: true,
      }));
    } else if (completePrizeMap(fallback.overlay[day]?.prizes)) {
      data.push(apiDraw(day, fallback.overlay[day].prizes, {
        kind: "xskt_fallback",
        provider: "xskt.vn",
        canonical: false,
        fetched_at_utc: fallback.overlay[day].fetched_at_utc,
      }));
    }
  }
  data.sort((a, b) => b.draw_date.localeCompare(a.draw_date));
  const counts = sourceCounts(data);
  return {
    schema_version: 1,
    query,
    meta: {
      generated_at_utc: new Date(nowUtcMs).toISOString(),
      total_results: data.length,
      requested_calendar_days: requestedDates.length,
      latest_draw_date: data[0]?.draw_date ?? null,
      source_counts: counts,
      sources_used: Object.entries(counts).filter(([, n]) => n > 0).map(([name]) => name),
      fallback_requested: missing.length > 0,
      fallback_network_fetch: fallback.fetched,
      unresolved_dates: fallback.unresolved,
      primary_cache: primary.cache,
      warning: [primary.warning, fallback.warning].filter(Boolean).join("; ") || null,
    },
    data,
  };
}

export async function handleTraditionalResults(request, env, ctx) {
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "GET, OPTIONS",
        "access-control-max-age": "86400",
      },
    });
  }
  if (request.method !== "GET") return response({ error: "method not allowed" }, { status: 405 });

  let query;
  try {
    query = parseTraditionalQuery(new URL(request.url));
  } catch (error) {
    return response({ error: "invalid_query", message: String(error?.message || error) }, { status: 400 });
  }

  const kv = cacheStore(env);
  const cacheKey = RESPONSE_PREFIX + [query.region, query.province, query.from, query.to].join(":");
  const cached = await readJson(kv, cacheKey);
  if (cached) {
    cached.meta ??= {};
    cached.meta.response_cache = "hit";
    return response(cached, { cacheControl: "public, max-age=60, s-maxage=300" });
  }

  try {
    const payload = await buildTraditionalResults(query, env);
    payload.meta.response_cache = "miss";
    const write = kv?.put(cacheKey, JSON.stringify(payload), { expirationTtl: 300 });
    if (write && ctx?.waitUntil) ctx.waitUntil(write);
    else if (write) await write;
    return response(payload, { cacheControl: "public, max-age=60, s-maxage=300" });
  } catch (error) {
    return response({
      error: "results_unavailable",
      message: String(error?.message || error),
    }, { status: 502 });
  }
}
