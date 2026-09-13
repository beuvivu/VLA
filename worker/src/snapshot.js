// Bản JS của `src/live_sync.py::fetch_snapshot`, tách làm hai nửa.
//
// `buildSnapshot` là phần THUẦN: vào là các bảng giải đã lấy được, ra là đúng
// payload live.json. Tách ra như vậy để `tests/test_worker_snapshot_parity.py`
// so được nó với bản Python mà không cần mạng.
//
// `collectSnapshot` là phần có tác dụng phụ: gọi sáu nguồn rồi giao cho phần
// thuần. Phần ấy không đối chiếu được vì phụ thuộc mạng thật.

import { EXPECTED_COUNTS, PRIZE_ORDER, emptyPrizeMap } from "./prize_map.js";
import { sourceConsensusPartial, sourceIndependenceKey } from "./consensus.js";
import { extractPartialPrizeMap } from "./prize_map.js";
import { SOURCES } from "./sources.js";

export const VIETNAM_OFFSET_MINUTES = 7 * 60;

/** Giờ Việt Nam suy từ UTC. Việt Nam không đổi giờ mùa nên cộng cứng 7 tiếng. */
export function vietnamParts(nowUtcMs) {
  const shifted = new Date(nowUtcMs + VIETNAM_OFFSET_MINUTES * 60_000);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
    second: shifted.getUTCSeconds(),
  };
}

const p2 = (v) => String(v).padStart(2, "0");

export function isoLocal(nowUtcMs) {
  const t = vietnamParts(nowUtcMs);
  return `${t.year}-${p2(t.month)}-${p2(t.day)}T`
    + `${p2(t.hour)}:${p2(t.minute)}:${p2(t.second)}+07:00`;
}

export function isoUtc(nowUtcMs) {
  return new Date(Math.floor(nowUtcMs / 1000) * 1000)
    .toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function drawDate(nowUtcMs) {
  const t = vietnamParts(nowUtcMs);
  return `${t.year}-${p2(t.month)}-${p2(t.day)}`;
}

/**
 * `round()` của Python làm tròn NỬA VỀ SỐ CHẴN, còn `Math.round` của JS làm
 * tròn nửa lên. Hai bên lệch nhau ở đúng các giá trị nửa chừng, và tuy hiếm,
 * một phần trăm lệch 0,1 giữa trang live và bảng kiểm là thứ không ai truy ra
 * nổi. Viết lại cho khớp.
 */
export function roundHalfEven(value, digits = 1) {
  const factor = 10 ** digits;
  const scaled = value * factor;
  const floor = Math.floor(scaled);
  const diff = scaled - floor;
  let rounded;
  if (Math.abs(diff - 0.5) < Number.EPSILON * Math.max(1, Math.abs(scaled))) {
    rounded = floor % 2 === 0 ? floor : floor + 1;
  } else {
    rounded = Math.round(scaled);
  }
  return rounded / factor;
}

export function buildSnapshot({ partials, sourceStatus, nowUtcMs, minAgreement = 2 }) {
  const [merged, meta] = sourceConsensusPartial(partials, { minAgreement });
  const received = meta.received_slots;
  const expected = meta.total_slots;
  const verified = meta.verified_slots;
  const conflicts = meta.conflicts;

  const complete = received === expected;
  const verifiedComplete = complete && verified === expected && conflicts.length === 0;

  const t = vietnamParts(nowUtcMs);
  const inWindow = (t.hour === 17 && t.minute >= 55) || (t.hour === 18 && t.minute <= 55);

  let status;
  if (verifiedComplete) status = "complete_verified";
  else if (complete) status = conflicts.length === 0 ? "complete_provisional" : "complete_conflict";
  else if (received > 0 && inWindow) status = "live";
  else if (received > 0) status = "partial";
  else status = "waiting";

  return {
    schema_version: 2,
    draw_date: drawDate(nowUtcMs),
    checked_at_utc: isoUtc(nowUtcMs),
    checked_at_local: isoLocal(nowUtcMs),
    status,
    complete,
    verified_complete: verifiedComplete,
    received_values: received,
    expected_values: expected,
    verified_values: verified,
    progress_percent: roundHalfEven(100.0 * received / expected, 1),
    verification_percent: roundHalfEven(100.0 * verified / expected, 1),
    prizes: merged,
    conflicts,
    source_status: sourceStatus,
    source_priority: SOURCES.map((s) => s.name),
    slot_meta: meta.slot_meta,
    note: "GitHub near-live snapshot. Single-source values are provisional; "
      + "canonical history is promoted only after complete multi-source consensus.",
  };
}

// --- Phần gọi mạng ---------------------------------------------------------

const RETRYABLE = new Set([408, 425, 429, 500, 502, 503, 504]);

/**
 * Thử lại có lùi mũ kèm nhiễu, khớp chính sách của `src/sources.py`.
 *
 * Nhiễu là bắt buộc chứ không phải trang trí: sáu nguồn chạy song song, nếu
 * cùng hỏng rồi cùng chờ đúng một khoảng thì lần thử sau lại dội vào cùng một
 * thời điểm — đúng lúc máy chủ đang quá tải.
 */
async function fetchWithRetry(url, { attempts = 3, timeoutMs = 8000, fetchImpl = fetch } = {}) {
  let delay = 500;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    let response;
    try {
      response = await fetchImpl(url, {
        signal: AbortSignal.timeout(timeoutMs),
        headers: {
          "User-Agent": "VLA-live/1.0 (+https://github.com/beuvivu/VLA)",
          "Accept": "text/html,application/xhtml+xml",
          "Accept-Language": "vi-VN,vi;q=0.9",
          "Cache-Control": "no-cache",
        },
      });
    } catch (error) {
      if (attempt === attempts) throw error;
      await sleep(jitter(delay));
      delay = Math.min(delay * 2, 4000);
      continue;
    }
    if (response.status === 200) return await response.text();
    // 403/404 thì thử lại vô ích: câu trả lời sẽ y hệt.
    if (!RETRYABLE.has(response.status) || attempt === attempts) {
      throw new Error(`HTTP ${response.status}`);
    }
    const retryAfter = Number(response.headers.get("retry-after"));
    // Có nơi trả về hàng trăm giây; chờ chừng ấy thì hết cả kỳ quay.
    const wait = Number.isFinite(retryAfter) && retryAfter > 0
      ? Math.min(retryAfter * 1000, 4000)
      : jitter(delay);
    await sleep(wait);
    delay = Math.min(delay * 2, 4000);
  }
  throw new Error("hết lượt thử");
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const jitter = (ms) => ms * (0.75 + Math.random() * 0.5);

export async function collectSnapshot({ nowUtcMs, minAgreement = 2, fetchImpl = fetch } = {}) {
  const now = nowUtcMs ?? Date.now();
  const date = vietnamParts(now);

  const results = await Promise.all(SOURCES.map(async (source, index) => {
    const started = Date.now();
    let prizeMap = emptyPrizeMap();
    let error = null;
    try {
      const html = await fetchWithRetry(source.liveUrl(date), { fetchImpl });
      const section = source.selectSection ? source.selectSection(html, date) : html;
      prizeMap = extractPartialPrizeMap(section);
    } catch (err) {
      error = `${err?.name || "Error"}: ${String(err?.message || err).slice(0, 120)}`;
    }
    let received = 0;
    for (const key of PRIZE_ORDER) received += (prizeMap[key] || []).length;
    let expected = 0;
    for (const key of PRIZE_ORDER) expected += EXPECTED_COUNTS[key];
    return {
      priority: index + 1,
      name: source.name,
      prizeMap,
      status: {
        priority: index + 1,
        source: source.name,
        provider_group: sourceIndependenceKey(source.name),
        received_values: received,
        complete: received === expected,
        latency_ms: Date.now() - started,
        error,
      },
    };
  }));

  return buildSnapshot({
    partials: results.map((r) => [r.name, r.prizeMap]),
    sourceStatus: results.map((r) => r.status),
    nowUtcMs: now,
    minAgreement,
  });
}
