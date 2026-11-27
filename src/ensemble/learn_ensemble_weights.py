from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from ensemble.calibration import CalibrationAudit, CalibParams, select_calibration
from ensemble.ensemble_components import COMPONENT_KEYS, availability_from_history_day
from ensemble.ensemble_utils import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    PROBABILITY_FLOOR_SHARE,
    EnsembleWeights,
    anchor_loto_level,
    clip01,
    finalize_blend,
    load_ensemble_weights,
    weight_grid,
)

COMPONENT_COLS = [f"p_{key}" for key in COMPONENT_KEYS]

TRAIN_FRACTION: Final[float] = 0.6

MIN_VALIDATION_DAYS: Final[int] = 8

MIN_RELATIVE_GAIN: Final[float] = 0.002

BOOTSTRAP_DRAWS: Final[int] = 2000
BOOTSTRAP_SEED: Final[int] = 20260921


def _select_recent_complete_days(
    df: pd.DataFrame, window_days: int, *, mode: str | None = None
) -> list[str]:
    if "target_date" not in df.columns or "y" not in df.columns:
        return []
    if any(c not in df.columns for c in COMPONENT_COLS):
        return []

    complete: list[str] = []
    for day, sub in df.groupby("target_date", sort=True):
        if len(sub) != 100 or not sub["y"].notna().all():
            continue
        numbers = pd.to_numeric(sub.get("number"), errors="coerce")
        if numbers.isna().any() or set(numbers.astype(int).tolist()) != set(range(100)):
            continue
        available = availability_from_history_day(sub, mode=mode, current_policy=True)
        if all(available.get(key, False) for key in COMPONENT_KEYS):
            complete.append(str(day))

    complete.sort()
    return complete if window_days <= 0 else complete[-window_days:]


def _stack_days(
    df: pd.DataFrame, days: Sequence[str]
) -> tuple[dict[str, np.ndarray], np.ndarray, list[str]]:
    wanted = set(days)
    work = df.assign(_day=df["target_date"].astype(str))
    work = work[work["_day"].isin(wanted)].sort_values(["_day", "number"], kind="stable")

    day_list = sorted(wanted.intersection(work["_day"].unique()))
    index_of = {day: i for i, day in enumerate(day_list)}
    arrays = {c: np.zeros((len(day_list), 100), dtype=np.float64) for c in COMPONENT_COLS}
    labels = np.zeros((len(day_list), 100), dtype=np.float64)

    for day, sub in work.groupby("_day", sort=False):
        row = index_of[day]
        for column in COMPONENT_COLS:
            arrays[column][row] = sub[column].to_numpy(dtype=np.float64)
        labels[row] = sub["y"].to_numpy(dtype=np.float64)
    return arrays, labels, day_list


def _day_weights(days: list[str], half_life_draws: int) -> np.ndarray:
    if half_life_draws <= 0:
        return np.ones(len(days), dtype=float)
    age = np.arange(len(days) - 1, -1, -1, dtype=float)
    lam = np.log(2.0) / float(half_life_draws)
    w = np.exp(-lam * age)
    return w / np.mean(w)


def _weight_vector(w: EnsembleWeights) -> np.ndarray:
    return np.array([w.w_ml, w.w_cau, w.w_stat, w.w_active, w.w_stable], dtype=float)


def _weights_from_vector(x: np.ndarray) -> EnsembleWeights:
    return EnsembleWeights(
        w_ml=float(x[0]),
        w_cau=float(x[1]),
        w_stat=float(x[2]),
        w_active=float(x[3]),
        w_stable=float(x[4]),
    ).normalized()


PRIOR_VECTOR: Final[np.ndarray] = _weight_vector(DEFAULT_ENSEMBLE_WEIGHTS)


def _blend(arrays: dict[str, np.ndarray], x: np.ndarray) -> np.ndarray:
    out = x[0] * arrays[COMPONENT_COLS[0]]
    for i in range(1, len(COMPONENT_COLS)):
        out = out + x[i] * arrays[COMPONENT_COLS[i]]
    return out


def _daily_scores(mode: str, p_blend: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    probs = np.asarray(p_blend, dtype=np.float64)
    labels = np.asarray(y, dtype=np.float64)
    n_outcomes = probs.shape[1]
    rows = np.arange(probs.shape[0])

    if mode == "de":
        totals = probs.sum(axis=1, keepdims=True)
        safe = np.where(totals > 0.0, totals, 1.0)
        q = np.where(totals > 0.0, probs / safe, 1.0 / n_outcomes)
        q = (1.0 - PROBABILITY_FLOOR_SHARE) * q + PROBABILITY_FLOOR_SHARE / n_outcomes
        hit = q[rows, np.argmax(labels, axis=1)]
        logloss = -np.log(np.clip(hit, 1e-12, 1.0))
        brier = np.sum(q * q, axis=1) - 2.0 * hit + 1.0
        return logloss, brier

    p = anchor_loto_level(probs)
    logloss = -np.mean(labels * np.log(p) + (1.0 - labels) * np.log(1.0 - p), axis=1)
    brier = np.mean((p - labels) ** 2, axis=1)
    return logloss, brier


def _optimize_weights_continuous(
    mode: str,
    arrays: dict[str, np.ndarray],
    y: np.ndarray,
    w_day: np.ndarray,
) -> tuple[EnsembleWeights, float, float]:
    try:
        from scipy.optimize import minimize
    except ImportError:
        minimize = None

    def eval_scores(w: np.ndarray) -> tuple[float, float]:
        w = np.clip(w, 0.0, 1.0)
        total = float(np.sum(w))
        w = PRIOR_VECTOR if total <= 0 else w / total
        logloss, brier = _daily_scores(mode, _blend(arrays, w), y)
        return float(np.average(logloss, weights=w_day)), float(np.average(brier, weights=w_day))

    if minimize is None:
        best_w: EnsembleWeights | None = None
        best_ll, best_br = float("inf"), float("inf")
        for w in weight_grid(step=0.10):
            ll, br = eval_scores(_weight_vector(w))
            if ll < best_ll - 1e-9 or (abs(ll - best_ll) <= 1e-9 and br < best_br):
                best_w, best_ll, best_br = w, ll, br
        if best_w is None:
            raise RuntimeError("ensemble weight grid unexpectedly produced no candidates")
        return best_w.normalized(), best_ll, best_br

    def obj(x: np.ndarray) -> float:
        return eval_scores(x)[0] + 0.025 * float(np.square(x - PRIOR_VECTOR).sum())

    res = minimize(
        obj,
        x0=PRIOR_VECTOR.copy(),
        bounds=[(0.0, 0.60)] * 5,
        constraints=({"type": "eq", "fun": lambda x: np.sum(x) - 1.0},),
        method="SLSQP",
        options={"maxiter": 250},
    )
    x = res.x if res.success else PRIOR_VECTOR.copy()
    x = np.clip(x, 0.0, 1.0)
    x = x / max(float(x.sum()), 1e-12)
    ll, br = eval_scores(x)
    return _weights_from_vector(x), ll, br


@dataclass(frozen=True)
class PromotionAudit:

    promoted: bool
    reason: str
    baseline: str
    train_days: int
    validation_days: int
    train_last_day: str
    validation_first_day: str
    validation_logloss: dict[str, float]
    relative_gain: float
    delta_ci95_low: float
    delta_ci95_high: float

    def describe(self) -> str:
        if not self.promoted:
            return (
                f"KHÔNG đề bạt trọng số mới ({self.reason}); giữ '{self.baseline}'. "
                f"Thẩm định {self.validation_days} kỳ: "
                f"{self.validation_logloss} — lợi tương đối {self.relative_gain:+.4%}, "
                f"KTC95 hiệu [{self.delta_ci95_low:+.6f}; {self.delta_ci95_high:+.6f}]"
            )
        return (
            f"ĐỀ BẠT trọng số mới; đường cơ sở '{self.baseline}'. "
            f"Khớp {self.train_days} kỳ, thẩm định {self.validation_days} kỳ: "
            f"{self.validation_logloss} — lợi tương đối {self.relative_gain:+.4%}, "
            f"KTC95 hiệu [{self.delta_ci95_low:+.6f}; {self.delta_ci95_high:+.6f}]"
        )


def _paired_bootstrap_ci(
    diff: np.ndarray, *, draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED
) -> tuple[float, float]:
    values = np.asarray(diff, dtype=np.float64)
    if values.size == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, values.size, size=(int(draws), values.size))
    means = values[picks].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def _promotion_verdict(gain: float, ci_high: float) -> tuple[bool, str]:
    if gain < MIN_RELATIVE_GAIN:
        return False, f"biên thắng {gain:+.4%} chưa đạt sàn {MIN_RELATIVE_GAIN:.2%}"
    if not ci_high < 0.0:
        return False, f"KTC95 của hiệu chưa loại trừ số không (cận trên {ci_high:+.6f})"
    return True, "thắng đường cơ sở ngoài mẫu, đạt sàn hiệu ứng và KTC loại trừ số không"


def learn_with_holdout(
    mode: str,
    arrays: dict[str, np.ndarray],
    y: np.ndarray,
    day_list: Sequence[str],
    half_life_draws: int,
    incumbent: EnsembleWeights,
) -> tuple[EnsembleWeights, PromotionAudit]:
    keys = [str(d) for d in day_list]
    if any(b <= a for a, b in zip(keys, keys[1:], strict=False)):
        raise ValueError("day_list phải sắp tăng dần và không trùng lặp")

    n_days = len(day_list)
    split = int(round(n_days * TRAIN_FRACTION))
    train = slice(0, split)
    valid = slice(split, n_days)
    n_valid = n_days - split

    if split <= 0 or n_valid < MIN_VALIDATION_DAYS:
        return incumbent, PromotionAudit(
            promoted=False,
            reason=f"lát thẩm định chỉ có {max(n_valid, 0)} kỳ, cần {MIN_VALIDATION_DAYS}",
            baseline="dang_hieu_luc",
            train_days=max(split, 0),
            validation_days=max(n_valid, 0),
            train_last_day="",
            validation_first_day="",
            validation_logloss={},
            relative_gain=float("nan"),
            delta_ci95_low=float("nan"),
            delta_ci95_high=float("nan"),
        )

    train_last, valid_first = keys[split - 1], keys[split]
    arrays_train = {c: arrays[c][train] for c in COMPONENT_COLS}
    arrays_valid = {c: arrays[c][valid] for c in COMPONENT_COLS}
    y_train, y_valid = y[train], y[valid]

    w_train = _day_weights(list(day_list[train]), half_life_draws)
    candidate, _, _ = _optimize_weights_continuous(mode, arrays_train, y_train, w_train)

    def validation_daily(w: EnsembleWeights) -> np.ndarray:
        return _daily_scores(mode, _blend(arrays_valid, _weight_vector(w)), y_valid)[0]

    baseline_name = "mac_dinh"
    daily = {
        baseline_name: validation_daily(DEFAULT_ENSEMBLE_WEIGHTS),
        "dang_hieu_luc": validation_daily(incumbent),
        "ung_vien": validation_daily(candidate),
    }
    logloss = {name: float(np.mean(values)) for name, values in daily.items()}

    base_ll = logloss[baseline_name]
    cand_ll = logloss["ung_vien"]
    gain = (base_ll - cand_ll) / base_ll if base_ll > 0 else 0.0
    low, high = _paired_bootstrap_ci(daily["ung_vien"] - daily[baseline_name])

    promoted, reason = _promotion_verdict(gain, high)
    audit = PromotionAudit(
        promoted=promoted,
        reason=reason,
        baseline=baseline_name,
        train_days=split,
        validation_days=n_valid,
        train_last_day=train_last,
        validation_first_day=valid_first,
        validation_logloss=logloss,
        relative_gain=float(gain),
        delta_ci95_low=low,
        delta_ci95_high=high,
    )
    return (candidate if promoted else DEFAULT_ENSEMBLE_WEIGHTS), audit


def learn_chronological_stack(
    mode: str,
    arrays: dict[str, np.ndarray],
    y: np.ndarray,
    day_list: Sequence[str],
    half_life_draws: int,
    incumbent: EnsembleWeights,
) -> tuple[EnsembleWeights, PromotionAudit, CalibParams, CalibrationAudit, dict]:
    days = [str(day) for day in day_list]
    if not days or any(b <= a for a, b in zip(days, days[1:], strict=False)):
        raise ValueError("day_list phải tăng nghiêm ngặt và không rỗng")
    if mode not in {"de", "loto"}:
        raise ValueError("mode phải là de hoặc loto")
    if any(date.fromisoformat(day).isoformat() != day for day in days):
        raise ValueError("ngày phải có định dạng ISO YYYY-MM-DD")
    y = np.asarray(y, dtype=float)
    if y.shape != (len(days), 100):
        raise ValueError("nhãn phải khớp số ngày và đủ 100 số")
    if not np.isfinite(y).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("nhãn mọi lát phải hữu hạn và nhị phân")
    if mode == "de" and not np.all(y.sum(axis=1) == 1):
        raise ValueError("mỗi kỳ Đặc Biệt phải có đúng một nhãn dương")
    arrays = {name: np.asarray(arrays[name], dtype=float) for name in COMPONENT_COLS}
    for values in arrays.values():
        if values.shape != (len(days), 100):
            raise ValueError("thành phần phải khớp số ngày và đủ 100 số")
        if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
            raise ValueError("xác suất mọi lát phải hữu hạn trong [0, 1]")
    split = max(1, int(np.floor(len(days) * 0.6)))
    weight_arrays = {name: values[:split] for name, values in arrays.items()}
    weights, promotion = learn_with_holdout(
        mode, weight_arrays, y[:split], days[:split], half_life_draws, incumbent
    )
    if promotion.validation_days < MIN_VALIDATION_DAYS:
        weights = DEFAULT_ENSEMBLE_WEIGHTS
    tail = {name: values[split:] for name, values in arrays.items()}
    raw = _blend(tail, _weight_vector(weights))
    probs = (np.vstack([finalize_blend(row, mode) for row in raw])
             if len(raw) else clip01(raw, eps=1e-6))
    params, calibration_audit = select_calibration(
        mode, probs, y[split:], _day_weights(days[split:], half_life_draws)
        if days[split:] else None,
    )
    boundaries = {
        "weight_days": split,
        "calibration_days": len(days) - split,
        "weight_first_day": days[0],
        "weight_last_day": days[split - 1],
        "calibration_first_day": days[split] if split < len(days) else None,
        "calibration_last_day": days[-1] if split < len(days) else None,
        "disjoint": True,
    }
    return weights, promotion, params, calibration_audit, boundaries


def main() -> None:
    ap = argparse.ArgumentParser(description="Learn five-component ensemble weights from labeled walk-forward history.")
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--history-dir", default="data/evaluation/history")
    ap.add_argument("--out-dir", default="data/ensemble")
    ap.add_argument("--window-days", type=int, default=180)
    ap.add_argument("--min-days", type=int, default=20)
    ap.add_argument("--half-life-days", type=int, default=45)
    args = ap.parse_args()

    hist = Path(args.history_dir) / f"pred_{args.mode}.csv"
    if not hist.exists():
        print(f"[SKIP] history not found: {hist}")
        return
    df = pd.read_csv(hist)
    days = _select_recent_complete_days(df, args.window_days, mode=args.mode)
    if len(days) < args.min_days:
        print(f"[SKIP] five-component labeled history not mature: {len(days)} < {args.min_days}; keeping current/default weights")
        return

    arrays, y, day_list = _stack_days(df, days)
    out_dir = Path(args.out_dir)
    incumbent = load_ensemble_weights(out_dir.parent, args.mode)
    final_w, audit, calib, calib_audit, boundaries = learn_chronological_stack(
        args.mode, arrays, y, day_list, args.half_life_days, incumbent
    )

    w_day = _day_weights(day_list, args.half_life_days)
    in_sample_ll, in_sample_br = (
        float(np.average(values, weights=w_day))
        for values in _daily_scores(args.mode, _blend(arrays, _weight_vector(final_w)), y)
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    weights_path = out_dir / f"weights_{args.mode}.json"
    payload = {
        "schema_version": 8,
        "mode": args.mode,
        "learned_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window_days": args.window_days,
        "half_life_days": args.half_life_days,
        "days_used": day_list,
        "component_availability_required": True,
        "metric": {"logloss": in_sample_ll, "brier": in_sample_br},
        "promotion": asdict(audit),
        "chronological_split": boundaries,
        "weights": final_w.as_dict(),
    }
    weights_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] five-component weights for {args.mode} -> {weights_path}")
    print(f"[OK] {audit.describe()}")

    calib_path = out_dir / f"calibration_{args.mode}.json"
    calib_payload = {
        "schema_version": 8,
        "mode": args.mode,
        "learned_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window_days": args.window_days,
        "half_life_days": args.half_life_days,
        "component_availability_required": True,
        "params": calib.as_dict(),
        "chronological_split": boundaries,
        "selection": {
            "chosen": calib_audit.chosen,
            "selected": calib_audit.selected,
            "brier_by_candidate": calib_audit.brier_by_candidate,
            "fit_days": calib_audit.fit_days,
            "holdout_days": calib_audit.holdout_days,
        },
    }
    calib_path.write_text(json.dumps(calib_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] calibration -> {calib_path}")
    print(f"[OK] {calib_audit.describe()}")


if __name__ == "__main__":
    main()
