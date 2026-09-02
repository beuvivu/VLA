from __future__ import annotations

"""Validation-gated domain challenger for the production cầu-kèo model.

The baseline model in :mod:`cau_keo_ml` remains the champion.  This module adds
Vietnamese lottery-domain relations only through leakage-safe, measurable
features and promotes them into production probabilities only when they show
positive out-of-sample skill.

Chronological gate:
- folds 1-2: screen each feature group independently versus the same baseline;
- fold 3: confirm each screened group on later unseen dates;
- fold 4: evaluate the combined confirmed challenger on an untouched final fold;
- production blend is enabled only when both Brier and LogLoss skill are > 0.

No deterministic relation (cặp/bộ/bóng/chạm/tổng) is treated as evidence of
predictability by itself.  The relation merely defines candidate features.
"""

import argparse
import csv
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss

from cau_keo_ml import (
    FEATURE_COLS,
    CauKeoConfig,
    _add_ai_judgement,
    _downsample,
    build_cau_keo_feature_frame,
    run as run_baseline,
)
from ml_models import PlattCalibratedClassifier
from number_reference import (
    bo,
    bo_family_id,
    bong_am,
    bong_duong,
    cap_loto_50_kind,
    cap_loto_50_partner,
    dan_cham,
    dan_tong_mod10,
)

Mode = Literal["loto", "de"]
DOMAIN_SCHEMA_VERSION = 1
POSITIVE_SKILL_EPS = 1e-4
N_FOLDS = 4
DEFAULT_VAL_DAYS = 30
DEFAULT_CALIB_DAYS = 30
MIN_TRAIN_DAYS = 90

logger = logging.getLogger(__name__)

NUMBERS = np.arange(100, dtype=np.int16)
CAP50_PARTNER = np.array([int(cap_loto_50_partner(int(n))) for n in NUMBERS], dtype=np.int16)
BONG_DUONG_PARTNER = np.array([int(bong_duong(int(n))) for n in NUMBERS], dtype=np.int16)
BONG_AM_PARTNER = np.array([int(bong_am(int(n))) for n in NUMBERS], dtype=np.int16)
CAP50_IS_KEP_BONG = np.array(
    [1 if cap_loto_50_kind(int(n)) == "kep_bong" else 0 for n in NUMBERS],
    dtype=np.int8,
)
BO_FAMILY_IDS = np.array([bo_family_id(int(n)) for n in NUMBERS], dtype=object)
BO_MEMBERS = [np.array(sorted(int(x) for x in bo(int(n))), dtype=np.int16) for n in NUMBERS]
CHAM_MEMBERS = [
    np.array(sorted(int(x) for x in set(dan_cham(int(n) // 10)) | set(dan_cham(int(n) % 10))), dtype=np.int16)
    for n in NUMBERS
]
TONG_MEMBERS = [
    np.array([int(x) for x in dan_tong_mod10((int(n) // 10 + int(n) % 10) % 10)], dtype=np.int16)
    for n in NUMBERS
]


def _mean_matrix(groups: list[np.ndarray]) -> np.ndarray:
    out = np.zeros((100, 100), dtype=np.float32)
    for n, members in enumerate(groups):
        out[n, members] = 1.0 / float(len(members))
    return out


BO_MEAN = _mean_matrix(BO_MEMBERS)
CHAM_MEAN = _mean_matrix(CHAM_MEMBERS)
TONG_MEAN = _mean_matrix(TONG_MEMBERS)

PARTNER_FEATURES = [
    "cap50_partner_hit_today",
    "cap50_partner_freq_7d",
    "cap50_partner_freq_30d",
    "cap50_partner_freq_90d",
    "cap50_partner_freq_365d",
    "cap50_partner_gap",
    "cap50_pair_freq_30_mean",
    "cap50_pair_freq_90_mean",
    "cap50_pair_freq_365_mean",
    "cap50_pair_balance_30d",
    "cap50_pair_balance_90d",
    "cap50_pair_balance_365d",
    "cap50_is_kep_bong",
]
BO_FEATURES = [
    "bo_family_size",
    "bo_hit_today_rate",
    "bo_freq_7d_mean",
    "bo_freq_30d_mean",
    "bo_freq_90d_mean",
    "bo_freq_365d_mean",
    "bo_gap_mean",
    "bo_path_support_mean",
]
BONG_FEATURES = [
    "bong_duong_hit_today",
    "bong_duong_freq_7d",
    "bong_duong_freq_30d",
    "bong_duong_gap",
    "bong_am_hit_today",
    "bong_am_freq_7d",
    "bong_am_freq_30d",
    "bong_am_gap",
]
CHAM_FEATURES = [
    "cham_hit_today_rate",
    "cham_freq_7d_mean",
    "cham_freq_30d_mean",
    "cham_freq_90d_mean",
    "cham_gap_mean",
    "cham_path_support_mean",
]
TONG_FEATURES = [
    "tong_hit_today_rate",
    "tong_freq_7d_mean",
    "tong_freq_30d_mean",
    "tong_freq_90d_mean",
    "tong_gap_mean",
    "tong_path_support_mean",
]

DOMAIN_FEATURE_GROUPS: dict[str, list[str]] = {
    "partner_cap50": PARTNER_FEATURES,
    "bo": BO_FEATURES,
    "bong": BONG_FEATURES,
    "cham": CHAM_FEATURES,
    "tong": TONG_FEATURES,
}
ALL_DOMAIN_FEATURES = [
    feature
    for group in DOMAIN_FEATURE_GROUPS.values()
    for feature in group
]


@dataclass(frozen=True)
class FoldSpec:
    fold: int
    calib_start: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp | None

    def as_dict(self) -> dict[str, object]:
        return {
            "fold": self.fold,
            "calib_start": self.calib_start.date().isoformat(),
            "val_start": self.val_start.date().isoformat(),
            "val_end_exclusive": self.val_end.date().isoformat() if self.val_end is not None else None,
        }


def _balance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = np.maximum(np.maximum(a.astype(float), b.astype(float)), 1.0)
    return np.clip(1.0 - np.abs(a.astype(float) - b.astype(float)) / denom, 0.0, 1.0)


def _validate_anchor_layout(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "anchor_date",
        "number",
        "freq_7d",
        "freq_30d",
        "freq_90d",
        "freq_365d",
        "gap",
        "hit_today",
        "path_support",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"domain challenger missing base feature columns: {sorted(missing)}")

    ordered = frame.copy()
    ordered["number"] = pd.to_numeric(ordered["number"], errors="raise").astype(int)
    ordered = ordered.sort_values(["anchor_date", "number"]).copy()
    counts = ordered.groupby("anchor_date", sort=False)["number"].nunique()
    if counts.empty or not bool((counts == 100).all()):
        raise ValueError("every anchor_date must contain exactly 100 unique numbers")
    expected = np.tile(np.arange(100, dtype=int), len(counts))
    actual = ordered["number"].to_numpy(dtype=int)
    if not np.array_equal(actual, expected):
        raise ValueError("each anchor_date must contain the complete ordered 00..99 universe")
    return ordered


def augment_domain_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add leakage-safe domain relation features to a base cầu-kèo frame.

    All inputs already describe information available at the row's anchor day.
    Partner/family/chạm/tổng transforms only combine rows from that same anchor,
    so no target-day information is introduced.
    """

    if frame.empty:
        return frame.copy()

    original_index = frame.index
    ordered = _validate_anchor_layout(frame)
    n_anchors = ordered["anchor_date"].nunique()

    def matrix(col: str) -> np.ndarray:
        return pd.to_numeric(ordered[col], errors="raise").to_numpy(dtype=float).reshape(n_anchors, 100)

    hit = matrix("hit_today")
    f7 = matrix("freq_7d")
    f30 = matrix("freq_30d")
    f90 = matrix("freq_90d")
    f365 = matrix("freq_365d")
    gap = matrix("gap")
    path = matrix("path_support")

    def put(name: str, values: np.ndarray) -> None:
        ordered[name] = np.asarray(values).reshape(-1)

    partner_f7 = f7[:, CAP50_PARTNER]
    partner_f30 = f30[:, CAP50_PARTNER]
    partner_f90 = f90[:, CAP50_PARTNER]
    partner_f365 = f365[:, CAP50_PARTNER]
    put("cap50_partner_hit_today", hit[:, CAP50_PARTNER])
    put("cap50_partner_freq_7d", partner_f7)
    put("cap50_partner_freq_30d", partner_f30)
    put("cap50_partner_freq_90d", partner_f90)
    put("cap50_partner_freq_365d", partner_f365)
    put("cap50_partner_gap", gap[:, CAP50_PARTNER])
    put("cap50_pair_freq_30_mean", (f30 + partner_f30) / 2.0)
    put("cap50_pair_freq_90_mean", (f90 + partner_f90) / 2.0)
    put("cap50_pair_freq_365_mean", (f365 + partner_f365) / 2.0)
    put("cap50_pair_balance_30d", _balance(f30, partner_f30))
    put("cap50_pair_balance_90d", _balance(f90, partner_f90))
    put("cap50_pair_balance_365d", _balance(f365, partner_f365))
    put("cap50_is_kep_bong", np.tile(CAP50_IS_KEP_BONG, (n_anchors, 1)))

    put("bo_family_size", np.tile(np.array([len(x) for x in BO_MEMBERS], dtype=float), (n_anchors, 1)))
    put("bo_hit_today_rate", hit @ BO_MEAN.T)
    put("bo_freq_7d_mean", f7 @ BO_MEAN.T)
    put("bo_freq_30d_mean", f30 @ BO_MEAN.T)
    put("bo_freq_90d_mean", f90 @ BO_MEAN.T)
    put("bo_freq_365d_mean", f365 @ BO_MEAN.T)
    put("bo_gap_mean", gap @ BO_MEAN.T)
    put("bo_path_support_mean", path @ BO_MEAN.T)

    put("bong_duong_hit_today", hit[:, BONG_DUONG_PARTNER])
    put("bong_duong_freq_7d", f7[:, BONG_DUONG_PARTNER])
    put("bong_duong_freq_30d", f30[:, BONG_DUONG_PARTNER])
    put("bong_duong_gap", gap[:, BONG_DUONG_PARTNER])
    put("bong_am_hit_today", hit[:, BONG_AM_PARTNER])
    put("bong_am_freq_7d", f7[:, BONG_AM_PARTNER])
    put("bong_am_freq_30d", f30[:, BONG_AM_PARTNER])
    put("bong_am_gap", gap[:, BONG_AM_PARTNER])

    put("cham_hit_today_rate", hit @ CHAM_MEAN.T)
    put("cham_freq_7d_mean", f7 @ CHAM_MEAN.T)
    put("cham_freq_30d_mean", f30 @ CHAM_MEAN.T)
    put("cham_freq_90d_mean", f90 @ CHAM_MEAN.T)
    put("cham_gap_mean", gap @ CHAM_MEAN.T)
    put("cham_path_support_mean", path @ CHAM_MEAN.T)

    put("tong_hit_today_rate", hit @ TONG_MEAN.T)
    put("tong_freq_7d_mean", f7 @ TONG_MEAN.T)
    put("tong_freq_30d_mean", f30 @ TONG_MEAN.T)
    put("tong_freq_90d_mean", f90 @ TONG_MEAN.T)
    put("tong_gap_mean", gap @ TONG_MEAN.T)
    put("tong_path_support_mean", path @ TONG_MEAN.T)

    ordered["cap50_partner"] = np.tile([f"{n:02d}" for n in CAP50_PARTNER], n_anchors)
    ordered["cap50_pair_kind"] = np.tile(
        [cap_loto_50_kind(int(n)) for n in NUMBERS], n_anchors
    )
    ordered["bo_family_id"] = np.tile(BO_FAMILY_IDS, n_anchors)
    ordered["bong_duong_partner"] = np.tile([f"{n:02d}" for n in BONG_DUONG_PARTNER], n_anchors)
    ordered["bong_am_partner"] = np.tile([f"{n:02d}" for n in BONG_AM_PARTNER], n_anchors)

    # Restore the caller's original row order/index.
    ordered = ordered.sort_index()
    if not ordered.index.equals(original_index):
        ordered = ordered.reindex(original_index)
    return ordered


def _make_folds(anchor_days: pd.DatetimeIndex) -> list[FoldSpec]:
    days = pd.DatetimeIndex(sorted(pd.to_datetime(anchor_days).normalize().unique()))
    available = len(days) - MIN_TRAIN_DAYS - DEFAULT_CALIB_DAYS
    val_days = min(DEFAULT_VAL_DAYS, available // N_FOLDS)
    if val_days < 15:
        raise RuntimeError(
            f"Need more history for 4-fold domain ablation: {len(days)} anchor days"
        )

    folds: list[FoldSpec] = []
    for idx in range(N_FOLDS):
        val_start_idx = len(days) - (N_FOLDS - idx) * val_days
        val_end_idx = val_start_idx + val_days
        calib_start_idx = val_start_idx - DEFAULT_CALIB_DAYS
        if calib_start_idx < MIN_TRAIN_DAYS:
            raise RuntimeError("insufficient pre-calibration training history")
        val_end = days[val_end_idx] if val_end_idx < len(days) else None
        folds.append(
            FoldSpec(
                fold=idx + 1,
                calib_start=days[calib_start_idx],
                val_start=days[val_start_idx],
                val_end=val_end,
            )
        )
    return folds


def _new_model(seed: int) -> PlattCalibratedClassifier:
    return PlattCalibratedClassifier(
        base=HistGradientBoostingClassifier(
            max_depth=4,
            learning_rate=0.045,
            max_iter=180,
            l2_regularization=0.35,
            early_stopping=True,
            random_state=seed,
        )
    )


def _fold_masks(frame: pd.DataFrame, fold: FoldSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dates = pd.to_datetime(frame["anchor_date"]).dt.normalize()
    train = (dates < fold.calib_start).to_numpy()
    calib = ((dates >= fold.calib_start) & (dates < fold.val_start)).to_numpy()
    valid_s = dates >= fold.val_start
    if fold.val_end is not None:
        valid_s &= dates < fold.val_end
    valid = valid_s.to_numpy()
    return train, calib, valid


def _metrics(y_true: np.ndarray, prob: np.ndarray) -> tuple[float, float]:
    p = np.clip(np.asarray(prob, dtype=float), 1e-9, 1.0 - 1e-9)
    brier = float(brier_score_loss(y_true, p))
    ll = float(log_loss(y_true, np.column_stack([1.0 - p, p]), labels=[0, 1]))
    return brier, ll


def _fit_fold(
    frame: pd.DataFrame,
    y: np.ndarray,
    *,
    features: list[str],
    fold: FoldSpec,
    mode: Mode,
    seed: int,
) -> tuple[float, float]:
    train_mask, calib_mask, val_mask = _fold_masks(frame, fold)
    if min(int(train_mask.sum()), int(calib_mask.sum()), int(val_mask.sum())) <= 0:
        raise RuntimeError(f"empty chronological split in fold {fold.fold}")

    values = frame[features].astype(np.float32).to_numpy()
    X_train, y_train = values[train_mask], y[train_mask]
    X_cal, y_cal = values[calib_mask], y[calib_mask]
    X_val, y_val = values[val_mask], y[val_mask]
    neg_ratio = 22 if mode == "de" else 8
    X_train, y_train = _downsample(X_train, y_train, neg_ratio=neg_ratio, seed=seed)

    model = _new_model(seed)
    model.fit(X_train, y_train)
    p_cal = model.base_.predict_proba(X_cal)[:, 1]
    model.fit_platt(p_cal, y_cal)
    p_val = model.predict_proba(X_val)[:, 1]
    return _metrics(y_val, p_val)


def _skill(candidate: float, baseline: float) -> float:
    if not np.isfinite(candidate) or not np.isfinite(baseline) or baseline <= 0:
        return float("-inf")
    return float(1.0 - candidate / baseline)


def _row(
    *,
    mode: Mode,
    stage: str,
    fold: FoldSpec,
    candidate: str,
    features: list[str],
    baseline_metrics: tuple[float, float],
    candidate_metrics: tuple[float, float],
) -> dict[str, object]:
    bb, bl = baseline_metrics
    cb, cl = candidate_metrics
    return {
        "mode": mode,
        "stage": stage,
        "fold": fold.fold,
        "candidate": candidate,
        "feature_count": len(features),
        "calib_start": fold.calib_start.date().isoformat(),
        "val_start": fold.val_start.date().isoformat(),
        "val_end_exclusive": fold.val_end.date().isoformat() if fold.val_end is not None else "",
        "baseline_brier": bb,
        "candidate_brier": cb,
        "brier_skill": _skill(cb, bb),
        "baseline_logloss": bl,
        "candidate_logloss": cl,
        "logloss_skill": _skill(cl, bl),
    }


def _positive_pair(brier_skill: float, logloss_skill: float) -> bool:
    return brier_skill > POSITIVE_SKILL_EPS and logloss_skill > POSITIVE_SKILL_EPS


def _trust_from_skill(brier_skill: float, logloss_skill: float) -> float:
    if not _positive_pair(brier_skill, logloss_skill):
        return 0.0
    strength = min(float(brier_skill), float(logloss_skill))
    return float(np.clip(5.0 * strength, 0.05, 0.30))


def walk_forward_ablation(
    frame: pd.DataFrame,
    y: pd.Series,
    *,
    mode: Mode,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run four chronological folds with selection/confirmation/final gate."""

    data = frame.copy()
    data["anchor_date"] = pd.to_datetime(data["anchor_date"]).dt.normalize()
    target = y.to_numpy(dtype=int)
    days = pd.DatetimeIndex(sorted(data["anchor_date"].unique()))
    folds = _make_folds(days)

    baseline_by_fold: dict[int, tuple[float, float]] = {}
    rows: list[dict[str, object]] = []
    for fold in folds:
        metrics = _fit_fold(
            data,
            target,
            features=list(FEATURE_COLS),
            fold=fold,
            mode=mode,
            seed=20260920 + fold.fold,
        )
        baseline_by_fold[fold.fold] = metrics
        rows.append(
            _row(
                mode=mode,
                stage="baseline",
                fold=fold,
                candidate="baseline",
                features=list(FEATURE_COLS),
                baseline_metrics=metrics,
                candidate_metrics=metrics,
            )
        )

    screen_summary: dict[str, dict[str, float]] = {}
    screened: list[str] = []
    for group, group_features in DOMAIN_FEATURE_GROUPS.items():
        feature_set = list(FEATURE_COLS) + list(group_features)
        group_rows: list[dict[str, object]] = []
        for fold in folds[:2]:
            metrics = _fit_fold(
                data,
                target,
                features=feature_set,
                fold=fold,
                mode=mode,
                seed=20261000 + 100 * list(DOMAIN_FEATURE_GROUPS).index(group) + fold.fold,
            )
            r = _row(
                mode=mode,
                stage="screen",
                fold=fold,
                candidate=group,
                features=feature_set,
                baseline_metrics=baseline_by_fold[fold.fold],
                candidate_metrics=metrics,
            )
            rows.append(r)
            group_rows.append(r)

        mean_brier = float(np.mean([float(r["brier_skill"]) for r in group_rows]))
        mean_ll = float(np.mean([float(r["logloss_skill"]) for r in group_rows]))
        screen_summary[group] = {
            "mean_brier_skill": mean_brier,
            "mean_logloss_skill": mean_ll,
        }
        if _positive_pair(mean_brier, mean_ll):
            screened.append(group)

    confirmed: list[str] = []
    confirmation: dict[str, dict[str, float | bool]] = {}
    fold3 = folds[2]
    for group in screened:
        feature_set = list(FEATURE_COLS) + list(DOMAIN_FEATURE_GROUPS[group])
        metrics = _fit_fold(
            data,
            target,
            features=feature_set,
            fold=fold3,
            mode=mode,
            seed=20262000 + 100 * list(DOMAIN_FEATURE_GROUPS).index(group),
        )
        r = _row(
            mode=mode,
            stage="confirm",
            fold=fold3,
            candidate=group,
            features=feature_set,
            baseline_metrics=baseline_by_fold[fold3.fold],
            candidate_metrics=metrics,
        )
        rows.append(r)
        ok = _positive_pair(float(r["brier_skill"]), float(r["logloss_skill"]))
        confirmation[group] = {
            "brier_skill": float(r["brier_skill"]),
            "logloss_skill": float(r["logloss_skill"]),
            "confirmed": ok,
        }
        if ok:
            confirmed.append(group)

    fold4 = folds[3]
    all_features = list(FEATURE_COLS) + list(ALL_DOMAIN_FEATURES)
    all_metrics = _fit_fold(
        data,
        target,
        features=all_features,
        fold=fold4,
        mode=mode,
        seed=20263000,
    )
    all_row = _row(
        mode=mode,
        stage="final_diagnostic",
        fold=fold4,
        candidate="all_domain_groups",
        features=all_features,
        baseline_metrics=baseline_by_fold[fold4.fold],
        candidate_metrics=all_metrics,
    )
    rows.append(all_row)

    selected_features = list(FEATURE_COLS)
    for group in confirmed:
        selected_features.extend(DOMAIN_FEATURE_GROUPS[group])

    if confirmed:
        combined_metrics = _fit_fold(
            data,
            target,
            features=selected_features,
            fold=fold4,
            mode=mode,
            seed=20264000,
        )
        combined_row = _row(
            mode=mode,
            stage="final_gate",
            fold=fold4,
            candidate="confirmed_domain_groups",
            features=selected_features,
            baseline_metrics=baseline_by_fold[fold4.fold],
            candidate_metrics=combined_metrics,
        )
        rows.append(combined_row)
        final_brier_skill = float(combined_row["brier_skill"])
        final_ll_skill = float(combined_row["logloss_skill"])
        active = _positive_pair(final_brier_skill, final_ll_skill)
    else:
        combined_row = None
        final_brier_skill = 0.0
        final_ll_skill = 0.0
        active = False

    trust = _trust_from_skill(final_brier_skill, final_ll_skill) if active else 0.0
    report = pd.DataFrame(rows)
    gate: dict[str, object] = {
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "mode": mode,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "positive_skill_threshold": POSITIVE_SKILL_EPS,
        "folds": [fold.as_dict() for fold in folds],
        "feature_groups": DOMAIN_FEATURE_GROUPS,
        "screen_summary": screen_summary,
        "screened_groups": screened,
        "confirmation": confirmation,
        "confirmed_groups": confirmed,
        "selected_features": selected_features if active else list(FEATURE_COLS),
        "final_brier_skill": final_brier_skill,
        "final_logloss_skill": final_ll_skill,
        "all_groups_final_brier_skill": float(all_row["brier_skill"]),
        "all_groups_final_logloss_skill": float(all_row["logloss_skill"]),
        "domain_active": bool(active),
        "domain_trust": trust,
        "policy": (
            "A domain feature group can affect production only after positive OOS Brier and "
            "LogLoss skill in screening, confirmation, and the untouched combined final gate."
        ),
    }
    if combined_row is None:
        gate["reason"] = "no individual domain feature group survived confirmation"
    elif not active:
        gate["reason"] = "combined confirmed challenger did not beat baseline on both final OOS metrics"
    else:
        gate["reason"] = "confirmed challenger passed the untouched final OOS gate"
    return report, gate


def _fit_final_challenger(
    frame: pd.DataFrame,
    y: pd.Series,
    *,
    mode: Mode,
    features: list[str],
) -> PlattCalibratedClassifier:
    data = frame.copy()
    data["anchor_date"] = pd.to_datetime(data["anchor_date"]).dt.normalize()
    days = pd.DatetimeIndex(sorted(data["anchor_date"].unique()))
    if len(days) <= DEFAULT_CALIB_DAYS + MIN_TRAIN_DAYS:
        raise RuntimeError("insufficient history to fit final domain challenger")
    calib_start = days[-DEFAULT_CALIB_DAYS]
    train_mask = (data["anchor_date"] < calib_start).to_numpy()
    calib_mask = (data["anchor_date"] >= calib_start).to_numpy()
    values = data[features].astype(np.float32).to_numpy()
    target = y.to_numpy(dtype=int)
    X_train, y_train = values[train_mask], target[train_mask]
    X_cal, y_cal = values[calib_mask], target[calib_mask]
    neg_ratio = 22 if mode == "de" else 8
    X_train, y_train = _downsample(
        X_train,
        y_train,
        neg_ratio=neg_ratio,
        seed=20265000 if mode == "loto" else 20265001,
    )
    model = _new_model(20265000 if mode == "loto" else 20265001)
    model.fit(X_train, y_train)
    model.fit_platt(model.base_.predict_proba(X_cal)[:, 1], y_cal)
    return model


def _write_prediction_outputs(
    pred: pd.DataFrame,
    *,
    mode: Mode,
    out_dir: Path,
    top: int,
) -> list[Path]:
    base_cols = [
        "predict_for_date",
        "anchor_date",
        "mode",
        "number_str",
        "number",
        "prob",
        "prob_percent",
        "ml_prob_raw",
        "ml_prob_baseline",
        "ml_prob_domain",
        "domain_prob_edge",
        "domain_trust",
        "domain_active",
        "domain_groups",
        "cap50_partner",
        "cap50_pair_kind",
        "bo_family_id",
        "bong_duong_partner",
        "bong_am_partner",
        "cau_score",
        "score_band",
        "primary_reason",
        "reason_1",
        "reason_2",
        "reason_3",
        "evidence",
        "freq_7d",
        "freq_30d",
        "freq_90d",
        "gap",
        "loto_occ_today",
        "same_weekday_freq_364",
        "path_support",
        "cond_de_rate",
        "cond_loto_mean_rate",
        "cond_loto_max_rate",
        "reverse_hit_today",
        "is_reverse_prev_special",
        "is_bong_prev_special",
        "cham_overlap_prev_special",
        "trend_7_vs_30",
        "note",
    ]
    cols = [c for c in base_cols if c in pred.columns]
    all_path = out_dir / f"cau_keo_{mode}_all.csv"
    top_path = out_dir / f"cau_keo_{mode}_top{top}.csv"
    pred[cols].to_csv(all_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    pred.head(top)[cols].to_csv(top_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    return [all_path, top_path]


def _ensure_baseline(
    *,
    mode: Mode,
    models_dir: Path,
    out_dir: Path,
    config: CauKeoConfig,
) -> None:
    model_path = models_dir / f"cau_keo_{mode}.joblib"
    output_path = out_dir / f"cau_keo_{mode}_all.csv"
    if model_path.exists() and output_path.exists():
        return
    run_baseline(
        mode=mode,
        models_dir=models_dir,
        out_dir=out_dir,
        config=config,
        force_train=False,
    )


def run_mode(
    mode: Mode,
    *,
    models_dir: Path,
    out_dir: Path,
    config: CauKeoConfig,
) -> list[Path]:
    _ensure_baseline(mode=mode, models_dir=models_dir, out_dir=out_dir, config=config)
    model_path = models_dir / f"cau_keo_{mode}.joblib"
    pack = joblib.load(model_path)
    if pack.get("features") != FEATURE_COLS:
        raise RuntimeError(f"baseline feature schema mismatch for {mode}")

    X_train, y_train = build_cau_keo_feature_frame(
        mode, include_target=True, config=config
    )
    if y_train is None:
        raise RuntimeError("missing supervised target")
    X_aug = augment_domain_features(X_train)
    ablation, gate = walk_forward_ablation(X_aug, y_train, mode=mode)

    active = bool(gate["domain_active"])
    trust = float(gate["domain_trust"])
    selected_groups = list(gate["confirmed_groups"]) if active else []
    selected_features = list(FEATURE_COLS)
    for group in selected_groups:
        selected_features.extend(DOMAIN_FEATURE_GROUPS[str(group)])

    challenger = (
        _fit_final_challenger(
            X_aug,
            y_train,
            mode=mode,
            features=selected_features,
        )
        if active
        else None
    )

    X_pred, _ = build_cau_keo_feature_frame(
        mode, include_target=False, config=config
    )
    latest_anchor = sorted(X_pred["anchor_date"].astype(str).unique())[-1]
    X_pred = X_pred[X_pred["anchor_date"].astype(str) == latest_anchor].copy()
    X_pred = augment_domain_features(X_pred).reset_index(drop=True)

    baseline_model = pack["model"]
    p_baseline = baseline_model.predict_proba(
        X_pred[FEATURE_COLS].astype(np.float32).to_numpy()
    )[:, 1]
    if challenger is not None:
        p_domain = challenger.predict_proba(
            X_pred[selected_features].astype(np.float32).to_numpy()
        )[:, 1]
    else:
        p_domain = p_baseline.copy()

    p_prod = (1.0 - trust) * p_baseline + trust * p_domain
    X_pred["ml_prob_baseline"] = p_baseline
    X_pred["ml_prob_domain"] = p_domain
    X_pred["domain_prob_edge"] = p_domain - p_baseline
    X_pred["domain_trust"] = trust
    X_pred["domain_active"] = active
    X_pred["domain_groups"] = "|".join(selected_groups) if selected_groups else ""
    X_pred["ml_prob_raw"] = p_prod
    judged = _add_ai_judgement(X_pred, mode=mode)

    out_dir.mkdir(parents=True, exist_ok=True)
    created = _write_prediction_outputs(judged, mode=mode, out_dir=out_dir, top=config.top)
    ablation_path = out_dir / f"cau_keo_domain_ablation_{mode}.csv"
    gate_path = out_dir / f"cau_keo_domain_gate_{mode}.json"
    ablation.to_csv(ablation_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    gate.update(
        {
            "anchor_date": latest_anchor,
            "predict_for_date": str(judged["predict_for_date"].iloc[0]),
            "production_selected_groups": selected_groups,
            "production_feature_count": len(selected_features),
            "baseline_feature_count": len(FEATURE_COLS),
        }
    )
    gate_path.write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    created.extend([ablation_path, gate_path])

    pack["domain_schema_version"] = DOMAIN_SCHEMA_VERSION
    pack["domain_active"] = active
    pack["domain_trust"] = trust
    pack["domain_groups"] = selected_groups
    pack["domain_features"] = selected_features if active else list(FEATURE_COLS)
    pack["domain_challenger_model"] = challenger
    pack["domain_gate"] = {
        "final_brier_skill": float(gate["final_brier_skill"]),
        "final_logloss_skill": float(gate["final_logloss_skill"]),
        "reason": gate["reason"],
    }
    pack["domain_trained_through_date"] = str(
        pd.to_datetime(X_train["anchor_date"]).max().date()
    )
    joblib.dump(pack, model_path)

    manifest_path = out_dir / f"cau_keo_manifest_{mode}.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            manifest = {}
    manifest["domain_challenger"] = {
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "active": active,
        "trust": trust,
        "selected_groups": selected_groups,
        "selected_features": selected_features if active else list(FEATURE_COLS),
        "ablation_report": ablation_path.name,
        "gate_report": gate_path.name,
        "final_brier_skill": float(gate["final_brier_skill"]),
        "final_logloss_skill": float(gate["final_logloss_skill"]),
        "policy": gate["policy"],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    created.append(manifest_path)

    logger.info(
        "Domain challenger %s: active=%s trust=%.3f groups=%s BrierSkill=%.4f%% LogLossSkill=%.4f%%",
        mode,
        active,
        trust,
        selected_groups,
        100.0 * float(gate["final_brier_skill"]),
        100.0 * float(gate["final_logloss_skill"]),
    )
    return created


def run(
    *,
    mode: Mode | Literal["both"] = "both",
    models_dir: Path | str = "models",
    out_dir: Path | str = "data/ai_ml",
    config: CauKeoConfig | None = None,
) -> list[Path]:
    cfg = config or CauKeoConfig()
    models = Path(models_dir)
    out = Path(out_dir)
    modes: list[Mode] = ["loto", "de"] if mode == "both" else [mode]
    created: list[Path] = []
    for current in modes:
        created.extend(
            run_mode(
                current,
                models_dir=models,
                out_dir=out,
                config=cfg,
            )
        )
    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run validation-gated partner/cặp50/bộ/bóng/chạm/tổng cầu-kèo challenger."
    )
    parser.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--out-dir", default="data/ai_ml")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--window-days", type=int, default=2000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--lag-max", type=int, default=30)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = CauKeoConfig(
        min_history_days=args.min_history_days,
        lag_max_for_path_support=args.lag_max,
        window_days=args.window_days,
        top=args.top,
    )
    for path in run(
        mode=args.mode,
        models_dir=args.models_dir,
        out_dir=args.out_dir,
        config=config,
    ):
        print(f"[OK] {path}")


if __name__ == "__main__":
    main()
