#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${VN_LOTTERY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT/src}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

printf '%s\n' "== Canonical number ontology =="
python - <<'PYREF'
from number_reference import BONG, all_bo, bo, bong, dan_cham, dan_tong_mod10, reverse
for d in range(10):
    assert BONG[BONG[d]] == d
for n in range(100):
    s = f"{n:02d}"
    assert reverse(reverse(s)) == s
    assert bong(bong(s)) == s
    assert s in bo(s)
assert all(len(dan_cham(d)) == 19 for d in range(10))
assert all(len(dan_tong_mod10(d)) == 10 for d in range(10))
assert 1 < len(all_bo()) < 100
print("OK number ontology", len(all_bo()), "distinct bộ families")
PYREF

printf '%s\n' "== Legacy descriptive preservation =="
python src/descriptive_extensions.py --head-windows 30,90,365 --pair-top 300
python src/research_legacy_extensions.py
python src/legacy_advanced_diagnostics.py --max-lag 15 --coverage-windows 3,7,14,30
python src/conditional_nextday.py --top 20 --prior-strength 60

printf '%s\n' "== Cross-lag positional research family =="
python src/crosslag_positional_lab.py \
  --lag-pairs 1-1,1-2 \
  --operators concat,lon,bo,cham,tong \
  --warmup 180

printf '%s\n' "== Legacy path explainability preservation =="
python src/path_timeline_evidence.py --recent 20

printf '%s\n' "== Scientific falsification battery =="
python src/research_diagnostics.py --permutations 31 --max-lag 14 --seed 20260901

printf '%s\n' "== Data-snooping research firewall =="
python src/research_firewall.py \
  --mode both \
  --permutations 15 \
  --max-reality-days 500 \
  --seed 20260901

printf '%s\n' "== Standardized strategy lab =="
python src/strategy_lab.py --mode both --warmup 180

printf '%s\n' "== Research artifact integrity =="
python - <<'PYRESEARCH'
import json
from pathlib import Path
import pandas as pd

root = Path("data/research")
diag = json.loads((root / "scientific_diagnostics.json").read_text(encoding="utf-8"))
assert diag["draw_days"] >= 365
assert len(diag["primary_tests"]) == 5
for item in diag["primary_tests"]:
    q = item.get("q_value_fdr")
    if q is not None:
        assert 0.0 <= float(q) <= 1.0

firewall = json.loads((root / "research_firewall_report.json").read_text(encoding="utf-8"))
for mode in ("loto", "de"):
    item = firewall["modes"][mode]
    assert int(item["hypotheses"]) == 27 * 27 * 2
    p = float(item["reality_check"]["p_value"])
    assert 0.0 <= p <= 1.0
    table = pd.read_csv(root / f"research_firewall_{mode}.csv")
    assert len(table) == 27 * 27 * 2
    assert table["train_q_value_fdr"].between(0, 1).all()

    strategy = pd.read_csv(root / f"strategy_lab_{mode}.csv")
    assert len(strategy) == 20
    assert strategy["holdout_q_value_fdr"].dropna().between(0, 1).all()
    agreement = pd.read_csv(root / f"strategy_agreement_{mode}.csv")
    assert not agreement.empty
    diversity = pd.read_csv(root / f"strategy_diversity_{mode}.csv")
    assert len(diversity) == 20 * 19 // 2

for path in [
    "data/descriptive_ext/head_table_30d.csv",
    "data/descriptive_ext/gap_touch_loto.csv",
    "data/descriptive_ext/gap_digit_sum_de.csv",
    "data/descriptive_ext/number_recency_loto.csv",
    "data/descriptive_ext/number_recency_de.csv",
    "data/descriptive_ext/pair_recency_loto.csv",
]:
    p = Path(path)
    assert p.is_file() and p.stat().st_size > 0, path

ext = root / "legacy_extensions"
manifest = json.loads((ext / "manifest.json").read_text(encoding="utf-8"))
assert manifest["research_only"] is True
assert manifest["anchor_date"] == diag["end_date"]
assert int(manifest["rows"]["number_recency_loto.csv"]) == 100
assert int(manifest["rows"]["number_recency_de.csv"]) == 100
assert int(manifest["rows"]["de_weekday_profile.csv"]) == 700
assert int(manifest["rows"]["loto_transition_independence.csv"]) == 100
assert int(manifest["rows"]["loto_acf_bartlett.csv"]) >= 500
for name in (
    "number_recency_loto.csv",
    "number_recency_de.csv",
    "pair_recency_loto.csv",
    "de_weekday_profile.csv",
    "loto_transition_independence.csv",
    "loto_acf_bartlett.csv",
):
    table = pd.read_csv(ext / name)
    assert not table.empty, name
for name in ("loto_transition_independence.csv", "loto_acf_bartlett.csv"):
    table = pd.read_csv(ext / name)
    assert table["p_value"].between(0, 1).all(), name
    assert table["q_value_fdr"].between(0, 1).all(), name
for key in ("ks_full_special", "ljung_box_even_tail_count"):
    p = manifest[key].get("p_value")
    assert p is None or 0.0 <= float(p) <= 1.0, (key, p)

advanced = root / "legacy_advanced"
advanced_manifest = json.loads((advanced / "manifest.json").read_text(encoding="utf-8"))
assert advanced_manifest["research_only"] is True
assert advanced_manifest["anchor_date"] == diag["end_date"]
for key in ("aggregate_transition", "weekday_special_tail"):
    p = advanced_manifest[key].get("p_value")
    assert p is None or 0.0 <= float(p) <= 1.0, (key, p)
acf_full = pd.read_csv(advanced / "full_special_acf.csv")
assert len(acf_full) == 15
assert acf_full["p_value"].between(0, 1).all()
assert acf_full["q_value_fdr"].between(0, 1).all()
coverage = pd.read_csv(advanced / "rolling_coverage.csv")
assert coverage["window_days"].astype(int).tolist() == [3, 7, 14, 30]
assert coverage["observed_mean_distinct"].between(0, 100).all()

conditional_dir = Path("data/conditional")
conditional_manifest = json.loads((conditional_dir / "manifest.json").read_text(encoding="utf-8"))
assert conditional_manifest["schema_version"] == 2
assert conditional_manifest["research_only"] is True
assert conditional_manifest["anchor_date"] == diag["end_date"]
conditional = pd.read_csv(conditional_dir / "loto_nextday_given_special_long.csv")
assert not conditional.empty
assert conditional["p_raw"].between(0, 1).all()
assert conditional["p_eb"].between(0, 1).all()
assert conditional["baseline"].between(0, 1).all()
assert conditional["p_value"].between(0, 1).all()
assert conditional["q_value_fdr"].between(0, 1).all()

cross = root / "crosslag_positional"
cross_report = json.loads((cross / "report.json").read_text(encoding="utf-8"))
assert cross_report["research_only"] is True
assert cross_report["production_wired"] is False
assert cross_report["anchor_date"] == diag["end_date"]
assert int(cross_report["hypotheses"]) == 5832, cross_report["hypotheses"]
assert int(cross_report["holdout_days"]) > 0
cross_table = pd.read_csv(cross / "crosslag_rules.csv")
assert len(cross_table) == 5832
assert cross_table["train_q_value_fdr"].between(0, 1).all()
assert cross_table["train_bonferroni_p"].between(0, 1).all()
assert (~cross_table["production_eligible"].astype(bool)).all()
assert set(cross_table["operator"]) == {"concat", "lon", "bo", "cham", "tong"}

path_manifest = json.loads((root / "path_timelines" / "manifest.json").read_text(encoding="utf-8"))
assert path_manifest["research_only"] is True
for mode in ("loto", "de"):
    item = path_manifest["modes"][mode]
    assert item["status"] == "ok", (mode, item)
    assert int(item["rows"]) > 0, (mode, item)
    timeline = pd.read_csv(root / "path_timelines" / f"path_timeline_{mode}.csv")
    assert not timeline.empty
    assert timeline["timeline_trials"].gt(0).all()
    assert timeline["recent_hit_rate"].dropna().between(0, 1).all()
print("OK research artifacts")
PYRESEARCH

printf '%s\n' "== Static research page =="
python src/build_research_lab.py
python - <<'PYPAGE'
from pathlib import Path
page = Path("docs/research-lab.html")
assert page.is_file() and page.stat().st_size > 1000
text = page.read_text(encoding="utf-8")
assert "Scientific Research Lab" in text
assert "Research firewall" in text
for name in ("index.html", "landing.html", "landing_desktop.html"):
    path = Path("docs") / name
    if path.exists():
        assert path.read_text(encoding="utf-8").count('id="research-lab-link"') == 1, name
print("OK research page")
PYPAGE

echo "OK research-plane release check"
