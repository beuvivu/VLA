#!/usr/bin/env node
// Bộ cài đặt MỘT LỆNH cho Worker đúng giờ.
//
//   cd worker && npm run setup
//
// Việc của bạn chỉ còn: có tài khoản Cloudflare (miễn phí, không cần thẻ).
// Kịch bản này lo phần còn lại và KHÔNG bắt bạn chép–dán gì cả:
//
//   1. đăng nhập Cloudflare nếu chưa
//   2. tạo kho KV, tự đọc id, tự điền vào wrangler.toml
//   3. triển khai Worker, tự đọc địa chỉ, tự điền vào docs/live.html
//   4. gọi thử /health để xác minh nó sống thật
//
// Chạy lại nhiều lần đều an toàn: bước nào đã xong thì bỏ qua.
// Thêm `--dry-run` để xem nó ĐỊNH làm gì mà không đụng vào đâu.

import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  currentLiveWorkerUrl,
  extractKvId,
  extractWorkerUrl,
  patchLiveWorkerUrl,
  patchWranglerKvId,
} from "./setup/patch.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..");
const WRANGLER_TOML = join(HERE, "wrangler.toml");
const LIVE_HTML = join(REPO, "docs", "live.html");
const DRY = process.argv.includes("--dry-run");

let step = 0;
const say = (msg) => process.stdout.write(msg + "\n");
const heading = (msg) => say(`\n[${++step}] ${msg}`);
const ok = (msg) => say(`    ✓ ${msg}`);
const note = (msg) => say(`    · ${msg}`);

function fail(msg, extra) {
  process.stderr.write(`\n✗ ${msg}\n`);
  if (extra) process.stderr.write(String(extra).trim() + "\n");
  process.exit(1);
}

function wrangler(args, { capture = true } = {}) {
  const result = spawnSync("npx", ["--yes", "wrangler@4", ...args], {
    cwd: HERE,
    encoding: "utf-8",
    stdio: capture ? ["inherit", "pipe", "pipe"] : "inherit",
  });
  if (result.error) {
    fail(`không chạy được npx wrangler: ${result.error.message}`);
  }
  const output = `${result.stdout || ""}\n${result.stderr || ""}`;
  return { code: result.status, output };
}

// --- 1. Đăng nhập ----------------------------------------------------------

heading("Kiểm tra đăng nhập Cloudflare");
if (DRY) {
  // Thử khô KHÔNG gọi wrangler: nó sẽ tải về ~30 MB và cần mạng. Phép kiểm
  // chạy đúng nhánh này trong CI, nên nó phải hermetic và nhanh.
  note("(thử khô) sẽ kiểm `wrangler whoami`, mở trình duyệt đăng nhập nếu cần");
} else {
  const who = wrangler(["whoami"]);
  if (who.code !== 0 || /not authenticated|You are not logged in/i.test(who.output)) {
    note("chưa đăng nhập — đang mở trình duyệt…");
    const login = wrangler(["login"], { capture: false });
    if (login.code !== 0) fail("đăng nhập Cloudflare thất bại");
    ok("đã đăng nhập");
  } else {
    const email = who.output.match(/[\w.+-]+@[\w.-]+\.\w+/);
    ok(`đã đăng nhập${email ? ` (${email[0]})` : ""}`);
  }
}

// --- 2. Kho KV -------------------------------------------------------------

heading("Kho KV (nơi cất ảnh chụp giữa hai lượt cron)");
{
  const toml = readFileSync(WRANGLER_TOML, "utf-8");
  if (!toml.includes("THAY_BANG_ID_KV_CUA_BAN")) {
    ok("wrangler.toml đã có id kho KV — bỏ qua");
  } else if (DRY) {
    note("(thử khô) sẽ tạo kho KV rồi tự điền id vào wrangler.toml");
  } else {
    let created = wrangler(["kv", "namespace", "create", "LIVE"]);
    if (created.code !== 0 && /unknown argument|did you mean/i.test(created.output)) {
      // Wrangler cũ dùng cú pháp hai chấm. Tự thử, không bắt người dùng đoán.
      note("wrangler bản cũ — thử lại với cú pháp kv:namespace");
      created = wrangler(["kv:namespace", "create", "LIVE"]);
    }
    if (created.code !== 0) fail("tạo kho KV thất bại", created.output);
    const id = extractKvId(created.output);
    writeFileSync(WRANGLER_TOML, patchWranglerKvId(toml, id), "utf-8");
    ok(`đã tạo kho KV và điền id vào wrangler.toml (${id.slice(0, 8)}…)`);
  }
}

// --- 3. Triển khai ---------------------------------------------------------

heading("Triển khai Worker");
let workerUrl = null;
{
  if (DRY) {
    note("(thử khô) sẽ chạy wrangler deploy rồi tự đọc địa chỉ");
  } else {
    const deployed = wrangler(["deploy"]);
    if (deployed.code !== 0) fail("triển khai thất bại", deployed.output);
    workerUrl = extractWorkerUrl(deployed.output);
    ok(`đã triển khai: ${workerUrl}`);
  }
}

// --- 4. Trỏ trang live vào Worker -----------------------------------------

heading("Trỏ docs/live.html vào Worker");
{
  const html = readFileSync(LIVE_HTML, "utf-8");
  const current = currentLiveWorkerUrl(html);
  if (DRY) {
    note(`(thử khô) sẽ điền địa chỉ vào docs/live.html (hiện: ${current || "trống"})`);
  } else if (current && current.startsWith(workerUrl)) {
    ok("đã trỏ đúng rồi — bỏ qua");
  } else {
    writeFileSync(LIVE_HTML, patchLiveWorkerUrl(html, workerUrl), "utf-8");
    ok(`đã điền: ${workerUrl}/live.json`);
  }
}

// --- 5. Xác minh -----------------------------------------------------------

heading("Gọi thử để xác minh");
if (DRY) {
  note("(thử khô) sẽ gọi /health và /live.json");
} else {
  // Worker vừa lên có thể cần vài giây để lan ra biên.
  let health = null;
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    try {
      const response = await fetch(`${workerUrl}/health`, { cache: "no-store" });
      if (response.ok) { health = await response.json(); break; }
    } catch { /* chưa lan tới, thử lại */ }
    await new Promise((r) => setTimeout(r, attempt * 1500));
  }
  if (!health) fail(`Worker chưa trả lời tại ${workerUrl}/health`);
  ok(`/health trả lời: ok=${health.ok}, đã có ảnh chụp=${health.has_snapshot}`);

  note("đang ép thu thập một lượt để kiểm đường ra nguồn…");
  try {
    const snap = await (await fetch(`${workerUrl}/live.json`, { cache: "no-store" })).json();
    const rows = snap.source_status || [];
    const alive = rows.filter((r) => !r.error).length;
    ok(`${alive}/${rows.length} nguồn trả lời được`);
    if (rows.length > 0 && alive === 0) {
      say("");
      say("    ⚠ KHÔNG nguồn nào trả lời. Nhiều khả năng các trang chặn IP trung");
      say("      tâm dữ liệu — đây là rủi ro đã ghi ở mục 6 của");
      say("      documentation/operations/live-worker.md.");
      say("      Lỗi của từng nguồn:");
      for (const row of rows) say(`        ${row.source}: ${row.error}`);
      say("      Muốn quay lại như cũ: xoá nội dung window.LIVE_WORKER_URL");
      say("      trong docs/live.html rồi đẩy lên.");
    }
  } catch (error) {
    note(`chưa gọi được /live.json (${error.message}) — thử lại sau vài phút`);
  }
}

// --- Xong ------------------------------------------------------------------

say("");
if (DRY) {
  say("Thử khô xong. Bỏ --dry-run để chạy thật.");
} else {
  say("XONG. Còn đúng một việc cho bạn:");
  say("");
  say("    git add worker/wrangler.toml docs/live.html");
  say('    git commit -m "worker: trỏ trang live vào Worker đã triển khai"');
  say("    git push");
  say("");
  say(`Theo dõi lượt cron chạy thật:  cd worker && npx wrangler tail`);
}
