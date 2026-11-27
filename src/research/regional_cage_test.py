from __future__ import annotations

import argparse
import csv
import io
import json
import math
from datetime import date
from pathlib import Path

import numpy as np

from core.atomic_io import atomic_write_text
from core.paths import REPO_ROOT
from core.regional_domain import CAGE_OF_DIGIT, REGIONS
from stats import regional_stats
from stats.regional_stats import StationHistory, cage_table, load_stations

VERSION = 1
SCHEMA_VERSION = 1
ALPHA = 0.01
PRIOR_STRENGTH = 50.0
TRIGGER_TEST = "cage_uniformity"
REGISTRY = Path("research") / "hypotheses" / "regional_cage_bias.json"
LEDGER = Path("research") / "hypotheses" / "regional_cage_bias.csv"
FIELDS = ["id", "date", "log_e", "log_e_total", "draws"]
_LAW_DECIMALS = 12
_CAGES = np.array(CAGE_OF_DIGIT)


def frozen_law(station: StationHistory) -> list[list[float]]:
    counts = cage_table(station.digits).astype(float)
    law = (counts + PRIOR_STRENGTH / 10.0) / (counts.sum(axis=1, keepdims=True) + PRIOR_STRENGTH)
    return [[round(float(value), _LAW_DECIMALS) for value in row] for row in law]


def log_evidence(law: list[list[float]], digits: np.ndarray) -> float:
    table = np.asarray(law, dtype=float)
    return float(np.log(table[_CAGES, np.asarray(digits, dtype=np.int64)] * 10.0).sum())


def _read_registry(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "version": VERSION, "alpha": ALPHA, "registrations": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_ledger(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _flagged(summary: dict) -> dict[str, dict]:
    out = {}
    for block in summary.get("tests", {}).get("per_station", []):
        for test in block["tests"]:
            if test["test"] == TRIGGER_TEST and test["q_value"] < regional_stats.ALPHA:
                out[block["province"]] = test
    return out


def register(registry: dict, summaries: dict[str, dict], stations: dict[str, list[StationHistory]]) -> list[dict]:
    held = {(r["region"], r["province"]) for r in registry["registrations"]}
    family = sum(len(summary.get("tests", {}).get("per_station", [])) for summary in summaries.values())
    added = []
    for region in sorted(summaries):
        summary = summaries[region]
        by_name = {s.province: s for s in stations.get(region, [])}
        latest = max((s.dates[-1] for s in by_name.values()), default=None)
        if summary.get("data_through") != latest:
            continue
        for province, test in sorted(_flagged(summary).items()):
            if (region, province) in held or province not in by_name:
                continue
            station = by_name[province]
            entry = {
                "id": f"{region}:{province}:{station.dates[-1]}",
                "version": VERSION,
                "region": region,
                "province": province,
                "registered_through": station.dates[-1],
                "draws_used": len(station),
                "cage_counts": cage_table(station.digits).tolist(),
                "law": frozen_law(station),
                "prior_strength": PRIOR_STRENGTH,
                "alpha": ALPHA,
                "family": family,
                "threshold": family / ALPHA,
                "trigger": {key: test[key] for key in ("p_value", "q_value", "p_asymptotic") if key in test},
            }
            registry["registrations"].append(entry)
            added.append(entry)
    return added


def score(registry: dict, ledger: list[dict[str, str]], stations: dict[str, list[StationHistory]]) -> list[dict]:
    new_rows = []
    for entry in registry["registrations"]:
        own = [row for row in ledger if row["id"] == entry["id"]]
        total = float(own[-1]["log_e_total"]) if own else 0.0
        seen = {row["date"] for row in own}
        last_scored = max(seen, default=entry["registered_through"])
        station = next((s for s in stations.get(entry["region"], []) if s.province == entry["province"]), None)
        if station is None:
            continue
        for index, day in enumerate(station.dates):
            if day <= last_scored:
                continue
            step = log_evidence(entry["law"], station.digits[index])
            total += step
            row = {"id": entry["id"], "date": day, "log_e": f"{step:.10f}", "log_e_total": f"{total:.10f}",
                   "draws": str(len(own) + 1)}
            own.append(row)
            ledger.append(row)
            new_rows.append(row)
            last_scored = day
    return new_rows


def status(registry: dict, ledger: list[dict[str, str]]) -> list[dict]:
    out = []
    for entry in registry["registrations"]:
        own = [row for row in ledger if row["id"] == entry["id"]]
        totals = [float(row["log_e_total"]) for row in own]
        threshold = math.log(entry["threshold"])
        crossed = next((row["date"] for row, value in zip(own, totals, strict=True) if value >= threshold), None)
        out.append({
            "id": entry["id"],
            "region": entry["region"],
            "province": entry["province"],
            "registered_through": entry["registered_through"],
            "draws_scored": len(own),
            "last_scored": own[-1]["date"] if own else None,
            "log10_e": round(totals[-1] / math.log(10), 6) if totals else 0.0,
            "log10_e_max": round(max(totals) / math.log(10), 6) if totals else 0.0,
            "log10_threshold": round(threshold / math.log(10), 6),
            "confirmed": crossed is not None,
            "confirmed_on": crossed,
        })
    return out


def _vn_date(day: str) -> str:
    return date.fromisoformat(day).strftime("%d/%m/%Y")


def _vn(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def reading(row: dict) -> str:
    head = f"Đài {row['province']}: giả thuyết đóng băng theo các kỳ đến {_vn_date(row['registered_through'])}"
    if not row["draws_scored"]:
        return f"{head}; chưa có kỳ mới nào để chấm."
    evidence = (f"bằng chứng 10^{_vn(row['log10_e'])} sau {row['draws_scored']} kỳ mới "
                f"(ngưỡng 10^{_vn(row['log10_threshold'])})")
    if row["confirmed"]:
        return (f"{head}; ĐÃ XÁC NHẬN ngày {_vn_date(row['confirmed_on'])}: kết quả ghi được lệch khỏi phân bố "
                f"đều trên các kỳ sau đăng ký ({evidence}).")
    if row["log10_e"] < 0:
        return f"{head}; các kỳ mới KHÔNG ủng hộ độ lệch đã thấy ({evidence})."
    return f"{head}; chưa đủ bằng chứng ({evidence})."


def run(repo_root: Path) -> tuple[Path, Path]:
    data = repo_root / "data"
    summaries, stations = {}, {}
    for region in REGIONS:
        summary_path = data / regional_stats.OUT_DIR / f"summary_{region}.json"
        if summary_path.exists():
            summaries[region] = json.loads(summary_path.read_text(encoding="utf-8"))
        stations[region] = load_stations(data / "regions" / f"xs{region}.csv", region)
    registry_path, ledger_path = data / REGISTRY, data / LEDGER
    registry = _read_registry(registry_path)
    ledger = _read_ledger(ledger_path)
    register(registry, summaries, stations)
    new_rows = score(registry, ledger, stations)
    rows = status(registry, ledger)
    for row in rows:
        row["reading"] = reading(row)
    registry["status"] = rows
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing = ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else ""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    if not existing:
        writer.writeheader()
    writer.writerows(new_rows)
    if buffer.getvalue():
        atomic_write_text(ledger_path, existing + buffer.getvalue())
    atomic_write_text(registry_path, json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    return registry_path, ledger_path


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Phép kiểm tiến cứu độ lệch chữ số theo lồng của đài XSMT/XSMN").parse_args(argv)
    for path in run(REPO_ROOT):
        print("Wrote:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
