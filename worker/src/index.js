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
// trong khung quay số; nó đọc nguồn, dựng live.json rồi cất vào KV.
// Trình duyệt đọc thẳng từ `fetch()` bên dưới.
//
// Hệ quả quan trọng: GitHub Actions không còn nằm trên đường găng ĐÚNG GIỜ.
// Nó vẫn ghi lịch sử vào kho, nhưng trễ bao nhiêu cũng không ảnh hưởng trang
// live nữa.

import { anonymiseSnapshot, collectSnapshot, drawDate } from "./snapshot.js";
import { handleTraditionalResults, refreshFallbackOverlay } from "./traditional_results.js";

const KV_KEY = "live.json";
// Lượt yêu cầu của người xem CHỈ ĐỌC KV, không bao giờ gọi nguồn.
//
// Trước 08-10-2026, KV rỗng thì lượt yêu cầu thu thập ngay, chặn bằng một khoá trong KV cộng
// một mốc trong bộ nhớ của isolate. KV nhất quán sau và không có đọc-ghi nguyên tử: lúc khởi
// động lạnh, các isolate ở nhiều nơi cùng đọc thấy khoá rỗng (kết quả "không có" còn được
// đệm tới 60 giây) và mỗi isolate tự chạy một vòng sáu nguồn. Cron là đường duy nhất gọi nguồn,
// nên lưu lượng khách không còn đường nào chạm tới trang nguồn. KV rỗng thì trả 503: trang
// live coi đó là lỗi và đọc live.json dự phòng trên nhánh `live`.

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
 * và đã xác minh, nó vẫn gọi nguồn thêm vài chục lần nữa mà không thêm
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

async function refresh(env) {
  const kv = requireKv(env);
  if (alreadySettled(await kv.get(KV_KEY), Date.now())) return;
  // Ẩn danh TRƯỚC khi ghi vào KV, không phải lúc trả lời. Mọi đường đọc đều
  // đi qua KV, nên ẩn ở đây là ẩn ở mọi nơi — kể cả những đường sẽ thêm về
  // sau. Chi tiết từng nguồn vẫn xem được bằng `wrangler tail`, không công khai.
  const snapshot = anonymiseSnapshot(await collectSnapshot({
    minAgreement: Number(env.MIN_AGREEMENT ?? 2),
  }));
  // Ghi hỏng (hết hạn mức, sự cố nền tảng) thì lỗi lên tới `scheduled()`, được ghi log, và
  // lượt cron sau — chỉ cách một phút — thử lại.
  await kv.put(KV_KEY, JSON.stringify(snapshot), {
    // Giữ qua đêm để trang mở lúc sáng vẫn thấy kỳ hôm trước thay vì trắng.
    expirationTtl: 60 * 60 * 36,
  });
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
    // Lớp bù của API Sổ kết quả chỉ được nạp ở ĐÂY, không bao giờ trong lượt yêu cầu: lưu
    // lượng khách vì thế không chạm được tới nguồn dự phòng. Bật bằng biến trong wrangler.toml.
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

    // Chưa có ảnh chụp: lần đầu sau khi triển khai (cho tới lượt cron đầu trong khung quay số)
    // hoặc khi cron hỏng quá 36 giờ. Trả JSON có CORS để trang đọc được mã lỗi và chuyển
    // sang nguồn kế tiếp.
    return jsonResponse({ schema_version: 2, status: "waiting" }, { status: 503 });
  },
};
