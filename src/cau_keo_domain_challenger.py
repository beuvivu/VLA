from __future__ import annotations

"""Scientifically gated domain-feature challenger for production cầu-kèo ML.

The established ``cau_keo_ml`` model remains the champion. Experimental domain
feature families are allowed into the production blend only after controlled,
strictly chronological comparisons with:

1. identical train/calibration/test dates;
2. identical training-row downsampling and model random state;
3. paired OOS Brier and LogLoss in the same probability space production serves;
4. paired DATE-cluster bootstrap confidence intervals;
5. individual screening, later confirmation and an untouched final production-blend test.

No historical relation is treated as predictive evidence by construction.
"""

import argparse
import csv
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from cau_keo_feature_groups import (
    ALL_DOMAIN_FEATURES,
    DOMAIN_FEATURE_GROUPS,
    FEATURE_GROUP_SCHEMA_VERSION,
    augment_domain_features,
)
from cau_keo_ml import (
    FEATURE_COLS,
    CauKeoConfig,
    _add_ai_judgement,
    build_cau_keo_feature_frame,
    run as run_baseline,
)
from ml_models import PlattCalibratedClassifier
from ml_validation import BootstrapConfig, evaluate_paired_oos

Mode = Literal["loto", "de"]
DOMAIN_SCHEMA_VERSION = 2
POSITIVE_SKILL_EPS = 0.0
N_FOLDS = 4
DEFAULT_VAL_DAYS = 30
DEFAULT_CALIB_DAYS = 30
MIN_TRAIN_DAYS = 90
DEFAULT_MODEL_SEED = 20260920

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainGateConfig:
    validation_days: int = DEFAULT_VAL_DAYS
    calibration_days: int = DEFAULT_CALIB_DAYS
    minimum_train_days: int = MIN_TRAIN_DAYS
    model_seed: int = DEFAULT_MODEL_SEED
    maximum_trust: float = 0.30
    bootstrap: BootstrapConfig = field(default_factory=BootstrapConfig)

    def __post_init__(self) -> None:
        if self.validation_days < 10:
            raise ValueError("validation_days must be >= 10")
        if self.calibration_days < 10:
            raise ValueError("calibration_days must be >= 10")
        if self.minimum_train_days < 30:
            raise ValueError("minimum_train_days must be >= 30")
        if not 0.0 < self.maximum_trust <= 1.0:
            raise ValueError("maximum_trust must be within (0, 1]")


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
        }


@dataclass(frozen=True)
class FoldOutput:
    fold: int
    frame: pd.DataFrame
    target: np.ndarray
    prob: np.ndarray
    train_rows_raw: int
    train_rows_fit: int
    calibration_rows: int
    test_rows: int
    fit_row_fingerprint: str
    seed: int


def _make_folds(
    anchor_days: pd.DatetimeIndex,
    gate_config: DomainGateConfig | None = None,
) -> list[FoldSpec]:
    cfg = gate_config or DomainGateConfig()
    days = pd.DatetimeIndex(sorted(pd.to_datetime(anchor_days).normalize().unique()))
    available = len(days) - cfg.minimum_train_days - cfg.calibration_days
    val_days = min(cfg.validation_days, available // N_FOLDS)
    if val_days < 10:
        raise RuntimeError(
            f"Need more history for {N_FOLDS}-fold domain ablation: {len(days)} anchor days"
        )

    folds: list[FoldSpec] = []
    for idx in range(N_FOLDS):
        val_start_idx = len(days) - (N_FOLDS - idx) * val_days
        val_end_idx = val_start_idx + val_days
        calib_start_idx = val_start_idx - cfg.calibration_days
        if calib_start_idx < cfg.minimum_train_days:
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
            random_state=int(seed),
        )
    )


def _fold_masks(
    frame: pd.DataFrame, fold: FoldSpec
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dates = pd.to_datetime(frame["anchor_date"], errors="raise").dt.normalize()
    train = (dates < fold.calib_start).to_numpy()
    calib = ((dates >= fold.calib_start) & (dates < fold.val_start)).to_numpy()
    valid_s = dates >= fold.val_start
    if fold.val_end is not None:
        valid_s &= dates < fold.val_end
    return train, calib, valid_s.to_numpy()


def _downsample_relative_indices(
    y: np.ndarray, *, neg_ratio: int, seed: int
) -> np.ndarray:
    """Return deterministic fit-row positions shared by baseline and challengers."""
    target = np.asarray(y, dtype=int)
    rng = np.random.default_rng(seed)
    pos = np.where(target == 1)[0]
    neg = np.where(target == 0)[0]
    if len(pos) == 0 or len(neg) == 0:
        return np.arange(len(target), dtype=int)
    n_neg = min(len(neg), len(pos) * int(neg_ratio))
    if n_neg == len(neg):
        keep = np.arange(len(target), dtype=int)
    else:
        sel_neg = rng.choice(neg, size=n_neg, replace=False)
        keep = np.concatenate([pos, sel_neg]).astype(int)
        rng.shuffle(keep)
    return keep


def _fit_fold(
    frame: pd.DataFrame,
    y: np.ndarray,
    *,
    features: list[str],
    fold: FoldSpec,
    mode: Mode,
    seed: int,
) -> FoldOutput:
    train_mask, calib_mask, val_mask = _fold_masks(frame, fold)
    if min(int(train_mask.sum()), int(calib_mask.sum()), int(val_mask.sum())) <= 0:
        raise RuntimeError(f"empty chronological split in fold {fold.fold}")

    target = np.asarray(y, dtype=int)
    train_abs = np.flatnonzero(train_mask)
    calibration_abs = np.flatnonzero(calib_mask)
    test_abs = np.flatnonzero(val_mask)
    y_train_raw = target[train_abs]
    y_cal = target[calibration_abs]
    y_val = target[test_abs]
    if np.unique(y_train_raw).size < 2:
        raise RuntimeError(f"fold {fold.fold}: training block is single-class")
    if np.unique(y_cal).size < 2:
        raise RuntimeError(f"fold {fold.fold}: calibration_failure single-class block")

    neg_ratio = 22 if mode == "de" else 8
    keep_rel = _downsample_relative_indices(
        y_train_raw, neg_ratio=neg_ratio, seed=seed
    )
    fit_abs = train_abs[keep_rel]
    values = frame[features].astype(np.float32).to_numpy()

    model = _new_model(seed)
    model.fit(values[fit_abs], target[fit_abs])
    p_cal = model.base_.predict_proba(values[calibration_abs])[:, 1]
    model.fit_platt(p_cal, y_cal)
    p_val = model.predict_proba(values[test_abs])[:, 1]

    fingerprint = hashlib.sha256(np.asarray(fit_abs, dtype=np.int64).tobytes()).hexdigest()
    return FoldOutput(
        fold=fold.fold,
        frame=frame.loc[val_mask, ["anchor_date", "number"]].reset_index(drop=True),
        target=y_val,
        prob=np.asarray(p_val, dtype=float),
        train_rows_raw=int(len(train_abs)),
        train_rows_fit=int(len(fit_abs)),
        calibration_rows=int(len(calibration_abs)),
        test_rows=int(len(test_abs)),
        fit_row_fingerprint=fingerprint,
        seed=int(seed),
    )


def _concat_outputs(outputs: list[FoldOutput]) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    if not outputs:
        raise ValueError("at least one fold output is required")
    frame = pd.concat([o.frame for o in outputs], ignore_index=True)
    target = np.concatenate([o.target for o in outputs]).astype(int)
    prob = np.concatenate([o.prob for o in outputs]).astype(float)
    return frame, target, prob


def _assert_controlled_pair(
    baseline: list[FoldOutput], challenger: list[FoldOutput]
) -> None:
    if len(baseline) != len(challenger):
        raise RuntimeError("baseline/challenger fold count mismatch")
    for base, cand in zip(baseline, challenger, strict=True):
        if base.fold != cand.fold:
            raise RuntimeError("baseline/challenger fold mismatch")
        if base.seed != cand.seed:
            raise RuntimeError("baseline/challenger model seeds differ")
        if base.fit_row_fingerprint != cand.fit_row_fingerprint:
            raise RuntimeError("baseline/challenger training rows differ")
        if not base.frame.equals(cand.frame) or not np.array_equal(base.target, cand.target):
            raise RuntimeError("baseline/challenger OOS observations differ")


def _pair_evidence(
    baseline: list[FoldOutput],
    challenger: list[FoldOutput],
    *,
    mode: Mode,
    bootstrap: BootstrapConfig,
) -> tuple[dict[str, object], pd.DataFrame]:
    _assert_controlled_pair(baseline, challenger)
    frame, target, p_base = _concat_outputs(baseline)
    frame_c, target_c, p_challenger = _concat_outputs(challenger)
    if not frame.equals(frame_c) or not np.array_equal(target, target_c):
        raise RuntimeError("paired OOS concatenation mismatch")
    return evaluate_paired_oos(
        frame,
        target,
        p_base,
        p_challenger,
        mode=mode,
        bootstrap=bootstrap,
    )


def _blend_outputs(
    baseline: list[FoldOutput], challenger: list[FoldOutput], *, trust: float
) -> list[FoldOutput]:
    _assert_controlled_pair(baseline, challenger)
    out: list[FoldOutput] = []
    for base, cand in zip(baseline, challenger, strict=True):
        p = (1.0 - trust) * base.prob + trust * cand.prob
        out.append(
            FoldOutput(
                fold=cand.fold,
                frame=cand.frame,
                target=cand.target,
                prob=p,
                train_rows_raw=cand.train_rows_raw,
                train_rows_fit=cand.train_rows_fit,
                calibration_rows=cand.calibration_rows,
                test_rows=cand.test_rows,
                fit_row_fingerprint=cand.fit_row_fingerprint,
                seed=cand.seed,
            )
        )
    return out


def _positive_pair(brier_skill: float, logloss_skill: float) -> bool:
    return bool(
        np.isfinite(brier_skill)
        and np.isfinite(logloss_skill)
        and brier_skill > POSITIVE_SKILL_EPS
        and logloss_skill > POSITIVE_SKILL_EPS
    )


def _trust_from_skill(
    brier_skill: float,
    logloss_skill: float,
    *,
    maximum_trust: float = 0.30,
) -> float:
    if not _positive_pair(brier_skill, logloss_skill):
        return 0.0
    strength = min(float(brier_skill), float(logloss_skill))
    return float(np.clip(5.0 * strength, 0.05, maximum_trust))


def _fold_report(frame: pd.DataFrame, fold: FoldSpec) -> dict[str, object]:
    train, calib, test = _fold_masks(frame, fold)
    dates = pd.to_datetime(frame["anchor_date"], errors="raise").dt.normalize()

    def bounds(mask: np.ndarray) -> tuple[str | None, str | None, int]:
        selected = pd.DatetimeIndex(sorted(dates[mask].unique()))
        if selected.empty:
            return None, None, 0
        return (
            selected[0].date().isoformat(),
            selected[-1].date().isoformat(),
            int(len(selected)),
        )

    tr_start, tr_end, tr_days = bounds(train)
    ca_start, ca_end, ca_days = bounds(calib)
    te_start, te_end, te_days = bounds(test)
    return {
        "fold": fold.fold,
        "train_start": tr_start,
        "train_end": tr_end,
        "calibration_start": ca_start,
        "calibration_end": ca_end,
        "test_start": te_start,
        "test_end": te_end,
        "train_dates": tr_days,
        "calibration_dates": ca_days,
        "test_dates": te_days,
        "train_rows": int(train.sum()),
        "calibration_rows": int(calib.sum()),
        "test_rows": int(test.sum()),
    }


def _data_fingerprint(frame: pd.DataFrame, y: pd.Series) -> str:
    cols = ["anchor_date", "number", *FEATURE_COLS, *ALL_DOMAIN_FEATURES]
    hashes = pd.util.hash_pandas_object(frame[cols], index=False).to_numpy(dtype=np.uint64)
    digest = hashlib.sha256()
    digest.update(hashes.tobytes())
    digest.update(y.to_numpy(dtype=np.int8).tobytes())
    return digest.hexdigest()


def _ablation_row(
    *,
    mode: Mode,
    stage: str,
    candidate: str,
    features: list[str],
    folds: str,
    evidence: dict[str, object],
) -> dict[str, object]:
    reasons = evidence.get("rejection_reasons", [])
    return {
        "mode": mode,
        "stage": stage,
        "folds": folds,
        "candidate": candidate,
        "feature_count": len(features),
        "oos_dates": int(evidence.get("oos_dates", 0)),
        "oos_rows": int(evidence.get("oos_rows", 0)),
        "baseline_brier": evidence.get("baseline_brier"),
        "candidate_brier": evidence.get("challenger_brier"),
        "brier_delta": evidence.get("brier_improvement"),
        "brier_skill": evidence.get("brier_skill"),
        "brier_ci_low": evidence.get("brier_ci_low"),
        "brier_ci_high": evidence.get("brier_ci_high"),
        "baseline_logloss": evidence.get("baseline_logloss"),
        "candidate_logloss": evidence.get("challenger_logloss"),
        "logloss_delta": evidence.get("logloss_improvement"),
        "logloss_skill": evidence.get("logloss_skill"),
        "logloss_ci_low": evidence.get("logloss_ci_low"),
        "logloss_ci_high": evidence.get("logloss_ci_high"),
        "gate_pass": bool(evidence.get("promoted", False)),
        "rejection_reason": "|".join(str(x) for x in reasons),
        "probability_space": evidence.get("probability_space"),
    }


def walk_forward_ablation(
    frame: pd.DataFrame,
    y: pd.Series,
    *,
    mode: Mode,
    gate_config: DomainGateConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run controlled temporal ablation and an untouched production-blend gate."""
    cfg = gate_config or DomainGateConfig()
    data = frame.copy()
    data["anchor_date"] = pd.to_datetime(data["anchor_date"], errors="raise").dt.normalize()
    target = y.to_numpy(dtype=int)
    days = pd.DatetimeIndex(sorted(data["anchor_date"].unique()))
    folds = _make_folds(days, cfg)

    baseline_by_fold: dict[int, FoldOutput] = {}
    rows: list[dict[str, object]] = []
    for fold in folds:
        seed = cfg.model_seed + fold.fold
        output = _fit_fold(
            data,
            target,
            features=list(FEATURE_COLS),
            fold=fold,
            mode=mode,
            seed=seed,
        )
        baseline_by_fold[fold.fold] = output
        baseline_evidence, _ = _pair_evidence(
            [output],
            [output],
            mode=mode,
            bootstrap=cfg.bootstrap.with_seed(cfg.bootstrap.seed + fold.fold),
        )
        rows.append(
            _ablation_row(
                mode=mode,
                stage="baseline",
                candidate="baseline",
                features=list(FEATURE_COLS),
                folds=str(fold.fold),
                evidence=baseline_evidence,
            )
        )

    screened: list[str] = []
    screen_summary: dict[str, dict[str, object]] = {}
    for group_index, (group, group_features) in enumerate(DOMAIN_FEATURE_GROUPS.items()):
        feature_set = list(FEATURE_COLS) + list(group_features)
        base_outputs = [baseline_by_fold[1], baseline_by_fold[2]]
        challenger_outputs = [
            _fit_fold(
                data,
                target,
                features=feature_set,
                fold=fold,
                mode=mode,
                seed=cfg.model_seed + fold.fold,
            )
            for fold in folds[:2]
        ]
        evidence, _ = _pair_evidence(
            base_outputs,
            challenger_outputs,
            mode=mode,
            bootstrap=cfg.bootstrap.with_seed(cfg.bootstrap.seed + 100 + group_index),
        )
        screen_summary[group] = evidence
        rows.append(
            _ablation_row(
                mode=mode,
                stage="screen",
                candidate=group,
                features=feature_set,
                folds="1,2",
                evidence=evidence,
            )
        )
        if bool(evidence["promoted"]):
            screened.append(group)

    confirmed: list[str] = []
    confirmation: dict[str, dict[str, object]] = {}
    fold3 = folds[2]
    for group_index, group in enumerate(screened):
        feature_set = list(FEATURE_COLS) + list(DOMAIN_FEATURE_GROUPS[group])
        candidate = _fit_fold(
            data,
            target,
            features=feature_set,
            fold=fold3,
            mode=mode,
            seed=cfg.model_seed + fold3.fold,
        )
        evidence, _ = _pair_evidence(
            [baseline_by_fold[fold3.fold]],
            [candidate],
            mode=mode,
            bootstrap=cfg.bootstrap.with_seed(cfg.bootstrap.seed + 200 + group_index),
        )
        confirmation[group] = evidence
        rows.append(
            _ablation_row(
                mode=mode,
                stage="confirm",
                candidate=group,
                features=feature_set,
                folds="3",
                evidence=evidence,
            )
        )
        if bool(evidence["promoted"]):
            confirmed.append(group)

    selected_features = list(FEATURE_COLS)
    for group in confirmed:
        selected_features.extend(DOMAIN_FEATURE_GROUPS[group])

    combined_confirmation: dict[str, object] | None = None
    proposed_trust = 0.0
    if confirmed:
        combined_fold3 = _fit_fold(
            data,
            target,
            features=selected_features,
            fold=fold3,
            mode=mode,
            seed=cfg.model_seed + fold3.fold,
        )
        combined_confirmation, _ = _pair_evidence(
            [baseline_by_fold[fold3.fold]],
            [combined_fold3],
            mode=mode,
            bootstrap=cfg.bootstrap.with_seed(cfg.bootstrap.seed + 300),
        )
        rows.append(
            _ablation_row(
                mode=mode,
                stage="combined_confirmation",
                candidate="confirmed_domain_groups",
                features=selected_features,
                folds="3",
                evidence=combined_confirmation,
            )
        )
        if bool(combined_confirmation["promoted"]):
            proposed_trust = _trust_from_skill(
                float(combined_confirmation["brier_skill"]),
                float(combined_confirmation["logloss_skill"]),
                maximum_trust=cfg.maximum_trust,
            )

    fold4 = folds[3]
    all_features = list(FEATURE_COLS) + list(ALL_DOMAIN_FEATURES)
    all_candidate = _fit_fold(
        data,
        target,
        features=all_features,
        fold=fold4,
        mode=mode,
        seed=cfg.model_seed + fold4.fold,
    )
    all_evidence, _ = _pair_evidence(
        [baseline_by_fold[fold4.fold]],
        [all_candidate],
        mode=mode,
        bootstrap=cfg.bootstrap.with_seed(cfg.bootstrap.seed + 400),
    )
    rows.append(
        _ablation_row(
            mode=mode,
            stage="final_diagnostic",
            candidate="all_domain_groups",
            features=all_features,
            folds="4",
            evidence=all_evidence,
        )
    )

    full_challenger_evaluation: dict[str, object] | None = None
    production_blend_evaluation: dict[str, object] | None = None
    final_candidate: FoldOutput | None = None
    active = False
    if confirmed and combined_confirmation and bool(combined_confirmation["promoted"]):
        final_candidate = _fit_fold(
            data,
            target,
            features=selected_features,
            fold=fold4,
            mode=mode,
            seed=cfg.model_seed + fold4.fold,
        )
        full_challenger_evaluation, _ = _pair_evidence(
            [baseline_by_fold[fold4.fold]],
            [final_candidate],
            mode=mode,
            bootstrap=cfg.bootstrap.with_seed(cfg.bootstrap.seed + 500),
        )
        rows.append(
            _ablation_row(
                mode=mode,
                stage="final_full_challenger",
                candidate="confirmed_domain_groups",
                features=selected_features,
                folds="4",
                evidence=full_challenger_evaluation,
            )
        )

        blended = _blend_outputs(
            [baseline_by_fold[fold4.fold]], [final_candidate], trust=proposed_trust
        )
        production_blend_evaluation, _ = _pair_evidence(
            [baseline_by_fold[fold4.fold]],
            blended,
            mode=mode,
            bootstrap=cfg.bootstrap.with_seed(cfg.bootstrap.seed + 600),
        )
        rows.append(
            _ablation_row(
                mode=mode,
                stage="final_gate",
                candidate="production_blend",
                features=selected_features,
                folds="4",
                evidence=production_blend_evaluation,
            )
        )
        active = bool(production_blend_evaluation["promoted"] and proposed_trust > 0.0)

    # Leave-one-group-out is diagnostic only. It occurs after the final production
    # decision and must never be used to retune selection on the untouched fold.
    leave_one_group_out: dict[str, dict[str, object]] = {}
    if final_candidate is not None and len(confirmed) > 1:
        for offset, omitted in enumerate(confirmed):
            loo_features = list(FEATURE_COLS)
            for group in confirmed:
                if group != omitted:
                    loo_features.extend(DOMAIN_FEATURE_GROUPS[group])
            loo_candidate = _fit_fold(
                data,
                target,
                features=loo_features,
                fold=fold4,
                mode=mode,
                seed=cfg.model_seed + fold4.fold,
            )
            loo_evidence, _ = _pair_evidence(
                [baseline_by_fold[fold4.fold]],
                [loo_candidate],
                mode=mode,
                bootstrap=cfg.bootstrap.with_seed(cfg.bootstrap.seed + 700 + offset),
            )
            loo_evidence["diagnostic_only"] = True
            loo_evidence["selection_use"] = False
            leave_one_group_out[omitted] = loo_evidence

    trust = proposed_trust if active else 0.0
    final_evidence = production_blend_evaluation or {}
    if not confirmed:
        reason = "no_confirmed_groups"
        rejection_reasons = ["no_confirmed_groups"]
    elif not combined_confirmation or not bool(combined_confirmation["promoted"]):
        reason = "combined_confirmation_failed"
        rejection_reasons = list(
            (combined_confirmation or {}).get("rejection_reasons", ["combined_confirmation_failed"])
        )
    elif not active:
        reason = "untouched_production_blend_gate_failed"
        rejection_reasons = list(
            final_evidence.get("rejection_reasons", ["untouched_production_blend_gate_failed"])
        )
    else:
        reason = "production_blend_passed_untouched_oos_gate"
        rejection_reasons = []

    fingerprint = _data_fingerprint(data, y)
    anchor_end = pd.to_datetime(data["anchor_date"]).max().date().isoformat()
    experiment_id = f"cau-keo-domain-v{DOMAIN_SCHEMA_VERSION}-{mode}-{anchor_end}-{fingerprint[:12]}"
    production_groups = list(confirmed) if active else []
    production_features = list(selected_features) if active else list(FEATURE_COLS)

    gate: dict[str, object] = {
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "feature_group_schema_version": FEATURE_GROUP_SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "mode": mode,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "history_start": pd.to_datetime(data["anchor_date"]).min().date().isoformat(),
        "history_end": anchor_end,
        "data_fingerprint_sha256": fingerprint,
        "baseline_features": list(FEATURE_COLS),
        "feature_groups": DOMAIN_FEATURE_GROUPS,
        "screen_summary": screen_summary,
        "screened_groups": screened,
        "confirmation": confirmation,
        "confirmed_groups": confirmed,
        "combined_confirmation": combined_confirmation,
        "all_groups_final_diagnostic": all_evidence,
        "full_challenger_final_evaluation": full_challenger_evaluation,
        "production_blend_final_evaluation": production_blend_evaluation,
        "leave_one_group_out": leave_one_group_out,
        "folds": [_fold_report(data, fold) for fold in folds],
        "model_seed_policy": "same seed and identical downsampled training row IDs within each fold",
        "model_seed_base": int(cfg.model_seed),
        "bootstrap": {
            "cluster_unit": "date",
            "replicates": int(cfg.bootstrap.replicates),
            "seed": int(cfg.bootstrap.seed),
            "confidence": float(cfg.bootstrap.confidence),
            "minimum_oos_dates": int(cfg.bootstrap.minimum_oos_dates),
        },
        "proposed_trust_before_final_holdout": float(proposed_trust),
        "domain_active": bool(active),
        "domain_trust": float(trust),
        "production_selected_groups": production_groups,
        "production_features": production_features,
        "selected_features": production_features,
        "final_brier_skill": float(final_evidence.get("brier_skill", 0.0)),
        "final_logloss_skill": float(final_evidence.get("logloss_skill", 0.0)),
        "final_brier_ci_low": float(final_evidence.get("brier_ci_low", float("nan"))),
        "final_logloss_ci_low": float(final_evidence.get("logloss_ci_low", float("nan"))),
        "domain_rejection_reasons": rejection_reasons,
        "reason": reason,
        "selection_bias_control": (
            "folds 1-2 screen; fold 3 confirms groups and fixes blend trust; fold 4 is untouched "
            "until the final production-blend gate; post-gate leave-one-out is diagnostic only"
        ),
        "policy": (
            "Experimental domain features affect production only when the actual fixed-trust "
            "production blend has positive OOS Brier and LogLoss skill and both paired draw-level "
            "bootstrap improvement confidence intervals are strictly above zero."
        ),
    }
    return pd.DataFrame(rows), gate


def _fit_final_challenger(
    frame: pd.DataFrame,
    y: pd.Series,
    *,
    mode: Mode,
    features: list[str],
    gate_config: DomainGateConfig,
) -> PlattCalibratedClassifier:
    data = frame.copy()
    data["anchor_date"] = pd.to_datetime(data["anchor_date"], errors="raise").dt.normalize()
    days = pd.DatetimeIndex(sorted(data["anchor_date"].unique()))
    if len(days) <= gate_config.calibration_days + gate_config.minimum_train_days:
        raise RuntimeError("insufficient history to fit final domain challenger")
    calib_start = days[-gate_config.calibration_days]
    train_mask = (data["anchor_date"] < calib_start).to_numpy()
    calib_mask = (data["anchor_date"] >= calib_start).to_numpy()
    values = data[features].astype(np.float32).to_numpy()
    target = y.to_numpy(dtype=int)
    train_abs = np.flatnonzero(train_mask)
    cal_abs = np.flatnonzero(calib_mask)
    if np.unique(target[cal_abs]).size < 2:
        raise RuntimeError("calibration_failure final challenger single-class block")

    neg_ratio = 22 if mode == "de" else 8
    seed = gate_config.model_seed + (1000 if mode == "loto" else 1001)
    keep_rel = _downsample_relative_indices(
        target[train_abs], neg_ratio=neg_ratio, seed=seed
    )
    fit_abs = train_abs[keep_rel]
    model = _new_model(seed)
    model.fit(values[fit_abs], target[fit_abs])
    p_cal = model.base_.predict_proba(values[cal_abs])[:, 1]
    model.fit_platt(p_cal, target[cal_abs])
    return model


def _predict_gated_probabilities(
    frame: pd.DataFrame,
    *,
    baseline_model: object,
    challenger_model: object | None,
    production_features: list[str],
    trust: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Explicit allowlist firewall: extra/rejected dataframe columns are ignored."""
    p_baseline = baseline_model.predict_proba(
        frame[FEATURE_COLS].astype(np.float32).to_numpy()
    )[:, 1]
    if challenger_model is None or trust <= 0.0:
        p_domain = p_baseline.copy()
    else:
        p_domain = challenger_model.predict_proba(
            frame[production_features].astype(np.float32).to_numpy()
        )[:, 1]
    p_production = (1.0 - trust) * p_baseline + trust * p_domain
    return p_baseline, p_domain, p_production


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
    # Reuse the champion's own schema/freshness logic instead of trusting file existence.
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
    gate_config: DomainGateConfig,
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
    ablation, gate = walk_forward_ablation(
        X_aug, y_train, mode=mode, gate_config=gate_config
    )

    active = bool(gate["domain_active"])
    trust = float(gate["domain_trust"])
    selected_groups = list(gate["production_selected_groups"])
    production_features = list(gate["production_features"])
    if active and not selected_groups:
        raise RuntimeError("active domain challenger has no promoted groups")
    if len(production_features) != len(set(production_features)):
        raise RuntimeError("production feature manifest contains duplicates")

    challenger = (
        _fit_final_challenger(
            X_aug,
            y_train,
            mode=mode,
            features=production_features,
            gate_config=gate_config,
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

    p_baseline, p_domain, p_prod = _predict_gated_probabilities(
        X_pred,
        baseline_model=pack["model"],
        challenger_model=challenger,
        production_features=production_features,
        trust=trust,
    )
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
            "production_feature_count": len(production_features),
            "baseline_feature_count": len(FEATURE_COLS),
        }
    )
    gate_path.write_text(
        json.dumps(gate, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    created.extend([ablation_path, gate_path])

    pack["domain_schema_version"] = DOMAIN_SCHEMA_VERSION
    pack["domain_feature_group_schema_version"] = FEATURE_GROUP_SCHEMA_VERSION
    pack["domain_active"] = active
    pack["domain_trust"] = trust
    pack["domain_groups"] = selected_groups
    pack["domain_features"] = production_features
    pack["domain_challenger_model"] = challenger
    pack["domain_feature_manifest"] = {
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "baseline_features": list(FEATURE_COLS),
        "feature_groups": DOMAIN_FEATURE_GROUPS,
        "promoted_groups": selected_groups,
        "production_features": production_features,
        "experiment_id": gate["experiment_id"],
    }
    pack["domain_gate"] = {
        "experiment_id": gate["experiment_id"],
        "final_brier_skill": float(gate["final_brier_skill"]),
        "final_logloss_skill": float(gate["final_logloss_skill"]),
        "final_brier_ci_low": gate["final_brier_ci_low"],
        "final_logloss_ci_low": gate["final_logloss_ci_low"],
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
        "experiment_id": gate["experiment_id"],
        "active": active,
        "trust": trust,
        "baseline_features": list(FEATURE_COLS),
        "feature_groups": DOMAIN_FEATURE_GROUPS,
        "promoted_groups": selected_groups,
        "production_features": production_features,
        "ablation_report": ablation_path.name,
        "gate_report": gate_path.name,
        "evaluation": {
            "final_brier_skill": gate["final_brier_skill"],
            "final_logloss_skill": gate["final_logloss_skill"],
            "final_brier_ci_low": gate["final_brier_ci_low"],
            "final_logloss_ci_low": gate["final_logloss_ci_low"],
            "rejection_reasons": gate["domain_rejection_reasons"],
        },
        "policy": gate["policy"],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
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
    gate_config: DomainGateConfig | None = None,
) -> list[Path]:
    cfg = config or CauKeoConfig()
    gate_cfg = gate_config or DomainGateConfig()
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
                gate_config=gate_cfg,
            )
        )
    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run confidence-gated partner/cặp50/bộ/bóng/chạm/tổng challenger."
    )
    parser.add_argument("--mode", choices=["loto", "de", "both"], default="both")
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
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = CauKeoConfig(
        min_history_days=args.min_history_days,
        lag_max_for_path_support=args.lag_max,
        window_days=args.window_days,
        top=args.top,
    )
    gate_config = DomainGateConfig(
        bootstrap=BootstrapConfig(
            replicates=args.bootstrap_replicates,
            seed=args.bootstrap_seed,
            confidence=args.promotion_ci,
            minimum_oos_dates=args.minimum_oos_dates,
        )
    )
    for path in run(
        mode=args.mode,
        models_dir=args.models_dir,
        out_dir=args.out_dir,
        config=config,
        gate_config=gate_config,
    ):
        print(f"[OK] {path}")


if __name__ == "__main__":
    main()
