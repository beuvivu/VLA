// Chạy phần THUẦN của bản dựng payload trên bộ ca dùng chung.
import { readFileSync } from "node:fs";
import { buildSnapshot } from "../src/snapshot.js";

const cases = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const out = cases.map((c) => buildSnapshot({
  partials: c.partials,
  sourceStatus: c.source_status,
  nowUtcMs: Date.parse(c.now_utc),
  minAgreement: c.min_agreement,
}));
process.stdout.write(JSON.stringify(out, null, 2));
