from __future__ import annotations

"""Historical statistics for the common 50-cặp-loto partition.

The partition contains 45 reverse pairs and five kép-bóng pairs.  This module
measures whether members actually behave similarly in historical data.  It does
not assume that a domain relation is predictive; it emits evidence that can be
used later by leakage-safe feature engineering or score regularization.
"""

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from lottery import Lottery
from number_reference import all_cap_loto_50, cap_loto_50_id, cap_loto_50_kind


def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out.sort_values("date").reset_index(drop=True)


def _hit_matrices(two_digit_df: pd.DataFrame) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    two = _ensure_datetime(two_digit_df)
    if two.empty:
        raise RuntimeError("No two-digit history loaded")
    value_cols = [c for c in two.columns if c != "date"]
    vals = (
        two[value_cols]
        .apply(pd.to_numeric, errors="raise")
        .astype(int)
        .to_numpy()
        % 100
    )
    loto = np.zeros((len(two), 100), dtype=bool)
    for i in range(len(two)):
        loto[i, np.unique(vals[i])] = True

    de = np.zeros((len(two), 100), dtype=bool)
    special = (two["special"].astype(int).to_numpy() % 100).astype(int)
    de[np.arange(len(two)), special] = True
    return pd.DatetimeIndex(two["date"]), loto, de


def _phi(x: np.ndarray, y: np.ndarray) -> float:
    x = x.astype(bool)
    y = y.astype(bool)
    n11 = float(np.sum(x & y))
    n10 = float(np.sum(x & ~y))
    n01 = float(np.sum(~x & y))
    n00 = float(np.sum(~x & ~y))
    denom = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    return (n11 * n00 - n10 * n01) / denom if denom > 0 else 0.0


def _current_gap(hit: np.ndarray) -> int:
    idx = np.where(hit)[0]
    if idx.size == 0:
        return int(len(hit))
    return int(len(hit) - 1 - idx[-1])


def _window_metrics(x: np.ndarray, y: np.ndarray, window: int) -> dict[str, float]:
    n = min(window, len(x))
    if n <= 0:
        return {
            f"a_rate_{window}d": 0.0,
            f"b_rate_{window}d": 0.0,
            f"pair_any_rate_{window}d": 0.0,
            f"pair_both_rate_{window}d": 0.0,
            f"member_rate_gap_{window}d": 0.0,
            f"member_balance_{window}d": 1.0,
        }
    xa = x[-n:].astype(bool)
    yb = y[-n:].astype(bool)
    ra = float(xa.mean())
    rb = float(yb.mean())
    denom = max(ra, rb, 1.0 / n)
    balance = float(np.clip(1.0 - abs(ra - rb) / denom, 0.0, 1.0))
    return {
        f"a_rate_{window}d": ra,
        f"b_rate_{window}d": rb,
        f"pair_any_rate_{window}d": float((xa | yb).mean()),
        f"pair_both_rate_{window}d": float((xa & yb).mean()),
        f"member_rate_gap_{window}d": abs(ra - rb),
        f"member_balance_{window}d": balance,
    }


def _current_cau_scores(mode: str, data_dir: Path) -> dict[str, float]:
    path = data_dir / "ai_ml" / f"cau_keo_{mode}_all.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path, dtype={"number_str": str})
    except Exception:
        return {}
    if "number_str" not in df.columns or "cau_score" not in df.columns:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        raw = str(row["number_str"]).strip()
        if raw.isdigit():
            number = f"{int(raw):02d}"
            score = pd.to_numeric(pd.Series([row["cau_score"]]), errors="coerce").iloc[0]
            if pd.notna(score):
                out[number] = float(score)
    return out


def build_stats(mode: str, *, data_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    if mode not in {"loto", "de"}:
        raise ValueError("mode must be loto or de")

    lot = Lottery()
    lot.load()
    dates, loto_hit, de_hit = _hit_matrices(lot.get_2_digits_data())
    hit = loto_hit if mode == "loto" else de_hit
    cau = _current_cau_scores(mode, data_dir)

    rows: list[dict[str, object]] = []
    for pair in all_cap_loto_50():
        a, b = sorted(pair)
        ai, bi = int(a), int(b)
        x, y = hit[:, ai], hit[:, bi]
        any_hit = x | y
        both_hit = x & y
        union = int(any_hit.sum())
        intersection = int(both_hit.sum())
        row: dict[str, object] = {
            "mode": mode,
            "pair_id": cap_loto_50_id(a),
            "pair_kind": cap_loto_50_kind(a),
            "a": a,
            "b": b,
            "history_start": dates[0].date().isoformat(),
            "history_end": dates[-1].date().isoformat(),
            "history_days": len(dates),
            "a_hit_days": int(x.sum()),
            "b_hit_days": int(y.sum()),
            "pair_any_hit_days": union,
            "pair_both_hit_days": intersection,
            "pair_xor_hit_days": int((x ^ y).sum()),
            "a_rate_all": float(x.mean()),
            "b_rate_all": float(y.mean()),
            "member_rate_gap_all": abs(float(x.mean()) - float(y.mean())),
            "pair_any_rate_all": float(any_hit.mean()),
            "pair_both_rate_all": float(both_hit.mean()),
            "jaccard": float(intersection / union) if union else 0.0,
            "phi": float(_phi(x, y)),
            "gap_a": _current_gap(x),
            "gap_b": _current_gap(y),
            "gap_pair": _current_gap(any_hit),
        }
        for window in (30, 90, 365):
            row.update(_window_metrics(x, y, window))

        if a in cau and b in cau:
            sa, sb = cau[a], cau[b]
            row["cau_score_a"] = sa
            row["cau_score_b"] = sb
            row["cau_score_pair_mean"] = (sa + sb) / 2.0
            row["cau_score_gap"] = abs(sa - sb)
            row["cau_score_balance"] = float(
                np.clip(1.0 - abs(sa - sb) / max(sa, sb, 1.0), 0.0, 1.0)
            )
        rows.append(row)

    df = pd.DataFrame(rows).sort_values(["pair_kind", "pair_id"]).reset_index(drop=True)
    kep = df[df["pair_kind"] == "kep_bong"].copy()
    reverse = df[df["pair_kind"] == "reverse"].copy()

    summary: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "mode": mode,
        "history_start": dates[0].date().isoformat(),
        "history_end": dates[-1].date().isoformat(),
        "history_days": len(dates),
        "pair_count": len(df),
        "reverse_pair_count": len(reverse),
        "kep_bong_pair_count": len(kep),
        "kep_bong_pairs": kep["pair_id"].tolist(),
        "kep_bong_mean_member_rate_gap_365d": float(kep["member_rate_gap_365d"].mean()),
        "kep_bong_mean_member_balance_365d": float(kep["member_balance_365d"].mean()),
        "kep_bong_mean_phi": float(kep["phi"].mean()),
        "reverse_mean_member_rate_gap_365d": float(reverse["member_rate_gap_365d"].mean()),
        "reverse_mean_member_balance_365d": float(reverse["member_balance_365d"].mean()),
        "predictive_policy": (
            "pair relations provide shared evidence/candidate features; production predictive "
            "weight requires leakage-safe validation and must not force equal probabilities"
        ),
    }
    if "cau_score_gap" in kep.columns and kep["cau_score_gap"].notna().any():
        summary["kep_bong_mean_current_cau_score_gap"] = float(kep["cau_score_gap"].dropna().mean())
        summary["kep_bong_mean_current_cau_score_balance"] = float(
            kep["cau_score_balance"].dropna().mean()
        )
    return df, summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Build statistics for the 50 cặp-loto partition")
    ap.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="data/pairs")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    modes = ["loto", "de"] if args.mode == "both" else [args.mode]
    for mode in modes:
        df, summary = build_stats(mode, data_dir=data_dir)
        df.to_csv(out_dir / f"cap_loto_50_stats_{mode}.csv", index=False)
        (out_dir / f"cap_loto_50_summary_{mode}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"[OK] {mode}: 50 pairs; kép-bóng balance365="
            f"{summary['kep_bong_mean_member_balance_365d']:.4f}"
        )


if __name__ == "__main__":
    main()
