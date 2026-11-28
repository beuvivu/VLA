import { anonymiseSnapshot, collectSnapshot, drawDate } from "./snapshot.js";
import {
  handleTraditionalResults,
  latestCanonicalDrawBefore,
  refreshFallbackOverlay,
} from "./traditional_results.js";

const KV_KEY = "live.json";
const PREVIOUS_KEY = "previous-draw.json";

function cacheSeconds(status) {
  if (status === "complete_verified") return 60;
  if (status === "complete_provisional" || status === "complete_conflict") return 10;
  return 3;
}

function jsonResponse(body, { status = 200, cacheControl = "no-store" } = {}) {
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

function requireKv(env) {
  if (!env || !env.LIVE || typeof env.LIVE.get !== "function") {
    throw new Error(
      "thiếu ràng buộc KV 'LIVE' — chạy `npx wrangler kv namespace create LIVE` "
      + "rồi điền id vào worker/wrangler.toml (xem documentation/operations/live-worker.md)",
    );
  }
  return env.LIVE;
}

function alreadySettled(stored, nowUtcMs) {
  if (!stored) return false;
  try {
    const parsed = JSON.parse(stored);
    return parsed.status === "complete_verified"
      && parsed.draw_date === drawDate(nowUtcMs);
  } catch {
    return false;
  }
}

function verifiedOtherDay(raw, nowUtcMs) {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed.verified_complete === true && parsed.draw_date !== drawDate(nowUtcMs)
      ? { draw_date: parsed.draw_date, verified_complete: true, prizes: parsed.prizes }
      : null;
  } catch {
    return null;
  }
}

async function previousDraw(env, kv, stored, nowUtcMs) {
  const kept = verifiedOtherDay(await kv.get(PREVIOUS_KEY), nowUtcMs);
  const canonical = await latestCanonicalDrawBefore(env, drawDate(nowUtcMs));
  const candidates = [
    verifiedOtherDay(stored, nowUtcMs),
    kept,
    canonical && { ...canonical, verified_complete: true },
  ].filter(Boolean);
  if (candidates.length === 0) return null;
  const best = candidates.reduce((a, b) => (b.draw_date > a.draw_date ? b : a));
  if (!kept || kept.draw_date !== best.draw_date) {
    await kv.put(PREVIOUS_KEY, JSON.stringify(best), {
      expirationTtl: 60 * 60 * 24 * 7,
    });
  }
  return best.prizes;
}

async function refresh(env) {
  const kv = requireKv(env);
  const now = Date.now();
  const stored = await kv.get(KV_KEY);
  if (alreadySettled(stored, now)) return;
  const previous = await previousDraw(env, kv, stored, now);
  const collected = await collectSnapshot({
    nowUtcMs: now,
    minAgreement: Number(env.MIN_AGREEMENT ?? 1),
    previous,
  });
  if (previous === null && collected.status === "complete_verified") {
    collected.status = "complete_provisional";
    collected.verified_complete = false;
  }
  const snapshot = anonymiseSnapshot(collected);
  await kv.put(KV_KEY, JSON.stringify(snapshot), {
    expirationTtl: 60 * 60 * 36,
  });
}

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(refresh(env).catch((error) => {
      console.error("lượt thu thập theo lịch hỏng:", error?.message || error);
    }));
    if (env?.TRADITIONAL_FALLBACK_REFRESH === "on") {
      ctx.waitUntil(refreshFallbackOverlay(env).catch((error) => {
        console.error("lượt bù lịch sử theo lịch hỏng:", error?.message || error);
      }));
    }
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api/v1/traditional-results") {
      return handleTraditionalResults(request, env, ctx);
    }

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
    if (request.method !== "GET") {
      return jsonResponse({ error: "method not allowed" }, { status: 405 });
    }

    if (url.pathname === "/health") {
      const stored = await requireKv(env).get(KV_KEY);
      let parsed = null;
      try { parsed = stored ? JSON.parse(stored) : null; } catch { parsed = null; }
      return jsonResponse({
        ok: true,
        has_snapshot: Boolean(parsed),
        draw_date: parsed?.draw_date ?? null,
        status: parsed?.status ?? null,
        checked_at_utc: parsed?.checked_at_utc ?? null,
      });
    }

    if (url.pathname !== "/" && url.pathname !== "/live.json") {
      return jsonResponse({ error: "not found" }, { status: 404 });
    }

    const stored = await requireKv(env).get(KV_KEY);
    if (stored) {
      const status = (() => {
        try { return JSON.parse(stored).status; } catch { return "waiting"; }
      })();
      return jsonResponse(stored, {
        cacheControl: `public, max-age=${cacheSeconds(status)}`,
      });
    }

    return jsonResponse({ schema_version: 2, status: "waiting" }, { status: 503 });
  },
};
