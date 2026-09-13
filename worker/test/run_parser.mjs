// Chạy bản phân tích JS trên bộ mẫu dùng chung rồi in JSON ra stdout.
// `tests/test_worker_parser_parity.py` gọi tệp này và so với bản Python.
import { readFileSync } from "node:fs";
import { extractPartialPrizeMap } from "../src/prize_map.js";

const corpus = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const out = {};
for (const [name, html] of Object.entries(corpus)) {
  out[name] = extractPartialPrizeMap(html);
}
process.stdout.write(JSON.stringify(out, null, 2));
