// In danh mục nguồn của bản JS để `tests/test_worker_sources_parity.py` so.
import { SOURCES } from "../src/sources.js";

const [year, month, day] = process.argv[2].split("-").map(Number);
const d = { year, month, day };
process.stdout.write(JSON.stringify(
  SOURCES.map((s) => ({
    name: s.name,
    date_url: s.dateUrl(d),
    live_url: s.liveUrl(d),
    has_select_section: typeof s.selectSection === "function",
  })),
  null, 2,
));
