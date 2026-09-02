from __future__ import annotations

"""Scientifically gated domain-feature challenger for production cầu-kèo ML.

The production baseline in :mod:`cau_keo_ml` remains the champion. Vietnamese
lottery-domain relations are treated as experimental feature hypotheses only.
They can affect production probabilities only after strict chronological
out-of-sample comparison, paired draw-cluster bootstrap uncertainty, and an
explicit feature allowlist.

Protocol
--------
* folds 1-2: development screening of each feature family;
* fold 3: independent family confirmation with paired date-level bootstrap;
* fold 4: untouched combined holdout;
* the exact fixed-trust production blend is scored on fold 4;
* promotion requires positive Brier and LogLoss skill and both 95% confidence
  interval lower bounds strictly above zero.

All baseline/challenger fits within a fold use identical dates, target rows,
negative-sample indices, hyperparameters and random seed. The only intended
change is the challenger feature set.
"""

import argparse
import csv
import hashlib
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

from cau_keo_ml import (
    FEATURE_COLS,
    CauKeoConfig,
    _add_ai_judgement,
    build_cau_keo_feature_frame,
    run as run_baseline,
)
from ml_models import PlattCalibratedClassifier
from ml_validation import (
    BootstrapConfig,
    ImprovementCI,
    LossPair,
    PromotionDecision,
    decide_promotion,
    paired_cluster_bootstrap,
    relative_skill,
    score_by_date,
)
from number_reference import (
    bo,
    bo_family_id,
    bong_am,
    bong_duong,
    cap_loto_50_kind,
    cap_loto_50_partner,
    dan_cham,
    dan_tong_mod10,
    reverse,
)

Mode = Literal["loto", "de"]
DOMAIN_SCHEMA_VERSION = 2
POSITIVE_SKILL_EPS = 0.0
N_FOLDS = 4
DEFAULT_VAL_DAYS = 30
DEFAULT_CALIB_DAYS = 30
MIN_TRAIN_DAYS = 90
DEFAULT_PRODUCTION_TRUST = 0.10

logger = logging.getLogger(__name__)

NUMBERS = np.arange(100, dtype=np.int16)
REVERSE_PARTNER = np.array([int(reverse(int(n))) for n in NUMBERS], dtype=np.int16)
CAP50_PARTNER = np.array(
    [int(cap_loto_50_partner(int(n))) for n in NUMBERS], dtype=np.int16
)
BONG_DUONG_PARTNER = np.array(
    [int(bong_duong(int(n))) for n in NUMBERS], dtype=np.int16
)
BONG_AM_PARTNER = np.array(
    [int(bong_am(int(n))) for n in NUMBERS], dtype=np.int16
)
CAP50_IS_KEP_BONG = np.array(
    [1 if cap_loto_50_kind(int(n)) == "kep_bong" else 0 for n in NUMBERS],
    dtype=np.int8,
)
BO_FAMILY_IDS = np.array([bo_family_id(int(n)) for n in NUMBERS], dtype=object)
BO_MEMBERS = [
    np.array(sorted(int(x) for x in bo(int(n))), dtype=np.int16) for n in NUMBERS
]
CHAM_MEMBERS = [
    np.array(
        sorted(
            int(x)
            for x in set(dan_cham(int(n) // 10)) | set(dan_cham(int(n) % 10))
        ),
        dtype=np.int16,
    )
    for n in NUMBERS
]
TONG_MEMBERS = [
    np.array(
        [int(x) for x in dan_tong_mod10((int(n) // 10 + int(n) % 10) % 10)],
        dtype=np.int16,
    )
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

# ``partner`` means the canonical lộn/reverse partner AB<->BA. ``cap_50`` is the
# distinct 50-pair partition: reverse pairs for non-doubles and five kép-bóng
# pairs 00-55, 11-66, 22-77, 33-88, 44-99. They are intentionally evaluated as
# separate hypotheses even though they coincide for the 90 non-double numbers.
PARTNER_FEATURES = [
    "partner_hit_today",
    "partner_freq_7d",
    "partner_freq_30d",
    "partner_freq_90d",
    "partner_freq_365d",
    "partner_gap",
    "partner_path_support",
]
CAP50_FEATURES = [
    "cap50_pair_hit_today_rate",
    "cap50_pair_freq_30_mean",
    "cap50_pair_freq_90_mean",
    "cap50_pair_freq_365_mean",
    "cap50_pair_gap_mean",
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
    "partner": PARTNER_FEATURES,
    "cap_50": CAP50_FEATURES,
    "bo": BO_FEATURES,
    "bong": BONG_FEATURES,
    "cham": CHAM_FEATURES,
    "tong": TONG_FEATURES,
}
ALL_DOMAIN_FEATURES = [
    feature for group in DOMAIN_FEATURE_GROUPS.values() for feature in group
]


@dataclass(frozen=True)
class DomainValidationConfig:
    bootstrap_replicates: int = 1000
    bootstrap_seed: int = 20260902
    promotion_ci: float = 0.95
    minimum_oos_dates: int = 30
    production_trust: float = DEFAULT_PRODUCTION_TRUST

    def validate(self) -> None:
        BootstrapConfig(
            replicates=self.bootstrap_replicates,
            seed=self.bootstrap_seed,
            confidence=self.promotion_ci,
            minimum_oos_dates=self.minimum_oos_dates,
        ).validate()
        if not 0.0 < self.production_trust <= 0.30:
            raise ValueError("production_trust must be in (0, 0.30]")

    def bootstrap(self, *, seed_offset: int = 0) -> BootstrapConfig:
        self.validate()
        return BootstrapConfig(
            replicates=self.bootstrap_replicates,
            seed=self.bootstrap_seed + int(seed_offset),
            confidence=self.promotion_ci,
            minimum_oos_dates=self.minimum_oos_dates,
        )


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
            "val_end_exclusive": (
                self.val_end.date().isoformat() if self.val_end is not None else None
            ),
            "model_seed": _fold_seed(self.fold),
        }


@dataclass(frozen=True)
class FoldPlan:
    fold: FoldSpec
    train_mask: np.ndarray
    calib_mask: np.ndarray
    val_mask: np.ndarray
    train_keep: np.ndarray
    seed: int
    sample_signature: str


@dataclass(frozen=True)
class FoldEvaluation:
    loss: LossPair
    dates: np.ndarray
    y: np.ndarray
    probability: np.ndarray
    rows: int
    oos_dates: int


def _balance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = np.maximum(np.maximum(a.astype(float), b.astype(float)), 1.0)
    return np.clip(
        1.0 - np.abs(a.astype(float) - b.astype(float)) / denom,
        0.0,
        1.0,
    )


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
        raise ValueError(
            f"domain challenger missing base feature columns: {sorted(missing)}"
        )

    ordered = frame.copy()
    ordered["number"] = pd.to_numeric(
        ordered["number"], errors="raise"
    ).astype(int)
    ordered = ordered.sort_values(["anchor_date", "number"]).copy()
    counts = ordered.groupby("anchor_date", sort=False)["number"].nunique()
    if counts.empty or not bool((counts == 100).all()):
        raise ValueError("every anchor_date must contain exactly 100 unique numbers")
    expected = np.tile(np.arange(100, dtype=int), len(counts))
    actual = ordered["number"].to_numpy(dtype=int)
    if not np.array_equal(actual, expected):
        raise ValueError(
            "each anchor_date must contain the complete ordered 00..99 universe"
        )
    return ordered


def augment_domain_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add same-anchor domain transforms without reading any future row."""
    if frame.empty:
        return frame.copy()

    original_index = frame.index
    ordered = _validate_anchor_layout(frame)
    n_anchors = ordered["anchor_date"].nunique()

    def matrix(col: str) -> np.ndarray:
        return (
            pd.to_numeric(ordered[col], errors="raise")
            .to_numpy(dtype=float)
            .reshape(n_anchors, 100)
        )

    hit = matrix("hit_today")
    f7 = matrix("freq_7d")
    f30 = matrix("freq_30d")
    f90 = matrix("freq_90d")
    f365 = matrix("freq_365d")
    gap = matrix("gap")
    path = matrix("path_support")

    def put(name: str, values: np.ndarray) -> None:
        ordered[name] = np.asarray(values).reshape(-1)

    # Canonical lộn/reverse partner family.
    put("partner_hit_today", hit[:, REVERSE_PARTNER])
    put("partner_freq_7d", f7[:, REVERSE_PARTNER])
    put("partner_freq_30d", f30[:, REVERSE_PARTNER])
    put("partner_freq_90d", f90[:, REVERSE_PARTNER])
    put("partner_freq_365d", f365[:, REVERSE_PARTNER])
    put("partner_gap", gap[:, REVERSE_PARTNER])
    put("partner_path_support", path[:, REVERSE_PARTNER])

    # Cặp-50 pair-level features. Raw reverse-partner columns are deliberately
    # not repeated here; this family measures the pair as a unit.
    cap_hit = hit[:, CAP50_PARTNER]
    cap_f30 = f30[:, CAP50_PARTNER]
    cap_f90 = f90[:, CAP50_PARTNER]
    cap_f365 = f365[:, CAP50_PARTNER]
    cap_gap = gap[:, CAP50_PARTNER]
    put("cap50_pair_hit_today_rate", (hit + cap_hit) / 2.0)
    put("cap50_pair_freq_30_mean", (f30 + cap_f30) / 2.0)
    put("cap50_pair_freq_90_mean", (f90 + cap_f90) / 2.0)
    put("cap50_pair_freq_365_mean", (f365 + cap_f365) / 2.0)
    put("cap50_pair_gap_mean", (gap + cap_gap) / 2.0)
    put("cap50_pair_balance_30d", _balance(f30, cap_f30))
    put("cap50_pair_balance_90d", _balance(f90, cap_f90))
    put("cap50_pair_balance_365d", _balance(f365, cap_f365))
    put(
        "cap50_is_kep_bong",
        np.tile(CAP50_IS_KEP_BONG, (n_anchors, 1)),
    )

    put(
        "bo_family_size",
        np.tile(
            np.array([len(x) for x in BO_MEMBERS], dtype=float),
            (n_anchors, 1),
        ),
    )
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

    ordered["partner"] = np.tile(
        [f"{n:02d}" for n in REVERSE_PARTNER], n_anchors
    )
    ordered["cap50_partner"] = np.tile(
        [f"{n:02d}" for n in CAP50_PARTNER], n_anchors
    )
    ordered["cap50_pair_kind"] = np.tile(
        [cap_loto_50_kind(int(n)) for n in NUMBERS], n_anchors
    )
    ordered["bo_family_id"] = np.tile(BO_FAMILY_IDS, n_anchors)
    ordered["bong_duong_partner"] = np.tile(
        [f"{n:02d}" for n in BONG_DUONG_PARTNER], n_anchors
    )
    ordered["bong_am_partner"] = np.tile(
        [f"{n:02d}" for n in BONG_AM_PARTNER], n_anchors
    )

    ordered = ordered.sort_index()
    if not ordered.index.equals(original_index):
        ordered = ordered.reindex(original_index)
    return ordered


def _make_folds(anchor_days: pd.DatetimeIndex) -> list[FoldSpec]:
    days = pd.DatetimeIndex(
        sorted(pd.to_datetime(anchor_days).normalize().unique())
    )
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


def _fold_seed(fold: int) -> int:
    return 20260920 + int(fold)


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


def _fold_masks(
    frame: pd.DataFrame,
    fold: FoldSpec,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dates = pd.to_datetime(frame["anchor_date"]).dt.normalize()
    train = (dates < fold.calib_start).to_numpy()
    calib = ((dates >= fold.calib_start) & (dates < fold.val_start)).to_numpy()
    valid_s = dates >= fold.val_start
    if fold.val_end is not None:
        valid_s &= dates < fold.val_end
    return train, calib, valid_s.to_numpy()


def _training_keep_indices(
    y_train: np.ndarray,
    *,
    neg_ratio: int,
    seed: int,
) -> np.ndarray:
    """Return one deterministic sample plan reused by every model in a fold."""
    target = np.asarray(y_train, dtype=int)
    pos = np.where(target == 1)[0]
    neg = np.where(target == 0)[0]
    if len(pos) == 0 or len(neg) == 0:
        return np.arange(len(target), dtype=int)
    n_neg = min(len(neg), len(pos) * int(neg_ratio))
    rng = np.random.default_rng(seed)
    selected_neg = rng.choice(neg, size=n_neg, replace=False)
    keep = np.concatenate([pos, selected_neg])
    rng.shuffle(keep)
    return keep.astype(int)


def _make_fold_plan(
    frame: pd.DataFrame,
    y: np.ndarray,
    *,
    fold: FoldSpec,
    mode: Mode,
) -> FoldPlan:
    train_mask, calib_mask, val_mask = _fold_masks(frame, fold)
    if min(
        int(train_mask.sum()), int(calib_mask.sum()), int(val_mask.sum())
    ) <= 0:
        raise RuntimeError(f"empty chronological split in fold {fold.fold}")
    train_y = np.asarray(y, dtype=int)[train_mask]
    seed = _fold_seed(fold.fold)
    keep = _training_keep_indices(
        train_y,
        neg_ratio=22 if mode == "de" else 8,
        seed=seed,
    )
    signature = hashlib.sha256(keep.tobytes()).hexdigest()[:16]
    return FoldPlan(
        fold=fold,
        train_mask=train_mask,
        calib_mask=calib_mask,
        val_mask=val_mask,
        train_keep=keep,
        seed=seed,
        sample_signature=signature,
    )


def _fit_fold(
    frame: pd.DataFrame,
    y: np.ndarray,
    *,
    features: list[str],
    plan: FoldPlan,
    mode: Mode,
) -> FoldEvaluation:
    """Fit one candidate using an immutable shared fold/sample plan."""
    values = frame[features].astype(np.float32).to_numpy()
    target = np.asarray(y, dtype=int)
    X_train_raw = values[plan.train_mask]
    y_train_raw = target[plan.train_mask]
    X_train = X_train_raw[plan.train_keep]
    y_train = y_train_raw[plan.train_keep]
    X_cal = values[plan.calib_mask]
    y_cal = target[plan.calib_mask]
    X_val = values[plan.val_mask]
    y_val = target[plan.val_mask]

    model = _new_model(plan.seed)
    model.fit(X_train, y_train)
    p_cal = model.base_.predict_proba(X_cal)[:, 1]
    model.fit_platt(p_cal, y_cal)
    p_val = model.predict_proba(X_val)[:, 1]
    dates = (
        pd.to_datetime(frame.loc[plan.val_mask, "anchor_date"])
        .dt.normalize()
        .astype(str)
        .to_numpy()
    )
    unique, brier, ll = score_by_date(mode, dates, p_val, y_val)
    loss = LossPair(brier=float(np.mean(brier)), logloss=float(np.mean(ll)))
    return FoldEvaluation(
        loss=loss,
        dates=dates,
        y=y_val,
        probability=p_val,
        rows=len(y_val),
        oos_dates=len(unique),
    )


def _combine_evaluations(
    mode: Mode,
    evaluations: list[FoldEvaluation],
) -> FoldEvaluation:
    if not evaluations:
        raise ValueError("at least one fold evaluation is required")
    dates = np.concatenate([x.dates for x in evaluations])
    y = np.concatenate([x.y for x in evaluations])
    p = np.concatenate([x.probability for x in evaluations])
    unique, brier, ll = score_by_date(mode, dates, p, y)
    return FoldEvaluation(
        loss=LossPair(float(np.mean(brier)), float(np.mean(ll))),
        dates=dates,
        y=y,
        probability=p,
        rows=len(y),
        oos_dates=len(unique),
    )


def _skill(candidate: float, baseline: float) -> float:
    value = relative_skill(baseline, candidate)
    return value if np.isfinite(value) else float("-inf")


def _positive_pair(brier_skill: float, logloss_skill: float) -> bool:
    return bool(
        np.isfinite(brier_skill)
        and np.isfinite(logloss_skill)
        and brier_skill > POSITIVE_SKILL_EPS
        and logloss_skill > POSITIVE_SKILL_EPS
    )


def _trust_from_skill(brier_skill: float, logloss_skill: float) -> float:
    """Backward-compatible helper; trust is fixed, never tuned on final holdout."""
    return DEFAULT_PRODUCTION_TRUST if _positive_pair(brier_skill, logloss_skill) else 0.0


def _row(
    *,
    mode: Mode,
    stage: str,
    fold: FoldSpec,
    candidate: str,
    features: list[str],
    baseline: FoldEvaluation,
    challenger: FoldEvaluation,
    plan: FoldPlan,
    ci: ImprovementCI | None = None,
    decision: PromotionDecision | None = None,
) -> dict[str, object]:
    bb, bl = baseline.loss.brier, baseline.loss.logloss
    cb, cl = challenger.loss.brier, challenger.loss.logloss
    row: dict[str, object] = {
        "mode": mode,
        "stage": stage,
        "fold": fold.fold,
        "candidate": candidate,
        "feature_count": len(features),
        "calib_start": fold.calib_start.date().isoformat(),
        "val_start": fold.val_start.date().isoformat(),
        "val_end_exclusive": (
            fold.val_end.date().isoformat() if fold.val_end is not None else ""
        ),
        "oos_dates": challenger.oos_dates,
        "oos_rows": challenger.rows,
        "model_seed": plan.seed,
        "training_sample_signature": plan.sample_signature,
        "baseline_brier": bb,
        "candidate_brier": cb,
        "brier_improvement": bb - cb,
        "brier_skill": _skill(cb, bb),
        "baseline_logloss": bl,
        "candidate_logloss": cl,
        "logloss_improvement": bl - cl,
        "logloss_skill": _skill(cl, bl),
        "brier_ci_low": np.nan,
        "brier_ci_high": np.nan,
        "logloss_ci_low": np.nan,
        "logloss_ci_high": np.nan,
        "promoted": False,
        "rejection_reason": "not_promotion_stage",
    }
    if ci is not None:
        row.update(
            {
                "brier_ci_low": ci.brier_low,
                "brier_ci_high": ci.brier_high,
                "logloss_ci_low": ci.logloss_low,
                "logloss_ci_high": ci.logloss_high,
                "bootstrap_replicates": ci.replicates,
                "bootstrap_confidence": ci.confidence,
                "bootstrap_seed": ci.seed,
            }
        )
    if decision is not None:
        row["promoted"] = bool(decision.promoted)
        row["rejection_reason"] = decision.reason
    return row


def _bootstrap_decision(
    *,
    mode: Mode,
    baseline: FoldEvaluation,
    challenger: FoldEvaluation,
    validation: DomainValidationConfig,
    seed_offset: int,
) -> tuple[ImprovementCI | None, PromotionDecision]:
    try:
        ci = paired_cluster_bootstrap(
            mode,
            baseline.dates,
            baseline.probability,
            challenger.probability,
            baseline.y,
            config=validation.bootstrap(seed_offset=seed_offset),
        )
    except (ValueError, FloatingPointError) as exc:
        logger.warning("Bootstrap failed closed for %s: %s", mode, exc)
        decision = decide_promotion(
            baseline=baseline.loss,
            challenger=challenger.loss,
            ci=None,
            oos_dates=challenger.oos_dates,
            minimum_oos_dates=validation.minimum_oos_dates,
        )
        reason = (
            "insufficient_oos_dates"
            if challenger.oos_dates < validation.minimum_oos_dates
            else "bootstrap_invalid"
        )
        decision = PromotionDecision(
            False,
            reason,
            decision.brier_skill,
            decision.logloss_skill,
        )
        return None, decision

    decision = decide_promotion(
        baseline=baseline.loss,
        challenger=challenger.loss,
        ci=ci,
        oos_dates=challenger.oos_dates,
        minimum_oos_dates=validation.minimum_oos_dates,
    )
    return ci, decision


def _blend_evaluation(
    mode: Mode,
    baseline: FoldEvaluation,
    challenger: FoldEvaluation,
    trust: float,
) -> FoldEvaluation:
    if not np.array_equal(baseline.dates, challenger.dates):
        raise ValueError("baseline/challenger OOS dates differ")
    if not np.array_equal(baseline.y, challenger.y):
        raise ValueError("baseline/challenger OOS labels differ")
    prob = (1.0 - trust) * baseline.probability + trust * challenger.probability
    unique, brier, ll = score_by_date(mode, baseline.dates, prob, baseline.y)
    return FoldEvaluation(
        loss=LossPair(float(np.mean(brier)), float(np.mean(ll))),
        dates=baseline.dates.copy(),
        y=baseline.y.copy(),
        probability=prob,
        rows=len(prob),
        oos_dates=len(unique),
    )


def _production_features(promoted_groups: list[str]) -> list[str]:
    unknown = [g for g in promoted_groups if g not in DOMAIN_FEATURE_GROUPS]
    if unknown:
        raise ValueError(f"unknown domain feature groups: {unknown}")
    out = list(FEATURE_COLS)
    for group in promoted_groups:
        out.extend(DOMAIN_FEATURE_GROUPS[group])
    if len(out) != len(set(out)):
        raise ValueError("production feature manifest contains duplicate columns")
    return out


def _predict_proba_allowlisted(
    model: PlattCalibratedClassifier,
    frame: pd.DataFrame,
    features: list[str],
) -> np.ndarray:
    """Inference firewall: only explicitly allowlisted columns reach the model."""
    missing = [c for c in features if c not in frame.columns]
    if missing:
        raise ValueError(f"missing production features: {missing}")
    return model.predict_proba(
        frame[features].astype(np.float32).to_numpy()
    )[:, 1]


def walk_forward_ablation(
    frame: pd.DataFrame,
    y: pd.Series,
    *,
    mode: Mode,
    validation: DomainValidationConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run controlled four-fold ablation and fail-closed promotion."""
    validation_cfg = validation or DomainValidationConfig()
    validation_cfg.validate()

    data = frame.copy()
    data["anchor_date"] = pd.to_datetime(data["anchor_date"]).dt.normalize()
    target = y.to_numpy(dtype=int)
    days = pd.DatetimeIndex(sorted(data["anchor_date"].unique()))
    folds = _make_folds(days)
    plans = {
        fold.fold: _make_fold_plan(data, target, fold=fold, mode=mode)
        for fold in folds
    }

    baseline_by_fold: dict[int, FoldEvaluation] = {}
    rows: list[dict[str, object]] = []
    for fold in folds:
        plan = plans[fold.fold]
        evaluation = _fit_fold(
            data,
            target,
            features=list(FEATURE_COLS),
            plan=plan,
            mode=mode,
        )
        baseline_by_fold[fold.fold] = evaluation
        rows.append(
            _row(
                mode=mode,
                stage="baseline",
                fold=fold,
                candidate="baseline",
                features=list(FEATURE_COLS),
                baseline=evaluation,
                challenger=evaluation,
                plan=plan,
            )
        )

    screen_summary: dict[str, dict[str, object]] = {}
    screened: list[str] = []
    for group, group_features in DOMAIN_FEATURE_GROUPS.items():
        feature_set = list(FEATURE_COLS) + list(group_features)
        challenger_evals: list[FoldEvaluation] = []
        baseline_evals: list[FoldEvaluation] = []
        for fold in folds[:2]:
            plan = plans[fold.fold]
            challenger = _fit_fold(
                data,
                target,
                features=feature_set,
                plan=plan,
                mode=mode,
            )
            baseline = baseline_by_fold[fold.fold]
            rows.append(
                _row(
                    mode=mode,
                    stage="screen",
                    fold=fold,
                    candidate=group,
                    features=feature_set,
                    baseline=baseline,
                    challenger=challenger,
                    plan=plan,
                )
            )
            challenger_evals.append(challenger)
            baseline_evals.append(baseline)

        pooled_baseline = _combine_evaluations(mode, baseline_evals)
        pooled_challenger = _combine_evaluations(mode, challenger_evals)
        brier_skill = _skill(
            pooled_challenger.loss.brier, pooled_baseline.loss.brier
        )
        logloss_skill = _skill(
            pooled_challenger.loss.logloss, pooled_baseline.loss.logloss
        )
        passed = _positive_pair(brier_skill, logloss_skill)
        screen_summary[group] = {
            "pooled_oos_dates": pooled_challenger.oos_dates,
            "pooled_oos_rows": pooled_challenger.rows,
            "baseline_brier": pooled_baseline.loss.brier,
            "challenger_brier": pooled_challenger.loss.brier,
            "brier_skill": brier_skill,
            "baseline_logloss": pooled_baseline.loss.logloss,
            "challenger_logloss": pooled_challenger.loss.logloss,
            "logloss_skill": logloss_skill,
            "screened": passed,
        }
        if passed:
            screened.append(group)

    confirmed: list[str] = []
    confirmation: dict[str, dict[str, object]] = {}
    fold3 = folds[2]
    plan3 = plans[fold3.fold]
    for group in screened:
        feature_set = list(FEATURE_COLS) + list(DOMAIN_FEATURE_GROUPS[group])
        challenger = _fit_fold(
            data,
            target,
            features=feature_set,
            plan=plan3,
            mode=mode,
        )
        baseline = baseline_by_fold[fold3.fold]
        ci, decision = _bootstrap_decision(
            mode=mode,
            baseline=baseline,
            challenger=challenger,
            validation=validation_cfg,
            seed_offset=100 + list(DOMAIN_FEATURE_GROUPS).index(group),
        )
        rows.append(
            _row(
                mode=mode,
                stage="confirm",
                fold=fold3,
                candidate=group,
                features=feature_set,
                baseline=baseline,
                challenger=challenger,
                plan=plan3,
                ci=ci,
                decision=decision,
            )
        )
        confirmation[group] = {
            "brier_skill": decision.brier_skill,
            "logloss_skill": decision.logloss_skill,
            "brier_ci": [ci.brier_low, ci.brier_high] if ci else None,
            "logloss_ci": [ci.logloss_low, ci.logloss_high] if ci else None,
            "confirmed": decision.promoted,
            "reason": decision.reason,
        }
        if decision.promoted:
            confirmed.append(group)

    fold4 = folds[3]
    plan4 = plans[fold4.fold]
    all_features = list(FEATURE_COLS) + list(ALL_DOMAIN_FEATURES)
    all_eval = _fit_fold(
        data,
        target,
        features=all_features,
        plan=plan4,
        mode=mode,
    )
    rows.append(
        _row(
            mode=mode,
            stage="final_diagnostic",
            fold=fold4,
            candidate="all_domain_groups",
            features=all_features,
            baseline=baseline_by_fold[fold4.fold],
            challenger=all_eval,
            plan=plan4,
        )
    )

    candidate_features = _production_features(confirmed)
    combined_eval: FoldEvaluation | None = None
    blend_eval: FoldEvaluation | None = None
    final_ci: ImprovementCI | None = None
    final_decision = PromotionDecision(False, "no_confirmed_groups", 0.0, 0.0)
    challenger_brier_skill = 0.0
    challenger_logloss_skill = 0.0

    if confirmed:
        combined_eval = _fit_fold(
            data,
            target,
            features=candidate_features,
            plan=plan4,
            mode=mode,
        )
        baseline4 = baseline_by_fold[fold4.fold]
        challenger_brier_skill = _skill(
            combined_eval.loss.brier, baseline4.loss.brier
        )
        challenger_logloss_skill = _skill(
            combined_eval.loss.logloss, baseline4.loss.logloss
        )

        # Score the exact fixed-trust blend that would be served in production.
        blend_eval = _blend_evaluation(
            mode,
            baseline4,
            combined_eval,
            validation_cfg.production_trust,
        )
        final_ci, final_decision = _bootstrap_decision(
            mode=mode,
            baseline=baseline4,
            challenger=blend_eval,
            validation=validation_cfg,
            seed_offset=1000,
        )
        rows.append(
            _row(
                mode=mode,
                stage="final_gate",
                fold=fold4,
                candidate="production_blend",
                features=candidate_features,
                baseline=baseline4,
                challenger=blend_eval,
                plan=plan4,
                ci=final_ci,
                decision=final_decision,
            )
        )

    active = bool(final_decision.promoted)
    trust = validation_cfg.production_trust if active else 0.0
    production_groups = list(confirmed) if active else []
    production_features = _production_features(production_groups)

    report = pd.DataFrame(rows)
    gate: dict[str, object] = {
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "experiment_id": f"cau-keo-domain-v2-{mode}",
        "mode": mode,
        "generated_at": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "positive_skill_threshold": POSITIVE_SKILL_EPS,
        "folds": [fold.as_dict() for fold in folds],
        "feature_groups": DOMAIN_FEATURE_GROUPS,
        "screen_summary": screen_summary,
        "screened_groups": screened,
        "confirmation": confirmation,
        "confirmed_groups": confirmed,
        "production_selected_groups": production_groups,
        "baseline_features": list(FEATURE_COLS),
        "production_features": production_features,
        "final_brier_skill": final_decision.brier_skill,
        "final_logloss_skill": final_decision.logloss_skill,
        "combined_challenger_brier_skill": challenger_brier_skill,
        "combined_challenger_logloss_skill": challenger_logloss_skill,
        "final_brier_ci": (
            [final_ci.brier_low, final_ci.brier_high] if final_ci else None
        ),
        "final_logloss_ci": (
            [final_ci.logloss_low, final_ci.logloss_high] if final_ci else None
        ),
        "bootstrap_replicates": validation_cfg.bootstrap_replicates,
        "bootstrap_seed": validation_cfg.bootstrap_seed,
        "promotion_ci": validation_cfg.promotion_ci,
        "minimum_oos_dates": validation_cfg.minimum_oos_dates,
        "configured_production_trust": validation_cfg.production_trust,
        "domain_active": active,
        "domain_trust": trust,
        "reason": final_decision.reason,
        "metric_contract": (
            "loto uses Bernoulli Brier/LogLoss; de normalizes each 100-number "
            "draw and uses categorical Brier/LogLoss, matching production"
        ),
        "bootstrap_contract": (
            "paired draw/date clusters; all 100 candidate rows remain together; "
            "sampled-date multiplicity is preserved"
        ),
        "policy": (
            "Experimental domain features affect production only after individual "
            "chronological confirmation and a final untouched test of the exact "
            "fixed-trust production blend with positive Brier/LogLoss skill and "
            "both clustered-bootstrap CI lower bounds strictly above zero."
        ),
    }
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
    X_train_raw = values[train_mask]
    y_train_raw = target[train_mask]
    keep = _training_keep_indices(
        y_train_raw,
        neg_ratio=22 if mode == "de" else 8,
        seed=20265000 if mode == "loto" else 20265001,
    )
    X_train = X_train_raw[keep]
    y_train = y_train_raw[keep]
    X_cal = values[calib_mask]
    y_cal = target[calib_mask]
    seed = 20265000 if mode == "loto" else 20265001
    model = _new_model(seed)
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
        "partner",
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
    pred.head(top)[cols].to_csv(
        top_path, index=False, quoting=csv.QUOTE_NONNUMERIC
    )
    return [all_path, top_path]


def _ensure_baseline(
    *,
    mode: Mode,
    models_dir: Path,
    out_dir: Path,
    config: CauKeoConfig,
) -> None:
    # Always invoke the baseline freshness gate. ``run_baseline`` reuses a current
    # artifact but retrains if the supervised anchor/schema has advanced.
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
    validation: DomainValidationConfig | None = None,
) -> list[Path]:
    validation_cfg = validation or DomainValidationConfig()
    validation_cfg.validate()
    _ensure_baseline(
        mode=mode,
        models_dir=models_dir,
        out_dir=out_dir,
        config=config,
    )
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
    ablation, gate = walk_forward_ablation(
        X_aug,
        y_train,
        mode=mode,
        validation=validation_cfg,
    )

    active = bool(gate["domain_active"])
    trust = float(gate["domain_trust"])
    selected_groups = list(gate["production_selected_groups"])
    selected_features = _production_features(
        [str(group) for group in selected_groups]
    )

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
    X_pred = X_pred[
        X_pred["anchor_date"].astype(str) == latest_anchor
    ].copy()
    X_pred = augment_domain_features(X_pred).reset_index(drop=True)

    baseline_model = pack["model"]
    p_baseline = _predict_proba_allowlisted(
        baseline_model, X_pred, list(FEATURE_COLS)
    )
    if challenger is not None:
        p_domain = _predict_proba_allowlisted(
            challenger, X_pred, selected_features
        )
    else:
        p_domain = p_baseline.copy()

    p_prod = (1.0 - trust) * p_baseline + trust * p_domain
    X_pred["ml_prob_baseline"] = p_baseline
    X_pred["ml_prob_domain"] = p_domain
    X_pred["domain_prob_edge"] = p_domain - p_baseline
    X_pred["domain_trust"] = trust
    X_pred["domain_active"] = active
    X_pred["domain_groups"] = (
        "|".join(str(x) for x in selected_groups) if selected_groups else ""
    )
    X_pred["ml_prob_raw"] = p_prod
    judged = _add_ai_judgement(X_pred, mode=mode)

    out_dir.mkdir(parents=True, exist_ok=True)
    created = _write_prediction_outputs(
        judged, mode=mode, out_dir=out_dir, top=config.top
    )
    ablation_path = out_dir / f"cau_keo_domain_ablation_{mode}.csv"
    gate_path = out_dir / f"cau_keo_domain_gate_{mode}.json"
    ablation.to_csv(ablation_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    gate.update(
        {
            "anchor_date": latest_anchor,
            "predict_for_date": str(judged["predict_for_date"].iloc[0]),
            "production_feature_count": len(selected_features),
            "baseline_feature_count": len(FEATURE_COLS),
        }
    )
    gate_path.write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    created.extend([ablation_path, gate_path])

    feature_manifest = {
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "baseline_features": list(FEATURE_COLS),
        "feature_groups": DOMAIN_FEATURE_GROUPS,
        "promoted_groups": selected_groups,
        "production_features": selected_features,
        "feature_ordering": "explicit_allowlist",
    }
    pack["domain_schema_version"] = DOMAIN_SCHEMA_VERSION
    pack["domain_active"] = active
    pack["domain_trust"] = trust
    pack["domain_groups"] = selected_groups
    pack["domain_features"] = selected_features
    pack["domain_feature_manifest"] = feature_manifest
    pack["domain_challenger_model"] = challenger
    pack["domain_gate"] = {
        "experiment_id": gate["experiment_id"],
        "final_brier_skill": float(gate["final_brier_skill"]),
        "final_logloss_skill": float(gate["final_logloss_skill"]),
        "final_brier_ci": gate["final_brier_ci"],
        "final_logloss_ci": gate["final_logloss_ci"],
        "reason": gate["reason"],
    }
    pack["domain_trained_through_date"] = str(
        pd.to_datetime(X_train["anchor_date"]).max().date()
    )
    joblib.dump(pack, model_path)

    manifest_path = out_dir / f"cau_keo_manifest_{mode}.json"
    manifest: dict[str, object] = {}
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
        "selected_features": selected_features,
        "feature_manifest": feature_manifest,
        "ablation_report": ablation_path.name,
        "gate_report": gate_path.name,
        "final_brier_skill": float(gate["final_brier_skill"]),
        "final_logloss_skill": float(gate["final_logloss_skill"]),
        "final_brier_ci": gate["final_brier_ci"],
        "final_logloss_ci": gate["final_logloss_ci"],
        "policy": gate["policy"],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    created.append(manifest_path)

    logger.info(
        "Domain challenger %s: active=%s trust=%.3f groups=%s "
        "BrierSkill=%.4f%% LogLossSkill=%.4f%% reason=%s",
        mode,
        active,
        trust,
        selected_groups,
        100.0 * float(gate["final_brier_skill"]),
        100.0 * float(gate["final_logloss_skill"]),
        gate["reason"],
    )
    return created


def run(
    *,
    mode: Mode | Literal["both"] = "both",
    models_dir: Path | str = "models",
    out_dir: Path | str = "data/ai_ml",
    config: CauKeoConfig | None = None,
    validation: DomainValidationConfig | None = None,
) -> list[Path]:
    cfg = config or CauKeoConfig()
    validation_cfg = validation or DomainValidationConfig()
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
                validation=validation_cfg,
            )
        )
    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run scientifically gated partner/cap50/bo/bong/cham/tong "
            "cau-keo challengers."
        )
    )
    parser.add_argument(
        "--mode", choices=["loto", "de", "both"], default="both"
    )
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--out-dir", default="data/ai_ml")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--window-days", type=int, default=2000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--lag-max", type=int, default=30)
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260902)
    parser.add_argument("--promotion-ci", type=float, default=0.95)
    parser.add_argument("--minimum-oos-dates", type=int, default=30)
    parser.add_argument(
        "--production-trust", type=float, default=DEFAULT_PRODUCTION_TRUST
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = CauKeoConfig(
        min_history_days=args.min_history_days,
        lag_max_for_path_support=args.lag_max,
        window_days=args.window_days,
        top=args.top,
    )
    validation = DomainValidationConfig(
        bootstrap_replicates=args.bootstrap_replicates,
        bootstrap_seed=args.bootstrap_seed,
        promotion_ci=args.promotion_ci,
        minimum_oos_dates=args.minimum_oos_dates,
        production_trust=args.production_trust,
    )
    for path in run(
        mode=args.mode,
        models_dir=args.models_dir,
        out_dir=args.out_dir,
        config=config,
        validation=validation,
    ):
        print(f"[OK] {path}")


if __name__ == "__main__":
    main()
