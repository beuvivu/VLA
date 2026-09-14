// In danh mục nguồn của bản JS để `tests/test_worker_sources_parity.py` so.
import { SOURCES, SOURCE_PUBLIC_CODE } from "../src/sources.js";

const [year, month, day] = process.argv[2].split("-").map(Number);
const d = { year, month, day };
process.stdout.write(JSON.stringify(
  {
    sources: SOURCES.map((s) => ({
      name: s.name,
      tier: s.tier,
      date_urls: s.dateUrls(d),
      live_urls: s.liveUrls(d),
      has_select_section: typeof s.selectSection === "function",
    })),
    public_codes: SOURCE_PUBLIC_CODE,
  },
  null, 2,
));
