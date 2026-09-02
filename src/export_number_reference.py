from __future__ import annotations

"""Export the canonical 00..99 ontology used by VLA."""

import argparse
import json
from pathlib import Path

import pandas as pd

from number_reference import (
    all_cap_loto_50,
    bo_seed_catalog,
    cap_loto_50_id,
    cap_loto_50_kind,
    classify_number,
    reference_catalog,
    unique_bo_catalog,
    validate_ontology,
)


def build_number_ontology() -> pd.DataFrame:
    validate_ontology()
    rows: list[dict[str, object]] = []
    for n in range(100):
        info = classify_number(n)
        rows.append(
            {
                "number": n,
                "number_str": info["number"],
                "head": info["head"],
                "tail": info["tail"],
                "reverse": info["reverse"],
                "bong_duong": info["bong_duong"],
                "bong_am": info["bong_am"],
                "cap_loto_50_id": info["cap_loto_50_id"],
                "cap_loto_50_kind": info["cap_loto_50_kind"],
                "cap_loto_50_partner": info["cap_loto_50_partner"],
                "bo_seed_label": info["bo_seed_label"],
                "bo_family_id": info["bo_family_id"],
                "bo_family_kind": info["bo_family_kind"],
                "bo_family_size": info["bo_family_size"],
                "bo_members": json.dumps(info["bo_members"], ensure_ascii=False),
                "digit_sum": info["digit_sum"],
                "sum_mod10": info["sum_mod10"],
                "is_kep_bang": info["is_kep_bang"],
                "is_kep_lech": info["is_kep_lech"],
                "is_kep_am": info["is_kep_am"],
                "is_sat_kep": info["is_sat_kep"],
                "is_sat_kep_vong": info["is_sat_kep_vong"],
            }
        )
    return pd.DataFrame(rows)


def build_seed_catalog() -> pd.DataFrame:
    rows = []
    for item in bo_seed_catalog():
        rows.append(
            {
                "seed_label": item["seed_label"],
                "canonical_family_id": item["canonical_family_id"],
                "family_kind": item["family_kind"],
                "family_size": item["family_size"],
                "members": json.dumps(item["members"], ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows)


def build_unique_family_catalog() -> pd.DataFrame:
    rows = []
    for item in unique_bo_catalog():
        rows.append(
            {
                "canonical_family_id": item["canonical_family_id"],
                "family_kind": item["family_kind"],
                "family_size": item["family_size"],
                "members": json.dumps(item["members"], ensure_ascii=False),
                "seed_labels": json.dumps(item["seed_labels"], ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows)


def build_cap_loto_50_catalog() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for pair in all_cap_loto_50():
        members = tuple(sorted(pair))
        pair_id = cap_loto_50_id(members[0])
        rows.append(
            {
                "pair_id": pair_id,
                "pair_kind": cap_loto_50_kind(members[0]),
                "a": members[0],
                "b": members[1],
                "members": json.dumps(members, ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows).sort_values("pair_id").reset_index(drop=True)


def export_reference(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    numbers = build_number_ontology()
    seeds = build_seed_catalog()
    unique = build_unique_family_catalog()
    pairs = build_cap_loto_50_catalog()

    if len(numbers) != 100 or numbers["number_str"].nunique() != 100:
        raise RuntimeError("number ontology must contain exactly 100 unique 00..99 rows")
    if len(seeds) != 100:
        raise RuntimeError("bộ seed catalog must contain exactly 100 labels")
    if len(unique) != 15:
        raise RuntimeError("canonical bộ catalog must contain exactly 15 unique families")
    if set(unique["family_size"].astype(int)) - {4, 8}:
        raise RuntimeError("canonical bộ family sizes must be 4 or 8")
    if int((unique["family_size"].astype(int) == 4).sum()) != 5:
        raise RuntimeError("expected exactly five 4-number canonical bộ families")
    if int((unique["family_size"].astype(int) == 8).sum()) != 10:
        raise RuntimeError("expected exactly ten 8-number canonical bộ families")
    if len(pairs) != 50 or pairs["pair_id"].nunique() != 50:
        raise RuntimeError("cặp loto catalog must contain exactly 50 unique pairs")
    if int((pairs["pair_kind"] == "kep_bong").sum()) != 5:
        raise RuntimeError("expected exactly five kép-bóng pairs")
    if int((pairs["pair_kind"] == "reverse").sum()) != 45:
        raise RuntimeError("expected exactly 45 reverse pairs")

    numbers.to_csv(out_dir / "number_ontology_00_99.csv", index=False)
    seeds.to_csv(out_dir / "bo_seed_catalog_00_99.csv", index=False)
    unique.to_csv(out_dir / "bo_unique_families.csv", index=False)
    pairs.to_csv(out_dir / "cap_loto_50.csv", index=False)

    manifest = reference_catalog()
    manifest.update(
        {
            "artifact_schema_version": 2,
            "number_rows": len(numbers),
            "seed_rows": len(seeds),
            "unique_family_rows": len(unique),
            "cap_loto_50_rows": len(pairs),
            "files": [
                "number_ontology_00_99.csv",
                "bo_seed_catalog_00_99.csv",
                "bo_unique_families.csv",
                "cap_loto_50.csv",
            ],
            "data_semantics": {
                "bo_seed_label": "historical 00..99 lookup label",
                "bo_family_id": "one of the 15 unique bóng-dương/lộn families",
                "cap_loto_50": "45 reverse pairs plus 5 kép-bóng pairs",
                "kep_bong": "00-55,11-66,22-77,33-88,44-99",
                "pair": "statistical pair artifacts must always carry pair_kind",
                "predictive_contract": (
                    "domain relations are candidate explanatory features; predictive "
                    "weight must be established by leakage-safe validation"
                ),
            },
        }
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Export canonical number-reference data.")
    ap.add_argument("--out-dir", default="data/reference")
    args = ap.parse_args()
    export_reference(Path(args.out_dir))
    print(f"[OK] canonical number ontology -> {args.out_dir}")


if __name__ == "__main__":
    main()
