from __future__ import annotations

"""Validate persisted cầu-kèo challenger scientific and rollback invariants."""

import argparse
import json
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from cau_keo_domain_challenger import (
    DOMAIN_FEATURE_GROUPS,
    DOMAIN_SCHEMA_VERSION,
    FEATURE_COLS,
    POSITIVE_SKILL_EPS,
)


def _expected_features(groups: list[str]) -> list[str]:
    unknown = [g for g in groups if g not in DOMAIN_FEATURE_GROUPS]
    if unknown:
        raise RuntimeError(f"unknown production domain groups: {unknown}")
    features = list(FEATURE_COLS)
    for group in groups:
        features.extend(DOMAIN_FEATURE_GROUPS[group])
    if len(features) != len(set(features)):
        raise RuntimeError("production feature manifest contains duplicate columns")
    return features


def _positive_ci(value: object, *, name: str, mode: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise RuntimeError(f"{mode}: active challenger missing {name}")
    low, high = float(value[0]), float(value[1])
    if not np.isfinite([low, high]).all() or low <= 0.0 or high < low:
        raise RuntimeError(f"{mode}: invalid positive {name}: {value}")
    return [low, high]


def validate(*, data_dir: Path, models_dir: Path) -> dict[str, object]:
    canonical = pd.read_csv(data_dir / "xsmb.csv", usecols=["date"])
    latest = pd.to_datetime(canonical["date"]).max().date()
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
        for path in (
            gate_path,
            ablation_path,
            pred_path,
            manifest_path,
            model_path,
        ):
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"missing domain challenger artifact: {path}")

        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if int(gate.get("schema_version", 0)) != DOMAIN_SCHEMA_VERSION:
            raise RuntimeError(f"{mode}: domain gate schema mismatch")
        if len(gate.get("folds", [])) != 4:
            raise RuntimeError(
                f"{mode}: domain gate must contain four chronological folds"
            )
        if set(gate.get("feature_groups", {})) != set(DOMAIN_FEATURE_GROUPS):
            raise RuntimeError(f"{mode}: feature-group schema mismatch")

        confirmed = [str(x) for x in gate.get("confirmed_groups", [])]
        production_groups = [
            str(x) for x in gate.get("production_selected_groups", [])
        ]
        if not set(confirmed).issubset(DOMAIN_FEATURE_GROUPS):
            raise RuntimeError(f"{mode}: unknown confirmed feature group")
        if not set(production_groups).issubset(confirmed):
            raise RuntimeError(
                f"{mode}: production groups are not a subset of confirmed groups"
            )

        if str(gate.get("anchor_date")) != prediction_anchor:
            raise RuntimeError(
                f"{mode}: prediction anchor {gate.get('anchor_date')} != "
                f"{prediction_anchor}"
            )
        if str(gate.get("predict_for_date")) != next_target:
            raise RuntimeError(f"{mode}: next-day prediction date mismatch")

        active = bool(gate.get("domain_active"))
        trust = float(gate.get("domain_trust", 0.0))
        brier_skill = float(gate.get("final_brier_skill", 0.0))
        logloss_skill = float(gate.get("final_logloss_skill", 0.0))
        if not 0.0 <= trust <= 0.30:
            raise RuntimeError(f"{mode}: domain trust outside 0..0.30")
        if int(gate.get("bootstrap_replicates", 0)) < 100:
            raise RuntimeError(f"{mode}: invalid bootstrap replicate contract")
        if int(gate.get("minimum_oos_dates", 0)) < 2:
            raise RuntimeError(f"{mode}: invalid minimum OOS date contract")

        expected_features = _expected_features(production_groups)
        if list(gate.get("production_features", [])) != expected_features:
            raise RuntimeError(f"{mode}: gate production feature allowlist mismatch")
        if list(gate.get("baseline_features", [])) != list(FEATURE_COLS):
            raise RuntimeError(f"{mode}: gate baseline feature allowlist mismatch")

        brier_ci: list[float] | None = None
        logloss_ci: list[float] | None = None
        if active:
            if not production_groups:
                raise RuntimeError(
                    f"{mode}: active domain challenger has no promoted groups"
                )
            if (
                brier_skill <= POSITIVE_SKILL_EPS
                or logloss_skill <= POSITIVE_SKILL_EPS
            ):
                raise RuntimeError(
                    f"{mode}: active challenger lacks positive final OOS skill"
                )
            brier_ci = _positive_ci(
                gate.get("final_brier_ci"), name="Brier CI", mode=mode
            )
            logloss_ci = _positive_ci(
                gate.get("final_logloss_ci"), name="LogLoss CI", mode=mode
            )
            if trust <= 0.0:
                raise RuntimeError(
                    f"{mode}: active challenger must have positive fixed trust"
                )
        else:
            if trust != 0.0:
                raise RuntimeError(
                    f"{mode}: inactive challenger must have zero trust"
                )
            if production_groups:
                raise RuntimeError(
                    f"{mode}: inactive challenger cannot expose production groups"
                )
            if expected_features != list(FEATURE_COLS):
                raise RuntimeError(
                    f"{mode}: inactive challenger must preserve baseline features"
                )

        ablation = pd.read_csv(ablation_path)
        stages = set(ablation["stage"].astype(str))
        if not {"baseline", "screen", "final_diagnostic"}.issubset(stages):
            raise RuntimeError(f"{mode}: incomplete domain ablation stages")
        screened_candidates = set(
            ablation.loc[
                ablation["stage"].astype(str) == "screen", "candidate"
            ].astype(str)
        )
        if screened_candidates != set(DOMAIN_FEATURE_GROUPS):
            raise RuntimeError(
                f"{mode}: not every domain feature group was screened"
            )
        for col in (
            "baseline_brier",
            "candidate_brier",
            "brier_skill",
            "baseline_logloss",
            "candidate_logloss",
            "logloss_skill",
        ):
            if not np.isfinite(
                pd.to_numeric(ablation[col], errors="coerce")
            ).all():
                raise RuntimeError(f"{mode}: non-finite ablation metric {col}")

        pred = pd.read_csv(
            pred_path,
            dtype={"number_str": str, "partner": str, "cap50_partner": str},
        )
        if len(pred) != 100 or set(pred["number"].astype(int)) != set(range(100)):
            raise RuntimeError(
                f"{mode}: prediction universe is not exactly 00..99"
            )
        required_cols = {
            "prob",
            "ml_prob_raw",
            "ml_prob_baseline",
            "ml_prob_domain",
            "domain_prob_edge",
            "domain_trust",
            "domain_active",
            "partner",
            "cap50_partner",
            "cap50_pair_kind",
            "bo_family_id",
            "bong_duong_partner",
            "bong_am_partner",
        }
        missing_cols = required_cols - set(pred.columns)
        if missing_cols:
            raise RuntimeError(
                f"{mode}: missing prediction observability columns "
                f"{sorted(missing_cols)}"
            )

        baseline = pred["ml_prob_baseline"].astype(float).to_numpy()
        domain = pred["ml_prob_domain"].astype(float).to_numpy()
        production = pred["ml_prob_raw"].astype(float).to_numpy()
        expected = (1.0 - trust) * baseline + trust * domain
        if not np.allclose(production, expected, atol=1e-10, rtol=1e-9):
            raise RuntimeError(
                f"{mode}: persisted production probability is not gated blend"
            )
        if not active and not np.allclose(
            production, baseline, atol=1e-12, rtol=0.0
        ):
            raise RuntimeError(
                f"{mode}: inactive challenger changed baseline probabilities"
            )
        if mode == "de":
            served = pred["prob"].astype(float).to_numpy()
            if not np.isclose(float(served.sum()), 1.0, atol=1e-8):
                raise RuntimeError(
                    "de: served categorical probabilities do not sum to one"
                )

        pack = joblib.load(model_path)
        if int(pack.get("domain_schema_version", 0)) != DOMAIN_SCHEMA_VERSION:
            raise RuntimeError(f"{mode}: model-pack domain schema mismatch")
        if bool(pack.get("domain_active")) != active:
            raise RuntimeError(f"{mode}: model-pack active flag mismatch")
        if list(pack.get("domain_groups", [])) != production_groups:
            raise RuntimeError(f"{mode}: model-pack selected groups mismatch")
        if list(pack.get("domain_features", [])) != expected_features:
            raise RuntimeError(f"{mode}: model-pack feature allowlist mismatch")
        pack_manifest = pack.get("domain_feature_manifest", {})
        if list(pack_manifest.get("production_features", [])) != expected_features:
            raise RuntimeError(f"{mode}: model-pack feature manifest mismatch")
        if str(pack.get("domain_trained_through_date")) != supervised_anchor:
            raise RuntimeError(
                f"{mode}: domain model supervised anchor mismatch"
            )
        if active and pack.get("domain_challenger_model") is None:
            raise RuntimeError(f"{mode}: active challenger model is missing")
        if not active and pack.get("domain_challenger_model") is not None:
            raise RuntimeError(
                f"{mode}: inactive challenger must not retain production model"
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_domain = manifest.get("domain_challenger", {})
        if bool(manifest_domain.get("active")) != active:
            raise RuntimeError(f"{mode}: manifest active flag mismatch")
        if list(manifest_domain.get("selected_features", [])) != expected_features:
            raise RuntimeError(f"{mode}: manifest feature allowlist mismatch")

        result["modes"][mode] = {
            "active": active,
            "trust": trust,
            "groups": production_groups,
            "final_brier_skill": brier_skill,
            "final_logloss_skill": logloss_skill,
            "final_brier_ci": brier_ci,
            "final_logloss_ci": logloss_ci,
            "reason": gate.get("reason"),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate persisted scientific cầu-kèo domain challenger"
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()
    result = validate(
        data_dir=Path(args.data_dir), models_dir=Path(args.models_dir)
    )
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
