from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from core.xsmb_domain import FIELD_WIDTHS
from stats.statistical_corrections import benjamini_hochberg

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "model_overhaul" / "forecast_ceiling.json"
LOTO_BASE = 1.0 - 0.99**27
WINDOWS = (60, 120, 180, 365, 730)
STRENGTHS = (0, 500, 2000, 5000)
WARMUP = 400


def _load(data_dir: Path) -> tuple[np.ndarray, list[str]]:
    raw = pd.read_csv(data_dir / "xsmb.csv", dtype=str).sort_values("date")
    cols = [c for c in raw.columns if c != "date"]
    last_two = np.stack([raw[c].str.zfill(2).str[-2:].astype(int).to_numpy() for c in cols], axis=1)
    return last_two, cols


def digit_stability(last_two: np.ndarray, cols: list[str]) -> dict:
    half = len(last_two) // 2
    rows = []
    for k, col in enumerate(cols):
        for name, digits in (("chuc", last_two[:, k] // 10), ("don_vi", last_two[:, k] % 10)):
            a = np.bincount(digits[:half], minlength=10)
            b = np.bincount(digits[half:], minlength=10)
            corr = float(np.corrcoef(a / a.sum() - 0.1, b / b.sum() - 0.1)[0, 1])
            rows.append({"prize": col, "place": name,
                         "p_first": float(stats.chisquare(a).pvalue),
                         "p_second": float(stats.chisquare(b).pvalue),
                         "half_corr": corr})
    corr = np.array([r["half_corr"] for r in rows])
    return {
        "tests": len(rows),
        "p_below_001_first": int(sum(r["p_first"] < 0.01 for r in rows)),
        "p_below_001_second": int(sum(r["p_second"] < 0.01 for r in rows)),
        "half_corr_mean": float(corr.mean()),
        "half_corr_se": float(corr.std(ddof=1) / np.sqrt(len(corr))),
    }


def within_day_independence(last_two: np.ndarray) -> dict:
    out = {}
    for name, digits in (("chuc", last_two // 10), ("don_vi", last_two % 10)):
        counts = np.stack([(digits == d).sum(axis=1) for d in range(10)], axis=1)
        out[name] = float(counts.var(axis=0).mean())
    out["binomial"] = 27 * 0.1 * 0.9
    return out


def _appearance(last_two: np.ndarray) -> np.ndarray:
    hit = np.zeros((len(last_two), 100), dtype=bool)
    for t, row in enumerate(last_two):
        hit[t, row] = True
    return hit


def lag_dependence(hit: np.ndarray) -> list[dict]:
    out = []
    for lag in (1, 2, 3, 7):
        x, y = hit[:-lag], hit[lag:]
        a = (x & y).sum(axis=1).astype(float)
        b = x.sum(axis=1).astype(float)
        c = (~x & y).sum(axis=1).astype(float)
        d = (~x).sum(axis=1).astype(float)
        p1, p0 = a.sum() / b.sum(), c.sum() / d.sum()
        r1, r0 = a - p1 * b, c - p0 * d
        clusters = len(a)
        factor = clusters / (clusters - 1)
        var = factor * (np.sum(r1**2) / b.sum() ** 2 + np.sum(r0**2) / d.sum() ** 2
                        - 2 * np.sum(r1 * r0) / (b.sum() * d.sum()))
        out.append({"lag": lag, "after_hit": float(p1), "after_miss": float(p0),
                    "z": float((p1 - p0) / np.sqrt(var))})
    return out


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum())


def recency_digit_models(last_two: np.ndarray, hit: np.ndarray) -> list[dict]:
    tens = np.stack([(last_two // 10 == d).sum(axis=1) for d in range(10)], axis=1).astype(float)
    units = np.stack([(last_two % 10 == d).sum(axis=1) for d in range(10)], axis=1).astype(float)
    cum_t = np.vstack([np.zeros(10), np.cumsum(tens, axis=0)])
    cum_u = np.vstack([np.zeros(10), np.cumsum(units, axis=0)])
    flat = np.full(100, LOTO_BASE)
    out = []
    for window in WINDOWS:
        for strength in STRENGTHS:
            skill = []
            for t in range(WARMUP, len(hit)):
                lo = max(0, t - window)
                ft, fu = cum_t[t] - cum_t[lo], cum_u[t] - cum_u[lo]
                pt = (ft + strength * 0.1) / (ft.sum() + strength)
                pu = (fu + strength * 0.1) / (fu.sum() + strength)
                p = 1.0 - (1.0 - np.outer(pt, pu).ravel()) ** 27
                p *= 100 * LOTO_BASE / p.sum()
                skill.append(_logloss(flat, hit[t]) - _logloss(p, hit[t]))
            d = np.array(skill)
            half = len(d) // 2
            z = lambda v: float(v.mean() / v.std(ddof=1) * np.sqrt(len(v)))  # noqa: E731
            out.append({"window": window, "strength": strength, "days": len(d),
                        "skill_per_draw": float(d.mean()), "z": z(d),
                        "halves_z": [z(d[:half]), z(d[half:])]})
    return out


CAGE_NAMES = ("đơn vị", "chục", "trăm", "nghìn", "chục nghìn")


def cage_counts(frame: pd.DataFrame) -> np.ndarray:
    table = np.zeros((len(CAGE_NAMES), 10), dtype=np.int64)
    for name, width in FIELD_WIDTHS:
        values = frame[name].astype(str).str.zfill(width)
        for cage in range(width):
            table[cage] += np.bincount(values.str[width - 1 - cage].astype(int), minlength=10)
    return table


def cage_windows(raw: pd.DataFrame, top: int = 8) -> dict:
    dates = pd.to_datetime(raw["date"])
    quarter = dates.dt.year.astype(str) + "Q" + dates.dt.quarter.astype(str)
    rows = []
    for label, chunk in raw.groupby(quarter.to_numpy(), sort=True):
        if len(chunk) < 30:
            continue
        table = cage_counts(chunk)
        expected = table.sum(axis=1, keepdims=True) / 10.0
        chi = ((table - expected) ** 2 / expected).sum(axis=1)
        for cage, name in enumerate(CAGE_NAMES):
            rows.append({"quarter": str(label), "cage": name, "draws": int(len(chunk)), "chi2": float(chi[cage]),
                         "p_value": float(stats.chi2.sf(chi[cage], 9)), "counts": table[cage].tolist()})
    if not rows:
        return {"cells": 0}
    p = np.array([row["p_value"] for row in rows])
    for row, q in zip(rows, benjamini_hochberg(p), strict=True):
        row["q_value"] = float(q)
    ranked = sorted(rows, key=lambda row: (row["p_value"], row["quarter"], row["cage"]))
    return {
        "cells": len(rows),
        "p_below_001": int((p < 0.01).sum()),
        "expected_below_001": round(0.01 * len(rows), 2),
        "q_below_005": int(sum(row["q_value"] < 0.05 for row in rows)),
        "min_p": float(p.min()),
        "min_p_bonferroni": float(min(1.0, p.min() * len(rows))),
        "uniformity_ks_p": float(stats.kstest(p, "uniform").pvalue),
        "most_extreme": ranked[:top],
    }


def published_skill(data_dir: Path) -> dict:
    report = json.loads((data_dir / "evaluation" / "model_quality" / "report.json").read_text(encoding="utf-8"))
    out = {}
    for mode, block in report["modes"].items():
        sk = block["skill"]
        out[mode] = {k: sk[k] for k in ("days", "mean", "stderr", "ci_low", "ci_high",
                                         "distinguishable_from_zero")}
        out[mode]["reliability"] = block["murphy"]["reliability"]
        out[mode]["resolution"] = block["murphy"]["resolution"]
    return out


def run(data_dir: Path) -> dict:
    last_two, cols = _load(data_dir)
    hit = _appearance(last_two)
    return {
        "draws": int(len(last_two)),
        "digit_stability": digit_stability(last_two, cols),
        "within_day_variance": within_day_independence(last_two),
        "lag_dependence": lag_dependence(hit),
        "recency_digit_models": recency_digit_models(last_two, hit),
        "cage_windows": cage_windows(pd.read_csv(data_dir / "xsmb.csv", dtype=str).sort_values("date", kind="stable")),
        "published_skill": published_skill(data_dir),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    args = ap.parse_args()
    report = {"generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
              **run(Path(args.data_dir))}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    best = max(report["recency_digit_models"], key=lambda r: r["z"])
    print(f"[OK] {OUT}")
    print(f"lệch chữ số: tương quan hai nửa {report['digit_stability']['half_corr_mean']:+.3f} "
          f"± {report['digit_stability']['half_corr_se']:.3f}")
    print("độ trễ:", ", ".join(f"{r['lag']}: z = {r['z']:+.2f}" for r in report["lag_dependence"]))
    print(f"mô hình chữ số gần đây tốt nhất: W={best['window']} k={best['strength']} z = {best['z']:+.2f}")
    cage = report["cage_windows"]
    worst = cage["most_extreme"][0]
    print(f"chữ số theo lồng từng quý: {cage['q_below_005']}/{cage['cells']} ô có q < 0,05; lệch nhất "
          f"{worst['quarter']} lồng {worst['cage']} (p Bonferroni {cage['min_p_bonferroni']:.2g})")


if __name__ == "__main__":
    main()
