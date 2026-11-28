from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.atomic_io import atomic_write_text
from core.xsmb_domain import PRIZE_FIELDS
from evaluation.prediction_board import OUT as BOARD_DIR
from stats.statistical_corrections import holm

LOGGER = logging.getLogger(__name__)

VERSION = 1
OUT = Path("evaluation") / "board_record" / "record.json"
SIMULATIONS = 20_000
REPLICATES = 20_000
SEED = 20261104
ALPHA = 0.05
DRAWS_PER_DAY = 27
PRIZE_COLUMNS = list(PRIZE_FIELDS)


def item_hits(rule: dict, counts: np.ndarray, special: np.ndarray) -> np.ndarray:
    on = rule["on"]
    if on == "loto":
        numbers = sorted({int(n) for n in rule["numbers"]})
        chosen = counts[:, numbers]
        if rule.get("all"):
            return (chosen > 0).all(axis=1)
        return chosen.sum(axis=1) >= int(rule["need"])
    if on == "special":
        return np.isin(special, sorted({int(n) for n in rule["numbers"]}))
    if on == "special_digit":
        digits = sorted({int(g) for g in rule["digits"]})
        return np.isin(special // 10, digits) | np.isin(special % 10, digits)
    raise ValueError(f"luật không rõ: {rule!r}")


def list_hits(items: list[dict], counts: np.ndarray, special: np.ndarray) -> np.ndarray:
    total = np.zeros(len(special), dtype=np.int32)
    for item in items:
        total += item_hits(item["rule"], counts, special)
    return total


def outcome(values: list[str]) -> tuple[np.ndarray, np.ndarray]:
    tails = np.array([int(v) % 100 for v in values], dtype=np.int64)
    counts = np.bincount(tails, minlength=100).reshape(1, 100)
    return counts, tails[:1]


def fair_draws(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
    tails = rng.integers(0, 100, size=(n, DRAWS_PER_DAY))
    counts = np.zeros((n, 100), dtype=np.int16)
    rows = np.repeat(np.arange(n), DRAWS_PER_DAY)
    np.add.at(counts, (rows, tails.ravel()), 1)
    return counts, tails[:, 0]


def complete_draws(data_dir: Path) -> dict[str, list[str]]:
    frame = pd.read_csv(data_dir / "xsmb.csv", dtype=str)
    frame = frame.dropna(subset=PRIZE_COLUMNS)
    return {str(row["date"])[:10]: [str(row[c]).strip() for c in PRIZE_COLUMNS] for _, row in frame.iterrows()}


def scored_boards(data_dir: Path, draws: dict[str, list[str]]) -> list[dict]:
    boards = []
    for path in sorted((data_dir / BOARD_DIR).glob("????-??-??.json")):
        if path.stem in draws:
            boards.append(json.loads(path.read_text(encoding="utf-8")))
    return boards


def _tail_p(null: np.ndarray, observed: float) -> tuple[float, float]:
    n = len(null)
    return (1 + int((null >= observed).sum())) / (n + 1), (1 + int((null <= observed).sum())) / (n + 1)


def _verdict(p_adjusted: float, hits: int, expected: float) -> str:
    if p_adjusted >= ALPHA:
        return "chưa khác chọn bừa"
    return "trúng nhiều hơn chọn bừa" if hits > expected else "trúng ít hơn chọn bừa"


def _round(value: float) -> float:
    return float(round(value, 6))


def build_record(boards: list[dict], draws: dict[str, list[str]], *, simulations: int = SIMULATIONS,
                 replicates: int = REPLICATES, seed: int = SEED) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    sim_counts, sim_special = fair_draws(rng, simulations)

    lists: dict[str, dict[str, Any]] = {}
    sims: dict[str, list[np.ndarray]] = {}
    family_sims: list[np.ndarray] = []
    family_observed = 0
    family_expected = 0.0
    for board in boards:
        target = board["target_date"]
        counts, special = outcome(draws[target])
        day_family = np.zeros(simulations, dtype=np.int64)
        for entry in board["lists"]:
            items = entry["items"]
            if not items:
                continue
            seen = lists.setdefault(entry["id"], {
                "id": entry["id"], "title": entry["title"], "group": entry.get("group", ""),
                "page": entry.get("page", ""), "draws": 0, "items": 0, "hits": 0,
                "expected": 0.0, "expected_published": 0.0, "published_items": 0,
                "days_hit": 0, "days_expected": 0.0,
            })
            seen["title"] = entry["title"]
            observed = int(list_hits(items, counts, special)[0])
            simulated = list_hits(items, sim_counts, sim_special)
            base = sum(float(item["base"]) for item in items)
            published = [float(item["prob"]) for item in items if item.get("prob") is not None]
            seen["draws"] += 1
            seen["items"] += len(items)
            seen["hits"] += observed
            seen["expected"] += base
            seen["expected_published"] += sum(published) + sum(
                float(item["base"]) for item in items if item.get("prob") is None)
            seen["published_items"] += len(published)
            seen["days_hit"] += int(observed > 0)
            seen["days_expected"] += float((simulated > 0).mean())
            sims.setdefault(entry["id"], []).append(simulated)
            day_family += simulated
            family_observed += observed
            family_expected += base
        family_sims.append(day_family)

    def null_total(per_draw: list[np.ndarray]) -> np.ndarray:
        picks = rng.integers(0, simulations, size=(replicates, len(per_draw)))
        return np.stack([per_draw[d][picks[:, d]] for d in range(len(per_draw))], axis=1).sum(axis=1)

    rows = list(lists.values())
    for row in rows:
        high, low = _tail_p(null_total(sims[row["id"]]), row["hits"])
        row["p_high"], row["p_low"] = high, low
        row["p"] = _round(min(1.0, 2 * min(high, low)))
    for row, adjusted in zip(rows, holm([row["p"] for row in rows]), strict=True):
        row["p_holm"] = adjusted
        row["verdict"] = _verdict(adjusted, row["hits"], row["expected"])
        for key in ("expected", "expected_published", "days_expected", "p_high", "p_low", "p_holm"):
            row[key] = _round(row[key])

    family: dict[str, Any] = {"lists": len(rows), "hits": family_observed, "expected": _round(family_expected)}
    if family_sims:
        high, low = _tail_p(null_total(family_sims), family_observed)
        p = min(1.0, 2 * min(high, low))
        family.update(p=_round(p), verdict=_verdict(p, family_observed, family_expected))

    dates = [board["target_date"] for board in boards]
    return {
        "version": VERSION,
        "draws": len(dates),
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
        "method": {"unit": "kỳ", "null": "kỳ quay công bằng mô phỏng", "simulations": simulations,
                   "replicates": replicates, "seed": seed, "alpha": ALPHA, "adjust": "Holm"},
        "family": family,
        "lists": rows,
    }


def write_record(data_dir: Path) -> Path:
    draws = complete_draws(data_dir)
    record = build_record(scored_boards(data_dir, draws), draws)
    out = data_dir / OUT
    atomic_write_text(out, json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    out = write_record(args.data_dir)
    record = json.loads(out.read_text(encoding="utf-8"))
    print(f"[OK] thành tích {record['draws']} kỳ, {len(record['lists'])} danh sách -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
