function stripAnsi(text) {
  // eslint-disable-next-line no-control-regex
  return String(text).replace(/\u001b\[[0-9;]*[A-Za-z]/g, "");
}

export function extractKvId(output) {
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

export function patchWranglerKvId(toml, id) {
  if (!/^[0-9a-f]{32}$/i.test(id)) {
    throw new Error(`id kho KV không hợp lệ: ${id}`);
  }
  const text = String(toml);
  if (text.includes(KV_PLACEHOLDER)) {
    return text.replace(KV_PLACEHOLDER, id);
  }
  const line = /(\[\[kv_namespaces\]\][\s\S]{0,200}?\bid\s*=\s*")([^"]*)(")/;
  if (!line.test(text)) {
    throw new Error("không tìm thấy khối [[kv_namespaces]] trong wrangler.toml");
  }
  return text.replace(line, `$1${id}$3`);
}

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

const ASSIGNMENT_LINE = () =>
  /^(?![ \t]*\/\/)([ \t]*window\.LIVE_WORKER_URL\s*=\s*')([^']*)(';)/m;

export function currentLiveWorkerUrl(html) {
  const match = String(html).match(ASSIGNMENT_LINE());
  return match ? match[2] : null;
}
