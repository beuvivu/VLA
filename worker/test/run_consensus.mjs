// Chạy bản đồng thuận JS trên bộ ca dùng chung rồi in JSON ra stdout.
import { readFileSync } from "node:fs";
import { sourceConsensusPartial } from "../src/consensus.js";

const cases = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const out = cases.map(({ partials, min_agreement }) => {
  const [merged, meta] = sourceConsensusPartial(partials, { minAgreement: min_agreement });
  return { merged, meta };
});
process.stdout.write(JSON.stringify(out, null, 2));
