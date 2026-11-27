from __future__ import annotations

import csv
import io
import math
from pathlib import Path

import numpy as np
import pandas as pd

from core.xsmb_domain import PRIZE_FIELDS

from core.atomic_io import atomic_write_text

REGISTERED_ON = "2026-09-28"
FIRST_TARGET = "2026-09-29"
WINDOW = 7
MIN_DRAWS = 180
ALPHA = 0.01
Z_CRITICAL = 2.326
LEDGER = Path("research") / "hypotheses" / "hot_tail.csv"
FIELDS = ["date", "hot_tails", "hot_rate", "all_rate", "diff"]

RETROSPECTIVE = {
    "draws": 4212,
    "last_draw": "2026-09-28",
    "effect_pp": 0.456,
    "z": 2.43,
    "p_two_sided_mc": 0.011,
    "control_head_effect_pp": 0.135,
    "control_head_p": 0.475,
}

PRIZES = list(PRIZE_FIELDS)


def _hits(draws: np.ndarray) -> np.ndarray:
    hits = np.zeros((len(draws), 100), dtype=np.int32)
    hits[np.arange(len(draws))[:, None], draws] = 1
    return hits


def score_draw(history: np.ndarray, today: np.ndarray) -> dict:
    past = _hits(history[-WINDOW:]).sum(axis=0)
    per_tail = past.reshape(10, 10).sum(axis=0)
    hot = np.flatnonzero(per_tail == per_tail.max())
    hit = np.zeros(100, dtype=int)
    hit[today] = 1
    rate = hit.reshape(10, 10).mean(axis=0)
    hot_rate = float(rate[hot].mean())
    all_rate = float(rate.mean())
    return {"hot_tails": "".join(str(int(t)) for t in hot), "hot_rate": hot_rate,
            "all_rate": all_rate, "diff": hot_rate - all_rate}


def scored_draws(frame: pd.DataFrame) -> list[dict]:
    frame = frame.sort_values("date", kind="stable").reset_index(drop=True)
    draws = frame[PRIZES].to_numpy().astype(int)
    rows = []
    for t in range(WINDOW, len(frame)):
        day = str(frame["date"].iloc[t])[:10]
        if day < FIRST_TARGET:
            continue
        rows.append({"date": day, **score_draw(draws[t - WINDOW : t], draws[t])})
    return rows


def update_ledger(data_dir: Path) -> Path:
    path = data_dir / LEDGER
    known: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            known = {row["date"]: row for row in csv.DictReader(fh)}
    frame = pd.read_csv(data_dir / "xsmb-2-digits.csv", dtype={"date": str})
    for row in scored_draws(frame):
        known.setdefault(row["date"], {k: row[k] for k in FIELDS})
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for day in sorted(known):
        writer.writerow({k: known[day][k] for k in FIELDS})
    atomic_write_text(path, buffer.getvalue())
    return path


def evaluate(data_dir: Path) -> dict:
    path = data_dir / LEDGER
    diffs = []
    first = last = None
    if path.exists():
        ledger = pd.read_csv(path, dtype={"date": str, "hot_tails": str})
        diffs = ledger["diff"].astype(float).tolist()
        if len(ledger):
            first, last = str(ledger["date"].iloc[0]), str(ledger["date"].iloc[-1])
    n = len(diffs)
    mean = float(np.mean(diffs)) if n else 0.0
    se = float(np.std(diffs, ddof=1) / math.sqrt(n)) if n > 1 else 0.0
    z = mean / se if se > 0 else 0.0
    if n < MIN_DRAWS:
        state = "dang_thu"
    elif z >= Z_CRITICAL:
        state = "xac_nhan"
    else:
        state = "bac_bo"
    return {
        "registered_on": REGISTERED_ON, "first_target": FIRST_TARGET, "window": WINDOW,
        "min_draws": MIN_DRAWS, "alpha": ALPHA, "z_critical": Z_CRITICAL,
        "draws": n, "first": first, "last": last,
        "mean_diff": mean, "stderr": se, "z": z, "state": state,
        "retrospective": RETROSPECTIVE,
    }
