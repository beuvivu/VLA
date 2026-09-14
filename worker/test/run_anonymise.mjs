// Chạy anonymiseSnapshot của bản JS để `tests/test_source_privacy.py` so với Python.
import { readFileSync } from "node:fs";
import { anonymiseSnapshot } from "../src/snapshot.js";

const payload = JSON.parse(readFileSync(process.argv[2], "utf8"));
process.stdout.write(JSON.stringify(anonymiseSnapshot(payload), null, 2));
