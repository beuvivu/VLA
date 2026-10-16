"""Đo ngoài mẫu phép suy luận cầu vị trí bằng Bayes thực nghiệm (16-10-2026).

Bản cũ (``path_prob`` trước 16-10-2026): xác suất của một con là trung bình tỉ
lệ trúng LỊCH SỬ của các cầu báo nó — các cầu được chọn top 300 trên khoảng
5 671 cầu mỗi độ trễ — rồi co về nền với độ mạnh đặt tay
``6·√(1 + 2·ln(5671/300))``. Tỉ lệ lịch sử của cầu được chọn mang lời nguyền
người thắng: tổng LOTO của nhánh ổn định là 24,40 con mỗi kỳ, trong khi kỳ
vọng thật là 23,77.

Bản mới: mỗi cầu nhận xác suất trúng kỳ tới theo kinh nghiệm học từ MỌI cầu
trong cửa sổ (``path_prob.BridgeEvidence``): tỉ lệ chung + phần riêng của cầu
co theo mức chênh THẬT giữa các cầu (Bayes thực nghiệm, phương pháp mô men);
nhánh "đang chạy" cộng phần kinh nghiệm theo độ dài chuỗi, học trên mọi cầu.

Walk-forward trên ``--last`` kỳ cuối, cầu dựng lại mỗi kỳ bằng đúng tham số của
pipeline — cửa sổ lấy từ mặc định của ``pipeline.py`` (``--window-days`` 2000, cũng là
giá trị ``update-data.yml`` truyền vào), không viết cứng 365 như phép đo 04-10-2026. Mốc hằng số: tỉ lệ nền tích luỹ (LOTO), 1/100 (Đặc Biệt) — cùng mốc
với ``benchmark_component_trust``.

Luật quyết định chốt TRƯỚC khi đo:

1. Nhánh cầu (vector in trên trang soi cầu): bản mới không kém bản cũ ở bất kỳ
   ô nào trong bốn ô (LOTO/Đặc Biệt × đang chạy/ổn định) với z ≤ −2, và thắng
   với z ≥ 2 ở ít nhất một ô.
2. Tổ hợp (trọng số mặc định, ML/thống kê/cầu-kèo bằng tỉ lệ nền như đo
   04-10-2026, chốt bằng ``finalize_blend``): bản mới không kém bản cũ với
   z ≤ −2 ở cả hai chế độ.
3. Tổ hợp mới không kém dự báo hằng số với z ≤ −2.

    PYTHONPATH=src python3 scripts/research/benchmark_bridge_inference.py --last 2000
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from calendar_alignment import consecutive_next_pairs, normalize_dates  # noqa: E402
from ensemble_utils import DEFAULT_ENSEMBLE_WEIGHTS, finalize_blend  # noqa: E402
from lottery import Lottery  # noqa: E402
from path_models import PathParams, build_daily_targets, enumerate_position_pairs  # noqa: E402
from path_prob import (  # noqa: E402
    fit_paths_with_evidence,
    paths_to_dataframe,
    predict_from_fitted_paths_full,
    prepare_path_history,
)
from vla.backtest import evaluator  # noqa: E402
from xsmb_domain import TOTAL_DIGITS, baseline_rate  # noqa: E402

OUT = ROOT / "data" / "research" / "model_overhaul" / "bridge_inference.json"
MODES = ("loto", "de")
KINDS = ("active", "stable")
#: Cửa sổ production: ``pipeline.py`` mặc định ``--window-days 2000`` và truyền nó cho
#: ``run_path_ui``; ``update-data.yml`` cũng truyền 2000. ``path_manifest_<mode>.json`` ghi lại.
PRODUCTION_WINDOW_DAYS = 2000
PATH_PARAMS = PathParams(lag_max=30, window_days=PRODUCTION_WINDOW_DAYS, min_trials=60,
                         min_max_streak=3, min_current_streak=3, top_rules_per_lag=300)

_PREPARED = None


def legacy_prior_strength(n_screened: int, n_kept: int, base: float = 6.0) -> float:
    """Độ co đặt tay của bản cũ (``selection_shrinkage_strength`` trước 16-10-2026)."""
    screened = max(int(n_screened), 1)
    kept = max(int(n_kept), 1)
    if kept >= screened:
        return float(base)
    return float(base) * float(np.sqrt(1.0 + 2.0 * np.log(screened / kept)))


def legacy_branch(stats_df: pd.DataFrame, raw_by_date: dict, anchor, *, kind: str, mode: str) -> np.ndarray:
    """Tái lập đúng ``predict_from_fitted_paths_full`` trước 16-10-2026 (phạm vi "all")."""
    base = baseline_rate(mode)
    params = PATH_PARAMS
    paths = stats_df[stats_df["trials"] >= params.min_trials]
    if kind == "active":
        paths = paths[paths["current_streak"] >= params.min_current_streak]
    else:
        paths = paths[paths["max_streak"] >= params.min_max_streak]
    if paths.empty:
        return np.full(100, base)
    next_date = anchor + timedelta(days=1)
    lags = paths["lag"].to_numpy(dtype=int)
    i_arr = paths["i"].to_numpy(dtype=int)
    j_arr = paths["j"].to_numpy(dtype=int)
    nums = np.full(len(paths), -1, dtype=int)
    for lag in np.unique(lags):
        digits = raw_by_date.get(next_date - timedelta(days=int(lag)))
        if digits is None:
            continue
        rows = lags == lag
        digits = np.asarray(digits)
        nums[rows] = 10 * digits[i_arr[rows]].astype(int) + digits[j_arr[rows]].astype(int)
    ok = (nums >= 0) & (nums < 100)
    if not ok.any():
        return np.full(100, base)
    p = np.clip(paths["p_mean"].to_numpy(dtype=float)[ok], 1e-6, 1 - 1e-6)
    trials = paths["trials"].to_numpy(dtype=float)[ok]
    reliability = trials / (trials + 120.0)
    if kind == "active":
        streak_weight = 1.0 + 0.05 * np.minimum(paths["current_streak"].to_numpy(dtype=float)[ok], 8.0)
    else:
        streak_weight = 1.0 + 0.02 * np.minimum(paths["max_streak"].to_numpy(dtype=float)[ok], 15.0)
    w = reliability * streak_weight
    n = nums[ok]
    support = np.bincount(n, minlength=100)
    weight_sum = np.bincount(n, weights=w, minlength=100)
    weighted_p = np.bincount(n, weights=w * p, minlength=100)
    ps = legacy_prior_strength(len(enumerate_position_pairs(TOTAL_DIGITS)[0]), params.top_rules_per_lag)
    prob = (weighted_p + ps * base) / (weight_sum + ps)
    prob = np.where(support > 0, prob, base)
    if mode == "de":
        prob = prob / prob.sum()
    return prob


def _init_worker(prepared) -> None:
    global _PREPARED
    _PREPARED = prepared


def _day(anchor) -> dict:
    out = {}
    for mode in MODES:
        stats, raw_by_date, dates, evidence = fit_paths_with_evidence(
            params=PATH_PARAMS, mode=mode, anchor_date=anchor, prepared=_PREPARED
        )
        frame = paths_to_dataframe(stats)
        for kind in KINDS:
            new = predict_from_fitted_paths_full(stats=stats, raw_by_date=raw_by_date, dates=dates,
                                                 params=PATH_PARAMS, kind=kind, mode=mode,
                                                 anchor_date=anchor)
            out[(mode, kind, "new")] = new.sort_values("number")["prob"].to_numpy(dtype=float)
            out[(mode, kind, "old")] = legacy_branch(frame, raw_by_date, anchor, kind=kind, mode=mode)
        out[(mode, "evidence")] = {
            "variance_ratio": evidence.variance_ratio,
            "rules_fully_pooled": evidence.rules_fully_pooled,
            "rule_shrinkage": evidence.rule_shrinkage,
            "streak_posterior": list(evidence.streak_posterior),
            "base_rate": evidence.base_rate,
        }
    return out


def _paired(new: np.ndarray, old: np.ndarray) -> dict:
    half = len(new) // 2
    return {**evaluator.paired(new, old),
            "halves_z": [evaluator.paired(new[:half], old[:half])["z"],
                         evaluator.paired(new[half:], old[half:])["z"]]}


def decide(report: dict) -> dict:
    """Áp luật quyết định đã chốt ở docstring lên báo cáo."""
    branch = [report[m]["branch_new_vs_old"][k]["z"] for m in MODES for k in KINDS]
    ensemble = [report[m]["ensemble_new_vs_old"]["z"] for m in MODES]
    constant = [report[m]["vs_constant"]["ensemble_new"]["z"] for m in MODES]
    rule1 = min(branch) > -2.0 and max(branch) >= 2.0
    rule2 = min(ensemble) > -2.0
    rule3 = min(constant) > -2.0
    return {"rule1_branch": rule1, "rule2_ensemble": rule2, "rule3_constant": rule3,
            "adopt": bool(rule1 and rule2 and rule3)}


def run(last: int, workers: int) -> dict:
    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    dates = normalize_dates(raw["date"])
    source, target = consecutive_next_pairs(dates)
    source, target = source[-last:], target[-last:]
    _, loto_targets, de_targets = build_daily_targets(two)
    hit_loto = np.zeros((len(two), 100))
    for t, numbers in enumerate(loto_targets):
        hit_loto[t, list(numbers)] = 1.0
    hit_de = np.eye(100)[np.asarray(de_targets, dtype=int)]

    prepared = prepare_path_history(raw, two)
    anchors = [dates[i].date() for i in source]
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(prepared,)) as pool:
        days = list(pool.map(_day, anchors, chunksize=8))
    print(f"[cầu vị trí] {len(days)} kỳ", flush=True)

    weights = DEFAULT_ENSEMBLE_WEIGHTS
    report: dict = {}
    for mode in MODES:
        hits = (hit_loto if mode == "loto" else hit_de)[target]
        ref = evaluator.daily_logloss(mode, evaluator.cumulative_reference(
            mode, hit_loto if mode == "loto" else hit_de, target), hits)
        base = baseline_rate(mode)
        vec = {(k, v): np.vstack([d[(mode, k, v)] for d in days]) for k in KINDS for v in ("old", "new")}
        flat = (weights.w_ml + weights.w_stat + weights.w_cau) * base
        ens = {v: np.vstack([finalize_blend(r, mode) for r in
                             flat + weights.w_active * vec[("active", v)] + weights.w_stable * vec[("stable", v)]])
               for v in ("old", "new")}
        ll = {f"{k}_{v}": evaluator.daily_logloss(mode, p, hits) for (k, v), p in vec.items()}
        ll.update({f"ensemble_{v}": evaluator.daily_logloss(mode, p, hits) for v, p in ens.items()})
        ev = [d[(mode, "evidence")] for d in days]
        report[mode] = {
            "days": len(days),
            "first_target": str(dates[target[0]].date()),
            "last_target": str(dates[target[-1]].date()),
            "constant_logloss": float(ref.mean()),
            "logloss": {k: float(v.mean()) for k, v in ll.items()},
            "vs_constant": {k: _paired(v, ref) for k, v in ll.items()},
            "branch_new_vs_old": {k: _paired(ll[f"{k}_new"], ll[f"{k}_old"]) for k in KINDS},
            "ensemble_new_vs_old": _paired(ll["ensemble_new"], ll["ensemble_old"]),
            "median_sum": {name: float(np.median(p.sum(axis=1)))
                           for name, p in {**{f"{k}_{v}": p for (k, v), p in vec.items()},
                                           **{f"ensemble_{v}": p for v, p in ens.items()}}.items()},
            "expected_sum": float(100 * base) if mode == "loto" else 1.0,
            "evidence": {
                "variance_ratio_median": float(np.median([e["variance_ratio"] for e in ev])),
                "variance_ratio_range": [float(min(e["variance_ratio"] for e in ev)),
                                         float(max(e["variance_ratio"] for e in ev))],
                "share_fully_pooled": float(np.mean([e["rules_fully_pooled"] for e in ev])),
                "min_rule_shrinkage": float(min(e["rule_shrinkage"] for e in ev)),
                "streak_posterior_minus_base_max_abs": float(max(
                    max(abs(s - e["base_rate"]) for s in e["streak_posterior"]) for e in ev)),
            },
        }
        r = report[mode]
        print(f"[{mode}] nhánh mới so với cũ: "
              + ", ".join(f"{k} z = {r['branch_new_vs_old'][k]['z']:+.2f}" for k in KINDS)
              + f"; tổ hợp mới so với cũ z = {r['ensemble_new_vs_old']['z']:+.2f}"
              + f"; tổ hợp mới so với hằng số z = {r['vs_constant']['ensemble_new']['z']:+.2f}",
              flush=True)
    report["decision"] = decide(report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--last", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "last": args.last,
              "assumptions": ("Tổ hợp mô phỏng: ML, thống kê và cầu-kèo bằng tỉ lệ nền; cầu vị trí "
                              "từ walk-forward; trọng số mặc định; không hiệu chỉnh, không xếp chồng."),
              **run(args.last, args.workers)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {OUT}  quyết định: {report['decision']}")


if __name__ == "__main__":
    main()
