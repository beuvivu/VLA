from __future__ import annotations

import csv
import io
from pathlib import Path

import pandas as pd

from soi_cau import digit_sum_rules as dsr
from core.atomic_io import atomic_write_text

REGISTERED_ON = "2026-10-05"
FIRST_TARGET = "2026-10-06"
MIN_DRAWS = 180
ALPHA = 0.01
LEDGER = Path("research") / "hypotheses" / "digit_sum_rules.csv"
FIELDS = ["date", "rule", "base_date", "picks", "hit", "chance"]

RETROSPECTIVE = {
    "draws": 4225,
    "last_draw": "2026-10-05",
    "hit_rate": {"dau_db": 0.2054, "duoi_db": 0.1976, "dan_cham": 0.1806,
                 "lo_g5": 0.4005, "lo_vip": 0.3983},
    "expected_rate": {"dau_db": 0.2000, "duoi_db": 0.2000, "dan_cham": 0.1760,
                      "lo_g5": 0.4033, "lo_vip": 0.4025},
    "min_p_holm": 0.966,
}


def scored_draws(raw: pd.DataFrame) -> list[dict]:
    raw = raw.sort_values("date", kind="stable").reset_index(drop=True)
    rows = []
    for t in range(1, len(raw)):
        day = str(raw["date"].iloc[t])[:10]
        if day < FIRST_TARGET:
            continue
        base, today = raw.iloc[t - 1], raw.iloc[t]
        for rule in dsr.RULES:
            picks = rule.make(base)
            hit, chance = dsr.hit_and_chance(rule, picks, today)
            width = 1 if rule.target in ("dau_db", "duoi_db") else 2
            rows.append({
                "date": day,
                "rule": rule.key,
                "base_date": str(base["date"])[:10],
                "picks": " ".join(f"{n:0{width}d}" for n in picks),
                "hit": int(hit),
                "chance": repr(float(chance)),
            })
    return rows


def update_ledger(data_dir: Path) -> Path:
    path = data_dir / LEDGER
    known: dict[tuple[str, str], dict] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            known = {(row["date"], row["rule"]): row for row in csv.DictReader(fh)}
    raw = pd.read_csv(data_dir / "xsmb.csv", dtype={"date": str})
    for row in scored_draws(raw):
        known.setdefault((row["date"], row["rule"]), row)
    order = {rule.key: i for i, rule in enumerate(dsr.RULES)}
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for key in sorted(known, key=lambda k: (k[0], order.get(k[1], 99))):
        writer.writerow({field: known[key][field] for field in FIELDS})
    atomic_write_text(path, buffer.getvalue())
    return path


def evaluate(data_dir: Path) -> dict:
    path = data_dir / LEDGER
    ledger = (
        pd.read_csv(path, dtype={"date": str, "picks": str}) if path.exists()
        else pd.DataFrame(columns=FIELDS)
    )
    dates = sorted(ledger["date"].unique()) if len(ledger) else []
    frozen = set(dates[:MIN_DRAWS])
    rules = []
    for rule in dsr.RULES:
        part = ledger[(ledger["rule"] == rule.key) & ledger["date"].isin(frozen)]
        n = len(part)
        chances = part["chance"].astype(float).tolist()
        hits = int(part["hit"].astype(int).sum()) if n else 0
        rules.append({"rule": rule.key, "label": rule.label, "formula": rule.formula,
                      "draws": n, **dsr.verdict(n, hits, chances)})
    dsr.with_holm(rules)
    draws = min((r["draws"] for r in rules), default=0)
    for r in rules:
        if draws < MIN_DRAWS:
            r["state"] = "dang_thu"
        elif r["p_holm"] <= ALPHA:
            r["state"] = "xac_nhan"
        else:
            r["state"] = "bac_bo"
    states = {r["state"] for r in rules}
    state = ("dang_thu" if "dang_thu" in states
             else "xac_nhan" if "xac_nhan" in states else "bac_bo")
    raw_path = data_dir / "xsmb.csv"
    upcoming = dsr.next_picks(pd.read_csv(raw_path, dtype={"date": str})) if raw_path.exists() else None
    return {
        "registered_on": REGISTERED_ON, "first_target": FIRST_TARGET,
        "min_draws": MIN_DRAWS, "alpha": ALPHA,
        "draws": draws, "recorded": len(dates),
        "first": dates[0] if dates else None,
        "last": dates[min(len(dates), MIN_DRAWS) - 1] if dates else None,
        "rules": rules, "state": state, "next": upcoming,
        "retrospective": RETROSPECTIVE,
    }
