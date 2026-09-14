// Chạy các phép biến đổi của bộ cài đặt trên bộ ca dùng chung.
import { readFileSync } from "node:fs";
import {
  currentLiveWorkerUrl, extractKvId, extractWorkerUrl,
  patchLiveWorkerUrl, patchWranglerKvId,
} from "../setup/patch.mjs";

const cases = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const call = (fn, args) => {
  try { return { ok: true, value: fn(...args) }; }
  catch (error) { return { ok: false, error: String(error.message).split("\n")[0] }; }
};
const FNS = {
  extractKvId, extractWorkerUrl, patchWranglerKvId,
  patchLiveWorkerUrl, currentLiveWorkerUrl,
};
process.stdout.write(JSON.stringify(
  cases.map((c) => call(FNS[c.fn], c.args)), null, 2));
