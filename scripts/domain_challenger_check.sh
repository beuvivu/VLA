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

printf '%s\n' "== Four-fold domain-feature challenger =="
python src/cau_keo_domain_challenger.py \
  --mode both \
  --models-dir "$TMP_MODELS" \
  --out-dir "$TMP_OUT" \
  --window-days 2000 \
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

from cau_keo_domain_challenger import DOMAIN_FEATURE_GROUPS, DOMAIN_SCHEMA_VERSION
from cau_keo_ml import FEATURE_COLS

for mode in ("loto", "de"):
    gate = json.loads(Path(f"$TMP_OUT/cau_keo_domain_gate_{mode}.json").read_text(encoding="utf-8"))
    assert int(gate["schema_version"]) == DOMAIN_SCHEMA_VERSION, gate
    assert len(gate["folds"]) == 4, gate
    assert set(gate["feature_groups"]) == set(DOMAIN_FEATURE_GROUPS), gate
    assert set(gate["confirmed_groups"]).issubset(DOMAIN_FEATURE_GROUPS), gate
    assert 0.0 <= float(gate["domain_trust"]) <= 0.30, gate
    evaluation = gate["final_evaluation"]
    feature_manifest = gate["feature_manifest"]
    assert feature_manifest["production_features"] == gate["selected_features"], gate
    assert feature_manifest["promoted_groups"] == gate["production_selected_groups"], gate
    if gate["domain_active"]:
        assert gate["confirmed_groups"], gate
        assert float(gate["final_brier_skill"]) > 0.0, gate
        assert float(gate["final_logloss_skill"]) > 0.0, gate
        assert float(gate["domain_trust"]) > 0.0, gate
        assert not evaluation["rejection_reasons"], gate
        assert int(evaluation["oos_dates"]) >= 30, gate
        assert float(evaluation["brier_improvement_ci"]["lower"]) > 0.0, gate
        assert float(evaluation["logloss_improvement_ci"]["lower"]) > 0.0, gate
    else:
        assert float(gate["domain_trust"]) == 0.0, gate

    ablation = pd.read_csv(f"$TMP_OUT/cau_keo_domain_ablation_{mode}.csv")
    assert {"baseline", "screen", "confirmation_diagnostic"}.issubset(set(ablation["stage"])), ablation["stage"].unique()
    assert set(ablation.loc[ablation["stage"] == "screen", "candidate"]) == set(DOMAIN_FEATURE_GROUPS), mode
    assert ablation.groupby("fold")["seed"].nunique().eq(1).all(), mode
    for value in ablation["brier_skill"].astype(float):
        assert math.isfinite(value), (mode, value)
    for value in ablation["logloss_skill"].astype(float):
        assert math.isfinite(value), (mode, value)

    pred = pd.read_csv(f"$TMP_OUT/cau_keo_{mode}_all.csv", dtype={"number_str": str, "cap50_partner": str})
    assert len(pred) == 100, (mode, len(pred))
    assert set(pred["number"].astype(int)) == set(range(100)), mode
    assert {"ml_prob_baseline", "ml_prob_domain", "domain_prob_edge", "domain_trust", "domain_active"}.issubset(pred.columns), pred.columns
    trust = pred["domain_trust"].astype(float).to_numpy()
    assert np.allclose(trust, float(gate["domain_trust"])), mode
    baseline = pred["ml_prob_baseline"].astype(float).to_numpy()
    domain = pred["ml_prob_domain"].astype(float).to_numpy()
    production = pred["ml_prob_raw"].astype(float).to_numpy()
    expected = (1.0 - trust) * baseline + trust * domain
    assert np.allclose(production, expected, atol=1e-10), mode
    if not gate["domain_active"]:
        assert np.allclose(production, baseline, atol=1e-12), mode

    pack = joblib.load(f"$TMP_MODELS/cau_keo_{mode}.joblib")
    assert pack["features"] == FEATURE_COLS, mode
    assert int(pack["domain_schema_version"]) == DOMAIN_SCHEMA_VERSION, mode
    assert bool(pack["domain_active"]) == bool(gate["domain_active"]), mode
    assert pack["domain_groups"] == gate["production_selected_groups"], mode

    manifest = json.loads(Path(f"$TMP_OUT/cau_keo_manifest_{mode}.json").read_text(encoding="utf-8"))
    assert manifest["domain_challenger"]["active"] == gate["domain_active"], mode
    print(
        "OK domain challenger",
        mode,
        "active=",
        gate["domain_active"],
        "groups=",
        gate["production_selected_groups"],
        "brier_skill=",
        gate["final_brier_skill"],
        "logloss_skill=",
        gate["final_logloss_skill"],
    )
PY
