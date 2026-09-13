// Điểm vào của Worker: ĐỒNG HỒ và NGUỒN PHÁT của live.json.
//
// Vì sao có thành phần này
// ========================
// GitHub Pages là hosting tĩnh — không có tiến trình nào chạy ở đó. GitHub
// Actions chỉ chạy khi có thứ gì kích hoạt, và bộ lập lịch của GitHub đo được
// trên chính kho này là trễ 2h50m-4h40m (trung vị 4h04m). Không có cách nào
// khiến mã "tự chạy lúc 18:15" nếu đồng hồ không nằm ở đâu đó.
//
// Worker này LÀ cái đồng hồ ấy. Cron của nền tảng gọi `scheduled()` mỗi phút
// trong khung quay số; nó đọc sáu nguồn, dựng live.json rồi cất vào KV.
// Trình duyệt đọc thẳng từ `fetch()` bên dưới.
//
// Hệ quả quan trọng: GitHub Actions không còn nằm trên đường găng ĐÚNG GIỜ.
// Nó vẫn ghi lịch sử vào kho, nhưng trễ bao nhiêu cũng không ảnh hưởng trang
// live nữa.

import { collectSnapshot, drawDate } from "./snapshot.js";

const KV_KEY = "live.json";
const LOCK_KEY = "collect-lock";

// Chặn KHUẾCH ĐẠI YÊU CẦU.
//
// Nhánh "KV rỗng thì thu thập ngay" là đúng cho lần gọi đầu sau khi triển
// khai. Nhưng nếu KV ghi hỏng — hết hạn mức, cấu hình sai, sự cố nền tảng —
// thì nó biến thành: mỗi người xem, 5 giây một lần, kéo theo sáu lượt gọi ra
// trang nguồn. Mười người xem là 720 lượt/phút dội vào đúng lúc các trang ấy
// đang tải nặng nhất trong ngày.
//
// Khoá ngắn hạn này giữ cho tối đa một vòng thu thập theo yêu cầu mỗi 10
// giây, bất kể có bao nhiêu người xem. Cron vẫn chạy bình thường.
const ONDEMAND_LOCK_SECONDS = 10;

// Lớp chặn THỨ HAI, trong bộ nhớ.
//
// Khoá ở trên nằm trong KV, nên nếu chính KV là thứ đang hỏng thì khoá cũng
// hỏng theo và chốt chặn bốc hơi đúng lúc cần nhất. Đo được: với KV ghi hỏng,
// 12 lượt truy cập sinh 72 lượt gọi ra nguồn.
//
// Biến này sống trong một isolate của Worker, không dùng chung giữa các
// isolate — nên nó KHÔNG thay được khoá KV, chỉ chặn đỡ khi khoá kia mất tác
// dụng. Hai lớp cùng hỏng thì mới khuếch đại được.
let lastOnDemandAttemptMs = 0;

// Ảnh chụp đã xác minh thì không đổi nữa, nên cho phép đệm lâu hơn. Khi đang
// về số thì phải thật ngắn, nếu không trang live sẽ hiện số cũ.
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
      // Trang live nằm trên beuvivu.github.io còn Worker ở tên miền khác, nên
      // không có đầu mục này thì trình duyệt chặn. Chỉ mở đọc, không cookie.
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, OPTIONS",
    },
  });
}

function requireKv(env) {
  if (!env || !env.LIVE || typeof env.LIVE.get !== "function") {
    // Quên bước tạo KV là lỗi cấu hình hay gặp nhất. Không nói rõ thì nó hiện
    // ra dưới dạng "Cannot read properties of undefined", vô nghĩa với người
    // vừa triển khai lần đầu.
    throw new Error(
      "thiếu ràng buộc KV 'LIVE' — chạy `npx wrangler kv namespace create LIVE` "
      + "rồi điền id vào worker/wrangler.toml (xem documentation/operations/live-worker.md)",
    );
  }
  return env.LIVE;
}

/**
 * Kỳ hôm nay đã xác minh xong thì không còn gì để thu thập nữa.
 *
 * Cron chạy mỗi phút suốt khung quay số. Không có chốt này thì sau khi đủ 27 ô
 * và đã xác minh, nó vẫn gọi sáu nguồn thêm vài chục lần nữa mà không thêm
 * được thông tin gì — chỉ tốn hạn mức và dội vào đúng những trang đang tải
 * nặng nhất trong ngày.
 *
 * So theo NGÀY QUAY chứ không chỉ theo trạng thái: ảnh chụp đã xác minh của
 * hôm qua không được phép chặn việc thu thập hôm nay.
 */
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

async function refresh(env, { force = false } = {}) {
  const kv = requireKv(env);
  if (!force && alreadySettled(await kv.get(KV_KEY), Date.now())) return null;
  const snapshot = await collectSnapshot({
    minAgreement: Number(env.MIN_AGREEMENT ?? 2),
  });
  await kv.put(KV_KEY, JSON.stringify(snapshot), {
    // Giữ qua đêm để trang mở lúc sáng vẫn thấy kỳ hôm trước thay vì trắng.
    expirationTtl: 60 * 60 * 36,
  });
  return snapshot;
}

/** Thu thập theo yêu cầu, hai lớp khoá — trả `null` khi vòng khác vừa chạy. */
async function refreshOnDemand(env) {
  const kv = requireKv(env);
  const now = Date.now();
  if (now - lastOnDemandAttemptMs < ONDEMAND_LOCK_SECONDS * 1000) return null;
  // Đặt mốc TRƯỚC khi gọi nguồn, không phải sau: các lượt truy cập đến trong
  // lúc vòng thu thập đang chạy cũng phải bị chặn, chứ không chỉ các lượt đến
  // sau khi nó xong.
  lastOnDemandAttemptMs = now;
  if (await kv.get(LOCK_KEY)) return null;
  await kv.put(LOCK_KEY, "1", { expirationTtl: ONDEMAND_LOCK_SECONDS });
  // Ép chạy: tới nhánh này thì KV chắc chắn chưa có ảnh chụp, nên chốt
  // "đã xong" bên trong `refresh` không có gì để so và sẽ luôn cho qua —
  // nhưng nói rõ ý định vẫn hơn để nó phụ thuộc vào điều đó.
  return await refresh(env, { force: true });
}

export default {
  // Cron của nền tảng gọi vào đây. Đây là toàn bộ phần "tự chạy đúng giờ".
  async scheduled(_event, env, ctx) {
    // Nuốt lỗi CÓ CHỦ Ý: một lượt cron hỏng không được làm hỏng lượt sau, và
    // trong khung quay số lượt sau chỉ cách một phút. Vẫn ghi log để `wrangler
    // tail` thấy được.
    ctx.waitUntil(refresh(env).catch((error) => {
      console.error("lượt thu thập theo lịch hỏng:", error?.message || error);
    }));
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);

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
      const parsed = stored ? JSON.parse(stored) : null;
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

    // Chưa có ảnh chụp nào: thu thập ngay thay vì trả rỗng. Xảy ra ở lần gọi
    // đầu sau khi triển khai, hoặc khi KV vừa hết hạn.
    const snapshot = await refreshOnDemand(env);
    if (snapshot === null) {
      // Một vòng khác vừa chạy trong 10 giây qua. Trả trạng thái chờ thay vì
      // gọi nguồn lần nữa; trang sẽ tự thăm dò lại sau vài giây.
      return jsonResponse({ schema_version: 2, status: "waiting" },
        { cacheControl: "public, max-age=3" });
    }
    return jsonResponse(snapshot, {
      cacheControl: `public, max-age=${cacheSeconds(snapshot.status)}`,
    });
  },
};
