// In quyết định chuyển nguồn của bản JS để `tests/worker/test_source_failover_parity.py` so.
import { readFileSync } from "node:fs";
import { primaryHasFailed } from "../src/snapshot.js";

const cases = JSON.parse(readFileSync(process.argv[2], "utf8"));
process.stdout.write(JSON.stringify(
  cases.map((c) => primaryHasFailed(c.prize_map, c.now_utc_ms)),
  null, 2,
));
