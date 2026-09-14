// Các phép biến đổi chuỗi mà bộ cài đặt cần, tách riêng để KIỂM ĐƯỢC.
//
// Đây là chỗ duy nhất trong bộ cài đặt có thể hỏng âm thầm: nếu một biểu thức
// không khớp, kịch bản vẫn "chạy xong" nhưng tệp không được sửa, và người
// dùng chỉ phát hiện lúc 18:15 hôm sau khi trang không có gì. Vì thế mọi hàm
// ở đây đều NÉM LỖI khi không khớp, chứ không trả lại nguyên bản.

/**
 * Gỡ mã màu ANSI trước khi khớp.
 *
 * Wrangler đôi khi giữ màu cả khi đầu ra bị chuyển hướng, và khi ấy chuỗi
 * `id = "..."` thật ra là `\x1b[32mid\x1b[0m = "..."` — biểu thức tìm `id`
 * liền `=` sẽ trượt. Phép kiểm bắt được đúng ca này.
 */
function stripAnsi(text) {
  // eslint-disable-next-line no-control-regex
  return String(text).replace(/\u001b\[[0-9;]*[A-Za-z]/g, "");
}

/** Bóc id kho KV từ đầu ra của `wrangler kv namespace create`. */
export function extractKvId(output) {
  // Wrangler đổi cách in giữa các bản: khi thì khối TOML, khi thì JSON. Bắt cả
  // hai bằng cách tìm khoá `id` đi kèm một chuỗi 32 ký tự hex.
  const match = stripAnsi(output).match(
    /(?:"?id"?\s*[:=]\s*)["']([0-9a-f]{32})["']/i,
  );
  if (!match) {
    throw new Error(
      "không tìm thấy id kho KV trong đầu ra của wrangler.\n"
      + "Đầu ra thật:\n" + String(output).trim(),
    );
  }
  return match[1];
}

/** Bóc địa chỉ Worker từ đầu ra của `wrangler deploy`. */
export function extractWorkerUrl(output) {
  const match = stripAnsi(output).match(
    /https:\/\/[a-z0-9][a-z0-9.-]*\.workers\.dev/i,
  );
  if (!match) {
    throw new Error(
      "không tìm thấy địa chỉ *.workers.dev trong đầu ra của wrangler.\n"
      + "Đầu ra thật:\n" + String(output).trim(),
    );
  }
  return match[0];
}

const KV_PLACEHOLDER = "THAY_BANG_ID_KV_CUA_BAN";

/** Điền id kho KV vào wrangler.toml. Chạy lại nhiều lần vẫn ra cùng kết quả. */
export function patchWranglerKvId(toml, id) {
  if (!/^[0-9a-f]{32}$/i.test(id)) {
    throw new Error(`id kho KV không hợp lệ: ${id}`);
  }
  const text = String(toml);
  if (text.includes(KV_PLACEHOLDER)) {
    return text.replace(KV_PLACEHOLDER, id);
  }
  // Đã điền rồi: thay id cũ, để chạy lại kịch bản không sinh mục trùng.
  const line = /(\[\[kv_namespaces\]\][\s\S]{0,200}?\bid\s*=\s*")([^"]*)(")/;
  if (!line.test(text)) {
    throw new Error("không tìm thấy khối [[kv_namespaces]] trong wrangler.toml");
  }
  return text.replace(line, `$1${id}$3`);
}

/** Điền địa chỉ Worker vào docs/live.html. */
export function patchLiveWorkerUrl(html, url) {
  if (!/^https:\/\/\S+$/.test(url)) {
    throw new Error(`địa chỉ Worker không hợp lệ: ${url}`);
  }
  const target = url.replace(/\/+$/, "") + "/live.json";
  const line = ASSIGNMENT_LINE();
  if (!line.test(String(html))) {
    throw new Error(
      "không tìm thấy dòng gán window.LIVE_WORKER_URL trong docs/live.html",
    );
  }
  return String(html).replace(ASSIGNMENT_LINE(), `$1${target}$3`);
}

const RESULTS_API_ASSIGNMENT_LINE = () => (
  /^(?![ \t]*\/\/)([ \t]*window\.VLA_RESULTS_API_URL\s*=\s*')([^']*)(';)/m
);

/** Điền endpoint Sổ kết quả của cùng Worker vào trang tra cứu. */
export function patchTraditionalResultsApiUrl(html, url) {
  if (!/^https:\/\/\S+$/.test(url)) {
    throw new Error(`địa chỉ Worker không hợp lệ: ${url}`);
  }
  if (!RESULTS_API_ASSIGNMENT_LINE().test(String(html))) {
    throw new Error(
      "không tìm thấy dòng gán window.VLA_RESULTS_API_URL trong "
      + "docs/so-ket-qua-truyen-thong.html",
    );
  }
  const target = url.replace(/\/+$/, "") + "/api/v1/traditional-results";
  return String(html).replace(RESULTS_API_ASSIGNMENT_LINE(), `$1${target}$3`);
}

/** Đọc endpoint Sổ kết quả hiện tại, hoặc chuỗi rỗng khi chưa cấu hình. */
export function currentTraditionalResultsApiUrl(html) {
  const match = RESULTS_API_ASSIGNMENT_LINE().exec(String(html));
  if (!match) {
    throw new Error(
      "không tìm thấy dòng gán window.VLA_RESULTS_API_URL trong "
      + "docs/so-ket-qua-truyen-thong.html",
    );
  }
  return match[2];
}

/**
 * Dòng GÁN thật, không phải dòng chú thích ví dụ.
 *
 * `docs/live.html` có hai dòng chứa `window.LIVE_WORKER_URL`: một dòng chú
 * thích chỉ cách điền, và dòng gán thật. Biểu thức đầu tôi viết không phân
 * biệt, nên nó vá vào CHÚ THÍCH và để nguyên dòng gán — kịch bản báo "xong"
 * mà trang vẫn không trỏ đi đâu cả. Chốt `(?![ \t]*\/\/)` loại dòng chú thích.
 *
 * Trả về biểu thức mới mỗi lần gọi: biểu thức có cờ `g`/dùng lại dễ mang theo
 * `lastIndex` cũ, và đó là một nguồn lỗi khó thấy khác.
 */
const ASSIGNMENT_LINE = () =>
  /^(?![ \t]*\/\/)([ \t]*window\.LIVE_WORKER_URL\s*=\s*')([^']*)(';)/m;

/** Địa chỉ đã được điền chưa? Dùng để kịch bản biết có cần nhắc commit không. */
export function currentLiveWorkerUrl(html) {
  const match = String(html).match(ASSIGNMENT_LINE());
  return match ? match[2] : null;
}
