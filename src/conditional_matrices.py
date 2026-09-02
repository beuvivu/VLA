from __future__ import annotations

"""Canonical calendar-safe next-day conditional matrices.

This module supersedes the row-adjacent conditional-table implementation that
historically lived inside ``statistical_matrices.py``. A "next day" transition
is counted only when source and target dates differ by exactly one calendar day.
Raw special-prize data and sparse loto data must describe the same date axis.
"""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from calendar_alignment import consecutive_next_pairs, normalize_dates
from lottery import Lottery, RepoPaths

NUMBER_COLS = list(range(100))


@dataclass(frozen=True)
class MatrixEvidence:
    """Full raw and normalized evidence for a 00..99 matrix."""

    counts: np.ndarray
    source_counts: np.ndarray
    target_counts: np.ndarray
    support: np.ndarray
    confidence: np.ndarray
    smoothed_probability: np.ndarray
    lift: np.ndarray
    eligible_observations: int
    alpha: float
    as_of_date: str
    relation: str


def _fmt2(n: int) -> str:
    return f"{int(n):02d}"


def _prepare_raw(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame(columns=["date", "special"])
    if "date" not in raw_df.columns or "special" not in raw_df.columns:
        raise ValueError("raw data must contain date and special columns")
    out = raw_df[["date", "special"]].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["special"] = pd.to_numeric(out["special"], errors="raise").astype(int)
    return out.sort_values("date").reset_index(drop=True)


def _prepare_sparse(sparse_df: pd.DataFrame) -> pd.DataFrame:
    if sparse_df.empty:
        return pd.DataFrame(columns=["date", *NUMBER_COLS])
    if "date" not in sparse_df.columns:
        raise ValueError("sparse data must contain date column")
    out = sparse_df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    rename: dict[object, int] = {}
    for col in out.columns:
        if col == "date":
            continue
        try:
            n = int(col)
        except (TypeError, ValueError):
            continue
        if 0 <= n <= 99:
            rename[col] = n
    out = out.rename(columns=rename)
    missing = [n for n in NUMBER_COLS if n not in out.columns]
    if missing:
        raise ValueError(f"sparse data missing number columns: {missing[:10]}")
    out = out[["date", *NUMBER_COLS]].copy()
    out[NUMBER_COLS] = out[NUMBER_COLS].apply(
        pd.to_numeric, errors="raise"
    ).astype(int)
    return out.sort_values("date").reset_index(drop=True)


def _matrix_evidence(
    source: np.ndarray,
    target: np.ndarray,
    *,
    alpha: float,
    as_of_date: pd.Timestamp,
    relation: str,
) -> MatrixEvidence:
    if alpha < 0.0 or not np.isfinite(alpha):
        raise ValueError("alpha must be finite and >= 0")
    eligible = len(source)
    counts = source.astype(np.int32).T @ target.astype(np.int32)
    source_counts = source.sum(axis=0, dtype=np.int32)
    target_counts = target.sum(axis=0, dtype=np.int32)
    support = counts / max(eligible, 1)
    confidence = np.divide(
        counts,
        source_counts[:, None],
        out=np.zeros((100, 100), dtype=float),
        where=source_counts[:, None] > 0,
    )
    # Each next-day number is a Bernoulli outcome in the multi-label Loto
    # state, so Beta smoothing uses two outcomes rather than forcing rows to
    # sum to one as an exclusive-state Markov chain would.
    smoothed = np.divide(
        counts + alpha,
        source_counts[:, None] + 2.0 * alpha,
        out=np.zeros((100, 100), dtype=float),
        where=(source_counts[:, None] + 2.0 * alpha) > 0,
    )
    marginal = target_counts / max(eligible, 1)
    lift = np.divide(
        confidence,
        marginal[None, :],
        out=np.zeros((100, 100), dtype=float),
        where=marginal[None, :] > 0,
    )
    return MatrixEvidence(
        counts=counts,
        source_counts=source_counts,
        target_counts=target_counts,
        support=support,
        confidence=confidence,
        smoothed_probability=smoothed,
        lift=lift,
        eligible_observations=eligible,
        alpha=float(alpha),
        as_of_date=as_of_date.date().isoformat(),
        relation=relation,
    )


def build_transition_matrix(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    alpha: float = 1.0,
) -> MatrixEvidence:
    """Build an exact-next-calendar-day multi-label Loto transition matrix.

    Only draws strictly before ``as_of_date`` are eligible.  Raw counts remain
    available alongside support, confidence, lift, and Beta-smoothed rates.
    """
    sparse = _prepare_sparse(history)
    cutoff = pd.Timestamp(as_of_date).normalize()
    sparse = sparse[sparse["date"] < cutoff].reset_index(drop=True)
    dates = normalize_dates(sparse["date"])
    source_index, target_index = consecutive_next_pairs(dates)
    presence = sparse[NUMBER_COLS].to_numpy(dtype=int, copy=False) > 0
    return _matrix_evidence(
        presence[source_index],
        presence[target_index],
        alpha=alpha,
        as_of_date=cutoff,
        relation="exact_next_calendar_day",
    )


def build_cooccurrence_matrix(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    alpha: float = 1.0,
) -> MatrixEvidence:
    """Build a same-draw co-occurrence matrix strictly before a cutoff."""
    sparse = _prepare_sparse(history)
    cutoff = pd.Timestamp(as_of_date).normalize()
    sparse = sparse[sparse["date"] < cutoff].reset_index(drop=True)
    normalize_dates(sparse["date"])
    presence = sparse[NUMBER_COLS].to_numpy(dtype=int, copy=False) > 0
    return _matrix_evidence(
        presence,
        presence,
        alpha=alpha,
        as_of_date=cutoff,
        relation="same_draw",
    )


def _top_matrix(
    mat_counts: np.ndarray,
    row_counts: np.ndarray,
    row_name: str,
    col_name: str,
    *,
    top: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for i in range(100):
        denom = int(row_counts[i])
        if denom <= 0:
            continue
        nz = np.flatnonzero(mat_counts[i] > 0)
        for j in nz:
            count = int(mat_counts[i, j])
            rows.append(
                {
                    row_name: _fmt2(i),
                    col_name: _fmt2(int(j)),
                    "count": count,
                    "base_count": denom,
                    "conditional_rate": count / denom,
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[row_name, col_name, "count", "base_count", "conditional_rate"]
        )
    return (
        pd.DataFrame(rows)
        .sort_values(
            ["conditional_rate", "count", row_name, col_name],
            ascending=[False, False, True, True],
        )
        .head(max(0, int(top)))
        .reset_index(drop=True)
    )


def build_conditional_tables(
    raw_df: pd.DataFrame,
    sparse_df: pd.DataFrame,
    *,
    top: int = 500,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Build ĐB→Loto, ĐB→ĐB and Loto→Loto using exact next-calendar-day pairs."""
    raw = _prepare_raw(raw_df)
    sparse = _prepare_sparse(sparse_df)
    if raw.empty or sparse.empty:
        empty = pd.DataFrame()
        return empty, empty.copy(), empty.copy(), {
            "calendar_rows": 0,
            "exact_next_day_pairs": 0,
            "skipped_nonconsecutive_boundaries": 0,
        }

    raw_dates = normalize_dates(raw["date"])
    sparse_dates = normalize_dates(sparse["date"])
    if not raw_dates.equals(sparse_dates):
        raise ValueError("raw and sparse histories must have the same ordered date axis")

    src_idx, dst_idx = consecutive_next_pairs(raw_dates)
    prev_de = (raw["special"].to_numpy(dtype=int) % 100).astype(int)
    loto = (sparse[NUMBER_COLS].to_numpy(dtype=int, copy=False) > 0)

    de_loto = np.zeros((100, 100), dtype=np.int32)
    de_de = np.zeros((100, 100), dtype=np.int32)
    loto_loto = np.zeros((100, 100), dtype=np.int32)
    prev_de_counts = np.zeros(100, dtype=np.int32)
    prev_loto_counts = np.zeros(100, dtype=np.int32)

    for src, dst in zip(src_idx, dst_idx, strict=True):
        d = int(prev_de[src])
        prev_de_counts[d] += 1
        next_hits = np.flatnonzero(loto[dst])
        if next_hits.size:
            de_loto[d, next_hits] += 1
        de_de[d, int(prev_de[dst])] += 1

        prev_hits = np.flatnonzero(loto[src])
        if prev_hits.size:
            prev_loto_counts[prev_hits] += 1
        if prev_hits.size and next_hits.size:
            loto_loto[np.ix_(prev_hits, next_hits)] += 1

    diagnostics = {
        "schema_version": 1,
        "calendar_rows": int(len(raw_dates)),
        "calendar_start": raw_dates[0].date().isoformat(),
        "calendar_end": raw_dates[-1].date().isoformat(),
        "exact_next_day_pairs": int(len(src_idx)),
        "skipped_nonconsecutive_boundaries": int(
            max(0, len(raw_dates) - 1 - len(src_idx))
        ),
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "contract": "only exact +1 calendar-day transitions are counted",
    }

    return (
        _top_matrix(
            de_loto,
            prev_de_counts,
            "prev_special_2d",
            "next_loto",
            top=top,
        ),
        _top_matrix(
            de_de,
            prev_de_counts,
            "prev_special_2d",
            "next_special_2d",
            top=top,
        ),
        _top_matrix(
            loto_loto,
            prev_loto_counts,
            "prev_loto",
            "next_loto",
            top=top,
        ),
        diagnostics,
    )


def write_canonical_tables(*, top: int = 500) -> list[Path]:
    paths = RepoPaths.from_module()
    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data()
    sparse = lot.get_sparse_data()
    de_loto, de_de, loto_loto, diagnostics = build_conditional_tables(
        raw, sparse, top=top
    )

    out = paths.data_dir / "advanced"
    out.mkdir(parents=True, exist_ok=True)
    tables = {
        "conditional_loto_after_special_top500": de_loto,
        "conditional_special_after_special_top500": de_de,
        "conditional_loto_after_loto_top500": loto_loto,
    }
    created: list[Path] = []
    for name, table in tables.items():
        csv_path = out / f"{name}.csv"
        json_path = out / f"{name}.json"
        table.to_csv(csv_path, index=False)
        table.to_json(json_path, orient="records", indent=2, force_ascii=False)
        created.extend([csv_path, json_path])

    diag_path = out / "conditional_matrices_diagnostics.json"
    diag_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    created.append(diag_path)
    return created


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Write canonical exact-calendar next-day conditional matrices."
    )
    ap.add_argument("--top", type=int, default=500)
    args = ap.parse_args()
    created = write_canonical_tables(top=args.top)
    print(f"[OK] calendar-safe conditional matrices: {len(created)} artifact(s)")


if __name__ == "__main__":
    main()
