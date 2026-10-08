import worker from "../src/index.js";
import {
  buildTraditionalResults,
  parseTraditionalQuery,
  parseXsktLedger,
  refreshFallbackOverlay,
} from "../src/traditional_results.js";

// So đúng TÊN HOST, không so chuỗi con: "raw.githubusercontent.com" có thể nằm ở bất kỳ đâu
// trong một URL của host khác.
const hostOf = (url) => new URL(String(url)).hostname;

class FakeKV {
  constructor() { this.store = new Map(); }
  async get(key) { return this.store.get(key) ?? null; }
  async put(key, value, options = {}) {
    // Như Cloudflare KV: TTL dưới 60 giây bị từ chối.
    if (options.expirationTtl !== undefined && options.expirationTtl < 60) {
      throw new Error(`Invalid expiration_ttl of ${options.expirationTtl}. Expiration TTL must be at least 60.`);
    }
    this.store.set(key, value);
  }
}

const primaryRow = {
  date: "2026-09-12T00:00:00.000",
  special: 58851,
  prize1: 93635,
  prize2_1: 62249, prize2_2: 19402,
  prize3_1: 15181, prize3_2: 68352, prize3_3: 76599,
  prize3_4: 77021, prize3_5: 54082, prize3_6: 85899,
  prize4_1: 5804, prize4_2: 9984, prize4_3: 3399, prize4_4: 1827,
  prize5_1: 2462, prize5_2: 9390, prize5_3: 4742,
  prize5_4: 1298, prize5_5: 8565, prize5_6: 6114,
  prize6_1: 119, prize6_2: 998, prize6_3: 793,
  prize7_1: 1, prize7_2: 39, prize7_3: 43, prize7_4: 23,
};

const xsktHtml = `
<table class="kqmb extendable"><tbody>
<tr><th><h2>XSMB chủ nhật ngày 13-09-2026</h2></th></tr>
<tr><td>ĐB</td><td>83799</td></tr>
<tr><td>G1</td><td>63029</td></tr>
<tr><td>G2</td><td>21509 71228</td></tr>
<tr><td>G3</td><td>28530 12732 41085 43205 58675 62527</td></tr>
<tr><td>G4</td><td>2812 7409 9962 7240</td></tr>
<tr><td>G5</td><td>5439 8360 4126 2579 5130 5884</td></tr>
<tr><td>G6</td><td>988 648 462</td></tr>
<tr><td>G7</td><td>21 88 40 27</td></tr>
</tbody></table>`;

const NOW = Date.UTC(2026, 8, 13, 12);   // 19:00 giờ VN ngày 13-09-2026: kỳ mới nhất là 13-09
const MINUTE = 60_000;
const ctxOf = () => ({ pending: [], waitUntil(promise) { this.pending.push(promise); } });

// Trang dự phòng chỉ có những ngày được nêu (cùng bộ giải, khác ngày).
const pageWith = (...days) => days.map((day) => xsktHtml.replace("13-09-2026", day)).join("\n");

function makeFetch(counter, { page = xsktHtml, primary = [primaryRow] } = {}) {
  return async (url) => {
    if (hostOf(url) === "raw.githubusercontent.com") {
      counter.primary += 1;
      return new Response(JSON.stringify(primary), { status: 200 });
    }
    if (hostOf(url) === "xskt.vn") {
      counter.xskt += 1;
      return new Response(page, { status: 200 });
    }
    return new Response("not found", { status: 404 });
  };
}

const query = {
  region: "north", province: "hanoi",
  from: "2026-09-12", to: "2026-09-13",
  preset_days: null, timezone: "Asia/Ho_Chi_Minh",
};

const scenarios = {
  async primary_first() {
    const counter = { primary: 0, xskt: 0 };
    const payload = await buildTraditionalResults(
      { ...query, to: "2026-09-12" },
      { LIVE: new FakeKV() },
      { fetchImpl: makeFetch(counter), nowUtcMs: Date.UTC(2026, 8, 13, 12) },
    );
    return {
      counter,
      count: payload.data.length,
      source: payload.data[0].source.kind,
      special: payload.data[0].prizes[0].values[0],
      leading_zero: payload.data[0].prizes.at(-1).values[0],
      head_tail_total: Object.values(payload.data[0].head_tail.heads)
        .reduce((total, values) => total + values.length, 0),
    };
  },

  // Cron nạp lớp bù; yêu cầu chỉ ĐỌC nó, và lượt thứ hai lấy từ đệm phản hồi.
  async cron_fills_then_requests_read() {
    const counter = { primary: 0, xskt: 0 };
    globalThis.fetch = makeFetch(counter);
    const env = { LIVE: new FakeKV() };
    const refreshed = await refreshFallbackOverlay(env, { fetchImpl: makeFetch(counter) });
    const xsktOnCron = counter.xskt;
    const url = "https://worker/api/v1/traditional-results"
      + "?province=hanoi&from=2026-09-12&to=2026-09-13";
    const ctx1 = ctxOf();
    const firstResponse = await worker.fetch(new Request(url), env, ctx1);
    const first = await firstResponse.json();
    await Promise.all(ctx1.pending);
    const secondResponse = await worker.fetch(new Request(url), env, ctxOf());
    const second = await secondResponse.json();
    return {
      refreshed: refreshed.fetched,
      xskt_on_cron: xsktOnCron,
      statuses: [firstResponse.status, secondResponse.status],
      counter,
      dates: first.data.map((row) => row.draw_date),
      sources: first.data.map((row) => row.source.kind),
      fallback_requested: first.meta.fallback_requested,
      fallback_network_fetch: first.meta.fallback_network_fetch,
      second_cache: second.meta.response_cache,
      xskt_special: first.data[0].prizes[0].values[0],
    };
  },

  // Nguồn dự phòng hỏng ở lượt cron: yêu cầu vẫn trả lịch sử chuẩn và báo ngày còn thiếu.
  async fallback_outage_keeps_primary() {
    const counter = { primary: 0, xskt: 0 };
    const fetchImpl = async (url) => {
      if (hostOf(url) === "raw.githubusercontent.com") {
        counter.primary += 1;
        return new Response(JSON.stringify([primaryRow]), { status: 200 });
      }
      counter.xskt += 1;
      throw new Error("upstream timeout");
    };
    const env = { LIVE: new FakeKV() };
    let refreshError = null;
    try { await refreshFallbackOverlay(env, { fetchImpl, nowUtcMs: NOW }); } catch (error) {
      refreshError = String(error.message);
    }
    const payload = await buildTraditionalResults(query, env, { fetchImpl, nowUtcMs: NOW });
    return {
      refresh_error: refreshError,
      counter,
      dates: payload.data.map((row) => row.draw_date),
      unresolved: payload.meta.unresolved_dates,
      warning: payload.meta.warning,
    };
  },

  // Khách đổi khoảng ngày liên tục: mỗi khoảng là một khoá đệm mới, nhưng yêu cầu không
  // bao giờ gọi nguồn dự phòng.
  async amplification() {
    const counter = { primary: 0, xskt: 0 };
    globalThis.fetch = makeFetch(counter);
    const env = { LIVE: new FakeKV() };
    const statuses = [];
    for (let i = 0; i < 20; i += 1) {
      const from = new Date(Date.UTC(2026, 5, 1 + i)).toISOString().slice(0, 10);
      const to = new Date(Date.UTC(2026, 5, 3 + i)).toISOString().slice(0, 10);
      const ctx = ctxOf();
      const res = await worker.fetch(new Request(
        `https://worker/api/v1/traditional-results?from=${from}&to=${to}`), env, ctx);
      await Promise.all(ctx.pending);
      statuses.push(res.status);
    }
    return { counter, statuses: [...new Set(statuses)] };
  },

  // Ngày 13-09 vẫn thiếu (trang chưa có): cron tải lại, nhưng cách nhau tối thiểu 10 phút.
  async cron_refresh_is_spaced() {
    const counter = { primary: 0, xskt: 0 };
    const fetchImpl = makeFetch(counter, { page: pageWith("10-09-2026") });
    const env = { LIVE: new FakeKV() };
    const after = [];
    for (const minutes of [0, 5, 9, 11, 15, 22]) {
      await refreshFallbackOverlay(env, { fetchImpl, nowUtcMs: NOW + minutes * MINUTE });
      after.push(counter.xskt);
    }
    return { xskt_after_each: after };
  },

  // Lịch sử chuẩn đủ mọi ngày trong cửa sổ trừ 11-09 (nghỉ quay) và 13-09. Trang có 10-09 và
  // 13-09: 13-09 được bù, 11-09 nằm giữa hai ngày của trang mà trang không có → ghi "absent".
  // Hết ngày thiếu thì cron không gọi nguồn nữa, kể cả khi đã quá 10 phút; nhưng sau 7 ngày dấu
  // "absent" hết hạn và cron kiểm lại đúng một lần.
  async days_the_source_never_had_are_remembered() {
    const counter = { primary: 0, xskt: 0 };
    const primary = [];
    for (let d = Date.UTC(2025, 4, 2); d <= Date.UTC(2026, 8, 21); d += 86_400_000) {
      const day = new Date(d).toISOString().slice(0, 10);
      if (day !== "2026-09-11" && day !== "2026-09-13") {
        primary.push({ ...primaryRow, date: `${day}T00:00:00.000` });
      }
    }
    const fetchImpl = makeFetch(counter, { page: pageWith("10-09-2026", "13-09-2026"), primary });
    const env = { LIVE: new FakeKV() };
    const first = await refreshFallbackOverlay(env, { fetchImpl, nowUtcMs: NOW });
    const second = await refreshFallbackOverlay(env, { fetchImpl, nowUtcMs: NOW + 30 * MINUTE });
    const xsktBeforeRecheck = counter.xskt;
    const payload = await buildTraditionalResults(
      { ...query, from: "2026-09-10", to: "2026-09-13" }, env, { fetchImpl, nowUtcMs: NOW });
    const DAY = 1440 * MINUTE;
    const recheck = await refreshFallbackOverlay(env, { fetchImpl, nowUtcMs: NOW + 8 * DAY });
    const afterRecheck = await refreshFallbackOverlay(env, { fetchImpl, nowUtcMs: NOW + 8 * DAY + 30 * MINUTE });
    return {
      first, second, xskt: xsktBeforeRecheck, recheck, after_recheck: afterRecheck,
      xskt_total: counter.xskt,
      dates: payload.data.map((row) => row.draw_date),
      unresolved: payload.meta.unresolved_dates,
    };
  },

  // Cron chỉ nạp lớp bù khi wrangler.toml bật TRADITIONAL_FALLBACK_REFRESH. Đếm đúng trang sổ
  // cuộn 500 ngày: bộ thu thập trang live cũng gọi cùng host, nên đếm theo host là gộp hai việc.
  async scheduled_refresh_needs_the_switch() {
    const run = async (vars) => {
      let ledgerFetches = 0;
      const base = makeFetch({ primary: 0, xskt: 0 });
      globalThis.fetch = async (url, init) => {
        if (new URL(String(url)).pathname.startsWith("/xsmb-500-ngay")) ledgerFetches += 1;
        return base(url, init);
      };
      const ctx = ctxOf();
      await worker.scheduled({}, { LIVE: new FakeKV(), ...vars }, ctx);
      await Promise.allSettled(ctx.pending);
      return ledgerFetches;
    };
    return {
      on: await run({ TRADITIONAL_FALLBACK_REFRESH: "on" }),
      off: await run({}),
    };
  },

  async future_range() {
    const env = { LIVE: new FakeKV() };
    const res = await worker.fetch(new Request(
      "https://worker/api/v1/traditional-results?from=2099-01-01&to=2099-01-05"), env, { waitUntil() {} });
    return { status: res.status };
  },

  // Ngày cũ hơn cửa sổ 500 ngày của nguồn dự phòng: gọi cũng không có, nên không gọi.
  async out_of_window() {
    const counter = { primary: 0, xskt: 0 };
    const payload = await buildTraditionalResults(
      { ...query, from: "2020-01-01", to: "2020-01-03" },
      { LIVE: new FakeKV() },
      { fetchImpl: makeFetch(counter), nowUtcMs: Date.UTC(2026, 8, 13, 12) },
    );
    return { counter, unresolved: payload.meta.unresolved_dates };
  },

  // Không gửi danh tính nguồn ra trình duyệt, như anonymiseSnapshot của live.json.
  async anonymised() {
    const counter = { primary: 0, xskt: 0 };
    const okEnv = { LIVE: new FakeKV() };
    await refreshFallbackOverlay(okEnv, { fetchImpl: makeFetch(counter), nowUtcMs: NOW });
    const ok = await buildTraditionalResults(query, okEnv, { fetchImpl: makeFetch(counter), nowUtcMs: NOW });
    const busy = async (url) => (hostOf(url) === "raw.githubusercontent.com"
      ? new Response(JSON.stringify([primaryRow]), { status: 200 })
      : new Response("busy", { status: 503 }));
    const failingEnv = { LIVE: new FakeKV() };
    try { await refreshFallbackOverlay(failingEnv, { fetchImpl: busy, nowUtcMs: NOW }); } catch { /* lỗi cron chỉ vào log */ }
    const failing = await buildTraditionalResults(query, failingEnv, { fetchImpl: busy, nowUtcMs: NOW });
    const text = JSON.stringify([ok, failing]).toLowerCase();
    return {
      mentions_source: text.includes("xskt"),
      sources: ok.data.map((row) => row.source.kind),
      schema_version: ok.schema_version,
      sources_used: ok.meta.sources_used,
    };
  },

  async validation() {
    const env = { LIVE: new FakeKV() };
    const ctx = { waitUntil() {} };
    const status = async (queryString) => (
      await worker.fetch(new Request("https://worker/api/v1/traditional-results?" + queryString), env, ctx)
    ).status;
    return {
      unsupported: await status("region=south&province=hcm&days=30"),
      invalid_days: await status("days=31"),
      missing_to: await status("from=2026-09-01"),
      too_long: await status("from=2025-01-01&to=2026-09-13"),
    };
  },

  async legacy_response_cache() {
    const kv = new FakeKV();
    await kv.put("traditional:response:v1:north:hanoi:2026-09-12:2026-09-12", JSON.stringify({
      schema_version: 1, data: [{ source: { kind: "vla_db", provider: "VLA canonical database" } }],
      meta: { source_counts: { vla_db: 1 } },
    }));
    const counter = { primary: 0, xskt: 0 };
    globalThis.fetch = makeFetch(counter);
    const reply = await worker.fetch(new Request(
      "https://worker/api/v1/traditional-results?from=2026-09-12&to=2026-09-12"), { LIVE: kv });
    const payload = await reply.json();
    return { status: reply.status, payload, counter };
  },

  async invalid_primary_is_anonymous() {
    const replies = [];
    for (const primary of [{}, []]) {
      globalThis.fetch = async () => new Response(JSON.stringify(primary));
      const reply = await worker.fetch(new Request(
        "https://worker/api/v1/traditional-results?from=2026-09-12&to=2026-09-12"), { LIVE: new FakeKV() });
      replies.push({ status: reply.status, payload: await reply.json() });
    }
    return { replies };
  },

  async incomplete_table_is_retried() {
    const kv = new FakeKV();
    const prizes = parseXsktLedger(xsktHtml)["2026-09-13"];
    const rows = {};
    for (let i = 0; i < 500; i++) {
      const day = new Date(Date.UTC(2026, 8, 13) - i * 86_400_000).toISOString().slice(0, 10);
      if (day !== "2026-09-11") rows[day] = prizes;
    }
    await kv.put("traditional:primary:fresh:v1", JSON.stringify(rows));
    const broken = pageWith("11-09-2026").replace("21 88 40 27", "21 88 40");
    let page = pageWith("10-09-2026") + broken + pageWith("13-09-2026");
    let calls = 0;
    const fetchImpl = async () => { calls += 1; return new Response(page); };
    const env = { LIVE: kv };
    const first = await refreshFallbackOverlay(env, { fetchImpl, nowUtcMs: NOW });
    const before = await buildTraditionalResults({ ...query, from: "2026-09-11", to: "2026-09-11" },
      env, { fetchImpl, nowUtcMs: NOW });
    page = pageWith("10-09-2026", "11-09-2026", "13-09-2026");
    const second = await refreshFallbackOverlay(env, { fetchImpl, nowUtcMs: NOW + 11 * MINUTE });
    const after = await buildTraditionalResults({ ...query, from: "2026-09-11", to: "2026-09-11" },
      env, { fetchImpl, nowUtcMs: NOW + 11 * MINUTE });
    return { first, second, calls, before: before.meta,
      after: { total: after.meta.total_results, unresolved: after.meta.unresolved_dates,
        special: after.data[0]?.prizes[0].values[0] } };
  },

  async cors_preflight() {
    const response = await worker.fetch(
      new Request("https://worker/api/v1/traditional-results", { method: "OPTIONS" }),
      {},
      { waitUntil() {} },
    );
    return {
      status: response.status,
      origin: response.headers.get("access-control-allow-origin"),
      methods: response.headers.get("access-control-allow-methods"),
      max_age: response.headers.get("access-control-max-age"),
    };
  },

  async parser_and_preset() {
    const rows = parseXsktLedger(xsktHtml);
    const parsed = parseTraditionalQuery(
      new URL("https://worker/api/v1/traditional-results?days=30"),
      { nowUtcMs: Date.UTC(2026, 8, 13, 10, 0) }, // 17:00 giờ Việt Nam
    );
    return {
      dates: Object.keys(rows),
      fields: rows["2026-09-13"] ? Object.keys(rows["2026-09-13"]).length : 0,
      from: parsed.from,
      to: parsed.to,
      timezone: parsed.timezone,
    };
  },
};

const name = process.argv[2];
if (!(name in scenarios)) {
  process.stderr.write(`kịch bản lạ: ${name}\n`);
  process.exit(2);
}
process.stdout.write(JSON.stringify(await scenarios[name](), null, 2));
