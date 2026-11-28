import worker from "../src/index.js";

let fixedNow = Date.parse("2026-10-13T11:20:00Z");
Date.now = () => fixedNow;

class FakeKV {
  constructor() { this.store = new Map(); this.puts = 0; }
  async get(key) {
    const row = this.store.get(key);
    if (!row) return null;
    if (row.expiresAt !== null && row.expiresAt <= Date.now()) {
      this.store.delete(key);
      return null;
    }
    return row.value;
  }
  async put(key, value, options = {}) {
    this.puts += 1;
    const ttl = options.expirationTtl;
    if (ttl !== undefined && ttl < 60) {
      throw new Error(`Invalid expiration_ttl of ${ttl}. Expiration TTL must be at least 60.`);
    }
    this.store.set(key, { value, expiresAt: ttl ? Date.now() + ttl * 1000 : null });
  }
}

const FULL_PRIZES = {
  special: ["83772"], prize1: ["68785"], prize2: ["50518", "27452"],
  prize3: ["57053", "92810", "56241", "65128", "33811", "42264"],
  prize4: ["4753", "1152", "6777", "3507"],
  prize5: ["9460", "2913", "3232", "2999", "3670", "5129"],
  prize6: ["939", "751", "594"], prize7: ["66", "21", "34", "78"],
};
const OTHER_PRIZES = { ...FULL_PRIZES, special: ["11111"] };

function historyRow(dateIso, prizes) {
  const row = { date: `${dateIso}T00:00:00.000` };
  for (const [key, values] of Object.entries(prizes)) {
    if (values.length === 1) row[key] = Number(values[0]);
    else values.forEach((v, i) => { row[`${key}_${i + 1}`] = Number(v); });
  }
  return row;
}

let history = [historyRow("2026-10-12", OTHER_PRIZES)];

function installFetch(handler) {
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/data/xsmb.json")) {
      if (history === null) return new Response("unavailable", { status: 503 });
      return new Response(JSON.stringify(history), {
        status: 200, headers: { "content-type": "application/json" },
      });
    }
    return handler(url, init);
  };
}

function makeFetch(counter, { fail = false } = {}) {
  return async () => {
    counter.calls += 1;
    if (fail) throw new Error("nguồn chặn");
    return new Response(
      "<div>ĐB 83772</div><div>G7 66 21 34 78</div>",
      { status: 200, headers: { "content-type": "text/html" } },
    );
  };
}

const FULL_PAGE = "<div>ĐB 83772</div><div>G1 68785</div>"
  + "<div>G2 50518 27452</div>"
  + "<div>G3 57053 92810 56241 65128 33811 42264</div>"
  + "<div>G4 4753 1152 6777 3507</div>"
  + "<div>G5 9460 2913 3232 2999 3670 5129</div>"
  + "<div>G6 939 751 594</div><div>G7 66 21 34 78</div>";
const STUCK_PAGE = "<div>ĐB 83772</div><div>G7 66 21 34 78</div>";

const newCtx = () => ({ pending: [], waitUntil(p) { this.pending.push(p); } });

const SCENARIOS = {
  async missing_kv() {
    try {
      await worker.fetch(new Request("https://w/live.json"), {}, newCtx());
      return { message: null };
    } catch (error) {
      return { message: String(error.message) };
    }
  },

  async requests_never_collect() {
    const counter = { calls: 0 };
    installFetch(makeFetch(counter));
    const other = (await import("../src/index.js?isolate=b")).default;
    const out = {};
    for (const [name, kv] of [["kv_empty", new FakeKV()], ["kv_put_drops", new FakeKV()]]) {
      if (name === "kv_put_drops") kv.put = async () => { kv.puts += 1; };
      const responses = [];
      for (let i = 0; i < 12; i += 1) {
        const handler = i % 2 === 0 ? worker : other;
        responses.push(await handler.fetch(new Request("https://w/live.json"), { LIVE: kv }, newCtx()));
      }
      out[name] = {
        statuses: [...new Set(responses.map((r) => r.status))],
        cors: [...new Set(responses.map((r) => r.headers.get("access-control-allow-origin")))],
        body_status: (await responses[0].json()).status,
      };
    }
    out.outbound_fetches = counter.calls;
    return out;
  },

  async normal() {
    const counter = { calls: 0 };
    installFetch(makeFetch(counter));
    const kv = new FakeKV();
    const env = { LIVE: kv, MIN_AGREEMENT: "1" };
    const ctx = newCtx();

    await worker.scheduled({}, env, ctx);
    await Promise.all(ctx.pending);
    const afterCron = counter.calls;

    const response = await worker.fetch(new Request("https://w/live.json"), env, ctx);
    const body = await response.json();
    const health = await (await worker.fetch(
      new Request("https://w/health"), env, ctx,
    )).json();

    return {
      outbound_on_cron: afterCron,
      outbound_after_read: counter.calls,
      schema_version: body.schema_version,
      source_count: body.source_status.length,
      special: body.prizes.special,
      cache_control: response.headers.get("cache-control"),
      cors: response.headers.get("access-control-allow-origin"),
      health_ok: health.ok,
      health_has_snapshot: health.has_snapshot,
    };
  },

  async all_sources_down() {
    installFetch(makeFetch({ calls: 0 }, { fail: true }));
    const kv = new FakeKV();
    const ctx = newCtx();
    await worker.scheduled({}, { LIVE: kv }, ctx);
    let threw = false;
    try { await Promise.all(ctx.pending); } catch { threw = true; }
    const stored = await kv.get("live.json");
    const parsed = stored ? JSON.parse(stored) : null;
    return {
      scheduled_threw: threw,
      wrote_snapshot: parsed !== null,
      status: parsed?.status ?? null,
      errors: parsed ? parsed.source_status.filter((r) => r.failed).length : 0,
      source_rows: parsed ? parsed.source_status.length : 0,
      fallback_activated: parsed?.failover?.fallback_activated ?? null,
    };
  },

  async primary_stuck_after_deadline() {
    fixedNow = Date.parse("2026-10-13T11:45:00Z");
    const hosts = [];
    installFetch(async (url) => {
      const host = new URL(String(url)).hostname;
      hosts.push(host);
      const body = host.endsWith("xoso.com.vn") ? STUCK_PAGE : FULL_PAGE;
      return new Response(body, { status: 200 });
    });
    const kv = new FakeKV();
    const ctx = newCtx();
    await worker.scheduled({}, { LIVE: kv, MIN_AGREEMENT: "1" }, ctx);
    await Promise.all(ctx.pending);
    const parsed = JSON.parse(await kv.get("live.json"));
    return {
      status: parsed.status,
      fallback_activated: parsed.failover.fallback_activated,
      source_rows: parsed.source_status.length,
      prize1: parsed.prizes.prize1,
      prize7: parsed.prizes.prize7,
      hosts: [...new Set(hosts)].sort(),
      supporters: [...new Set(Object.values(parsed.slot_meta).flatMap((m) => m.support))].sort(),
    };
  },

  async stale_page_is_not_today() {
    const kv = new FakeKV();
    const yesterday = {
      schema_version: 2, draw_date: "2026-10-12", status: "complete_verified",
      verified_complete: true,
      prizes: FULL_PRIZES,
    };
    await kv.put("live.json", JSON.stringify(yesterday));
    await kv.put("previous-draw.json", JSON.stringify({
      draw_date: "2026-10-10", verified_complete: true, prizes: OTHER_PRIZES,
    }));
    history = [historyRow("2026-10-12", FULL_PRIZES)];
    installFetch(async () => new Response(FULL_PAGE, { status: 200 }));
    const env = { LIVE: kv, MIN_AGREEMENT: "1" };
    const ctx = newCtx();
    await worker.scheduled({}, env, ctx);
    await Promise.all(ctx.pending);
    const parsed = JSON.parse(await kv.get("live.json"));
    const later = [];
    for (let i = 0; i < 3; i += 1) {
      const c = newCtx();
      await worker.scheduled({}, env, c);
      await Promise.all(c.pending);
      later.push(JSON.parse(await kv.get("live.json")).status);
    }
    return {
      draw_date: parsed.draw_date,
      status: parsed.status,
      received_values: parsed.received_values,
      fallback_activated: parsed.failover.fallback_activated,
      failed_rows: parsed.source_status.filter((r) => r.failed).length,
      later_statuses: later,
    };
  },

  async cold_start_seeds_from_canonical_history() {
    history = [historyRow("2026-10-11", OTHER_PRIZES), historyRow("2026-10-12", FULL_PRIZES)];
    installFetch(async () => new Response(FULL_PAGE, { status: 200 }));
    const kv = new FakeKV();
    const env = { LIVE: kv, MIN_AGREEMENT: "1" };
    const statuses = [];
    for (let i = 0; i < 3; i += 1) {
      const c = newCtx();
      await worker.scheduled({}, env, c);
      await Promise.all(c.pending);
      statuses.push(JSON.parse(await kv.get("live.json")).status);
    }
    return { statuses };
  },

  async cold_start_without_history_does_not_settle() {
    history = null;
    const counter = { calls: 0 };
    installFetch(async () => {
      counter.calls += 1;
      return new Response(FULL_PAGE, { status: 200 });
    });
    const kv = new FakeKV();
    const env = { LIVE: kv, MIN_AGREEMENT: "1" };
    const c1 = newCtx();
    await worker.scheduled({}, env, c1);
    await Promise.all(c1.pending);
    const first = JSON.parse(await kv.get("live.json"));
    const afterFirst = counter.calls;
    const c2 = newCtx();
    await worker.scheduled({}, env, c2);
    await Promise.all(c2.pending);
    return {
      status: first.status,
      verified_complete: first.verified_complete,
      outbound_after_first: afterFirst,
      outbound_after_second: counter.calls,
    };
  },

  async canonical_lags_behind_the_kv_snapshot() {
    history = [historyRow("2026-10-11", OTHER_PRIZES)];
    const kv = new FakeKV();
    await kv.put("live.json", JSON.stringify({
      schema_version: 2, draw_date: "2026-10-12", status: "complete_verified",
      verified_complete: true, prizes: FULL_PRIZES,
    }));
    installFetch(async () => new Response(FULL_PAGE, { status: 200 }));
    const c = newCtx();
    await worker.scheduled({}, { LIVE: kv, MIN_AGREEMENT: "1" }, c);
    await Promise.all(c.pending);
    return { status: JSON.parse(await kv.get("live.json")).status };
  },

  async settled_stops_collecting() {
    const counter = { calls: 0 };
    installFetch(async () => {
      counter.calls += 1;
      return new Response(FULL_PAGE, { status: 200 });
    });
    const kv = new FakeKV();
    const env = { LIVE: kv, MIN_AGREEMENT: "1" };

    const ctx = newCtx();
    await worker.scheduled({}, env, ctx);
    await Promise.all(ctx.pending);
    const afterFirst = counter.calls;
    const status = JSON.parse(await kv.get("live.json")).status;

    for (let i = 0; i < 5; i += 1) {
      const c = newCtx();
      await worker.scheduled({}, env, c);
      await Promise.all(c.pending);
    }
    const afterFive = counter.calls;

    const stale = JSON.parse(await kv.get("live.json"));
    stale.draw_date = "2000-01-01";
    stale.prizes = { ...stale.prizes, special: ["00000"] };
    await kv.put("live.json", JSON.stringify(stale));
    const c = newCtx();
    await worker.scheduled({}, env, c);
    await Promise.all(c.pending);

    return {
      status,
      outbound_after_first_cron: afterFirst,
      outbound_after_six_crons: afterFive,
      outbound_after_stale_date: counter.calls,
    };
  },

  async kv_put_throws() {
    const counter = { calls: 0 };
    installFetch(makeFetch(counter));
    const kv = new FakeKV();
    kv.put = async () => { throw new Error("KV put failed: quota exceeded"); };
    const ctx = newCtx();
    await worker.scheduled({}, { LIVE: kv }, ctx);
    const settled = await Promise.allSettled(ctx.pending);
    const afterCron = counter.calls;
    const out = [];
    for (let i = 0; i < 12; i += 1) {
      const res = await worker.fetch(new Request("https://w/live.json"), { LIVE: kv }, newCtx());
      out.push({ status: res.status, cors: res.headers.get("access-control-allow-origin") });
    }
    return {
      cron_rejected: settled.some((r) => r.status === "rejected"),
      outbound_on_cron: afterCron,
      statuses: [...new Set(out.map((r) => r.status))],
      cors: [...new Set(out.map((r) => r.cors))],
      outbound_after_reads: counter.calls,
    };
  },

  async health_corrupt_kv() {
    const kv = new FakeKV();
    kv.get = async () => "{not json";
    const res = await worker.fetch(new Request("https://w/health"), { LIVE: kv }, newCtx());
    const body = await res.json();
    return { status: res.status, has_snapshot: body.has_snapshot };
  },

  async routing() {
    installFetch(makeFetch({ calls: 0 }));
    const env = { LIVE: new FakeKV() };
    const ctx = newCtx();
    const at = async (path, init) =>
      (await worker.fetch(new Request("https://w" + path, init), env, ctx)).status;
    return {
      unknown_path: await at("/abc"),
      post: await at("/live.json", { method: "POST" }),
      options: await at("/live.json", { method: "OPTIONS" }),
    };
  },
};

const name = process.argv[2];
if (!(name in SCENARIOS)) {
  process.stderr.write(`kịch bản lạ: ${name}\n`);
  process.exit(2);
}
process.stdout.write(JSON.stringify(await SCENARIOS[name](), null, 2));
