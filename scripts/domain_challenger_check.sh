#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${VN_LOTTERY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT/src}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

TMP_MODELS="$(mktemp -d)"
TMP_OUT="$(mktemp -d)"
trap 'rm -rf "$TMP_MODELS" "$TMP_OUT"' EXIT

printf '%s\n' "== Confidence-gated four-fold domain challenger =="
python src/cau_keo_domain_challenger.py \
  --mode both \
  --models-dir "$TMP_MODELS" \
  --out-dir "$TMP_OUT" \
  --window-days 2000 \
  --bootstrap-replicates 500 \
  --bootstrap-seed 20260902 \
  --promotion-ci 0.95 \
  --minimum-oos-dates 30 \
  --top 3

for mode in loto de; do
  test -s "$TMP_MODELS/cau_keo_${mode}.joblib"
  test -s "$TMP_OUT/cau_keo_${mode}_all.csv"
  test -s "$TMP_OUT/cau_keo_domain_ablation_${mode}.csv"
  test -s "$TMP_OUT/cau_keo_domain_gate_${mode}.json"
  test -s "$TMP_OUT/cau_keo_manifest_${mode}.json"
done

python - <<PY
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from cau_keo_domain_challenger import DOMAIN_SCHEMA_VERSION
from cau_keo_feature_groups import DOMAIN_FEATURE_GROUPS
from cau_keo_ml import FEATURE_COLS

expected_groups = {"partner", "cap_50", "bo", "bong", "cham", "tong"}
assert set(DOMAIN_FEATURE_GROUPS) == expected_groups

for mode in ("loto", "de"):
    gate = json.loads(Path(f"$TMP_OUT/cau_keo_domain_gate_{mode}.json").read_text(encoding="utf-8"))
    assert int(gate["schema_version"]) == DOMAIN_SCHEMA_VERSION, gate
    assert len(gate["folds"]) == 4, gate
    assert set(gate["feature_groups"]) == expected_groups, gate
    assert gate["bootstrap"]["cluster_unit"] == "date", gate
    assert int(gate["bootstrap"]["replicates"]) == 500, gate
    assert float(gate["bootstrap"]["confidence"]) == 0.95, gate
    assert set(gate["confirmed_groups"]).issubset(expected_groups), gate
    assert 0.0 <= float(gate["domain_trust"]) <= 0.30, gate

    promoted = list(gate["production_selected_groups"])
    production_features = list(gate["production_features"])
    expected_features = list(FEATURE_COLS)
    if gate["domain_active"]:
        assert promoted, gate
        for group in promoted:
            expected_features.extend(DOMAIN_FEATURE_GROUPS[group])
        assert float(gate["final_brier_skill"]) > 0.0, gate
        assert float(gate["final_logloss_skill"]) > 0.0, gate
        assert float(gate["final_brier_ci_low"]) > 0.0, gate
        assert float(gate["final_logloss_ci_low"]) > 0.0, gate
        assert float(gate["domain_trust"]) > 0.0, gate
        final_eval = gate["production_blend_final_evaluation"]
        assert final_eval["promoted"] is True, final_eval
        assert final_eval["probability_space"] == (
            "categorical_100" if mode == "de" else "bernoulli_marginals"
        )
    else:
        assert promoted == [], gate
        assert float(gate["domain_trust"]) == 0.0, gate
    assert production_features == expected_features, (mode, production_features, expected_features)
    assert len(production_features) == len(set(production_features)), mode

    for fold in gate["folds"]:
        assert int(fold["test_rows"]) == 100 * int(fold["test_dates"]), fold
        assert pd.Timestamp(fold["train_end"]) < pd.Timestamp(fold["calibration_start"])
        assert pd.Timestamp(fold["calibration_end"]) < pd.Timestamp(fold["test_start"])

    ablation = pd.read_csv(f"$TMP_OUT/cau_keo_domain_ablation_{mode}.csv")
    assert {"baseline", "screen", "final_diagnostic"}.issubset(set(ablation["stage"])), ablation["stage"].unique()
    assert set(ablation.loc[ablation["stage"] == "screen", "candidate"]) == expected_groups, mode
    for col in ("brier_skill", "logloss_skill", "brier_delta", "logloss_delta"):
        for value in ablation[col].astype(float):
            assert math.isfinite(value), (mode, col, value)

    pred = pd.read_csv(f"$TMP_OUT/cau_keo_{mode}_all.csv", dtype={"number_str": str, "cap50_partner": str})
    assert len(pred) == 100, (mode, len(pred))
    assert set(pred["number"].astype(int)) == set(range(100)), mode
    required = {"prob", "ml_prob_baseline", "ml_prob_domain", "domain_prob_edge", "domain_trust", "domain_active"}
    assert required.issubset(pred.columns), pred.columns
    trust = pred["domain_trust"].astype(float).to_numpy()
    assert np.allclose(trust, float(gate["domain_trust"])), mode
    baseline = pred["ml_prob_baseline"].astype(float).to_numpy()
    domain = pred["ml_prob_domain"].astype(float).to_numpy()
    production = pred["ml_prob_raw"].astype(float).to_numpy()
    expected = (1.0 - trust) * baseline + trust * domain
    assert np.allclose(production, expected, atol=1e-10), mode
    if not gate["domain_active"]:
        assert np.allclose(production, baseline, atol=1e-12), mode
    if mode == "de":
        assert np.isclose(pred["prob"].astype(float).sum(), 1.0, atol=1e-9), pred["prob"].sum()

    pack = joblib.load(f"$TMP_MODELS/cau_keo_{mode}.joblib")
    assert pack["features"] == FEATURE_COLS, mode
    assert int(pack["domain_schema_version"]) == DOMAIN_SCHEMA_VERSION, mode
    assert bool(pack["domain_active"]) == bool(gate["domain_active"]), mode
    assert pack["domain_groups"] == promoted, mode
    assert pack["domain_features"] == production_features, mode
    assert pack["domain_feature_manifest"]["production_features"] == production_features, mode

    manifest = json.loads(Path(f"$TMP_OUT/cau_keo_manifest_{mode}.json").read_text(encoding="utf-8"))
    domain_manifest = manifest["domain_challenger"]
    assert domain_manifest["active"] == gate["domain_active"], mode
    assert domain_manifest["production_features"] == production_features, mode
    assert domain_manifest["promoted_groups"] == promoted, mode
    print(
        "OK confidence-gated domain challenger",
        mode,
        "active=",
        gate["domain_active"],
        "groups=",
        promoted,
        "brier_skill=",
        gate["final_brier_skill"],
        "logloss_skill=",
        gate["final_logloss_skill"],
        "reason=",
        gate["reason"],
    )
PY
