// Chạy `collectSnapshot` trên bộ ca dùng chung, thay lượt gọi từng nguồn bằng bảng giải cho sẵn.
//
// Đi qua `collectSnapshot` chứ không gọi thẳng `buildSnapshot`: luật chuyển nguồn (nguồn chính
// hỏng thì chỉ hợp nhất dự phòng) nằm ở đó, và bản Python chạy luật ấy trong `fetch_snapshot`.
import { readFileSync } from "node:fs";
import { collectSnapshot, observation } from "../src/snapshot.js";

const cases = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const out = [];
for (const c of cases) {
  const maps = Object.fromEntries(c.partials);
  out.push(await collectSnapshot({
    nowUtcMs: Date.parse(c.now_utc),
    minAgreement: c.min_agreement,
    previous: c.previous,
    fetchSource: async (source, tier, priority) => {
      if (!(source.name in maps)) throw new Error(`ca không có nguồn ${source.name}`);
      return observation({ priority, tier, name: source.name, prizeMap: maps[source.name] });
    },
  }));
}
process.stdout.write(JSON.stringify(out, null, 2));
