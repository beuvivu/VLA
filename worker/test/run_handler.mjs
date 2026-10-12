// Chạy handler của Worker với env giả, MỘT KỊCH BẢN mỗi lần gọi.
//
// Mỗi kịch bản là một tiến trình riêng: trạng thái cấp module (bộ đệm trong bộ nhớ) của ca
// trước không được lọt sang ca sau. Từng có một bản giữ mốc chặn ở cấp module, và ca sau báo 0
// lượt gọi nguồn chỉ vì ca trước đã đặt mốc.
import worker from "../src/index.js";

// Đồng hồ cố định 18:20 giờ Việt Nam. Nguồn chính chỉ bị coi là hỏng khi đã quá 18:40 mà còn
// thiếu ô, nên để đồng hồ thật thì kịch bản "normal" (trang giả chỉ có ĐB và G7) gọi hay không
// gọi nguồn dự phòng tuỳ GIỜ CHẠY KIỂM. Kịch bản "primary_stuck_after_deadline" tự đặt giờ khác.
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
    // Như Cloudflare KV: TTL dưới 60 giây bị từ chối. Bản giả không chặn điều này từng để lọt
    // một khoá 10 giây không bao giờ ghi được.
    if (ttl !== undefined && ttl < 60) {
      throw new Error(`Invalid expiration_ttl of ${ttl}. Expiration TTL must be at least 60.`);
    }
    this.store.set(key, { value, expiresAt: ttl ? Date.now() + ttl * 1000 : null });
  }
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
  // Quên tạo KV là lỗi cấu hình hay gặp nhất lúc triển khai lần đầu.
  async missing_kv() {
    try {
      await worker.fetch(new Request("https://w/live.json"), {}, newCtx());
      return { message: null };
    } catch (error) {
      return { message: String(error.message) };
    }
  },

  // KV chưa có ảnh chụp (khởi động lạnh) hoặc ghi không lưu được gì, nhiều isolate cùng lúc:
  // trước 08-10-2026 mỗi isolate tự thu thập vì khoá trong KV không nguyên tử. Lượt yêu cầu
  // nay không bao giờ gọi nguồn, nên số lượt gọi ra phải bằng 0 dù có bao nhiêu isolate.
  async requests_never_collect() {
    const counter = { calls: 0 };
    globalThis.fetch = makeFetch(counter);
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

  // Đường bình thường: cron ghi một lần, mọi lượt đọc lấy từ KV.
  async normal() {
    const counter = { calls: 0 };
    globalThis.fetch = makeFetch(counter);
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

  // Mọi nguồn cùng chặn: lượt cron không được đổ, và vẫn phải ghi ảnh chụp.
  // Nguồn chính hỏng thì hai nguồn dự phòng phải được gọi, nên bản chụp
  // có đủ CẢ BA hàng nguồn chứ không phải một.
  async all_sources_down() {
    globalThis.fetch = makeFetch({ calls: 0 }, { fail: true });
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
      // Bản chụp đã ẩn danh nên không còn trường `error`; cờ `failed` thay nó.
      errors: parsed ? parsed.source_status.filter((r) => r.failed).length : 0,
      source_rows: parsed ? parsed.source_status.length : 0,
      fallback_activated: parsed?.failover?.fallback_activated ?? null,
    };
  },

  // 18:45 giờ VN, nguồn chính vẫn chỉ có ĐB và G7 (kẹt), hai dự phòng có trọn kỳ: dự phòng
  // được gọi và CHỈ chúng được hợp nhất — bản kẹt của nguồn chính không được che chúng.
  async primary_stuck_after_deadline() {
    fixedNow = Date.parse("2026-10-13T11:45:00Z");
    const hosts = [];
    globalThis.fetch = async (url) => {
      const host = new URL(String(url)).hostname;
      hosts.push(host);
      const body = host.endsWith("xoso.com.vn") ? STUCK_PAGE : FULL_PAGE;
      return new Response(body, { status: 200 });
    };
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

  // Trước giờ quay, trang live của mọi nguồn vẫn hiện trọn kỳ hôm qua (đo 00:37 ngày
  // 13-10-2026). KV còn ảnh chụp đã xác minh của hôm qua với đúng bảng ấy: bản chụp hôm nay
  // phải là "waiting", không được báo kỳ hôm nay đã xác minh bằng số của hôm qua.
  async stale_page_is_not_today() {
    const kv = new FakeKV();
    const yesterday = {
      schema_version: 2, draw_date: "2026-10-12", status: "complete_verified",
      verified_complete: true,
      prizes: {
        special: ["83772"], prize1: ["68785"], prize2: ["50518", "27452"],
        prize3: ["57053", "92810", "56241", "65128", "33811", "42264"],
        prize4: ["4753", "1152", "6777", "3507"],
        prize5: ["9460", "2913", "3232", "2999", "3670", "5129"],
        prize6: ["939", "751", "594"], prize7: ["66", "21", "34", "78"],
      },
    };
    await kv.put("live.json", JSON.stringify(yesterday));
    globalThis.fetch = async () => new Response(FULL_PAGE, { status: 200 });
    const ctx = newCtx();
    await worker.scheduled({}, { LIVE: kv, MIN_AGREEMENT: "1" }, ctx);
    await Promise.all(ctx.pending);
    const parsed = JSON.parse(await kv.get("live.json"));
    return {
      draw_date: parsed.draw_date,
      status: parsed.status,
      received_values: parsed.received_values,
      fallback_activated: parsed.failover.fallback_activated,
      failed_rows: parsed.source_status.filter((r) => r.failed).length,
    };
  },

  // Sau khi kỳ đã xác minh xong, cron không được gọi nguồn nữa.
  async settled_stops_collecting() {
    const counter = { calls: 0 };
    // Trả trọn một kỳ để đạt complete_verified ngay vòng đầu.
    globalThis.fetch = async () => {
      counter.calls += 1;
      return new Response(FULL_PAGE, { status: 200 });
    };
    const kv = new FakeKV();
    const env = { LIVE: kv, MIN_AGREEMENT: "1" };

    const ctx = newCtx();
    await worker.scheduled({}, env, ctx);
    await Promise.all(ctx.pending);
    const afterFirst = counter.calls;
    const status = JSON.parse(await kv.get("live.json")).status;

    // Thêm năm lượt cron nữa, như trong khung quay số thật.
    for (let i = 0; i < 5; i += 1) {
      const c = newCtx();
      await worker.scheduled({}, env, c);
      await Promise.all(c.pending);
    }
    const afterFive = counter.calls;

    // Ảnh chụp của NGÀY KHÁC không được chặn thu thập hôm nay.
    // Kỳ hôm trước có số KHÁC: cùng số thì nguồn bị coi là còn hiện kỳ trước — đó là kịch
    // bản "stale_page_is_not_today" bên dưới.
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

  // KV đọc được nhưng GHI ném lỗi (hết hạn mức): lượt cron không được làm đổ Worker, lỗi chỉ
  // vào log; người xem nhận 503 có CORS để trang chuyển sang nguồn dự phòng.
  async kv_put_throws() {
    const counter = { calls: 0 };
    globalThis.fetch = makeFetch(counter);
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
    globalThis.fetch = makeFetch({ calls: 0 });
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
