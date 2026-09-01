#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${VN_LOTTERY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

export PYTHONPATH="${PYTHONPATH:-$ROOT/src}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

printf '%s\n' "== GitHub-only structure =="
for forbidden in \
  requirements-hosting.txt passenger_wsgi.py deploy hosting \
  src/webapp.py src/hosting_health.py src/scheduler.py; do
  if [[ -e "$forbidden" ]]; then
    echo "Forbidden server-deployment artifact still exists: $forbidden" >&2
    exit 2
  fi
done

printf '%s\n' "== Lint + Python syntax =="
ruff check --select E9,F63,F7,F82 src tests
python -m compileall -q src tests

printf '%s\n' "== Unit/regression tests =="
python -m pytest -q

printf '%s\n' "== Source policy =="
python - <<'PYSOURCE'
from sources import default_sources, source_independence_key
expected = [
    "xoso.com.vn",
    "mketqua.net",
    "www.minhngoc.net.vn",
    "xosominhngoc.com",
    "xosodaiphat.com",
    "hainhay.net",
]
actual = [s.name for s in default_sources()]
assert actual == expected, (actual, expected)
assert source_independence_key("www.minhngoc.net.vn") == source_independence_key("xosominhngoc.com")
print("OK", actual)
PYSOURCE

printf '%s\n' "== Data integrity + canonical statistics =="
python src/validate_data.py --lookback-days 90 --out data/health.json
python src/statistical_signal.py --mode both
python src/significance_stats.py --windows 30,90,365
# Rebuild the current production cầu-kèo artifacts and model pack from the
# calendar-validated feature builder.  The final supervised anchor is necessarily
# one day behind the latest canonical draw because its label is that latest draw.
python src/cau_keo_ml.py --mode both --models-dir models --out-dir data/ai_ml --window-days 2000 --top 20 --force-train
python src/statistical_matrices.py
python src/conditional_matrices.py --top 500
python src/statistics_ai_overlay.py

printf '%s\n' "== Calendar-safe conditional and AI-overlay integrity =="
python - <<'PYCANON'
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

latest = pd.to_datetime(pd.read_csv("data/xsmb.csv", usecols=["date"])["date"]).max().date()
expected_target = (latest + timedelta(days=1)).isoformat()
rows = len(pd.read_csv("data/xsmb.csv", usecols=["date"]))

cond = json.loads(Path("data/advanced/conditional_matrices_diagnostics.json").read_text(encoding="utf-8"))
assert cond["calendar_rows"] == rows, cond
assert cond["exact_next_day_pairs"] == max(0, rows - 1), cond
assert cond["skipped_nonconsecutive_boundaries"] == 0, cond
for name in (
    "conditional_loto_after_special_top500.csv",
    "conditional_special_after_special_top500.csv",
    "conditional_loto_after_loto_top500.csv",
):
    path = Path("data/advanced") / name
    assert path.is_file() and path.stat().st_size > 0, path

ai = json.loads(Path("data/advanced/ai_ml_signal_diagnostics.json").read_text(encoding="utf-8"))
assert ai["anchor_date"] == latest.isoformat(), ai
assert ai["target_date"] == expected_target, ai
for mode in ("loto", "de"):
    table = pd.read_csv(f"data/advanced/ai_ml_signal_{mode}.csv")
    assert len(table) == 100, (mode, len(table))
    assert set(table["number"].astype(int)) == set(range(100)), mode
    assert set(table["target_date"].astype(str)) == {expected_target}, mode
    assert table["ml_available"].astype(str).str.lower().isin(["true", "false"]).all(), mode
    diag = ai["modes"][mode]["ml"]
    if diag["available"]:
        assert diag["source"] in {"cau_keo", "base_ml", "ensemble_exact"}, diag
        assert diag["attempts"][-1]["status"] == "ok", diag
    else:
        assert table["ml_source"].eq("unavailable").all(), mode
print("OK canonical conditional/AI overlays", latest, "->", expected_target)
PYCANON

printf '%s\n' "== Higher-order dynamics integrity =="
python - <<'PYDYN'
import json
import numpy as np
import pandas as pd

for mode in ("loto", "de"):
    cur = pd.read_csv(f"data/number_dynamics/current_dynamics_{mode}.csv")
    trans = pd.read_csv(f"data/number_dynamics/transition_prob_lag1_{mode}.csv")
    lift = pd.read_csv(f"data/number_dynamics/transition_lift_lag1_{mode}.csv")
    phi = pd.read_csv(f"data/number_dynamics/cooccurrence_phi_{mode}.csv")
    lag = pd.read_csv(f"data/number_dynamics/lag_dependency_{mode}.csv")
    diag = json.load(open(f"data/number_dynamics/diagnostics_{mode}.json", encoding="utf-8"))

    assert len(cur) == 100, (mode, len(cur))
    assert trans.shape == (100, 101), (mode, trans.shape)
    assert lift.shape == (100, 101), (mode, lift.shape)
    assert phi.shape == (100, 101), (mode, phi.shape)
    assert len(lag) == 100 * 2 * 6, (mode, len(lag))
    p = cur.sort_values("number")["prob"].to_numpy(dtype=float)
    assert np.isfinite(p).all(), mode
    if mode == "de":
        assert np.isclose(float(p.sum()), 1.0, atol=1e-8), float(p.sum())
    else:
        assert ((p > 0.0) & (p < 1.0)).all(), mode
    assert diag["calendar_contiguous"] is True, diag
    assert 0.15 <= float(diag["global_dynamics_reliability"]) <= 0.80, diag
    print("OK dynamics", mode, "reliability=", diag["global_dynamics_reliability"])
PYDYN

printf '%s\n' "== Fresh base-ML train/predict smoke =="
TMP_MODELS="$(mktemp -d)"
TMP_PRED="$(mktemp -d)"
TMP_CAU="$(mktemp -d)"
trap 'rm -rf "$TMP_MODELS" "$TMP_PRED" "$TMP_CAU"' EXIT
python src/ml_train.py --mode loto --out-dir "$TMP_MODELS" --window-days 365
python src/ml_train.py --mode de --out-dir "$TMP_MODELS" --window-days 365
python src/ml_predict.py --models-dir "$TMP_MODELS" --out-dir "$TMP_PRED" --window-days 365 --top 3

test -s "$TMP_PRED/predict_next_loto_ml_all.csv"
test -s "$TMP_PRED/predict_next_de_ml_all.csv"

printf '%s\n' "== Leakage-safe stacked-ML challenger =="
python src/meta_predictor.py \
  --mode loto --models-dir "$TMP_MODELS" --report-dir "$TMP_PRED" \
  --window-days 240 --min-days 100 --half-life-days 90
python src/meta_predictor.py \
  --mode de --models-dir "$TMP_MODELS" --report-dir "$TMP_PRED" \
  --window-days 240 --min-days 100 --half-life-days 90

test -s "$TMP_MODELS/meta_loto.joblib"
test -s "$TMP_MODELS/meta_de.joblib"
test -s "$TMP_PRED/meta_report_loto.json"
test -s "$TMP_PRED/meta_report_de.json"

python - <<PYMETA
import joblib
import math
from meta_predictor import META_SCHEMA_VERSION

for mode in ("loto", "de"):
    path = "$TMP_MODELS/meta_" + mode + ".joblib"
    pack = joblib.load(path)
    assert int(pack["schema_version"]) == META_SCHEMA_VERSION, path
    assert pack["mode"] == mode, path
    assert 0.0 <= float(pack["meta_trust"]) <= 0.40, pack["meta_trust"]
    for key in (
        "validation_logloss",
        "validation_brier",
        "baseline_validation_logloss",
        "baseline_validation_brier",
        "logloss_skill",
        "brier_skill",
    ):
        assert math.isfinite(float(pack[key])), (mode, key, pack[key])
    assert len(pack["validation_days"]) >= 15, mode
    print(
        "OK stacked ML",
        mode,
        "quality=",
        pack["quality_pass"],
        "trust=",
        pack["meta_trust"],
        "skill=",
        pack["logloss_skill"],
    )
PYMETA

printf '%s\n' "== Production model artifact compatibility =="
python - <<'PYMODEL'
from datetime import timedelta

import joblib
import pandas as pd
from cau_keo_ml import FEATURE_COLS as CAU_FEATURE_COLS
from ml_train import FEATURE_SCHEMA_VERSION

calendar = sorted(
    pd.to_datetime(pd.read_csv("data/xsmb.csv", usecols=["date"])["date"])
    .dt.date.unique()
)
assert len(calendar) >= 2, len(calendar)
latest_date = calendar[-1]
latest = latest_date.isoformat()
last_supervised_anchor = calendar[-2].isoformat()
assert calendar[-2] + timedelta(days=1) == latest_date, calendar[-2:]

for path in ["models/ml_loto.joblib", "models/ml_de.joblib"]:
    obj = joblib.load(path)
    assert isinstance(obj, dict) and "model" in obj, path
    assert int(obj.get("feature_schema_version", 0)) == FEATURE_SCHEMA_VERSION, path
    assert str(obj.get("trained_through_date")) == latest, (path, obj.get("trained_through_date"), latest)
    print("OK", path, "trust=", obj.get("model_trust"))

for path in ["models/cau_keo_loto.joblib", "models/cau_keo_de.joblib"]:
    obj = joblib.load(path)
    assert isinstance(obj, dict) and "model" in obj, path
    assert obj.get("features") == CAU_FEATURE_COLS, path
    # Cầu-kèo rows are (anchor t -> target t+1).  The newest canonical draw is
    # the newest *label*, so the latest trainable anchor is exactly one day prior.
    assert str(obj.get("trained_through_date")) == last_supervised_anchor, (
        path,
        obj.get("trained_through_date"),
        last_supervised_anchor,
    )
    assert obj.get("calendar_contract") == "daily-contiguous raw and two-digit histories", obj
    print(
        "OK",
        path,
        "supervised_anchor=",
        obj.get("trained_through_date"),
        "target_through=",
        latest,
    )
PYMODEL

printf '%s\n' "== Cầu-kèo production-path smoke =="
python src/cau_keo_ml.py \
  --mode both --models-dir models --out-dir "$TMP_CAU" \
  --window-days 2000 --top 3
for path in \
  "$TMP_CAU/cau_keo_loto_all.csv" \
  "$TMP_CAU/cau_keo_de_all.csv" \
  "$TMP_CAU/cau_keo_manifest_loto.json" \
  "$TMP_CAU/cau_keo_manifest_de.json"; do
  test -s "$path" || { echo "Missing cầu-kèo smoke output: $path" >&2; exit 3; }
done
python - <<PYCAU
import json
from pathlib import Path
for mode in ("loto", "de"):
    obj = json.loads(Path("$TMP_CAU/cau_keo_manifest_" + mode + ".json").read_text(encoding="utf-8"))
    assert obj["calendar_contract"] == "daily-contiguous raw and two-digit histories", obj
print("OK cau-keo calendar-safe smoke")
PYCAU

printf '%s\n' "== Static GitHub Pages builders =="
python src/build_docs_ml.py
python src/build_dashboard.py
python src/build_markdown_dashboard.py
python src/build_statistics_dashboard.py
python src/build_landing_page.py
python src/build_fun_prediction.py
python src/cleanup_artifacts.py --retention-days 45

printf '%s\n' "== Fun prediction board integrity =="
python - <<'PYFUN'
import json
from pathlib import Path

payload = json.loads(Path("data/predict/fun_draw_next.json").read_text(encoding="utf-8"))
assert payload["kind"] == "entertainment_simulation"
assert len(payload["groups"]) == 8
assert len(payload["rows"]) == 27
assert len(payload["top_loto"]) == 10
assert len(payload["top_de"]) == 10
assert payload["target_date"] > payload["anchor_date"]
for page in ("docs/index.html", "docs/landing.html", "docs/landing_desktop.html"):
    text = Path(page).read_text(encoding="utf-8")
    assert text.count('id="du-doan-vui"') == 1, page
    assert "Không phải kết quả thật" in text, page
print("OK fun prediction", payload["anchor_date"], "->", payload["target_date"])
PYFUN

printf '%s\n' "== Post-build production consistency =="
python src/production_audit.py \
  --consistency-only \
  --strict \
  --json-out /tmp/production-audit-release.json

printf '%s\n' "== Required outputs =="
required=(
  data/xsmb.csv
  data/xsmb.json
  data/source_audit.json
  data/history/pred_loto.csv
  data/history/pred_de.csv
  data/ai_ml/cau_keo_loto_top20.csv
  data/ai_ml/cau_keo_de_top20.csv
  data/significance/global_diagnostics.json
  data/statistical_signal/predict_next_loto_stat_all.csv
  data/statistical_signal/predict_next_de_stat_all.csv
  data/number_dynamics/current_dynamics_loto.csv
  data/number_dynamics/current_dynamics_de.csv
  data/number_dynamics/transition_prob_lag1_loto.csv
  data/number_dynamics/transition_prob_lag1_de.csv
  data/number_dynamics/transition_lift_lag1_loto.csv
  data/number_dynamics/transition_lift_lag1_de.csv
  data/number_dynamics/cooccurrence_phi_loto.csv
  data/number_dynamics/cooccurrence_phi_de.csv
  data/number_dynamics/lag_dependency_loto.csv
  data/number_dynamics/lag_dependency_de.csv
  data/number_dynamics/diagnostics_loto.json
  data/number_dynamics/diagnostics_de.json
  data/advanced/conditional_matrices_diagnostics.json
  data/advanced/ai_ml_signal_diagnostics.json
  data/advanced/ai_ml_signal_loto.csv
  data/advanced/ai_ml_signal_de.csv
  data/predict/fun_draw_next.json
  data/predict/fun_draw_next.csv
  docs/live.html
  models/ml_loto.joblib
  models/ml_de.joblib
  models/cau_keo_loto.joblib
  models/cau_keo_de.joblib
  DASHBOARD.md
  docs/index.html
  docs/statistics.html
  docs/dashboard.html
  docs/model-quality.html
)
for path in "${required[@]}"; do
  test -s "$path" || { echo "Missing/empty output: $path" >&2; exit 3; }
done

echo "OK GitHub-only release check"
