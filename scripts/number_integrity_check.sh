#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${VN_LOTTERY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT/src}"

printf '%s\n' "== Canonical number ontology =="
python src/export_number_reference.py --out-dir data/reference

printf '%s\n' "== Pair artifacts + semantics =="
python src/pair_stats.py --out-dir data/pairs --data-dir data --top 300
python src/descriptive_extensions.py --out-dir data/descriptive_ext --pair-top 300
python src/normalize_pair_artifacts.py \
  --descriptive-dir data/descriptive_ext \
  --pairs-dir data/pairs

printf '%s\n' "== Rebuild exact-width Excel outputs from canonical history =="
python - <<'PY'
from lottery import Lottery

lot = Lottery()
lot.load()
lot.generate_dataframes()
lot.dump()
print("OK rebuilt canonical Excel workbooks")
PY

printf '%s\n' "== Excel canonical roundtrip =="
python src/validate_excel_integrity.py \
  --data-dir data \
  --json-out data/excel/integrity.json

python - <<'PY'
import json
from pathlib import Path

import pandas as pd

ref = json.loads(Path("data/reference/manifest.json").read_text(encoding="utf-8"))
assert ref["bo_seed_label_count"] == 100, ref
assert ref["bo_unique_family_count"] == 15, ref
assert ref["bo_family_size_distribution"] == {"4": 5, "8": 10}, ref
assert ref["bo_family_kind_distribution"] == {"bo_kep": 5, "bo_thuong": 10}, ref
assert ref["cap_loto_50_count"] == 50, ref
assert ref["cap_loto_50_kind_distribution"] == {"reverse": 45, "kep_bong": 5}, ref
assert ref["kep_bong_pairs"] == ["00-55", "11-66", "22-77", "33-88", "44-99"], ref
assert ref["bong_am"]["status"] == "documented_domain_convention", ref
assert ref["bong_am"]["predictive_status"] == "must_be_empirically_validated", ref

numbers = pd.read_csv(
    "data/reference/number_ontology_00_99.csv",
    dtype={
        "number_str": str,
        "reverse": str,
        "bong_duong": str,
        "bong_am": str,
        "bo_family_id": str,
        "cap_loto_50_id": str,
        "cap_loto_50_partner": str,
    },
)
assert len(numbers) == 100
assert set(numbers["number_str"]) == {f"{n:02d}" for n in range(100)}
assert numbers["bo_family_id"].nunique() == 15
assert numbers["cap_loto_50_id"].nunique() == 50
assert set(numbers.loc[numbers["cap_loto_50_kind"] == "kep_bong", "cap_loto_50_id"]) == {
    "00-55", "11-66", "22-77", "33-88", "44-99"
}

unique = pd.read_csv(
    "data/reference/bo_unique_families.csv",
    dtype={"canonical_family_id": str},
)
assert len(unique) == 15
assert (unique["family_size"] == 4).sum() == 5
assert (unique["family_size"] == 8).sum() == 10
assert (unique["family_kind"] == "bo_kep").sum() == 5
assert (unique["family_kind"] == "bo_thuong").sum() == 10

cap50 = pd.read_csv(
    "data/reference/cap_loto_50.csv",
    dtype={"pair_id": str, "a": str, "b": str},
)
assert len(cap50) == 50
assert cap50["pair_id"].nunique() == 50
assert (cap50["pair_kind"] == "reverse").sum() == 45
assert (cap50["pair_kind"] == "kep_bong").sum() == 5
assert set(cap50.loc[cap50["pair_kind"] == "kep_bong", "pair_id"]) == {
    "00-55", "11-66", "22-77", "33-88", "44-99"
}

pair = pd.read_csv(
    "data/descriptive_ext/pair_recency_loto.csv",
    dtype={"a_str": str, "b_str": str, "bo_family_id_a": str, "bo_family_id_b": str},
)
assert not pair.empty
assert set(pair["pair_kind"]) == {"same_draw_cooccurrence"}
assert pair["canonical_pair_key"].astype(str).str.match(r"^\d{2}-\d{2}$").all()
assert pair["a_str"].astype(str).str.match(r"^\d{2}$").all()
assert pair["b_str"].astype(str).str.match(r"^\d{2}$").all()

rev = pd.read_csv(
    "data/pairs/reversal_pair_cooccurrence.csv",
    dtype={"a_str": str, "b_str": str},
)
assert not rev.empty
assert set(rev["pair_kind"]) == {"reverse_pair_same_draw"}
assert rev["reverse_related"].astype(str).str.lower().eq("true").all()
assert rev["cap_loto_50_related"].astype(str).str.lower().eq("true").all()
assert set(rev["cap_loto_50_kind"]) == {"reverse"}

for mode in ("loto", "de"):
    stats = pd.read_csv(
        f"data/pairs/cap_loto_50_stats_{mode}.csv",
        dtype={"pair_id": str, "a": str, "b": str},
    )
    assert len(stats) == 50
    assert stats["pair_id"].nunique() == 50
    assert (stats["pair_kind"] == "reverse").sum() == 45
    assert (stats["pair_kind"] == "kep_bong").sum() == 5
    assert stats["member_balance_365d"].between(0.0, 1.0).all()
    summary = json.loads(
        Path(f"data/pairs/cap_loto_50_summary_{mode}.json").read_text(encoding="utf-8")
    )
    assert summary["pair_count"] == 50
    assert summary["reverse_pair_count"] == 45
    assert summary["kep_bong_pair_count"] == 5
    assert summary["kep_bong_pairs"] == ["00-55", "11-66", "22-77", "33-88", "44-99"]

excel = json.loads(Path("data/excel/integrity.json").read_text(encoding="utf-8"))
assert excel["ok"] is True, excel
assert excel["prize_values_per_draw"] == 27, excel
assert excel["latest_daily_prize_values_checked"] == 27, excel
print("OK number/pair/Excel integrity", excel["latest_date"])
PY
