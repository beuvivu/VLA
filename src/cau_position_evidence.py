from __future__ import annotations

"""Clickable evidence tables for "đường cầu" positions.

The AI/ML layer scores numbers, while this module answers the practical UI
question: *which concrete raw-result digit positions contributed to a number?*

Each output row is one active/stable path rule:
    base date + lag + rawdata position i + rawdata position j -> formed number

The tables are descriptive/explainable evidence for historical ranking signals;
they are not guaranteed future lottery outcomes.
"""

import argparse
import csv
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from lottery import Lottery
from path_models import PathParams, index_to_label
from path_prob import fit_paths, paths_to_dataframe

Mode = Literal["loto", "de"]
Kind = Literal["active", "stable"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionEvidenceConfig:
    lag_max: int = 30
    window_days: int = 2000
    min_trials: int = 60
    min_max_streak: int = 3
    min_current_streak: int = 3
    top_positions_per_number: int = 8
    scope: str = "all"


def _fmt2(n: int | float | str) -> str:
    return f"{int(float(n)):02d}"



FIELD_DISPLAY_NAMES = {
    "special": "Giải ĐB",
    "prize1": "Giải nhất",
    "prize2_1": "Giải nhì 1",
    "prize2_2": "Giải nhì 2",
    "prize3_1": "Giải ba 1",
    "prize3_2": "Giải ba 2",
    "prize3_3": "Giải ba 3",
    "prize3_4": "Giải ba 4",
    "prize3_5": "Giải ba 5",
    "prize3_6": "Giải ba 6",
    "prize4_1": "Giải tư 1",
    "prize4_2": "Giải tư 2",
    "prize4_3": "Giải tư 3",
    "prize4_4": "Giải tư 4",
    "prize5_1": "Giải năm 1",
    "prize5_2": "Giải năm 2",
    "prize5_3": "Giải năm 3",
    "prize5_4": "Giải năm 4",
    "prize5_5": "Giải năm 5",
    "prize5_6": "Giải năm 6",
    "prize6_1": "Giải sáu 1",
    "prize6_2": "Giải sáu 2",
    "prize6_3": "Giải sáu 3",
    "prize7_1": "Giải bảy 1",
    "prize7_2": "Giải bảy 2",
    "prize7_3": "Giải bảy 3",
    "prize7_4": "Giải bảy 4",
}


def _pretty_position_label(code: str) -> str:
    """Convert technical position code, e.g. prize3_2.d4, to a UI label."""
    try:
        field, digit = code.split(".d", 1)
        digit_no = int(digit) + 1
        return f"{FIELD_DISPLAY_NAMES.get(field, field)} · số {digit_no}"
    except Exception:
        return code


def _to_date(value: object) -> date:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _read_csv(path: Path, *, dtype: dict[str, object] | str | None = None) -> pd.DataFrame:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        return pd.read_csv(path, dtype=dtype, keep_default_na=False)
    except Exception:
        return pd.DataFrame()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        if not np.isfinite(out):
            return default
        return out
    except Exception:
        return default


def _filter_kind(paths: pd.DataFrame, params: PathParams, kind: Kind) -> pd.DataFrame:
    if paths.empty:
        return paths
    view = paths[pd.to_numeric(paths["trials"], errors="coerce").fillna(0).astype(int) >= params.min_trials].copy()
    if kind == "active":
        view = view[pd.to_numeric(view["current_streak"], errors="coerce").fillna(0).astype(int) >= params.min_current_streak]
    else:
        view = view[pd.to_numeric(view["max_streak"], errors="coerce").fillna(0).astype(int) >= params.min_max_streak]
    return view


def _rule_score(row: pd.Series) -> float:
    """Readable score for ordering explanation rows, not a betting signal."""
    p_mean = _safe_float(row.get("p_mean"))
    hits = _safe_float(row.get("hits"))
    trials = max(_safe_float(row.get("trials")), 1.0)
    current_streak = _safe_float(row.get("current_streak"))
    max_streak = _safe_float(row.get("max_streak"))
    special_touch = _safe_float(row.get("special_touch"))
    special_both = _safe_float(row.get("special_both"))
    reliability = min(1.0, trials / 365.0)
    score = (
        100.0 * p_mean * reliability
        + 3.8 * current_streak
        + 1.35 * max_streak
        + 0.20 * min(hits, 120.0)
        + 2.0 * special_touch
        + 4.0 * special_both
    )
    return round(float(score), 4)


def _row_reason(row: pd.Series) -> str:
    current_streak = int(_safe_float(row.get("current_streak")))
    max_streak = int(_safe_float(row.get("max_streak")))
    p_mean = _safe_float(row.get("p_mean"))
    hits = int(_safe_float(row.get("hits")))
    trials = int(_safe_float(row.get("trials")))
    kind = str(row.get("rule_kind", ""))
    if kind == "active" and current_streak > 0:
        return f"Cầu đang chạy {current_streak} nhịp; lịch sử {hits}/{trials}, p≈{p_mean:.3f}."
    return f"Cầu bền: max streak {max_streak}; lịch sử {hits}/{trials}, p≈{p_mean:.3f}."


def _build_positions_for_mode(
    *,
    mode: Mode,
    df_raw: pd.DataFrame,
    df_2digits: pd.DataFrame,
    out_dir: Path,
    config: PositionEvidenceConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    params = PathParams(
        lag_max=config.lag_max,
        window_days=config.window_days,
        min_trials=config.min_trials,
        min_max_streak=config.min_max_streak,
        min_current_streak=config.min_current_streak,
    )

    stats, raw_by_date, dates = fit_paths(
        df_raw=df_raw,
        df_2digits=df_2digits,
        params=params,
        mode=mode,
        anchor_date=None,
        scope=config.scope,
    )
    anchor_date = dates[-1]
    predict_for_date = anchor_date + timedelta(days=1)

    all_paths = paths_to_dataframe(stats)
    if all_paths.empty:
        return pd.DataFrame(), pd.DataFrame()

    rows: list[dict[str, object]] = []
    for kind in ("active", "stable"):
        view = _filter_kind(all_paths, params, kind)  # type: ignore[arg-type]
        if view.empty:
            continue

        for _, r in view.iterrows():
            lag = int(r["lag"])
            base_date = predict_for_date - timedelta(days=lag)
            raw = raw_by_date.get(base_date)
            if raw is None:
                continue
            i = int(r["i"])
            j = int(r["j"])
            digit_i = int(raw[i])
            digit_j = int(raw[j])
            formed = int(10 * digit_i + digit_j)
            pos_i_code = index_to_label(i)
            pos_j_code = index_to_label(j)
            pos_i_label = _pretty_position_label(pos_i_code)
            pos_j_label = _pretty_position_label(pos_j_code)
            base: dict[str, object] = {
                "mode": mode,
                "rule_kind": kind,
                "anchor_date": anchor_date.isoformat(),
                "predict_for_date": predict_for_date.isoformat(),
                "number": formed,
                "number_str": _fmt2(formed),
                "lag_days": lag,
                "base_date": base_date.isoformat(),
                "pos_i_index": i,
                "pos_i_code": pos_i_code,
                "pos_i_label": pos_i_label,
                "digit_i": digit_i,
                "pos_j_index": j,
                "pos_j_code": pos_j_code,
                "pos_j_label": pos_j_label,
                "digit_j": digit_j,
                "path_line": f"L{lag}: {pos_i_label}({digit_i}) + {pos_j_label}({digit_j}) → {_fmt2(formed)}",
                "p_mean": round(_safe_float(r.get("p_mean")), 8),
                "hits": int(_safe_float(r.get("hits"))),
                "trials": int(_safe_float(r.get("trials"))),
                "hit_rate": round(_safe_float(r.get("hits")) / max(_safe_float(r.get("trials")), 1.0), 8),
                "current_streak": int(_safe_float(r.get("current_streak"))),
                "max_streak": int(_safe_float(r.get("max_streak"))),
                "special_touch": int(_safe_float(r.get("special_touch"))),
                "special_both": int(_safe_float(r.get("special_both"))),
            }
            base["rule_score"] = _rule_score(pd.Series(base | r.to_dict()))
            base["reason"] = _row_reason(pd.Series(base | r.to_dict()))
            rows.append(base)

    positions = pd.DataFrame(rows)
    if positions.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Prefer active over stable when the same exact raw path appears twice.
    positions["kind_priority"] = positions["rule_kind"].map({"active": 0, "stable": 1}).fillna(2).astype(int)
    positions = positions.sort_values(
        ["number", "kind_priority", "rule_score", "p_mean", "current_streak", "max_streak", "hits"],
        ascending=[True, True, False, False, False, False, False],
    )
    positions = positions.drop_duplicates(["mode", "number", "lag_days", "pos_i_index", "pos_j_index"], keep="first")

    top_positions = (
        positions.sort_values(
            ["number", "rule_score", "p_mean", "current_streak", "max_streak", "hits"],
            ascending=[True, False, False, False, False, False],
        )
        .groupby("number", sort=True, group_keys=False)
        .head(config.top_positions_per_number)
        .reset_index(drop=True)
    )
    top_positions = top_positions.drop(columns=["kind_priority"], errors="ignore")

    summary = _build_summary_for_mode(
        mode=mode,
        positions=top_positions,
        out_dir=out_dir,
        anchor_date=anchor_date,
        predict_for_date=predict_for_date,
    )

    return top_positions, summary


def _build_summary_for_mode(
    *,
    mode: Mode,
    positions: pd.DataFrame,
    out_dir: Path,
    anchor_date: date,
    predict_for_date: date,
) -> pd.DataFrame:
    ai = _read_csv(out_dir / f"cau_keo_{mode}_all.csv", dtype=str)
    ai_lookup: dict[str, dict[str, object]] = {}
    if not ai.empty and "number_str" in ai.columns:
        for _, row in ai.iterrows():
            ai_lookup[_fmt2(row.get("number_str", 0))] = row.to_dict()

    rows: list[dict[str, object]] = []
    for n in range(100):
        ns = _fmt2(n)
        sub = positions[positions["number_str"].astype(str).str.zfill(2) == ns].copy() if not positions.empty else pd.DataFrame()
        top = sub.sort_values(["rule_score", "p_mean"], ascending=False).head(3)
        ai_row = ai_lookup.get(ns, {})
        ai_score = _safe_float(ai_row.get("cau_score"))
        ai_prob = _safe_float(ai_row.get("prob_percent"))
        primary_reason = str(ai_row.get("primary_reason", ""))
        evidence = str(ai_row.get("evidence", ""))

        top_lines = top["path_line"].astype(str).tolist() if not top.empty and "path_line" in top.columns else []
        active_count = int((sub.get("rule_kind", pd.Series(dtype=str)).astype(str) == "active").sum()) if not sub.empty else 0
        stable_count = int((sub.get("rule_kind", pd.Series(dtype=str)).astype(str) == "stable").sum()) if not sub.empty else 0

        rows.append(
            {
                "mode": mode,
                "anchor_date": anchor_date.isoformat(),
                "predict_for_date": predict_for_date.isoformat(),
                "number": n,
                "number_str": ns,
                "ai_cau_score": round(ai_score, 4),
                "ai_prob_percent": round(ai_prob, 4),
                "primary_reason": primary_reason,
                "ai_evidence": evidence,
                "path_lines_count": int(len(sub)),
                "active_path_count": active_count,
                "stable_path_count": stable_count,
                "top_path_score": round(float(top["rule_score"].max()), 4) if not top.empty else 0.0,
                "max_path_p_mean": round(float(pd.to_numeric(sub["p_mean"], errors="coerce").fillna(0).max()), 8) if not sub.empty else 0.0,
                "max_current_streak": int(pd.to_numeric(sub["current_streak"], errors="coerce").fillna(0).max()) if not sub.empty else 0,
                "max_streak": int(pd.to_numeric(sub["max_streak"], errors="coerce").fillna(0).max()) if not sub.empty else 0,
                "top_position_1": top_lines[0] if len(top_lines) > 0 else "",
                "top_position_2": top_lines[1] if len(top_lines) > 1 else "",
                "top_position_3": top_lines[2] if len(top_lines) > 2 else "",
                "explain_text": _summary_text(ns, ai_score, ai_prob, primary_reason, top_lines, len(sub)),
                "note": "Căn cứ đường cầu là bảng giải thích vị trí/tín hiệu lịch sử; không bảo đảm kết quả tương lai.",
            }
        )

    return pd.DataFrame(rows).sort_values(["ai_cau_score", "top_path_score", "path_lines_count"], ascending=False).reset_index(drop=True)


def _summary_text(number_str: str, ai_score: float, ai_prob: float, primary_reason: str, top_lines: list[str], count: int) -> str:
    parts = [f"Số {number_str}: AI score {ai_score:.1f}, xác suất hiển thị {ai_prob:.2f}%."]
    if primary_reason:
        parts.append(f"Lý do chính: {primary_reason}.")
    if top_lines:
        parts.append(f"Có {count} đường cầu vị trí; mạnh nhất: {top_lines[0]}.")
    else:
        parts.append("Chưa có đường cầu vị trí đủ ngưỡng; xem tần suất/nhịp/AI làm căn cứ phụ.")
    return " ".join(parts)


def run(
    *,
    mode: Mode | Literal["both"] = "both",
    out_dir: Path | str = "data/ai_ml",
    config: PositionEvidenceConfig | None = None,
) -> list[Path]:
    cfg = config or PositionEvidenceConfig()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    lot = Lottery()
    lot.load()
    df_raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    df_2digits = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    if df_raw.empty or df_2digits.empty:
        raise RuntimeError("No data loaded. Run src/sync.py first.")

    modes: list[Mode] = ["loto", "de"] if mode == "both" else [mode]
    created: list[Path] = []
    manifest_outputs: dict[str, dict[str, str]] = {}

    for m in modes:
        positions, summary = _build_positions_for_mode(
            mode=m,
            df_raw=df_raw,
            df_2digits=df_2digits,
            out_dir=out,
            config=cfg,
        )
        positions_path = out / f"cau_position_evidence_{m}.csv"
        summary_path = out / f"cau_number_explain_{m}.csv"

        positions.to_csv(positions_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
        summary.to_csv(summary_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
        created.extend([positions_path, summary_path])
        manifest_outputs[m] = {
            "positions": positions_path.name,
            "summary": summary_path.name,
            "rows_positions": str(len(positions)),
            "rows_summary": str(len(summary)),
        }
        logger.info("Generated %s position evidence rows for %s", len(positions), m)

    manifest_path = out / "cau_position_manifest.json"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": cfg.scope,
        "lag_max": cfg.lag_max,
        "window_days": cfg.window_days,
        "min_trials": cfg.min_trials,
        "min_max_streak": cfg.min_max_streak,
        "min_current_streak": cfg.min_current_streak,
        "top_positions_per_number": cfg.top_positions_per_number,
        "outputs": manifest_outputs,
        "note": "Position evidence powers click-to-explain UI for 00-99 matrices.",
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    created.append(manifest_path)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate clickable vị trí đường cầu evidence tables.")
    parser.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    parser.add_argument("--out-dir", default="data/ai_ml")
    parser.add_argument("--lag-max", type=int, default=30)
    parser.add_argument("--window-days", type=int, default=2000)
    parser.add_argument("--min-trials", type=int, default=60)
    parser.add_argument("--min-max-streak", type=int, default=3)
    parser.add_argument("--min-current-streak", type=int, default=3)
    parser.add_argument("--top-positions-per-number", type=int, default=8)
    parser.add_argument("--scope", choices=["all", "near_special", "special_only"], default="all")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = PositionEvidenceConfig(
        lag_max=args.lag_max,
        window_days=args.window_days,
        min_trials=args.min_trials,
        min_max_streak=args.min_max_streak,
        min_current_streak=args.min_current_streak,
        top_positions_per_number=args.top_positions_per_number,
        scope=args.scope,
    )
    created = run(mode=args.mode, out_dir=args.out_dir, config=cfg)
    for path in created:
        print(f"[OK] {path}")


if __name__ == "__main__":
    main()
