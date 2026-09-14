// In quyết định chuyển nguồn của bản JS để `tests/test_source_failover_parity.py` so.
import { readFileSync } from "node:fs";
import { independentGroupCount, primaryTierIsSufficient } from "../src/snapshot.js";

const cases = JSON.parse(readFileSync(process.argv[2], "utf8"));
process.stdout.write(JSON.stringify(
  cases.map((c) => {
    const results = c.observations.map(([name, prizeMap]) => ({ name, prizeMap }));
    const verdict = primaryTierIsSufficient(results, c.min_agreement);
    return {
      groups: independentGroupCount(results),
      sufficient: verdict.sufficient,
      reason: verdict.reason,
    };
  }),
  null, 2,
));
