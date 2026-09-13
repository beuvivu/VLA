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

import { collectSnapshot } from "./snapshot.js";

const KV_KEY = "live.json";

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

async function refresh(env) {
  const snapshot = await collectSnapshot({
    minAgreement: Number(env.MIN_AGREEMENT ?? 2),
  });
  await env.LIVE.put(KV_KEY, JSON.stringify(snapshot), {
    // Giữ qua đêm để trang mở lúc sáng vẫn thấy kỳ hôm trước thay vì trắng.
    expirationTtl: 60 * 60 * 36,
  });
  return snapshot;
}

export default {
  // Cron của nền tảng gọi vào đây. Đây là toàn bộ phần "tự chạy đúng giờ".
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(refresh(env));
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
      const stored = await env.LIVE.get(KV_KEY);
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

    const stored = await env.LIVE.get(KV_KEY);
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
    const snapshot = await refresh(env);
    return jsonResponse(snapshot, {
      cacheControl: `public, max-age=${cacheSeconds(snapshot.status)}`,
    });
  },
};
