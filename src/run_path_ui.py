from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from calendar_alignment import require_daily_contiguous
from lottery import Lottery
from path_models import PathParams, build_daily_targets, index_to_label
from path_prob import (
    fit_paths,
    paths_to_dataframe,
    predict_from_fitted_paths,
    predict_from_fitted_paths_full,
)


def _to_date(x):
    """Coerce common date-like objects to datetime.date."""
    import datetime as _dt

    if hasattr(x, "to_pydatetime"):
        x = x.to_pydatetime()
    if isinstance(x, _dt.datetime):
        return x.date()
    if isinstance(x, _dt.date):
        return x
    return _dt.date.fromisoformat(str(x))


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _resolve_anchor_date(dates: list[date], anchor: Optional[date]) -> date:
    if anchor is None:
        return dates[-1]
    if anchor not in dates:
        raise ValueError(f"anchor date {anchor} not found in dataset")
    return anchor


def _build_path_lines(
    *,
    stats_df: pd.DataFrame,
    df_raw: pd.DataFrame,
    df_2digits: pd.DataFrame,
    raw_by_date: dict[date, object],
    dates: list[date],
    anchor_date: date,
    mode: str,
    display_days: int,
    top_paths: int,
) -> pd.DataFrame:
    del df_raw
    _, loto_targets, de_targets = build_daily_targets(df_2digits)

    date_to_idx = {d: i for i, d in enumerate(dates)}
    anchor_idx = date_to_idx[anchor_date]
    start_idx = max(0, anchor_idx - display_days + 1)
    idxs = list(range(start_idx, anchor_idx + 1))

    stats_df = (
        stats_df.sort_values(
            ["p_mean", "current_streak", "max_streak", "hits"],
            ascending=[False, False, False, False],
        )
        .head(top_paths)
        .copy()
    )
    stats_df["pos_i"] = stats_df["i"].apply(index_to_label)
    stats_df["pos_j"] = stats_df["j"].apply(index_to_label)

    for t in idxs:
        d = dates[t]
        col_num = f"{d.isoformat()}_num"
        col_hit = f"{d.isoformat()}_hit"
        col_red = f"{d.isoformat()}_is_de"
        nums = []
        hits = []
        reds = []
        for _, r in stats_df.iterrows():
            lag = int(r["lag"])
            base_idx = t - lag
            if base_idx < 0:
                nums.append(None)
                hits.append(0)
                reds.append(0)
                continue
            base_date = dates[base_idx]
            raw = raw_by_date[base_date]
            n = int(10 * raw[int(r["i"])] + raw[int(r["j"])])
            nums.append(f"{n:02d}")
            if mode == "loto":
                hit = 1 if n in loto_targets[t] else 0
                is_de = 1 if n == de_targets[t] else 0
            else:
                hit = 1 if n == de_targets[t] else 0
                is_de = hit
            hits.append(hit)
            reds.append(is_de)
        stats_df[col_num] = nums
        stats_df[col_hit] = hits
        stats_df[col_red] = reds

    next_date = _to_date(anchor_date + pd.Timedelta(days=1))
    pred_nums = []
    for _, r in stats_df.iterrows():
        lag = int(r["lag"])
        base_date = _to_date(next_date - pd.Timedelta(days=lag))
        if base_date not in raw_by_date:
            pred_nums.append(None)
            continue
        raw = raw_by_date[base_date]
        n = int(10 * raw[int(r["i"])] + raw[int(r["j"])])
        pred_nums.append(f"{n:02d}")
    stats_df["next_day_pred"] = pred_nums

    fixed_cols = [
        "lag",
        "pos_i",
        "pos_j",
        "i",
        "j",
        "p_mean",
        "hits",
        "trials",
        "current_streak",
        "max_streak",
        "special_touch",
        "special_both",
        "next_day_pred",
    ]
    daily_cols = []
    for t in idxs:
        d = dates[t].isoformat()
        daily_cols.extend([f"{d}_num", f"{d}_hit", f"{d}_is_de"])
    keep_cols = [c for c in fixed_cols if c in stats_df.columns] + daily_cols
    return stats_df[keep_cols]


def _save_picks(
    out_dir: Path,
    mode: str,
    pred_active: pd.DataFrame,
    pred_stable: pd.DataFrame,
) -> None:
    def pack(df: pd.DataFrame) -> dict:
        nums = df["number"].astype(int).tolist()
        probs = df["prob"].astype(float).tolist()
        return {
            "bach_thu": f"{nums[0]:02d}" if nums else None,
            "song_thu": [f"{n:02d}" for n in nums[:2]],
            "dan_10": [f"{n:02d}" for n in nums[:10]],
            "prob_top10": [round(p, 6) for p in probs[:10]],
        }

    out = {
        "mode": mode,
        "active": pack(pred_active),
        "stable": pack(pred_stable),
    }
    (out_dir / f"picks_{mode}.json").write_text(
        pd.Series(out).to_json(force_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Website-style PATH report (rawdata -> numbers)."
    )
    ap.add_argument("--mode", choices=["loto", "de"], default="loto")
    ap.add_argument(
        "--bien-ngay",
        type=str,
        default=None,
        help="Anchor date (YYYY-MM-DD). Default: last date in data",
    )
    ap.add_argument(
        "--so-ngay",
        type=int,
        default=10,
        help="Display calendar days (like 'Số ngày cầu chạy' in UI)",
    )
    ap.add_argument(
        "--scope", choices=["all", "near_special", "special_only"], default="all"
    )
    ap.add_argument("--lag-max", type=int, default=30)
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--min-trials", type=int, default=60)
    ap.add_argument("--min-max-streak", type=int, default=3)
    ap.add_argument("--min-current-streak", type=int, default=3)
    ap.add_argument("--top-rules-per-lag", type=int, default=300)
    ap.add_argument("--bias-special-touch", type=float, default=1.0)
    ap.add_argument("--bias-special-both", type=float, default=1.0)
    ap.add_argument("--top-paths", type=int, default=80)
    ap.add_argument("--top-numbers", type=int, default=30)
    ap.add_argument("--out-dir", type=str, default="data/path_ui")
    args = ap.parse_args()

    display_days = max(1, args.so_ngay)
    params = PathParams(
        lag_max=args.lag_max,
        window_days=args.window_days,
        min_trials=args.min_trials,
        min_max_streak=args.min_max_streak,
        min_current_streak=args.min_current_streak,
        top_rules_per_lag=args.top_rules_per_lag,
    )

    lot = Lottery()
    lot.load()
    df_raw = lot.get_raw_data()
    df_2d = lot.get_2_digits_data()
    if df_raw.empty or df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    df_raw = df_raw.sort_values("date").reset_index(drop=True)
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    raw_calendar = require_daily_contiguous(
        df_raw["date"], context="path UI raw history"
    )
    two_calendar = require_daily_contiguous(
        df_2d["date"], context="path UI two-digit history"
    )
    if not raw_calendar.equals(two_calendar):
        raise ValueError("path UI raw and two-digit histories are not date-aligned")

    dates = [_to_date(d) for d in raw_calendar]
    anchor = _parse_date(args.bien_ngay) if args.bien_ngay else None
    anchor_date = _resolve_anchor_date(dates, anchor)

    stats, raw_by_date, fitted_dates = fit_paths(
        df_raw=df_raw,
        df_2digits=df_2d,
        params=params,
        mode=args.mode,
        anchor_date=anchor_date,
        scope=args.scope,
    )
    stats_df = paths_to_dataframe(stats)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stable_df = stats_df[
        (stats_df["trials"] >= params.min_trials)
        & (stats_df["max_streak"] >= params.min_max_streak)
    ].copy()
    active_df = stats_df[
        (stats_df["trials"] >= params.min_trials)
        & (stats_df["current_streak"] >= params.min_current_streak)
    ].copy()
    stable_df.to_csv(out_dir / f"paths_{args.mode}_stable.csv", index=False)
    active_df.to_csv(out_dir / f"paths_{args.mode}_active.csv", index=False)

    stable_lines = _build_path_lines(
        stats_df=stable_df,
        df_raw=df_raw,
        df_2digits=df_2d,
        raw_by_date=raw_by_date,
        dates=fitted_dates,
        anchor_date=anchor_date,
        mode=args.mode,
        display_days=display_days,
        top_paths=args.top_paths,
    )
    active_lines = _build_path_lines(
        stats_df=active_df,
        df_raw=df_raw,
        df_2digits=df_2d,
        raw_by_date=raw_by_date,
        dates=fitted_dates,
        anchor_date=anchor_date,
        mode=args.mode,
        display_days=display_days,
        top_paths=args.top_paths,
    )

    stable_lines.to_csv(
        out_dir
        / f"ui_{args.mode}_stable_{anchor_date.isoformat()}_{display_days}d.csv",
        index=False,
    )
    active_lines.to_csv(
        out_dir
        / f"ui_{args.mode}_active_{anchor_date.isoformat()}_{display_days}d.csv",
        index=False,
    )

    pred_active = predict_from_fitted_paths(
        stats=stats,
        raw_by_date=raw_by_date,
        dates=fitted_dates,
        params=params,
        kind="active",
        mode=args.mode,
        top_numbers=args.top_numbers,
        anchor_date=anchor_date,
        scope=args.scope,
        bias_special_touch=args.bias_special_touch,
        bias_special_both=args.bias_special_both,
    )
    pred_stable = predict_from_fitted_paths(
        stats=stats,
        raw_by_date=raw_by_date,
        dates=fitted_dates,
        params=params,
        kind="stable",
        mode=args.mode,
        top_numbers=args.top_numbers,
        anchor_date=anchor_date,
        scope=args.scope,
        bias_special_touch=args.bias_special_touch,
        bias_special_both=args.bias_special_both,
    )

    pred_active.to_csv(
        out_dir / f"predict_next_{args.mode}_active_{anchor_date.isoformat()}.csv",
        index=False,
    )
    pred_stable.to_csv(
        out_dir / f"predict_next_{args.mode}_stable_{anchor_date.isoformat()}.csv",
        index=False,
    )

    try:
        pred_active_full = predict_from_fitted_paths_full(
            stats=stats,
            raw_by_date=raw_by_date,
            dates=fitted_dates,
            params=params,
            kind="active",
            mode=args.mode,
            anchor_date=anchor_date,
            scope=args.scope,
            bias_special_touch=args.bias_special_touch,
            bias_special_both=args.bias_special_both,
        )
        pred_stable_full = predict_from_fitted_paths_full(
            stats=stats,
            raw_by_date=raw_by_date,
            dates=fitted_dates,
            params=params,
            kind="stable",
            mode=args.mode,
            anchor_date=anchor_date,
            scope=args.scope,
            bias_special_touch=args.bias_special_touch,
            bias_special_both=args.bias_special_both,
        )
        pred_active_full.to_csv(
            out_dir
            / f"predict_next_{args.mode}_active_{anchor_date.isoformat()}_all.csv",
            index=False,
        )
        pred_stable_full.to_csv(
            out_dir
            / f"predict_next_{args.mode}_stable_{anchor_date.isoformat()}_all.csv",
            index=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] could not export full predict tables: {exc}")

    manifest = {
        "schema_version": 2,
        "mode": args.mode,
        "anchor_date": anchor_date.isoformat(),
        "lag_max": params.lag_max,
        "lag_semantics": "calendar days on a verified daily-contiguous history",
        "window_days": params.window_days,
        "min_trials": params.min_trials,
        "min_max_streak": params.min_max_streak,
        "min_current_streak": params.min_current_streak,
        "scope": args.scope,
        "calendar_contiguous": True,
    }
    (out_dir / f"path_manifest_{args.mode}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    _save_picks(out_dir, args.mode, pred_active, pred_stable)

    print(
        f"Anchor date: {anchor_date} | mode={args.mode} | scope={args.scope} "
        f"| display_days={display_days}"
    )
    print("ACTIVE (current_streak) top picks:")
    print(pred_active.head(10))
    print("\nSTABLE (max_streak) top picks:")
    print(pred_stable.head(10))


if __name__ == "__main__":
    main()
