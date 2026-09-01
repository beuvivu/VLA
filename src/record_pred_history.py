from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ensemble_components import COMPONENT_KEYS, probability_component


def _latest_anchor_date(xsmb_csv: Path) -> date:
    df = pd.read_csv(xsmb_csv)
    df["date"] = pd.to_datetime(df["date"])
    return df["date"].max().date()


def _load_path_full(path_ui_dir: Path, mode: str, kind: str, anchor: date) -> pd.DataFrame:
    f = path_ui_dir / f"predict_next_{mode}_{kind}_{anchor.isoformat()}_all.csv"
    if f.exists():
        return pd.read_csv(f)
    f2 = path_ui_dir / f"predict_next_{mode}_{kind}_{anchor.isoformat()}.csv"
    if f2.exists():
        return pd.read_csv(f2)
    return pd.DataFrame(columns=["number", "prob"])


def _load_ml_full(ml_dir: Path, mode: str) -> pd.DataFrame:
    f = ml_dir / f"predict_next_{mode}_ml_all.csv"
    if f.exists():
        return pd.read_csv(f)
    return pd.DataFrame(columns=["number", "prob"])


def _load_cau_full(ai_ml_dir: Path, mode: str) -> pd.DataFrame:
    f = ai_ml_dir / f"cau_keo_{mode}_all.csv"
    if f.exists():
        return pd.read_csv(f)
    return pd.DataFrame(columns=["number", "prob"])


def _load_stat_full(stat_dir: Path, mode: str) -> pd.DataFrame:
    f = stat_dir / f"predict_next_{mode}_stat_all.csv"
    if f.exists():
        return pd.read_csv(f)
    return pd.DataFrame(columns=["number", "prob"])


def _sanitize_history(df: pd.DataFrame) -> pd.DataFrame:
    """Infer availability for legacy rows and erase synthetic all-zero placeholders."""
    out = df.copy()
    if "target_date" not in out.columns or "number" not in out.columns:
        return out

    for key in COMPONENT_KEYS:
        p_col = f"p_{key}"
        has_col = f"has_{key}"
        if has_col not in out.columns:
            out[has_col] = False
        if p_col not in out.columns:
            out[p_col] = np.nan
            out[has_col] = False
            continue

        for _, idx in out.groupby("target_date", sort=False).groups.items():
            loc = list(idx)
            sub = out.loc[loc]
            numbers = pd.to_numeric(sub["number"], errors="coerce")
            values = pd.to_numeric(sub[p_col], errors="coerce").to_numpy(dtype=float)
            valid = (
                len(sub) == 100
                and numbers.notna().all()
                and set(numbers.astype(int).tolist()) == set(range(100))
                and values.shape == (100,)
                and np.isfinite(values).all()
                and np.all((values >= 0.0) & (values <= 1.0))
                and float(values.sum()) > 0.0
            )
            out.loc[loc, has_col] = bool(valid)
            if not valid:
                out.loc[loc, p_col] = np.nan
    return out


def _upsert_history_csv(df_new: pd.DataFrame, out: Path, key_col: str = "target_date") -> None:
    """Upsert one prediction day and migrate the compact history to the availability contract."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 0:
        df_old = pd.read_csv(out)
        df_old = df_old[df_old[key_col].astype(str) != str(df_new[key_col].iloc[0])]
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new
    df_all = _sanitize_history(df_all)
    df_all.sort_values([key_col, "number"], inplace=True)
    df_all.to_csv(out, index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Record component predictions into history store.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--path-ui-dir", default="data/path_ui")
    ap.add_argument("--ml-dir", default="data/ml")
    ap.add_argument("--out-dir", default="data/history")
    ap.add_argument("--ai-ml-dir", default="data/ai_ml")
    ap.add_argument("--stat-dir", default="data/statistical_signal")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    anchor = _latest_anchor_date(data_dir / "xsmb.csv")
    target = anchor + timedelta(days=1)

    path_ui_dir = Path(args.path_ui_dir)
    ml_dir = Path(args.ml_dir)
    out_dir = Path(args.out_dir)
    ai_ml_dir = Path(args.ai_ml_dir)
    stat_dir = Path(args.stat_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for mode in ["loto", "de"]:
        frames = {
            "active": _load_path_full(path_ui_dir, mode, "active", anchor),
            "stable": _load_path_full(path_ui_dir, mode, "stable", anchor),
            "ml": _load_ml_full(ml_dir, mode),
            "cau": _load_cau_full(ai_ml_dir, mode),
            "stat": _load_stat_full(stat_dir, mode),
        }
        components = {
            key: probability_component(frame, mode=mode)  # type: ignore[arg-type]
            for key, frame in frames.items()
        }

        df_hist = pd.DataFrame(
            {
                "target_date": [target.isoformat()] * 100,
                "number": list(range(100)),
                **{
                    f"p_{key}": (
                        component.prob
                        if component.available
                        else np.full(100, np.nan, dtype=float)
                    )
                    for key, component in components.items()
                },
                **{
                    f"has_{key}": [bool(component.available)] * 100
                    for key, component in components.items()
                },
            }
        )
        out_path = out_dir / f"pred_{mode}.csv"
        _upsert_history_csv(df_hist, out_path)
        status = ", ".join(
            f"{key}={'ok' if component.available else component.reason}"
            for key, component in components.items()
        )
        print(
            f"[OK] recorded {mode} predictions for target_date={target} -> {out_path}; "
            f"components: {status}"
        )


if __name__ == "__main__":
    main()
