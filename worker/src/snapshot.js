// Bản JS của `src/live_sync.py::fetch_snapshot`, tách làm hai nửa.
//
// `buildSnapshot` là phần THUẦN: vào là các bảng giải đã lấy được, ra là đúng
// payload live.json. Tách ra như vậy để `tests/test_worker_snapshot_parity.py`
// so được nó với bản Python mà không cần mạng.
//
// `collectSnapshot` là phần có tác dụng phụ: gọi nguồn rồi giao cho phần
// thuần. Phần ấy không đối chiếu được vì phụ thuộc mạng thật.

import {
  EXPECTED_COUNTS,
  PRIZE_ORDER,
  emptyPrizeMap,
  extractPartialPrizeMap,
} from "./prize_map.js";
import { sourceConsensusPartial, sourceIndependenceKey } from "./consensus.js";
import {
  FALLBACK_SOURCES,
  PRIMARY_SOURCES,
  SOURCES,
  publicSourceCode,
} from "./sources.js";

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

export function buildSnapshot({ partials, sourceStatus, nowUtcMs, minAgreement = 2, failover = null }) {
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
    slot_meta: meta.slot_meta,
    failover,
    note: "GitHub near-live snapshot. Single-source values are provisional; "
      + "canonical history is promoted only after complete multi-source consensus.",
  };
}

// --- Phần gọi mạng ---------------------------------------------------------

const RETRYABLE = new Set([408, 425, 429, 500, 502, 503, 504]);

/**
 * Thử lại có lùi mũ kèm nhiễu, khớp chính sách của `src/sources.py`.
 *
 * Nhiễu là bắt buộc chứ không phải trang trí: các nguồn chạy song song, nếu
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

function totalExpected() {
  let expected = 0;
  for (const key of PRIZE_ORDER) expected += EXPECTED_COUNTS[key];
  return expected;
}

function receivedCount(prizeMap) {
  let received = 0;
  for (const key of PRIZE_ORDER) received += (prizeMap[key] || []).length;
  return received;
}

/**
 * Số NHÓM nhà cung cấp độc lập có dữ liệu dùng được.
 * Đếm theo nhóm, không theo tên miền: hai trang cùng thương hiệu không phải
 * hai lời chứng độc lập.
 */
export function independentGroupCount(results) {
  const groups = new Set();
  for (const r of results) {
    if (receivedCount(r.prizeMap) > 0) groups.add(sourceIndependenceKey(r.name));
  }
  return groups.size;
}

/**
 * Tầng chính có đủ để KHÔNG cần gọi dự phòng hay không. Khớp
 * `sources.primary_tier_is_sufficient` bên Python.
 */
export function primaryTierIsSufficient(results, minAgreement = 2) {
  const groups = independentGroupCount(results);
  if (groups < minAgreement) {
    return { sufficient: false, reason: `chỉ có ${groups} nhóm độc lập, cần ${minAgreement}` };
  }
  const usable = results.filter((r) => receivedCount(r.prizeMap) > 0);
  const [, meta] = sourceConsensusPartial(
    usable.map((r) => [r.name, r.prizeMap]),
    { minAgreement },
  );
  if (meta.conflicts.length > 0) {
    return { sufficient: false, reason: `tầng chính bất đồng ở ${meta.conflicts.length} ô` };
  }
  return { sufficient: true, reason: "tầng chính đủ" };
}

async function fetchOne(source, tier, priority, date, fetchImpl) {
  const started = Date.now();
  let prizeMap = emptyPrizeMap();
  let error = null;
  let best = 0;
  const expected = totalExpected();
  // Thử lần lượt các đường dẫn ứng viên; giữ bản bóc được nhiều giá trị nhất.
  for (const url of source.liveUrls(date)) {
    try {
      const html = await fetchWithRetry(url, { fetchImpl });
      const section = source.selectSection ? source.selectSection(html, date) : html;
      const candidate = extractPartialPrizeMap(section);
      const score = receivedCount(candidate);
      if (score > best) {
        prizeMap = candidate;
        best = score;
        error = null;
      }
      if (best === expected) break;
    } catch (err) {
      if (best === 0) {
        error = `${err?.name || "Error"}: ${String(err?.message || err).slice(0, 120)}`;
      }
    }
  }
  return {
    priority,
    name: source.name,
    prizeMap,
    status: {
      priority,
      tier,
      source: source.name,
      provider_group: sourceIndependenceKey(source.name),
      received_values: best,
      complete: best === expected,
      latency_ms: Date.now() - started,
      error,
    },
  };
}

export async function collectSnapshot({ nowUtcMs, minAgreement = 2, fetchImpl = fetch } = {}) {
  const now = nowUtcMs ?? Date.now();
  const date = vietnamParts(now);

  // Tầng chính trước. Chỉ chạm tới dự phòng khi tầng chính không đủ để xác
  // minh — thiếu nhóm độc lập, hoặc hai nguồn chính bất đồng.
  const results = await Promise.all(
    PRIMARY_SOURCES.map((source, i) => fetchOne(source, "primary", i + 1, date, fetchImpl)),
  );
  const verdict = primaryTierIsSufficient(results, minAgreement);
  const failover = {
    primary_attempted: PRIMARY_SOURCES.length,
    primary_usable_groups: independentGroupCount(results),
    fallback_activated: !verdict.sufficient,
    reason: verdict.reason,
    fallback_attempted: 0,
  };
  if (!verdict.sufficient) {
    const offset = PRIMARY_SOURCES.length;
    const extra = await Promise.all(
      FALLBACK_SOURCES.map((source, i) =>
        fetchOne(source, "fallback", offset + i + 1, date, fetchImpl)),
    );
    results.push(...extra);
    failover.fallback_attempted = FALLBACK_SOURCES.length;
    failover.usable_groups = independentGroupCount(results);
  }
  results.sort((a, b) => a.priority - b.priority);

  return buildSnapshot({
    partials: results.map((r) => [r.name, r.prizeMap]),
    sourceStatus: results.map((r) => r.status),
    nowUtcMs: now,
    minAgreement,
    failover,
  });
}

// --- Ẩn nguồn khỏi mọi thứ ra tới trình duyệt -------------------------------
// Khớp `sources.anonymise_snapshot` bên Python. Tên nguồn nằm rải ở bốn chỗ
// trong cùng một bản chụp; bỏ sót một chỗ là lộ hết, nên phép ẩn danh là MỘT
// hàm duy nhất kiểm được.

const GROUP_CODE = Object.fromEntries(
  [...new Set(SOURCES.map((s) => sourceIndependenceKey(s.name)))]
    .map((group, i) => [group, `G${i + 1}`]),
);

export function publicGroupCode(nameOrGroup) {
  const key = sourceIndependenceKey(nameOrGroup);
  return Object.prototype.hasOwnProperty.call(GROUP_CODE, key) ? GROUP_CODE[key] : "?";
}

export function anonymiseSnapshot(payload) {
  const out = { ...payload };
  if (Array.isArray(out.source_status)) {
    out.source_status = out.source_status.map((raw) => {
      const row = { ...raw };
      const name = String(row.source ?? "");
      delete row.source;
      delete row.provider_group;
      const error = row.error;
      delete row.error;
      row.source_code = publicSourceCode(name);
      row.provider_code = publicGroupCode(name);
      row.failed = error !== null && error !== undefined;
      return row;
    });
  }
  if ("source_priority" in out) {
    out.source_priority = SOURCES.map((s) => publicSourceCode(s.name));
  }
  if (out.slot_meta && typeof out.slot_meta === "object") {
    const meta = {};
    for (const [slot, raw] of Object.entries(out.slot_meta)) {
      const row = { ...raw };
      row.support = (row.support || []).map(publicSourceCode);
      row.support_groups = (row.support_groups || []).map(publicGroupCode);
      row.observations = Object.fromEntries(
        Object.entries(row.observations || {})
          .map(([value, names]) => [value, names.map(publicSourceCode)]),
      );
      meta[slot] = row;
    }
    out.slot_meta = meta;
  }
  return out;
}
