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
- production blend is enabled only when both losses improve and their paired,
  date-clustered bootstrap improvement intervals are strictly above zero.

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

from cau_keo_ml import (
    FEATURE_COLS,
    CauKeoConfig,
    _add_ai_judgement,
    _downsample,
    build_cau_keo_feature_frame,
    run as run_baseline,
)
from cau_keo_feature_groups import (
    ALL_DOMAIN_FEATURES,
    DOMAIN_FEATURE_GROUPS,
    FEATURE_GROUP_SCHEMA_VERSION,
    augment_domain_features,
)
from ml_models import PlattCalibratedClassifier
from ml_validation import (
    PredictionEvaluation,
    ValidationConfig,
    assert_temporal_partitions,
    compare_paired_predictions,
    evaluate_predictions,
    predict_with_feature_allowlist,
    relative_skill,
)

Mode = Literal["loto", "de"]
DOMAIN_SCHEMA_VERSION = FEATURE_GROUP_SCHEMA_VERSION
POSITIVE_SKILL_EPS = 1e-4
N_FOLDS = 4
DEFAULT_VAL_DAYS = 30
DEFAULT_CALIB_DAYS = 30
MIN_TRAIN_DAYS = 90
FINAL_GATE_CONFIG = ValidationConfig(
    bootstrap_replicates=1_000,
    bootstrap_seed=20260902,
    confidence_level=0.95,
    minimum_oos_dates=30,
    minimum_skill=POSITIVE_SKILL_EPS,
)

logger = logging.getLogger(__name__)


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


def _fit_fold(
    frame: pd.DataFrame,
    y: np.ndarray,
    *,
    features: list[str],
    fold: FoldSpec,
    mode: Mode,
    seed: int,
) -> PredictionEvaluation:
    train_mask, calib_mask, val_mask = _fold_masks(frame, fold)
    if min(int(train_mask.sum()), int(calib_mask.sum()), int(val_mask.sum())) <= 0:
        raise RuntimeError(f"empty chronological split in fold {fold.fold}")
    assert_temporal_partitions(
        frame["anchor_date"].to_numpy(), train_mask, calib_mask, val_mask
    )

    values = frame[features].astype(np.float32).to_numpy()
    X_train, y_train = values[train_mask], y[train_mask]
    X_cal, y_cal = values[calib_mask], y[calib_mask]
    y_val = y[val_mask]
    neg_ratio = 22 if mode == "de" else 8
    X_train, y_train = _downsample(X_train, y_train, neg_ratio=neg_ratio, seed=seed)

    model = _new_model(seed)
    model.fit(X_train, y_train)
    p_cal = model.base_.predict_proba(X_cal)[:, 1]
    model.fit_platt(p_cal, y_cal)
    validation_frame = frame.loc[val_mask]
    p_val = predict_with_feature_allowlist(model, validation_frame, features)
    return evaluate_predictions(
        y_val,
        p_val,
        validation_frame["anchor_date"].to_numpy(),
    )


def _skill(candidate: float, baseline: float) -> float:
    return relative_skill(baseline, candidate)


def _row(
    *,
    mode: Mode,
    stage: str,
    fold: FoldSpec,
    candidate: str,
    features: list[str],
    baseline_metrics: PredictionEvaluation,
    candidate_metrics: PredictionEvaluation,
    seed: int,
) -> dict[str, object]:
    bb, bl = baseline_metrics.brier, baseline_metrics.logloss
    cb, cl = candidate_metrics.brier, candidate_metrics.logloss
    return {
        "mode": mode,
        "stage": stage,
        "fold": fold.fold,
        "candidate": candidate,
        "feature_count": len(features),
        "seed": int(seed),
        "calib_start": fold.calib_start.date().isoformat(),
        "val_start": fold.val_start.date().isoformat(),
        "val_end_exclusive": fold.val_end.date().isoformat() if fold.val_end is not None else "",
        "baseline_brier": bb,
        "candidate_brier": cb,
        "brier_improvement": bb - cb,
        "brier_skill": _skill(cb, bb),
        "baseline_logloss": bl,
        "candidate_logloss": cl,
        "logloss_improvement": bl - cl,
        "logloss_skill": _skill(cl, bl),
        "oos_dates": candidate_metrics.oos_dates,
        "oos_rows": candidate_metrics.oos_rows,
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

    baseline_by_fold: dict[int, PredictionEvaluation] = {}
    rows: list[dict[str, object]] = []
    for fold in folds:
        fold_seed = 20260920 + fold.fold
        metrics = _fit_fold(
            data,
            target,
            features=list(FEATURE_COLS),
            fold=fold,
            mode=mode,
            seed=fold_seed,
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
                seed=fold_seed,
            )
        )

    screen_summary: dict[str, dict[str, float]] = {}
    screened: list[str] = []
    for group, group_features in DOMAIN_FEATURE_GROUPS.items():
        feature_set = list(FEATURE_COLS) + list(group_features)
        group_rows: list[dict[str, object]] = []
        for fold in folds[:2]:
            fold_seed = 20260920 + fold.fold
            metrics = _fit_fold(
                data,
                target,
                features=feature_set,
                fold=fold,
                mode=mode,
                seed=fold_seed,
            )
            r = _row(
                mode=mode,
                stage="screen",
                fold=fold,
                candidate=group,
                features=feature_set,
                baseline_metrics=baseline_by_fold[fold.fold],
                candidate_metrics=metrics,
                seed=fold_seed,
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
        fold_seed = 20260920 + fold3.fold
        feature_set = list(FEATURE_COLS) + list(DOMAIN_FEATURE_GROUPS[group])
        metrics = _fit_fold(
            data,
            target,
            features=feature_set,
            fold=fold3,
            mode=mode,
            seed=fold_seed,
        )
        r = _row(
            mode=mode,
            stage="confirm",
            fold=fold3,
            candidate=group,
            features=feature_set,
            baseline_metrics=baseline_by_fold[fold3.fold],
            candidate_metrics=metrics,
            seed=fold_seed,
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

    # Keep the fourth fold untouched unless a challenger has survived both
    # screening and confirmation.  The all-groups diagnostic belongs on the
    # confirmation fold and can never consume the final holdout pre-selection.
    diagnostic_fold = fold3
    diagnostic_seed = 20260920 + diagnostic_fold.fold
    all_features = list(FEATURE_COLS) + list(ALL_DOMAIN_FEATURES)
    all_metrics = _fit_fold(
        data,
        target,
        features=all_features,
        fold=diagnostic_fold,
        mode=mode,
        seed=diagnostic_seed,
    )
    all_row = _row(
        mode=mode,
        stage="confirmation_diagnostic",
        fold=diagnostic_fold,
        candidate="all_domain_groups",
        features=all_features,
        baseline_metrics=baseline_by_fold[diagnostic_fold.fold],
        candidate_metrics=all_metrics,
        seed=diagnostic_seed,
    )
    rows.append(all_row)

    selected_features = list(FEATURE_COLS)
    for group in confirmed:
        selected_features.extend(DOMAIN_FEATURE_GROUPS[group])

    fold4 = folds[3]
    fold4_seed = 20260920 + fold4.fold
    if confirmed:
        combined_metrics = _fit_fold(
            data,
            target,
            features=selected_features,
            fold=fold4,
            mode=mode,
            seed=fold4_seed,
        )
        combined_row = _row(
            mode=mode,
            stage="final_gate",
            fold=fold4,
            candidate="confirmed_domain_groups",
            features=selected_features,
            baseline_metrics=baseline_by_fold[fold4.fold],
            candidate_metrics=combined_metrics,
            seed=fold4_seed,
        )
        rows.append(combined_row)
        final_decision = compare_paired_predictions(
            baseline_by_fold[fold4.fold],
            combined_metrics,
            config=FINAL_GATE_CONFIG,
            temporal_checks_pass=True,
        )
        final_evaluation: dict[str, object] = final_decision.as_dict()
        final_evaluation["holdout_consumed"] = True
        final_brier_skill = final_decision.brier_skill
        final_ll_skill = final_decision.logloss_skill
        active = final_decision.promoted
    else:
        combined_row = None
        final_evaluation = {
            "promoted": False,
            "rejection_reasons": ["insufficient_support", "research_only"],
            "oos_dates": 0,
            "oos_rows": 0,
            "bootstrap_replicates": 0,
            "bootstrap_seed": FINAL_GATE_CONFIG.bootstrap_seed,
            "holdout_consumed": False,
        }
        final_brier_skill = 0.0
        final_ll_skill = 0.0
        active = False

    trust = _trust_from_skill(final_brier_skill, final_ll_skill) if active else 0.0
    production_features = selected_features if active else list(FEATURE_COLS)
    promoted_groups = confirmed if active else []
    feature_manifest = {
        "schema_version": 1,
        "baseline_features": list(FEATURE_COLS),
        "feature_groups": DOMAIN_FEATURE_GROUPS,
        "promoted_groups": promoted_groups,
        "production_features": production_features,
        "evaluation": final_evaluation,
    }
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
        "selected_features": production_features,
        "feature_manifest": feature_manifest,
        "final_evaluation": final_evaluation,
        "final_brier_skill": final_brier_skill,
        "final_logloss_skill": final_ll_skill,
        "all_groups_confirmation_brier_skill": float(all_row["brier_skill"]),
        "all_groups_confirmation_logloss_skill": float(all_row["logloss_skill"]),
        "domain_active": bool(active),
        "domain_trust": trust,
        "pattern_selection_bias_risk": (
            "screening folds select feature groups; only the untouched fourth fold is used "
            "for the paired promotion decision"
        ),
        "policy": (
            "A domain feature group can affect production only after positive OOS Brier and "
            "LogLoss skill in screening and confirmation, then positive clustered-bootstrap "
            "lower confidence bounds for both losses on the untouched combined final fold."
        ),
    }
    if combined_row is None:
        gate["reason"] = "no individual domain feature group survived confirmation"
    elif not active:
        reasons = ", ".join(str(x) for x in final_evaluation["rejection_reasons"])
        gate["reason"] = f"combined confirmed challenger failed closed: {reasons}"
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
    p_baseline = predict_with_feature_allowlist(
        baseline_model, X_pred, FEATURE_COLS
    )
    if challenger is not None:
        p_domain = predict_with_feature_allowlist(
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
        "final_evaluation": gate["final_evaluation"],
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
        "feature_manifest": gate["feature_manifest"],
        "final_evaluation": gate["final_evaluation"],
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
