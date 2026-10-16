"""Trần dự báo của XSMB: dữ liệu có cấu trúc nào để học không? (16-10-2026)

Yêu cầu của chủ dự án: "tăng tính phỏng đoán và thông minh khi suy luận cầu kèo
và xác suất cho toàn hệ thống lên mức cao nhất có thể". Mức cao nhất có thể do
DỮ LIỆU quyết định, không do mô hình: nếu kỳ quay độc lập và đều, mọi dự báo
khác hằng số đều có logloss kỳ vọng KÉM hơn hằng số, và trần là chính hằng số.

Kịch bản này dò những dạng cấu trúc có thể có thật trên một trò quay lồng cầu,
mỗi dạng một phép thử, rồi đặt kỹ năng ĐÃ CÔNG BỐ của hệ thống cạnh trần ấy.

1. Lệch chữ số theo vị trí (bi lệch, lồng lệch) có ỔN ĐỊNH giữa hai nửa lịch
   sử không — lệch thật thì tương quan dương giữa hai nửa.
2. Các chữ số trong CÙNG một kỳ có độc lập không (phương sai số đếm theo ngày
   so với nhị thức).
3. Lô về hôm nay có làm đổi khả năng về ở kỳ sau không (độ trễ 1, 2, 3, 7).
4. Mô hình tần suất chữ số gần đây (cửa sổ W kỳ, co về đều với độ mạnh k):
   walk-forward so với dự báo đều — dạng duy nhất khai thác được lệch vật lý
   nếu lệch ấy trôi theo thời gian.
5. Kỹ năng ngoài mẫu của vector ĐÃ CÔNG BỐ (``data/model_quality/report.json``).

    PYTHONPATH=src python3 scripts/research/audit_forecast_ceiling.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "model_overhaul" / "forecast_ceiling.json"
LOTO_BASE = 1.0 - 0.99**27
WINDOWS = (60, 120, 180, 365, 730)
STRENGTHS = (0, 500, 2000, 5000)
WARMUP = 400


def _load(data_dir: Path) -> tuple[np.ndarray, list[str]]:
    raw = pd.read_csv(data_dir / "xsmb.csv", dtype=str).sort_values("date")
    cols = [c for c in raw.columns if c != "date"]
    # Hai chữ số cuối của từng giải: ngày × 27.
    last_two = np.stack([raw[c].str.zfill(2).str[-2:].astype(int).to_numpy() for c in cols], axis=1)
    return last_two, cols


def digit_stability(last_two: np.ndarray, cols: list[str]) -> dict:
    """Lệch chữ số theo (giải, hàng) ở hai nửa lịch sử và tương quan giữa hai nửa."""
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
    """Phương sai số lần một chữ số xuất hiện trong một kỳ, so với nhị thức(27; 0,1)."""
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
        p1, p0 = float(y[x].mean()), float(y[~x].mean())
        se = np.sqrt(p1 * (1 - p1) / x.sum() + p0 * (1 - p0) / (~x).sum())
        out.append({"lag": lag, "after_hit": p1, "after_miss": p0, "z": float((p1 - p0) / se)})
    return out


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum())


def recency_digit_models(last_two: np.ndarray, hit: np.ndarray) -> list[dict]:
    """Walk-forward: P(chục=a)·P(đơn vị=b) từ W kỳ gần nhất, co về 0,1 với độ mạnh k."""
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


def published_skill(data_dir: Path) -> dict:
    report = json.loads((data_dir / "model_quality" / "report.json").read_text(encoding="utf-8"))
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
        "published_skill": published_skill(data_dir),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    args = ap.parse_args()
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              **run(Path(args.data_dir))}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    best = max(report["recency_digit_models"], key=lambda r: r["z"])
    print(f"[OK] {OUT}")
    print(f"lệch chữ số: tương quan hai nửa {report['digit_stability']['half_corr_mean']:+.3f} "
          f"± {report['digit_stability']['half_corr_se']:.3f}")
    print("độ trễ:", ", ".join(f"{r['lag']}: z = {r['z']:+.2f}" for r in report["lag_dependence"]))
    print(f"mô hình chữ số gần đây tốt nhất: W={best['window']} k={best['strength']} z = {best['z']:+.2f}")


if __name__ == "__main__":
    main()
