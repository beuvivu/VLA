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

printf '%s\n' "== Data integrity + statistical signal =="
python src/validate_data.py --lookback-days 90 --out data/health.json
python src/statistical_signal.py --mode both
python src/significance_stats.py --windows 30,90,365

printf '%s\n' "== Fresh base-ML train/predict smoke =="
TMP_MODELS="$(mktemp -d)"
TMP_PRED="$(mktemp -d)"
trap 'rm -rf "$TMP_MODELS" "$TMP_PRED"' EXIT
python src/ml_train.py --mode loto --out-dir "$TMP_MODELS" --window-days 365
python src/ml_train.py --mode de --out-dir "$TMP_MODELS" --window-days 365
python src/ml_predict.py --models-dir "$TMP_MODELS" --out-dir "$TMP_PRED" --window-days 365 --top 3

test -s "$TMP_PRED/predict_next_loto_ml_all.csv"
test -s "$TMP_PRED/predict_next_de_ml_all.csv"

printf '%s\n' "== Production model artifact compatibility =="
python - <<'PYMODEL'
import joblib
import pandas as pd
from ml_train import FEATURE_SCHEMA_VERSION
latest = str(pd.to_datetime(pd.read_csv("data/xsmb.csv", usecols=["date"])["date"]).max().date())
for path in ["models/ml_loto.joblib", "models/ml_de.joblib"]:
    obj = joblib.load(path)
    assert isinstance(obj, dict) and "model" in obj, path
    assert int(obj.get("feature_schema_version", 0)) == FEATURE_SCHEMA_VERSION, path
    assert str(obj.get("trained_through_date")) == latest, (path, obj.get("trained_through_date"), latest)
    print("OK", path, "trust=", obj.get("model_trust"))
for path in ["models/cau_keo_loto.joblib", "models/cau_keo_de.joblib"]:
    obj = joblib.load(path)
    assert isinstance(obj, dict) and "model" in obj, path
    print("OK", path)
PYMODEL

printf '%s\n' "== Static GitHub Pages builders =="
python src/build_docs_ml.py
python src/build_dashboard.py
python src/build_statistics_dashboard.py
python src/build_landing_page.py
python src/cleanup_artifacts.py --retention-days 45

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
  docs/live.html
  models/ml_loto.joblib
  models/ml_de.joblib
  docs/index.html
  docs/statistics.html
  docs/dashboard.html
  docs/model-quality.html
)
for path in "${required[@]}"; do
  test -s "$path" || { echo "Missing/empty output: $path" >&2; exit 3; }
done

echo "OK GitHub-only release check"
