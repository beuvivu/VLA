"""Tái lập chẩn đoán oracle risk; không ghi hoặc sửa mã trong kho."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


NAMES = ("old", "new", "hand60", "fully_pooled", "oracle", "raw")


def fixture(seed: int, scenario: str):
    """Giữ nguyên đặc biệt để phép tiêm không đổi nhãn nguồn các kỳ sau."""
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, 100, size=(900, 27))
    truth = np.full((100, 100), 1 - 0.99**27)
    if scenario != "null":
        affected = np.flatnonzero(draws[:-1, 0] == 42) + 1
        if scenario == "source42_prefers_first20":
            draws[affected, 1:] = rng.integers(0, 20, size=(len(affected), 26))
            truth[42, :] = 0.01
            truth[42, :20] = 1 - 0.99 * 0.95**26
        elif scenario == "source42_forces17":
            draws[affected, 1] = 17
            truth[42, :] = 1 - 0.99**26
            truth[42, 17] = 1.0
        else:
            raise ValueError(scenario)
    hit = np.zeros((900, 100), dtype=bool)
    hit[np.arange(900)[:, None], draws] = True
    return draws, hit, truth


def metrics(seed: int, scenario: str, fit_rows):
    draws, hit, truth = fixture(seed, scenario)
    # Khớp 700 ngày tạo 699 cặp; chấm 199 cặp nguồn 700..898 → đích 701..899.
    sources = draws[:699, 0]
    trials = np.bincount(sources, minlength=100).astype(float)
    counts = np.zeros((100, 100))
    np.add.at(counts, sources, hit[1:700])
    base = hit[1:700].mean(axis=0)
    n = np.maximum(trials, 1)[:, None]
    excess = ((counts / n - base) ** 2).mean(axis=1) - (base * (1 - base) / n).mean(axis=1)
    # Công thức cũ: không có 1−1/n và dùng phương sai tại trung bình các tâm.
    old = np.where(
        excess > 0,
        np.clip(base.mean() * (1 - base.mean()) / np.maximum(excess, 1e-99) - 1, 1e-6, 1e6),
        1e6,
    )
    new = fit_rows(counts, n[:, 0], base)
    strengths = (old, new, np.full(100, 60.0), np.full(100, 1e6))
    grids = [(counts + k[:, None] * base) / (trials[:, None] + k[:, None]) for k in strengths]
    # Giữ fallback scalar của regression lịch sử để tái lập chính xác số đo.
    # Test hợp đồng mới dùng baseline riêng từng số cho nguồn chưa quan sát.
    for grid in grids:
        grid[trials == 0] = base.mean()
    raw = counts / n
    raw[trials == 0] = base.mean()
    grids += [truth, raw]
    return {
        "brier": [float(np.mean((g[draws[700:899, 0]] - hit[701:900]) ** 2)) for g in grids],
        # Phần oracle uncertainty là chung; so Brier kỳ vọng chỉ cần excess risk.
        "oracle_excess_risk": [float(np.mean((g - truth) ** 2)) for g in grids],
        "row42_oracle_excess_risk": [float(np.mean((g[42] - truth[42]) ** 2)) for g in grids],
        "row42_number17_probability": [float(g[42, 17]) for g in grids],
    }


def summarize(records):
    out = {}
    for name in records[0]:
        values = np.asarray([r[name] for r in records])
        comparisons = {}
        for comparator in ("old", "hand60", "fully_pooled", "raw"):
            delta = values[:, NAMES.index("new")] - values[:, NAMES.index(comparator)]
            comparisons["new_minus_" + comparator] = {
                "mean": float(delta.mean()),
                "standard_error": float(delta.std(ddof=1) / np.sqrt(len(delta)))
                if len(delta) > 1
                else None,
                "win_fraction": float(np.mean(delta < 0)),
                "quantiles_05_50_95": np.quantile(delta, [0.05, 0.5, 0.95]).tolist(),
            }
        out[name] = {
            "mean": dict(zip(NAMES, values.mean(axis=0).tolist(), strict=True)),
            "comparisons": comparisons,
        }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument("--scenarios", nargs="+", default=["null", "source42_prefers_first20"])
    args = parser.parse_args()
    if args.seeds <= 0:
        parser.error("--seeds phải lớn hơn 0")
    sys.path.insert(0, str(args.repo / "src"))
    from hierarchical_pooling import fit_shrinkage_to_prior_rows

    result = {
        "seeds": [0, args.seeds - 1],
        "training_days": 700,
        "training_pairs": 699,
        "total_days": 900,
        "holdout_pairs": 199,
        "model_order": NAMES,
        "scenarios": {},
    }
    result["unseen_source_fallback"] = "mean_training_marginal_scalar"
    result["fully_pooled_strength"] = 1000000.0
    for scenario in args.scenarios:
        records = [
            metrics(seed, scenario, fit_shrinkage_to_prior_rows) for seed in range(args.seeds)
        ]
        result["scenarios"][scenario] = {
            "summary": summarize(records),
            "first20_summary": summarize(records[:20]),
            "first20_values": records[:20],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
