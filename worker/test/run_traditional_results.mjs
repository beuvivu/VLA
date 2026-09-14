import worker from "../src/index.js";
import {
  buildTraditionalResults,
  parseTraditionalQuery,
  parseXsktLedger,
} from "../src/traditional_results.js";

class FakeKV {
  constructor() { this.store = new Map(); }
  async get(key) { return this.store.get(key) ?? null; }
  async put(key, value) { this.store.set(key, value); }
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

function makeFetch(counter) {
  return async (url) => {
    if (String(url).includes("raw.githubusercontent.com")) {
      counter.primary += 1;
      return new Response(JSON.stringify([primaryRow]), { status: 200 });
    }
    if (String(url).includes("xskt.vn")) {
      counter.xskt += 1;
      return new Response(xsktHtml, { status: 200 });
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

  async fallback_and_response_cache() {
    const counter = { primary: 0, xskt: 0 };
    globalThis.fetch = makeFetch(counter);
    const kv = new FakeKV();
    const env = { LIVE: kv };
    const ctx1 = { pending: [], waitUntil(promise) { this.pending.push(promise); } };
    const url = "https://worker/api/v1/traditional-results"
      + "?province=hanoi&from=2026-09-12&to=2026-09-13";
    const firstResponse = await worker.fetch(new Request(url), env, ctx1);
    const first = await firstResponse.json();
    await Promise.all(ctx1.pending);
    const ctx2 = { pending: [], waitUntil(promise) { this.pending.push(promise); } };
    const secondResponse = await worker.fetch(new Request(url), env, ctx2);
    const second = await secondResponse.json();
    return {
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

  async fallback_outage_keeps_primary() {
    const counter = { primary: 0, xskt: 0 };
    const fetchImpl = async (url) => {
      if (String(url).includes("raw.githubusercontent.com")) {
        counter.primary += 1;
        return new Response(JSON.stringify([primaryRow]), { status: 200 });
      }
      counter.xskt += 1;
      throw new Error("upstream timeout");
    };
    const payload = await buildTraditionalResults(
      query,
      { LIVE: new FakeKV() },
      { fetchImpl, nowUtcMs: Date.UTC(2026, 8, 13, 12) },
    );
    return {
      counter,
      dates: payload.data.map((row) => row.draw_date),
      unresolved: payload.meta.unresolved_dates,
      warning: payload.meta.warning,
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
