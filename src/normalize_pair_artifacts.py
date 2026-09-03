from __future__ import annotations

"""Normalize pair artifacts to the canonical VLA number ontology.

Historically, the word ``pair`` was used for several different concepts:
- an unordered pair of two loto numbers co-occurring in the same draw;
- a deterministic reverse/lộn pair AB↔BA;
- the common 50-cặp-loto partition (45 reverse + 5 kép-bóng);
- two numbers related through bóng/bộ.

This post-processor preserves old filenames for compatibility while adding
explicit semantics and deterministic relation metadata.
"""

import argparse
from pathlib import Path

import pandas as pd

from number_reference import (
    bo_family_id,
    bong_am,
    bong_duong,
    cap_loto_50_id,
    cap_loto_50_kind,
    cap_loto_50_partner,
    normalize_two_digit,
    pair_key,
    pair_relation_tags,
    reverse,
)


def _as_number_text(value: object) -> str:
    if pd.isna(value):
        raise ValueError("pair member cannot be null")
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith(".0") and raw[:-2].isdigit():
            raw = raw[:-2]
        return normalize_two_digit(raw)
    return normalize_two_digit(int(value))


def annotate_pair_frame(
    frame: pd.DataFrame,
    *,
    a_col: str,
    b_col: str,
    pair_kind: str,
) -> pd.DataFrame:
    if frame.empty:
        out = frame.copy()
        out.insert(0, "pair_kind", pair_kind)
        return out
    missing = [c for c in (a_col, b_col) if c not in frame.columns]
    if missing:
        raise ValueError(f"missing pair columns: {missing}")

    out = frame.copy()
    a_text = out[a_col].map(_as_number_text)
    b_text = out[b_col].map(_as_number_text)

    out["pair_kind"] = pair_kind
    out["canonical_pair_key"] = [
        pair_key(a, b, allow_equal=True) for a, b in zip(a_text, b_text, strict=True)
    ]
    out["a_str"] = a_text
    out["b_str"] = b_text
    out["reverse_related"] = [
        reverse(a) == b and a != b for a, b in zip(a_text, b_text, strict=True)
    ]
    out["bong_duong_related"] = [
        bong_duong(a) == b for a, b in zip(a_text, b_text, strict=True)
    ]
    out["bong_am_related"] = [
        bong_am(a) == b for a, b in zip(a_text, b_text, strict=True)
    ]

    cap50_related = [
        cap_loto_50_partner(a) == b
        for a, b in zip(a_text, b_text, strict=True)
    ]
    out["cap_loto_50_related"] = cap50_related
    out["cap_loto_50_id"] = [
        cap_loto_50_id(a) if related else ""
        for a, related in zip(a_text, cap50_related, strict=True)
    ]
    out["cap_loto_50_kind"] = [
        cap_loto_50_kind(a) if related else ""
        for a, related in zip(a_text, cap50_related, strict=True)
    ]

    out["bo_family_id_a"] = a_text.map(bo_family_id)
    out["bo_family_id_b"] = b_text.map(bo_family_id)
    out["same_bo_family"] = out["bo_family_id_a"] == out["bo_family_id_b"]
    out["relation_tags"] = [
        "|".join(pair_relation_tags(a, b))
        for a, b in zip(a_text, b_text, strict=True)
    ]

    if "pair" in out.columns:
        out["pair"] = out["canonical_pair_key"]
    return out


def normalize_artifacts(
    *,
    descriptive_dir: Path,
    pairs_dir: Path,
) -> dict[str, int]:
    counts: dict[str, int] = {}

    recency = descriptive_dir / "pair_recency_loto.csv"
    if recency.exists():
        df = pd.read_csv(recency, dtype={"a_str": str, "b_str": str})
        normalized = annotate_pair_frame(
            df,
            a_col="a",
            b_col="b",
            pair_kind="same_draw_cooccurrence",
        )
        normalized.to_csv(recency, index=False)
        normalized.to_csv(
            descriptive_dir / "cooccurrence_pair_recency_loto.csv", index=False
        )
        counts["descriptive_pair_rows"] = len(normalized)

    reversal = pairs_dir / "reversal_pair_cooccurrence.csv"
    if reversal.exists():
        df = pd.read_csv(reversal)
        normalized = annotate_pair_frame(
            df,
            a_col="a",
            b_col="b",
            pair_kind="reverse_pair_same_draw",
        )
        if not normalized.empty and not bool(normalized["reverse_related"].all()):
            raise RuntimeError("reversal pair artifact contains a non-reverse pair")
        if not normalized.empty and not bool(
            normalized["cap_loto_50_related"].all()
        ):
            raise RuntimeError("reverse artifact contains a pair outside cap_loto_50")
        normalized.to_csv(reversal, index=False)
        counts["reversal_pair_rows"] = len(normalized)

    for path in sorted(pairs_dir.glob("top_unordered_pairs_top*.csv")):
        df = pd.read_csv(path)
        normalized = annotate_pair_frame(
            df,
            a_col="x",
            b_col="y",
            pair_kind="same_draw_cooccurrence",
        )
        normalized.to_csv(path, index=False)
        counts[path.name] = len(normalized)

    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Normalize pair artifacts and semantics.")
    ap.add_argument("--descriptive-dir", default="data/descriptive_ext")
    ap.add_argument("--pairs-dir", default="data/pairs")
    args = ap.parse_args()
    counts = normalize_artifacts(
        descriptive_dir=Path(args.descriptive_dir),
        pairs_dir=Path(args.pairs_dir),
    )
    print("[OK] pair artifact normalization:", counts)


if __name__ == "__main__":
    main()
