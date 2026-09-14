// Chạy handler của Worker với env giả, MỘT KỊCH BẢN mỗi lần gọi.
//
// Mỗi kịch bản phải là một tiến trình riêng: `index.js` giữ trạng thái ở cấp
// module (mốc chặn khuếch đại trong bộ nhớ), nên chạy nhiều kịch bản trong
// cùng một tiến trình thì ca sau thừa hưởng khoá của ca trước và số đo thành
// vô nghĩa. Bản đầu tôi viết đúng lỗi ấy: ca "KV lành lặn" báo 0 lượt gọi ra
// nguồn, mà thật ra chỉ vì ca trước đã đặt mốc.
import worker from "../src/index.js";

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

  // Tình huống XẤU NHẤT: KV còn sống nhưng ghi không lưu được gì, nên khoá
  // trong KV vô tác dụng. Trang live vẫn thăm dò 5 giây một lần.
  async amplification_kv_broken() {
    const counter = { calls: 0 };
    globalThis.fetch = makeFetch(counter);
    const kv = new FakeKV();
    kv.put = async () => { kv.puts += 1; };
    const ctx = newCtx();
    const statuses = [];
    for (let i = 0; i < 12; i += 1) {
      statuses.push((await worker.fetch(
        new Request("https://w/live.json"), { LIVE: kv }, ctx,
      )).status);
    }
    return { requests: 12, outbound_fetches: counter.calls,
             all_ok: statuses.every((s) => s === 200) };
  },

  // KV lành lặn nhưng chưa có ảnh chụp: đúng lần gọi đầu sau khi triển khai.
  async amplification_kv_healthy() {
    const counter = { calls: 0 };
    globalThis.fetch = makeFetch(counter);
    const kv = new FakeKV();
    const ctx = newCtx();
    const statuses = [];
    for (let i = 0; i < 12; i += 1) {
      statuses.push((await worker.fetch(
        new Request("https://w/live.json"), { LIVE: kv }, ctx,
      )).status);
    }
    return { requests: 12, outbound_fetches: counter.calls,
             all_ok: statuses.every((s) => s === 200) };
  },

  // Đường bình thường: cron ghi một lần, mọi lượt đọc lấy từ KV.
  async normal() {
    const counter = { calls: 0 };
    globalThis.fetch = makeFetch(counter);
    const kv = new FakeKV();
    const env = { LIVE: kv, MIN_AGREEMENT: "2" };
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

  // Bảy nguồn cùng chặn: lượt cron không được đổ, và vẫn phải ghi ảnh chụp.
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
      errors: parsed ? parsed.source_status.filter((r) => r.error).length : 0,
    };
  },

  // Sau khi kỳ đã xác minh xong, cron không được gọi nguồn nữa.
  async settled_stops_collecting() {
    const counter = { calls: 0 };
    // Trả trọn một kỳ để đạt complete_verified ngay vòng đầu.
    const full = "<div>ĐB 83772</div><div>G1 68785</div>"
      + "<div>G2 50518 27452</div>"
      + "<div>G3 57053 92810 56241 65128 33811 42264</div>"
      + "<div>G4 4753 1152 6777 3507</div>"
      + "<div>G5 9460 2913 3232 2999 3670 5129</div>"
      + "<div>G6 939 751 594</div><div>G7 66 21 34 78</div>";
    globalThis.fetch = async () => {
      counter.calls += 1;
      return new Response(full, { status: 200 });
    };
    const kv = new FakeKV();
    const env = { LIVE: kv, MIN_AGREEMENT: "2" };

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
    const stale = JSON.parse(await kv.get("live.json"));
    stale.draw_date = "2000-01-01";
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
