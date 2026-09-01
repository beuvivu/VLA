from __future__ import annotations

"""Date-safe AI/statistics overlay for the legacy 00..99 statistics dashboard.

The historical ``statistical_matrices`` builder accepted any probability file
that happened to exist. A structurally valid file from yesterday could therefore
be displayed as today's ML signal. This canonical post-processor accepts only an
artifact whose prediction target is exactly ``latest canonical date + 1 day``.
If no current ML artifact exists, it keeps the descriptive statistical overlay
but renormalizes the score over the non-ML factors and explicitly marks ML as
unavailable instead of reusing stale probabilities.
"""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from lottery import Lottery, RepoPaths
from statistical_matrices import (
    NUMBER_COLS,
    _de_sparse_from_raw,
    _minmax,
    _period_frequency_from_sparse,
    _prepare_sparse,
    _rhythm_from_sparse,
    _window_freq,
)

Mode = Literal["loto", "de"]


def _fmt2(n: int) -> str:
    return f"{int(n):02d}"


def _extract_single_date(df: pd.DataFrame, column: str) -> str | None:
    if column not in df.columns or df.empty:
        return None
    parsed = pd.to_datetime(df[column], errors="coerce")
    if parsed.isna().any():
        return None
    values = sorted(parsed.dt.date.astype(str).unique())
    return values[0] if len(values) == 1 else None


def _validated_probability_frame(
    path: Path,
    *,
    expected_target: str,
    target_from_filename: str | None = None,
) -> tuple[pd.DataFrame | None, str]:
    if not path.exists() or path.stat().st_size <= 0:
        return None, "missing"
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return None, f"read_error:{type(exc).__name__}"

    if len(df) != 100 or "number" not in df.columns or "prob" not in df.columns:
        return None, "invalid_shape_or_columns"

    numbers = pd.to_numeric(df["number"], errors="coerce")
    probs = pd.to_numeric(df["prob"], errors="coerce")
    if numbers.isna().any() or probs.isna().any():
        return None, "non_numeric_number_or_prob"
    n = numbers.to_numpy(dtype=float)
    p = probs.to_numpy(dtype=float)
    if not np.isfinite(n).all() or not np.isfinite(p).all():
        return None, "non_finite"
    if not np.all(n == np.floor(n)):
        return None, "non_integer_number"
    ints = n.astype(int)
    if set(ints.tolist()) != set(range(100)) or len(np.unique(ints)) != 100:
        return None, "number_universe_not_00_99"
    if np.any((p < 0.0) | (p > 1.0)) or float(p.sum()) <= 0.0:
        return None, "invalid_probability_vector"

    declared: str | None = None
    for col in ("predict_for_date", "target_date"):
        declared = _extract_single_date(df, col)
        if col in df.columns and declared is None:
            return None, f"invalid_{col}"
        if declared is not None:
            break
    if declared is None:
        declared = target_from_filename
    if declared is None:
        return None, "target_date_unverifiable"
    if declared != expected_target:
        return None, f"stale_target:{declared}"

    order = np.argsort(ints)
    out = pd.DataFrame(
        {
            "number": ints[order],
            "number_str": [_fmt2(int(x)) for x in ints[order]],
            "ml_prob": p[order],
        }
    )
    return out, "ok"


def _load_current_ml(
    data_dir: Path,
    *,
    mode: Mode,
    expected_target: str,
) -> tuple[pd.DataFrame, dict]:
    candidates: list[tuple[str, Path, str | None]] = [
        (
            "cau_keo",
            data_dir / "ai_ml" / f"cau_keo_{mode}_all.csv",
            None,
        ),
        (
            "base_ml",
            data_dir / "ml" / f"predict_next_{mode}_ml_all.csv",
            None,
        ),
    ]
    exact_ensemble = (
        data_dir / "predict" / f"predict_next_{mode}_all_{expected_target}.csv"
    )
    candidates.append(("ensemble_exact", exact_ensemble, expected_target))

    attempts: list[dict[str, str]] = []
    for source, path, filename_target in candidates:
        frame, reason = _validated_probability_frame(
            path,
            expected_target=expected_target,
            target_from_filename=filename_target,
        )
        attempts.append(
            {
                "source": source,
                "path": str(path),
                "status": reason,
            }
        )
        if frame is not None:
            return frame, {
                "available": True,
                "source": source,
                "path": str(path),
                "attempts": attempts,
            }

    empty = pd.DataFrame(
        {
            "number": NUMBER_COLS,
            "number_str": [_fmt2(i) for i in NUMBER_COLS],
            "ml_prob": np.zeros(100, dtype=float),
        }
    )
    return empty, {
        "available": False,
        "source": None,
        "path": None,
        "attempts": attempts,
    }


def _current_year_frequency(
    sparse_df: pd.DataFrame, *, mode: str
) -> pd.DataFrame:
    table = _period_frequency_from_sparse(sparse_df, period="year", mode=mode)
    if table.empty:
        return pd.DataFrame(
            {
                "number": NUMBER_COLS,
                "freq_current_year": np.zeros(100, dtype=float),
                "z_score_current_year": np.zeros(100, dtype=float),
            }
        )
    latest_year = sorted(table["period_key"].astype(str).unique())[-1]
    out = table[table["period_key"].astype(str) == latest_year][
        ["number", "freq", "z_score"]
    ].copy()
    return out.rename(
        columns={
            "freq": "freq_current_year",
            "z_score": "z_score_current_year",
        }
    )


def _weighted_score(
    factors: dict[str, np.ndarray],
    weights: dict[str, float],
    *,
    available: dict[str, bool],
) -> np.ndarray:
    active = {
        key: float(weight)
        for key, weight in weights.items()
        if bool(available.get(key, True)) and float(weight) > 0.0
    }
    total = float(sum(active.values()))
    if total <= 0.0:
        return np.zeros(100, dtype=float)
    score = np.zeros(100, dtype=float)
    for key, weight in active.items():
        score += (weight / total) * np.asarray(factors[key], dtype=float)
    return 100.0 * score


def build_overlay(
    *,
    mode: Mode,
    sparse_df: pd.DataFrame,
    data_dir: Path,
    expected_target: str,
) -> tuple[pd.DataFrame, dict]:
    sparse = _prepare_sparse(sparse_df)
    if sparse.empty:
        raise ValueError("statistics AI overlay requires non-empty sparse history")

    rhythm = _rhythm_from_sparse(sparse, mode=mode)
    f7 = _window_freq(sparse, 7, mode=mode)
    f30 = _window_freq(sparse, 30, mode=mode)
    f365 = _window_freq(sparse, 365, mode=mode)
    year = _current_year_frequency(sparse, mode=mode)
    ml, ml_diag = _load_current_ml(
        data_dir, mode=mode, expected_target=expected_target
    )

    out = pd.DataFrame(
        {
            "number": NUMBER_COLS,
            "number_str": [_fmt2(i) for i in NUMBER_COLS],
        }
    )
    for part in (f7, f30, f365):
        cols = [c for c in part.columns if c.startswith("freq_") or c.startswith("days_hit_")]
        out = out.merge(part[["number", *cols]], on="number", how="left")
    out = out.merge(
        rhythm[["number", "current_gap", "mean_gap", "rhythm_pressure"]],
        on="number",
        how="left",
    )
    out = out.merge(year, on="number", how="left")
    out = out.merge(ml[["number", "ml_prob"]], on="number", how="left")

    numeric = [
        "freq_7d",
        "freq_30d",
        "freq_365d",
        "current_gap",
        "mean_gap",
        "rhythm_pressure",
        "freq_current_year",
        "z_score_current_year",
        "ml_prob",
    ]
    for col in numeric:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    factors = {
        "ml": _minmax(out["ml_prob"]).to_numpy(dtype=float),
        "freq30": _minmax(out["freq_30d"]).to_numpy(dtype=float),
        "freq7": _minmax(out["freq_7d"]).to_numpy(dtype=float),
        "year": _minmax(out["freq_current_year"]).to_numpy(dtype=float),
        "pressure": _minmax(
            out["rhythm_pressure"].clip(lower=0, upper=5)
        ).to_numpy(dtype=float),
        "gap": _minmax(out["current_gap"]).to_numpy(dtype=float),
    }
    if mode == "loto":
        weights = {"ml": 0.40, "freq30": 0.25, "pressure": 0.20, "freq7": 0.15}
    else:
        weights = {"ml": 0.45, "year": 0.20, "gap": 0.25, "freq30": 0.10}
    availability = {key: True for key in weights}
    availability["ml"] = bool(ml_diag["available"])
    score = _weighted_score(
        factors,
        weights,
        available=availability,
    )

    out["ai_ml_signal_score"] = np.round(score, 4)
    out["ml_prob"] = out["ml_prob"].round(8)
    out["ml_available"] = bool(ml_diag["available"])
    out["ml_source"] = ml_diag.get("source") or "unavailable"
    out["target_date"] = expected_target
    out["score_band"] = pd.cut(
        out["ai_ml_signal_score"],
        bins=[-0.01, 25, 50, 75, 100.01],
        labels=["low", "medium", "high", "very_high"],
    ).astype(str)
    out["note"] = np.where(
        out["ml_available"],
        "date-verified ML + current descriptive statistics; ranking signal only",
        "ML unavailable/stale: score renormalized over current descriptive statistics only",
    )
    out = out.sort_values(
        ["ai_ml_signal_score", "number"], ascending=[False, True]
    ).reset_index(drop=True)

    diagnostics = {
        "schema_version": 1,
        "mode": mode,
        "target_date": expected_target,
        "ml": ml_diag,
        "weights_configured": weights,
        "weights_effective": {
            key: (
                value
                / sum(
                    w
                    for k, w in weights.items()
                    if availability.get(k, True)
                )
                if availability.get(key, True)
                else 0.0
            )
            for key, value in weights.items()
        },
    }
    return out, diagnostics


def write_overlays() -> list[Path]:
    paths = RepoPaths.from_module()
    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data().copy()
    sparse_loto = lot.get_sparse_data().copy()
    if raw.empty or sparse_loto.empty:
        raise RuntimeError("No canonical lottery data loaded")

    latest = pd.to_datetime(raw["date"]).max().date()
    expected_target = (latest + timedelta(days=1)).isoformat()
    sparse_de = _de_sparse_from_raw(raw)
    out_dir = paths.data_dir / "advanced"
    out_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    diagnostics: dict[str, object] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "anchor_date": latest.isoformat(),
        "target_date": expected_target,
        "modes": {},
    }
    for mode, sparse in (("loto", sparse_loto), ("de", sparse_de)):
        table, diag = build_overlay(
            mode=mode,  # type: ignore[arg-type]
            sparse_df=sparse,
            data_dir=paths.data_dir,
            expected_target=expected_target,
        )
        csv_path = out_dir / f"ai_ml_signal_{mode}.csv"
        json_path = out_dir / f"ai_ml_signal_{mode}.json"
        table.to_csv(csv_path, index=False)
        table.to_json(
            json_path,
            orient="records",
            indent=2,
            force_ascii=False,
        )
        created.extend([csv_path, json_path])
        diagnostics["modes"][mode] = diag  # type: ignore[index]

    diag_path = out_dir / "ai_ml_signal_diagnostics.json"
    diag_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    created.append(diag_path)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write date-safe legacy statistics AI overlays."
    )
    parser.parse_args()
    created = write_overlays()
    print(f"[OK] date-safe statistics AI overlay: {len(created)} artifact(s)")


if __name__ == "__main__":
    main()
