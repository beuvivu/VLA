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
const PRIMARY_FRESH_KEY = "traditional:primary:fresh:v2";
const PRIMARY_LAST_GOOD_KEY = "traditional:primary:last-good:v2";
const OVERLAY_KEY = "traditional:xskt-overlay:v1";
const ALLOWED_DAYS = new Set([30, 60, 90, 100]);
const MAX_RANGE_DAYS = 500;

const FALLBACK_WINDOW_DAYS = 500;

const FALLBACK_REFRESH_KEY = "traditional:fallback-refreshed-at:v1";
const FALLBACK_REFRESH_SECONDS = 600;
const ABSENT_RECHECK_DAYS = 7;

const PRIZE_LABELS = {
  special: "Đặc Biệt",
  prize1: "Giải Nhất",
  prize2: "Giải Nhì",
  prize3: "Giải Ba",
  prize4: "Giải Tư",
  prize5: "Giải Năm",
  prize6: "Giải Sáu",
  prize7: "Giải Bảy",
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

export class PublicError extends Error {}
const INTERNAL_ERROR_MESSAGE = "Tạm thời không trả được kết quả; thử lại sau.";

function publicMessage(error, fallback) {
  return error instanceof PublicError ? error.message : fallback;
}

function response(body, { status = 200, cacheControl = "no-store" } = {}) {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
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
    throw new PublicError("Sổ kết quả chỉ hỗ trợ Miền Bắc / Hà Nội.");
  }

  const fromRaw = url.searchParams.get("from");
  const toRaw = url.searchParams.get("to");
  let from;
  let to;
  let presetDays = null;
  if (fromRaw !== null || toRaw !== null) {
    if (!fromRaw || !toRaw) throw new PublicError("Khoảng tùy chọn phải có đủ từ ngày và đến ngày.");
    from = parseDate(fromRaw);
    to = parseDate(toRaw);
    if (!from || !to) throw new PublicError("Ngày phải đúng định dạng YYYY-MM-DD.");
    if (to > latestEligibleDate(nowUtcMs)) {
      throw new PublicError("Đến ngày không được sau kỳ gần nhất đã quay.");
    }
  } else {
    const days = Number(url.searchParams.get("days") || 30);
    if (!Number.isInteger(days) || !ALLOWED_DAYS.has(days)) {
      throw new PublicError("Số ngày chỉ nhận 30, 60, 90 hoặc 100.");
    }
    presetDays = days;
    to = latestEligibleDate(nowUtcMs);
    from = addDays(to, -(days - 1));
  }

  if (from > to) throw new PublicError("Từ ngày không được sau đến ngày.");
  if (daysInclusive(from, to) > MAX_RANGE_DAYS) {
    throw new PublicError(`Khoảng tùy chọn tối đa ${MAX_RANGE_DAYS} ngày.`);
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
  if (!Array.isArray(payload)) throw new PublicError("Lịch sử chuẩn không phải một danh sách.");
  const byDate = {};
  for (const row of payload) {
    const drawDate = String(row?.date || "").slice(0, 10);
    if (!parseDate(drawDate)) continue;
    const prizes = prizeMapFromInternal(row);
    if (prizes && completePrizeMap(prizes)) byDate[drawDate] = prizes;
  }
  if (Object.keys(byDate).length === 0) throw new PublicError("Lịch sử chuẩn không có kỳ hợp lệ.");
  return byDate;
}

async function readJson(kv, key) {
  if (!kv) return null;
  const raw = await kv.get(key);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

const PRIZE_SLOT_WIDTHS = PRIZE_ORDER.flatMap((key) => Array(EXPECTED_COUNTS[key]).fill(EXPECTED_WIDTHS[key]));
const RECORD_LENGTH = 10 + PRIZE_SLOT_WIDTHS.reduce((total, width) => total + width, 0) + 1;
const RECORD_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function encodePrimaryLedger(byDate) {
  return Object.keys(byDate).sort().map((day) => {
    const record = `${day}${PRIZE_ORDER.map((key) => byDate[day][key].join("")).join("")}\n`;
    if (record.length !== RECORD_LENGTH) throw new PublicError("Lịch sử chuẩn có kỳ sai độ rộng.");
    return record;
  }).join("");
}

function openLedger(text) {
  if (typeof text !== "string" || text.length === 0 || text.length % RECORD_LENGTH !== 0) return null;
  const count = text.length / RECORD_LENGTH;
  let previous = "";
  for (let index = 0; index < count; index += 1) {
    const start = index * RECORD_LENGTH;
    const day = text.slice(start, start + 10);
    if (!(day > previous) || !RECORD_DATE.test(day) || text.charCodeAt(start + RECORD_LENGTH - 1) !== 10) return null;
    previous = day;
  }
  return { text, count };
}

function ledgerDate(ledger, index) {
  const start = index * RECORD_LENGTH;
  return ledger.text.slice(start, start + 10);
}

function ledgerLowerBound(ledger, day) {
  let low = 0;
  let high = ledger.count;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (ledgerDate(ledger, middle) < day) low = middle + 1;
    else high = middle;
  }
  return low;
}

function ledgerPrizesAt(ledger, index) {
  let cursor = index * RECORD_LENGTH + 10;
  let slot = 0;
  const prizes = {};
  for (const key of PRIZE_ORDER) {
    prizes[key] = [];
    for (let n = 0; n < EXPECTED_COUNTS[key]; n += 1) {
      const width = PRIZE_SLOT_WIDTHS[slot];
      prizes[key].push(ledger.text.slice(cursor, cursor + width));
      cursor += width;
      slot += 1;
    }
  }
  return completePrizeMap(prizes) ? prizes : null;
}

function ledgerPrizes(ledger, day) {
  const index = ledgerLowerBound(ledger, day);
  return index < ledger.count && ledgerDate(ledger, index) === day ? ledgerPrizesAt(ledger, index) : null;
}

const PRIMARY_MEMO_MS = 60_000;
const primaryMemo = new WeakMap();

export function primaryFreshTtlSeconds(nowUtcMs) {
  const t = vietnamParts(nowUtcMs);
  const secondOfDay = (t.hour * 60 + t.minute) * 60 + t.second;
  const windowStart = 18 * 3600;
  if (secondOfDay >= windowStart) return 300;
  return Math.max(60, Math.min(3600, windowStart - secondOfDay));
}

function rememberPrimary(holder, historyUrl, ledger, nowUtcMs) {
  if (holder && typeof holder === "object") {
    primaryMemo.set(holder, { historyUrl, ledger, expiresAtMs: nowUtcMs + PRIMARY_MEMO_MS });
  }
}

async function loadPrimary(env, fetchImpl, nowUtcMs = Date.now()) {
  const kv = cacheStore(env);
  const historyUrl = env?.VLA_HISTORY_URL || DEFAULT_HISTORY_URL;
  const holder = kv ?? env;
  const memo = holder && typeof holder === "object" ? primaryMemo.get(holder) : undefined;
  if (memo && memo.historyUrl === historyUrl && memo.expiresAtMs > nowUtcMs) {
    return { ledger: memo.ledger, cache: "memory" };
  }
  const freshText = kv ? await kv.get(PRIMARY_FRESH_KEY) : null;
  if (freshText) {
    const sameAsMemo = memo && memo.historyUrl === historyUrl && memo.ledger.text === freshText;
    const ledger = sameAsMemo ? memo.ledger : openLedger(freshText);
    if (ledger) {
      rememberPrimary(holder, historyUrl, ledger, nowUtcMs);
      return { ledger, cache: "hit" };
    }
  }

  try {
    const fetched = await fetchImpl(historyUrl, {
      headers: {
        "Accept": "application/json",
        "User-Agent": "VLA-traditional-results/1.0",
      },
      signal: AbortSignal.timeout(10_000),
    });
    if (!fetched.ok) throw new Error(`HTTP ${fetched.status}`);
    const ledger = openLedger(encodePrimaryLedger(normalizePrimary(await fetched.json())));
    if (!ledger) throw new Error("bản lưu lịch sử chuẩn sai hình dạng");
    if (kv) {
      await kv.put(PRIMARY_FRESH_KEY, ledger.text, { expirationTtl: primaryFreshTtlSeconds(nowUtcMs) });
      if ((await kv.get(PRIMARY_LAST_GOOD_KEY)) !== ledger.text) await kv.put(PRIMARY_LAST_GOOD_KEY, ledger.text);
    }
    rememberPrimary(holder, historyUrl, ledger, nowUtcMs);
    return { ledger, cache: "miss" };
  } catch {
    const stale = kv ? openLedger(await kv.get(PRIMARY_LAST_GOOD_KEY)) : null;
    if (stale) return { ledger: stale, cache: "stale", warning: "Lịch sử chuẩn tạm không khả dụng; đang dùng bản lưu gần nhất." };
    throw new PublicError("Không đọc được lịch sử chuẩn.");
  }
}

export async function latestCanonicalDrawBefore(env, beforeIso, { fetchImpl = fetch, nowUtcMs = Date.now() } = {}) {
  try {
    const { ledger } = await loadPrimary(env, fetchImpl, nowUtcMs);
    const index = ledgerLowerBound(ledger, beforeIso) - 1;
    if (index < 0) return null;
    const prizes = ledgerPrizesAt(ledger, index);
    return prizes ? { draw_date: ledgerDate(ledger, index), prizes } : null;
  } catch {
    return null;
  }
}

function parseLedgerPage(html) {
  const rows = {};
  const presentDates = new Set();
  const tablePattern = /<table\b[^>]*class=["'][^"']*\bkqmb\b[^"']*["'][^>]*>[\s\S]*?<\/table\s*>/gi;
  for (const match of String(html || "").matchAll(tablePattern)) {
    const table = match[0];
    const dateMatch = /XSMB[\s\S]{0,180}?ngày\s*(\d{1,2})[-/]\s*(\d{1,2})[-/]\s*(\d{4})/i.exec(table);
    if (!dateMatch) continue;
    const drawDate = `${dateMatch[3]}-${pad2(dateMatch[2])}-${pad2(dateMatch[1])}`;
    if (!parseDate(drawDate)) continue;
    presentDates.add(drawDate);
    const prizes = extractPartialPrizeMap(table);
    if (completePrizeMap(prizes)) rows[drawDate] = prizes;
  }
  return { rows, presentDates };
}

export function parseXsktLedger(html) {
  return parseLedgerPage(html).rows;
}

function overlayResolved(entry, nowUtcMs) {
  if (completePrizeMap(entry?.prizes)) return true;
  if (!entry?.absent) return false;
  const checked = Date.parse(entry.checked_at_utc);
  return Number.isFinite(checked) && nowUtcMs - checked < ABSENT_RECHECK_DAYS * 86_400_000;
}

async function readOverlay(env, missingDates, nowUtcMs) {
  const overlay = (await readJson(cacheStore(env), OVERLAY_KEY)) || {};
  const unresolved = missingDates.filter((day) => !overlayResolved(overlay[day], nowUtcMs));
  return {
    overlay,
    unresolved,
    warning: unresolved.length
      ? "Một số ngày chưa có trong lịch sử chuẩn; lượt cập nhật theo lịch sẽ bù."
      : null,
  };
}

export async function refreshFallbackOverlay(env, { fetchImpl = fetch, nowUtcMs = Date.now() } = {}) {
  const kv = cacheStore(env);
  if (!kv) return { fetched: false, missing: 0 };
  const primary = await loadPrimary(env, fetchImpl, nowUtcMs);
  const overlay = (await readJson(kv, OVERLAY_KEY)) || {};
  const latest = latestEligibleDate(nowUtcMs);
  const missing = dateRange(isoDate(addDays(latest, -(FALLBACK_WINDOW_DAYS - 1))), isoDate(latest))
    .filter((day) => !ledgerPrizes(primary.ledger, day) && !overlayResolved(overlay[day], nowUtcMs));
  if (missing.length === 0) return { fetched: false, missing: 0 };
  const last = Number(await kv.get(FALLBACK_REFRESH_KEY)) || 0;
  if (nowUtcMs - last < FALLBACK_REFRESH_SECONDS * 1000) return { fetched: false, missing: missing.length };
  await kv.put(FALLBACK_REFRESH_KEY, String(nowUtcMs), { expirationTtl: 86_400 });

  const responseFromSource = await fetchImpl(env?.XSKT_HISTORY_URL || DEFAULT_XSKT_URL, {
    headers: {
      "Accept": "text/html,application/xhtml+xml",
      "Accept-Language": "vi-VN,vi;q=0.9",
      "User-Agent": "VLA-traditional-results/1.0 (+https://github.com/beuvivu/VLA)",
    },
    signal: AbortSignal.timeout(12_000),
  });
  if (!responseFromSource.ok) throw new Error(`nguồn dự phòng trả HTTP ${responseFromSource.status}`);
  const { rows: parsed, presentDates } = parseLedgerPage(await responseFromSource.text());
  const pageDays = Object.keys(parsed).sort();
  const stamp = new Date(nowUtcMs).toISOString();
  let filled = 0;
  let absent = 0;
  for (const day of missing) {
    if (completePrizeMap(parsed[day])) {
      overlay[day] = { prizes: parsed[day], fetched_at_utc: stamp };
      filled += 1;
    } else if (!presentDates.has(day) && pageDays.length && day > pageDays[0] && day < pageDays.at(-1)) {
      overlay[day] = { absent: true, checked_at_utc: stamp };
      absent += 1;
    }
  }
  await kv.put(OVERLAY_KEY, JSON.stringify(overlay), { expirationTtl: 2_592_000 });
  return { fetched: true, missing: missing.length, filled, absent };
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

const canonicalDraws = new WeakMap();

function canonicalDraw(ledger, day) {
  let built = canonicalDraws.get(ledger);
  if (!built) {
    built = new Map();
    canonicalDraws.set(ledger, built);
  }
  if (!built.has(day)) {
    const prizes = ledgerPrizes(ledger, day);
    built.set(day, prizes ? apiDraw(day, prizes, { kind: "canonical", canonical: true }) : null);
  }
  return built.get(day);
}

function sourceCounts(data) {
  const counts = { canonical: 0, fallback: 0 };
  for (const draw of data) counts[draw.source.kind] += 1;
  return counts;
}

export async function buildTraditionalResults(
  query,
  env,
  { fetchImpl = fetch, nowUtcMs = Date.now() } = {},
) {
  const primary = await loadPrimary(env, fetchImpl, nowUtcMs);
  const requestedDates = dateRange(query.from, query.to);
  const canonical = new Map(requestedDates.map((day) => [day, canonicalDraw(primary.ledger, day)]));
  const missing = requestedDates.filter((day) => !canonical.get(day));
  const fallback = missing.length
    ? await readOverlay(env, missing, nowUtcMs)
    : { overlay: {}, unresolved: [], warning: null };

  const data = [];
  for (const day of requestedDates) {
    const draw = canonical.get(day);
    if (draw) {
      data.push(draw);
    } else if (completePrizeMap(fallback.overlay[day]?.prizes)) {
      data.push(apiDraw(day, fallback.overlay[day].prizes, {
        kind: "fallback",
        canonical: false,
        fetched_at_utc: fallback.overlay[day].fetched_at_utc,
      }));
    }
  }
  data.sort((a, b) => b.draw_date.localeCompare(a.draw_date));
  const counts = sourceCounts(data);
  return {
    schema_version: 2,
    query,
    meta: {
      generated_at_utc: new Date(nowUtcMs).toISOString(),
      total_results: data.length,
      requested_calendar_days: requestedDates.length,
      latest_draw_date: data[0]?.draw_date ?? null,
      source_counts: counts,
      sources_used: Object.entries(counts).filter(([, n]) => n > 0).map(([name]) => name),
      fallback_requested: missing.length > 0,
      fallback_network_fetch: false,
      unresolved_dates: fallback.unresolved,
      primary_cache: primary.cache,
      warning: [primary.warning, fallback.warning].filter(Boolean).join("; ") || null,
    },
    data,
  };
}

const RESPONSE_MEMO_MS = 60_000;
const RESPONSE_MEMO_ENTRIES = 64;
const responseMemo = new WeakMap();

function responseShelf(env) {
  const holder = cacheStore(env) ?? env;
  if (!holder || typeof holder !== "object") return null;
  let shelf = responseMemo.get(holder);
  if (!shelf) {
    shelf = new Map();
    responseMemo.set(holder, shelf);
  }
  return shelf;
}

export function rememberedRangeCount(env) {
  return responseShelf(env)?.size ?? 0;
}

function rememberedResponse(env, key, nowUtcMs = Date.now()) {
  const entry = responseShelf(env)?.get(key);
  return entry && entry.expiresAtMs > nowUtcMs ? entry.body : null;
}

function rememberResponse(env, key, body, nowUtcMs = Date.now()) {
  const shelf = responseShelf(env);
  if (!shelf) return;
  shelf.delete(key);
  shelf.set(key, { body, expiresAtMs: nowUtcMs + RESPONSE_MEMO_MS });
  while (shelf.size > RESPONSE_MEMO_ENTRIES) shelf.delete(shelf.keys().next().value);
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
    return response({ error: "invalid_query", message: publicMessage(error, "Truy vấn không hợp lệ.") }, { status: 400 });
  }

  try {
    const cacheControl = "public, max-age=60, s-maxage=300";
    const key = `${query.preset_days ?? "range"}:${query.from}:${query.to}`;
    const hit = rememberedResponse(env, key);
    if (hit !== null) return response(hit, { cacheControl });
    const body = JSON.stringify(await buildTraditionalResults(query, env));
    rememberResponse(env, key, body);
    return response(body, { cacheControl });
  } catch (error) {
    return response({
      error: "results_unavailable",
      message: publicMessage(error, INTERNAL_ERROR_MESSAGE),
    }, { status: 502 });
  }
}
