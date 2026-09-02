from __future__ import annotations

"""Validate persisted cầu-kèo domain challenger artifacts and rollback invariants."""

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
    POSITIVE_SKILL_EPS,
)


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
        for path in (gate_path, ablation_path, pred_path, manifest_path, model_path):
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"missing domain challenger artifact: {path}")

        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if int(gate.get("schema_version", 0)) != DOMAIN_SCHEMA_VERSION:
            raise RuntimeError(f"{mode}: domain gate schema mismatch")
        if len(gate.get("folds", [])) != 4:
            raise RuntimeError(f"{mode}: domain gate must contain four chronological folds")
        confirmed = list(gate.get("confirmed_groups", []))
        if not set(confirmed).issubset(DOMAIN_FEATURE_GROUPS):
            raise RuntimeError(f"{mode}: unknown confirmed feature group")

        # Two date contracts coexist intentionally:
        # - prediction anchor = latest canonical draw T, used to predict T+1;
        # - supervised-through anchor = T-1, because its known label is draw T.
        if str(gate.get("anchor_date")) != prediction_anchor:
            raise RuntimeError(
                f"{mode}: prediction anchor {gate.get('anchor_date')} != {prediction_anchor}"
            )
        if str(gate.get("predict_for_date")) != next_target:
            raise RuntimeError(f"{mode}: next-day prediction date mismatch")

        active = bool(gate.get("domain_active"))
        trust = float(gate.get("domain_trust", 0.0))
        brier_skill = float(gate.get("final_brier_skill", 0.0))
        logloss_skill = float(gate.get("final_logloss_skill", 0.0))
        if not 0.0 <= trust <= 0.30:
            raise RuntimeError(f"{mode}: domain trust outside 0..0.30")
        if active:
            if not confirmed:
                raise RuntimeError(f"{mode}: active domain challenger has no confirmed groups")
            if brier_skill <= POSITIVE_SKILL_EPS or logloss_skill <= POSITIVE_SKILL_EPS:
                raise RuntimeError(f"{mode}: active challenger lacks positive final OOS skill")
            if trust <= 0.0:
                raise RuntimeError(f"{mode}: active challenger must have positive trust")
        elif trust != 0.0:
            raise RuntimeError(f"{mode}: inactive challenger must have zero trust")

        ablation = pd.read_csv(ablation_path)
        stages = set(ablation["stage"].astype(str))
        if not {"baseline", "screen", "final_diagnostic"}.issubset(stages):
            raise RuntimeError(f"{mode}: incomplete domain ablation stages")
        screened_candidates = set(
            ablation.loc[ablation["stage"].astype(str) == "screen", "candidate"].astype(str)
        )
        if screened_candidates != set(DOMAIN_FEATURE_GROUPS):
            raise RuntimeError(f"{mode}: not every domain feature group was screened")
        for col in ("brier_skill", "logloss_skill"):
            if not np.isfinite(pd.to_numeric(ablation[col], errors="coerce")).all():
                raise RuntimeError(f"{mode}: non-finite ablation metric {col}")

        pred = pd.read_csv(pred_path, dtype={"number_str": str, "cap50_partner": str})
        if len(pred) != 100 or set(pred["number"].astype(int)) != set(range(100)):
            raise RuntimeError(f"{mode}: prediction universe is not exactly 00..99")
        required_cols = {
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
            raise RuntimeError(f"{mode}: missing prediction observability columns {sorted(missing_cols)}")

        baseline = pred["ml_prob_baseline"].astype(float).to_numpy()
        domain = pred["ml_prob_domain"].astype(float).to_numpy()
        production = pred["ml_prob_raw"].astype(float).to_numpy()
        expected = (1.0 - trust) * baseline + trust * domain
        if not np.allclose(production, expected, atol=1e-10, rtol=1e-9):
            raise RuntimeError(f"{mode}: persisted production probability is not the gated blend")
        if not active and not np.allclose(production, baseline, atol=1e-12, rtol=0.0):
            raise RuntimeError(f"{mode}: inactive challenger changed baseline probabilities")

        pack = joblib.load(model_path)
        if int(pack.get("domain_schema_version", 0)) != DOMAIN_SCHEMA_VERSION:
            raise RuntimeError(f"{mode}: model-pack domain schema mismatch")
        if bool(pack.get("domain_active")) != active:
            raise RuntimeError(f"{mode}: model-pack active flag mismatch")
        if list(pack.get("domain_groups", [])) != list(gate.get("production_selected_groups", [])):
            raise RuntimeError(f"{mode}: model-pack selected groups mismatch")
        if str(pack.get("domain_trained_through_date")) != supervised_anchor:
            raise RuntimeError(f"{mode}: domain model supervised anchor mismatch")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_domain = manifest.get("domain_challenger", {})
        if bool(manifest_domain.get("active")) != active:
            raise RuntimeError(f"{mode}: manifest active flag mismatch")

        result["modes"][mode] = {
            "active": active,
            "trust": trust,
            "groups": list(gate.get("production_selected_groups", [])),
            "final_brier_skill": brier_skill,
            "final_logloss_skill": logloss_skill,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate persisted cầu-kèo domain challenger")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()
    result = validate(data_dir=Path(args.data_dir), models_dir=Path(args.models_dir))
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
