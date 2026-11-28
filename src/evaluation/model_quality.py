from __future__ import annotations


import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ensemble.ensemble_components import (
    COMPONENT_KEYS,
    availability_from_history_day,
    published_with_level_anchor,
)
from ensemble.ensemble_utils import (
    EnsembleWeights,
    finalize_blend,
    load_ensemble_weights,
)
from core.xsmb_domain import LOTO_DRAWS_PER_DAY, baseline_rate
from evaluation.forecast_metrics import (
    auc_by_draw,
    by_period,
    calibration_error,
    chance_reciprocal_rank,
    cluster_bootstrap_ci,
    rank_of_truth,
    within_draw_permutation_p,
)
from evaluation.skill_monitor import MIN_DAYS, graded_series, published_evaluation, update_ledger
from evaluation.skill_monitor import evaluate as evaluate_skill

SCHEMA_VERSION = 2

CALIBRATION_BINS = 10

MODES: tuple[str, ...] = ("loto", "de")


def normalize_brier_scale(history: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = history.copy()
    converted = 0
    for column in ("brier", "baseline_brier", "logloss"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")

    is_de = out["mode"].astype(str) == "de"
    winner = np.exp(-out["logloss"].to_numpy(dtype=float))
    lower_bound = (1.0 - winner) ** 2
    stale = is_de.to_numpy() & np.isfinite(lower_bound) & (
        out["brier"].to_numpy(dtype=float) < lower_bound * (1.0 - 1e-6)
    )
    if stale.any():
        out.loc[stale, "brier"] = out.loc[stale, "brier"] * 100.0
        if "baseline_brier" in out.columns:
            baseline = out.loc[stale, "baseline_brier"]
            out.loc[stale, "baseline_brier"] = baseline * 100.0
        converted = int(stale.sum())
    return out, converted


def ensemble_probabilities(history: pd.DataFrame, weights: EnsembleWeights, mode: str):
    columns = {"ml": "p_ml", "cau": "p_cau", "stat": "p_stat",
               "active": "p_active", "stable": "p_stable"}
    raw = np.array([getattr(weights, f"w_{key}") for key in COMPONENT_KEYS], dtype=float)
    days, probs, labels = [], [], []

    for day, group in history.groupby("target_date", sort=True):
        sub = group.sort_values("number", kind="stable")
        if len(sub) != 100 or sub["y"].isna().any():
            continue
        available = availability_from_history_day(sub, mode=mode)
        vectors, mask = [], []
        for index, key in enumerate(COMPONENT_KEYS):
            values = pd.to_numeric(sub[columns[key]], errors="coerce").to_numpy(dtype=float)
            usable = bool(available.get(key, False)) and raw[index] > 0.0
            vectors.append(np.nan_to_num(values))
            mask.append(1.0 if usable else 0.0)
        effective = raw * np.asarray(mask)
        if effective.sum() <= 0.0:
            continue
        effective /= effective.sum()
        blend = sum(w * v for w, v in zip(effective, vectors, strict=True))
        blend = finalize_blend(blend, mode, anchor_loto=published_with_level_anchor(sub))
        days.append(str(day))
        probs.append(blend)
        labels.append(pd.to_numeric(sub["y"], errors="coerce").to_numpy(dtype=float))

    if not days:
        raise ValueError(f"{mode}: không có kỳ nào đủ điều kiện chấm")
    return days, np.asarray(probs), np.asarray(labels)


def _wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    rate = hits / total
    denom = 1.0 + z * z / total
    centre = (rate + z * z / (2 * total)) / denom
    half = z * np.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def calibration(p: np.ndarray, y: np.ndarray, bins: int = CALIBRATION_BINS) -> list[dict]:
    flat_p, flat_y = p.reshape(-1), y.reshape(-1)
    edges = np.unique(np.quantile(flat_p, np.linspace(0.0, 1.0, bins + 1)))
    if len(edges) < 2:
        edges = np.repeat(edges, 2)
    edges[-1] += 1e-12
    index = np.clip(np.digitize(flat_p, edges) - 1, 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        chosen = index == b
        count = int(chosen.sum())
        if count == 0:
            continue
        hits = int(flat_y[chosen].sum())
        low, high = _wilson(hits, count)
        rows.append(
            {
                "bin": b,
                "count": count,
                "predicted": float(flat_p[chosen].mean()),
                "observed": hits / count,
                "ci_low": low,
                "ci_high": high,
            }
        )
    return rows


def murphy(p: np.ndarray, y: np.ndarray, bins: int = CALIBRATION_BINS) -> dict:
    flat_p, flat_y = p.reshape(-1), y.reshape(-1)
    total = len(flat_p)
    mean_y = float(flat_y.mean())
    rows = calibration(p, y, bins)
    reliability = sum(r["count"] * (r["predicted"] - r["observed"]) ** 2 for r in rows) / total
    resolution = sum(r["count"] * (r["observed"] - mean_y) ** 2 for r in rows) / total
    uncertainty = mean_y * (1.0 - mean_y)

    binned = sum(
        r["count"] * ((r["predicted"] - r["observed"]) ** 2 + r["observed"] * (1 - r["observed"]))
        for r in rows
    ) / total
    direct = float(np.mean((flat_p - flat_y) ** 2))
    return {
        "reliability": float(reliability),
        "resolution": float(resolution),
        "uncertainty": float(uncertainty),
        "brier_binned": float(binned),
        "brier_from_decomposition": float(reliability - resolution + uncertainty),
        "brier_direct": direct,
        "binning_residual": float(direct - binned),
        "resolution_share_of_uncertainty": float(resolution / uncertainty) if uncertainty else 0.0,
        "base_rate": mean_y,
    }


def sharpness(p: np.ndarray, mode: str, bins: int = 24) -> dict:
    flat = p.reshape(-1)
    base = baseline_rate(mode)
    counts, edges = np.histogram(flat, bins=bins)
    return {
        "base_rate": float(base),
        "min": float(flat.min()),
        "max": float(flat.max()),
        "std": float(flat.std()),
        "spread_vs_base": float(flat.std() / base) if base else 0.0,
        "histogram": [
            {"lo": float(edges[i]), "hi": float(edges[i + 1]), "count": int(counts[i])}
            for i in range(len(counts))
        ],
    }


ECE_SIMULATIONS = 500
ECE_SEED = 20261116


def simulate_calibrated_outcomes(p: np.ndarray, mode: str, rng: np.random.Generator) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    if mode == "de":
        per_slot, slots = p / p.sum(axis=1, keepdims=True), 1
    else:
        per_slot = 1.0 - (1.0 - np.clip(p, 0.0, 1.0 - 1e-12)) ** (1.0 / LOTO_DRAWS_PER_DAY)
        per_slot, slots = per_slot / per_slot.sum(axis=1, keepdims=True), LOTO_DRAWS_PER_DAY
    cumulative = np.cumsum(per_slot, axis=1)
    cumulative[:, -1] = 1.0
    picks = (rng.random((len(p), slots, 1)) >= cumulative[:, None, :]).sum(axis=2)
    outcomes = np.zeros(p.shape)
    outcomes[np.arange(len(p))[:, None], picks] = 1.0
    return outcomes


def calibration_summary(p: np.ndarray, y: np.ndarray, mode: str, *, simulations: int = ECE_SIMULATIONS,
                        seed: int = ECE_SEED) -> dict:
    out = calibration_error(calibration(p, y))
    rng = np.random.default_rng(seed)
    null = np.array([
        calibration_error(calibration(p, simulate_calibrated_outcomes(p, mode, rng)))["ece"]
        for _ in range(simulations)
    ])
    out["ece_expected"] = float(null.mean())
    out["ece_upper95"] = float(np.quantile(null, 0.95))
    out["p_value"] = float((int((null >= out["ece"]).sum()) + 1) / (simulations + 1))
    out["simulations"] = simulations
    return out


def ranking(p: np.ndarray, y: np.ndarray, mode: str) -> dict:
    hits = np.asarray(y) > 0.5
    if len(hits) < 2:
        return {"draws": int(len(hits))}
    if mode == "de":
        truth = hits.argmax(axis=1)
        rank, reciprocal = rank_of_truth(p, truth)
        low, high = cluster_bootstrap_ci(reciprocal)
        return {
            "draws": int(len(hits)),
            "metric": "mrr",
            "value": float(reciprocal.mean()),
            "chance": chance_reciprocal_rank(hits.shape[1]),
            "ci_low": low,
            "ci_high": high,
            "mean_rank": float(rank.mean()),
            "chance_rank": (hits.shape[1] + 1) / 2.0,
            "p_value": within_draw_permutation_p(
                p, hits, lambda s, h: float(rank_of_truth(s, h.argmax(axis=1))[1].mean())
            ),
        }
    per_draw = auc_by_draw(p, hits)
    usable = per_draw[np.isfinite(per_draw)]
    low, high = cluster_bootstrap_ci(usable)
    return {
        "draws": int(len(usable)),
        "metric": "auc",
        "value": float(usable.mean()),
        "chance": 0.5,
        "ci_low": low,
        "ci_high": high,
        "p_value": within_draw_permutation_p(p, hits, lambda s, h: float(np.nanmean(auc_by_draw(s, h)))),
    }


def skill_series(history: pd.DataFrame, mode: str) -> dict:
    sub = history[history["mode"].astype(str) == mode].sort_values("target_date", kind="stable")
    if "logloss_skill" not in sub.columns:
        return {"days": 0}
    values = pd.to_numeric(sub["logloss_skill"], errors="coerce")
    usable = sub[values.notna()]
    return summarize_skill(
        usable["target_date"].astype(str).tolist(), values.dropna().to_numpy(dtype=float)
    )


def summarize_skill(dates: list[str], series: np.ndarray) -> dict:
    series = np.asarray(series, dtype=float)
    if len(series) == 0:
        return {"days": 0}
    mean = float(series.mean())
    stderr = float(series.std(ddof=1) / np.sqrt(len(series))) if len(series) > 1 else 0.0
    return {
        "days": int(len(series)),
        "mean": mean,
        "stderr": stderr,
        "ci_low": mean - 1.96 * stderr,
        "ci_high": mean + 1.96 * stderr,
        "distinguishable_from_zero": bool(abs(mean) > 1.96 * stderr),
        "share_worse_than_baseline": float((series < 0).mean()),
        "points": [
            {"date": str(d), "skill": float(v), "cumulative": float(c)}
            for d, v, c in zip(
                dates,
                series,
                np.cumsum(series) / np.arange(1, len(series) + 1),
                strict=True,
            )
        ],
    }


def coverage(history: pd.DataFrame) -> dict:
    if "evaluation_source" not in history.columns:
        history = history.assign(evaluation_source="")
    if "logloss_skill" not in history.columns:
        history = history.assign(logloss_skill=np.nan)
    source = history["evaluation_source"].fillna("")
    exact = source == "exact_emitted_prediction_artifact"
    rows = []
    for mode in MODES:
        chosen = history["mode"].astype(str) == mode
        total = int(chosen.sum())
        exact_count = int((chosen & exact).sum())
        rows.append(
            {
                "mode": mode,
                "rows": total,
                "exact_artifact_rows": exact_count,
                "exact_share": (exact_count / total) if total else 0.0,
                "exact_mean_skill": float(
                    pd.to_numeric(history.loc[chosen & exact, "logloss_skill"], errors="coerce").mean()
                )
                if exact_count
                else float("nan"),
                "reconstructed_mean_skill": float(
                    pd.to_numeric(history.loc[chosen & ~exact, "logloss_skill"], errors="coerce").mean()
                )
                if total - exact_count
                else float("nan"),
            }
        )
    return {"by_mode": rows}


def build(data_dir: Path) -> Path:
    update_ledger(data_dir)
    history_path = data_dir / "evaluation" / "prob_eval" / "ensemble_history.csv"
    raw_history = pd.read_csv(history_path)
    history, converted = normalize_brier_scale(raw_history)

    modes = {}
    for mode in MODES:
        days, probabilities, labels = published_evaluation(data_dir, mode)
        monthly: list[dict] = []
        if len(days) >= MIN_DAYS:
            source = "published"
            graded_days, graded_skill = graded_series(data_dir, mode)
            skill = summarize_skill(graded_days, graded_skill)
            monthly = by_period(graded_days, graded_skill)
        else:
            source = "reconstructed"
            predictions = pd.read_csv(data_dir / "evaluation" / "history" / f"pred_{mode}.csv")
            weights = load_ensemble_weights(data_dir, mode)
            days, probabilities, labels = ensemble_probabilities(predictions, weights, mode)
            skill = skill_series(history, mode)
        modes[mode] = {
            "mode": mode,
            "source": source,
            "days": len(days),
            "first_day": days[0],
            "last_day": days[-1],
            "murphy": murphy(probabilities, labels),
            "calibration": calibration(probabilities, labels),
            "calibration_error": calibration_summary(probabilities, labels, mode),
            "sharpness": sharpness(probabilities, mode),
            "ranking": ranking(probabilities, labels, mode),
            "skill": skill,
            "by_month": monthly,
        }

    covered = [block["last_day"] for block in modes.values() if block.get("last_day")]
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "covers_through": max(covered) if covered else None,
        "brier_rows_rescaled": converted,
        "coverage": coverage(history),
        "monitor": [check.as_dict() for check in evaluate_skill(data_dir)],
        "modes": modes,
    }
    out_dir = data_dir / "evaluation" / "model_quality"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Chẩn đoán chất lượng mô hình xác suất")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    print("Wrote:", build(Path(args.data_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
