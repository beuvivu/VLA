from __future__ import annotations

"""Validate persisted cầu-kèo challenger artifacts and production firewall."""

import argparse
import json
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from cau_keo_domain_challenger import DOMAIN_SCHEMA_VERSION
from cau_keo_feature_groups import (
    DOMAIN_FEATURE_GROUPS,
    FEATURE_GROUP_SCHEMA_VERSION,
)
from cau_keo_ml import FEATURE_COLS


def _finite_float(value: object, *, field: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid numeric field {field}: {value!r}") from exc
    if not np.isfinite(out):
        raise RuntimeError(f"non-finite numeric field {field}")
    return out


def _expected_features(promoted_groups: list[str]) -> list[str]:
    out = list(FEATURE_COLS)
    for group in promoted_groups:
        if group not in DOMAIN_FEATURE_GROUPS:
            raise RuntimeError(f"unknown promoted feature group: {group}")
        out.extend(DOMAIN_FEATURE_GROUPS[group])
    if len(out) != len(set(out)):
        raise RuntimeError("production feature allowlist contains duplicate columns")
    return out


def validate(*, data_dir: Path, models_dir: Path) -> dict[str, object]:
    canonical = pd.read_csv(data_dir / "xsmb.csv", usecols=["date"])
    latest = pd.to_datetime(canonical["date"], errors="raise").max().date()
    prediction_anchor = latest.isoformat()
    supervised_anchor = (latest - timedelta(days=1)).isoformat()
    next_target = (latest + timedelta(days=1)).isoformat()

    result: dict[str, object] = {
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "latest_canonical": latest.isoformat(),
        "prediction_anchor": prediction_anchor,
        "supervised_anchor": supervised_anchor,
        "next_target": next_target,
        "modes": {},
        "ok": True,
    }

    for mode in ("loto", "de"):
        gate_path = data_dir / "ai_ml" / f"cau_keo_domain_gate_{mode}.json"
        ablation_path = data_dir / "ai_ml" / f"cau_keo_domain_ablation_{mode}.csv"
        pred_path = data_dir / "ai_ml" / f"cau_keo_{mode}_all.csv"
        manifest_path = data_dir / "ai_ml" / f"cau_keo_manifest_{mode}.json"
        model_path = models_dir / f"cau_keo_{mode}.joblib"
        for path in (gate_path, ablation_path, pred_path, manifest_path, model_path):
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"missing domain challenger artifact: {path}")

        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if int(gate.get("schema_version", 0)) != DOMAIN_SCHEMA_VERSION:
            raise RuntimeError(f"{mode}: domain gate schema mismatch")
        if int(gate.get("feature_group_schema_version", 0)) != FEATURE_GROUP_SCHEMA_VERSION:
            raise RuntimeError(f"{mode}: feature-group schema mismatch")
        if set(gate.get("feature_groups", {})) != set(DOMAIN_FEATURE_GROUPS):
            raise RuntimeError(f"{mode}: feature-group manifest mismatch")
        if len(gate.get("folds", [])) != 4:
            raise RuntimeError(f"{mode}: domain gate must contain four chronological folds")

        # Enforce the temporal contract from persisted fold metadata.
        for fold in gate["folds"]:
            tr_end = pd.Timestamp(fold["train_end"])
            ca_start = pd.Timestamp(fold["calibration_start"])
            ca_end = pd.Timestamp(fold["calibration_end"])
            te_start = pd.Timestamp(fold["test_start"])
            if not tr_end < ca_start <= ca_end < te_start:
                raise RuntimeError(f"{mode}: invalid chronological boundary in fold {fold}")
            if int(fold["test_rows"]) != int(fold["test_dates"]) * 100:
                raise RuntimeError(f"{mode}: test dates are not complete 100-row clusters")

        if str(gate.get("anchor_date")) != prediction_anchor:
            raise RuntimeError(
                f"{mode}: prediction anchor {gate.get('anchor_date')} != {prediction_anchor}"
            )
        if str(gate.get("predict_for_date")) != next_target:
            raise RuntimeError(f"{mode}: next-day prediction date mismatch")

        bootstrap = gate.get("bootstrap", {})
        if bootstrap.get("cluster_unit") != "date":
            raise RuntimeError(f"{mode}: bootstrap must use date clusters")
        if int(bootstrap.get("replicates", 0)) < 100:
            raise RuntimeError(f"{mode}: insufficient bootstrap replicates")
        confidence = _finite_float(bootstrap.get("confidence"), field="bootstrap.confidence")
        if not 0.50 < confidence < 1.0:
            raise RuntimeError(f"{mode}: invalid bootstrap confidence")
        if int(bootstrap.get("minimum_oos_dates", 0)) < 5:
            raise RuntimeError(f"{mode}: invalid minimum OOS date count")

        active = bool(gate.get("domain_active"))
        trust = _finite_float(gate.get("domain_trust", 0.0), field="domain_trust")
        if not 0.0 <= trust <= 0.30:
            raise RuntimeError(f"{mode}: domain trust outside 0..0.30")
        promoted = list(gate.get("production_selected_groups", []))
        if not set(promoted).issubset(DOMAIN_FEATURE_GROUPS):
            raise RuntimeError(f"{mode}: unknown production feature group")
        production_features = list(gate.get("production_features", []))
        expected_features = _expected_features(promoted if active else [])
        if production_features != expected_features:
            raise RuntimeError(f"{mode}: production feature allowlist mismatch")

        if active:
            if not promoted:
                raise RuntimeError(f"{mode}: active challenger has no promoted groups")
            brier_skill = _finite_float(gate.get("final_brier_skill"), field="final_brier_skill")
            logloss_skill = _finite_float(
                gate.get("final_logloss_skill"), field="final_logloss_skill"
            )
            brier_ci_low = _finite_float(
                gate.get("final_brier_ci_low"), field="final_brier_ci_low"
            )
            logloss_ci_low = _finite_float(
                gate.get("final_logloss_ci_low"), field="final_logloss_ci_low"
            )
            if min(brier_skill, logloss_skill, brier_ci_low, logloss_ci_low) <= 0.0:
                raise RuntimeError(
                    f"{mode}: active challenger lacks strictly positive OOS skill/CI evidence"
                )
            if trust <= 0.0:
                raise RuntimeError(f"{mode}: active challenger must have positive trust")
            final_eval = gate.get("production_blend_final_evaluation") or {}
            if not bool(final_eval.get("promoted")):
                raise RuntimeError(f"{mode}: active flag disagrees with final production-blend gate")
            if final_eval.get("probability_space") != (
                "categorical_100" if mode == "de" else "bernoulli_marginals"
            ):
                raise RuntimeError(f"{mode}: final evaluation probability-space mismatch")
        else:
            brier_skill = float(gate.get("final_brier_skill", 0.0) or 0.0)
            logloss_skill = float(gate.get("final_logloss_skill", 0.0) or 0.0)
            if trust != 0.0:
                raise RuntimeError(f"{mode}: inactive challenger must have zero trust")
            if promoted:
                raise RuntimeError(f"{mode}: inactive challenger cannot expose promoted groups")
            if production_features != list(FEATURE_COLS):
                raise RuntimeError(f"{mode}: inactive challenger must use baseline allowlist")

        ablation = pd.read_csv(ablation_path)
        stages = set(ablation["stage"].astype(str))
        if not {"baseline", "screen", "final_diagnostic"}.issubset(stages):
            raise RuntimeError(f"{mode}: incomplete domain ablation stages")
        screened_candidates = set(
            ablation.loc[ablation["stage"].astype(str) == "screen", "candidate"].astype(str)
        )
        if screened_candidates != set(DOMAIN_FEATURE_GROUPS):
            raise RuntimeError(f"{mode}: not every feature group was independently screened")
        metric_cols = [
            "baseline_brier",
            "candidate_brier",
            "brier_delta",
            "brier_skill",
            "baseline_logloss",
            "candidate_logloss",
            "logloss_delta",
            "logloss_skill",
        ]
        for col in metric_cols:
            if not np.isfinite(pd.to_numeric(ablation[col], errors="coerce")).all():
                raise RuntimeError(f"{mode}: non-finite ablation metric {col}")

        pred = pd.read_csv(pred_path, dtype={"number_str": str, "cap50_partner": str})
        if len(pred) != 100 or set(pred["number"].astype(int)) != set(range(100)):
            raise RuntimeError(f"{mode}: prediction universe is not exactly 00..99")
        required_cols = {
            "prob",
            "ml_prob_raw",
            "ml_prob_baseline",
            "ml_prob_domain",
            "domain_prob_edge",
            "domain_trust",
            "domain_active",
            "cap50_partner",
            "cap50_pair_kind",
            "bo_family_id",
            "bong_duong_partner",
            "bong_am_partner",
        }
        missing_cols = required_cols - set(pred.columns)
        if missing_cols:
            raise RuntimeError(
                f"{mode}: missing prediction observability columns {sorted(missing_cols)}"
            )

        baseline = pred["ml_prob_baseline"].astype(float).to_numpy()
        domain = pred["ml_prob_domain"].astype(float).to_numpy()
        production = pred["ml_prob_raw"].astype(float).to_numpy()
        expected = (1.0 - trust) * baseline + trust * domain
        if not np.allclose(production, expected, atol=1e-10, rtol=1e-9):
            raise RuntimeError(f"{mode}: persisted production probability is not the gated blend")
        if not active and not np.allclose(production, baseline, atol=1e-12, rtol=0.0):
            raise RuntimeError(f"{mode}: inactive challenger changed baseline probabilities")
        if mode == "de" and not np.isclose(pred["prob"].astype(float).sum(), 1.0, atol=1e-9):
            raise RuntimeError("de: served probability vector must sum to one")

        pack = joblib.load(model_path)
        if pack.get("features") != FEATURE_COLS:
            raise RuntimeError(f"{mode}: baseline model feature schema mismatch")
        if int(pack.get("domain_schema_version", 0)) != DOMAIN_SCHEMA_VERSION:
            raise RuntimeError(f"{mode}: model-pack domain schema mismatch")
        if bool(pack.get("domain_active")) != active:
            raise RuntimeError(f"{mode}: model-pack active flag mismatch")
        if list(pack.get("domain_groups", [])) != promoted:
            raise RuntimeError(f"{mode}: model-pack promoted groups mismatch")
        if list(pack.get("domain_features", [])) != production_features:
            raise RuntimeError(f"{mode}: model-pack production features mismatch")
        feature_manifest = pack.get("domain_feature_manifest", {})
        if list(feature_manifest.get("production_features", [])) != production_features:
            raise RuntimeError(f"{mode}: serialized feature manifest mismatch")
        if list(feature_manifest.get("promoted_groups", [])) != promoted:
            raise RuntimeError(f"{mode}: serialized promoted groups mismatch")
        if str(pack.get("domain_trained_through_date")) != supervised_anchor:
            raise RuntimeError(f"{mode}: domain model supervised anchor mismatch")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_domain = manifest.get("domain_challenger", {})
        if bool(manifest_domain.get("active")) != active:
            raise RuntimeError(f"{mode}: manifest active flag mismatch")
        if list(manifest_domain.get("production_features", [])) != production_features:
            raise RuntimeError(f"{mode}: manifest production feature mismatch")
        if list(manifest_domain.get("promoted_groups", [])) != promoted:
            raise RuntimeError(f"{mode}: manifest promoted-group mismatch")

        result["modes"][mode] = {
            "active": active,
            "trust": trust,
            "groups": promoted,
            "final_brier_skill": brier_skill,
            "final_logloss_skill": logloss_skill,
            "experiment_id": gate.get("experiment_id"),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate confidence-gated persisted cầu-kèo domain challenger"
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()
    result = validate(data_dir=Path(args.data_dir), models_dir=Path(args.models_dir))
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
