from __future__ import annotations

"""Recent hit/miss timelines for VLA positional path evidence.

The legacy ``xoso`` repository exposed a useful explainability primitive: for a
specific path, show what number it generated on each recent target date and whether
that number actually hit. VLA already has a materially stronger path engine; this
module adds the missing timeline evidence *around that engine's selected paths*
without changing path probabilities or prediction weights.
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd

from lottery import Lottery
from path_models import build_daily_targets, build_rawdata_digits_from_row

Mode = Literal["loto", "de"]


def _as_date(value: object) -> date:
    return pd.Timestamp(value).date()


def build_timeline_table(
    raw: pd.DataFrame,
    two: pd.DataFrame,
    positions: pd.DataFrame,
    *,
    mode: Mode,
    recent: int = 20,
) -> pd.DataFrame:
    if raw.empty or two.empty or positions.empty:
        return pd.DataFrame()

    raw_sorted = raw.sort_values("date").reset_index(drop=True)
    two_sorted = two.sort_values("date").reset_index(drop=True)
    raw_by_date = {
        _as_date(row["date"]): build_rawdata_digits_from_row(row)
        for _, row in raw_sorted.iterrows()
    }
    dates, loto_targets, de_targets = build_daily_targets(two_sorted)
    loto_by_date = {d: loto_targets[i] for i, d in enumerate(dates)}
    de_by_date = {d: int(de_targets[i]) for i, d in enumerate(dates)}

    rows: list[dict[str, object]] = []
    view = positions.copy()
    for col in ("rule_score", "p_mean", "current_streak", "max_streak"):
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0)
    sort_cols = [c for c in ("rule_score", "p_mean", "current_streak", "max_streak") if c in view.columns]
    if sort_cols:
        view = view.sort_values(sort_cols, ascending=[False] * len(sort_cols))

    dedupe_cols = [c for c in ("lag_days", "pos_i_index", "pos_j_index", "rule_kind") if c in view.columns]
    if dedupe_cols:
        view = view.drop_duplicates(dedupe_cols, keep="first")

    for _, rule in view.iterrows():
        lag = int(rule["lag_days"])
        i = int(rule["pos_i_index"])
        j = int(rule["pos_j_index"])
        timeline: list[dict[str, object]] = []

        for target_date in dates:
            base_date = target_date - timedelta(days=lag)
            digits = raw_by_date.get(base_date)
            if digits is None or i >= len(digits) or j >= len(digits):
                continue
            candidate = int(10 * int(digits[i]) + int(digits[j]))
            hit = (
                candidate in loto_by_date[target_date]
                if mode == "loto"
                else candidate == de_by_date[target_date]
            )
            timeline.append(
                {
                    "target_date": target_date.isoformat(),
                    "base_date": base_date.isoformat(),
                    "candidate": f"{candidate:02d}",
                    "hit": bool(hit),
                }
            )

        recent_rows = timeline[-max(1, int(recent)) :]
        hits_recent = int(sum(bool(x["hit"]) for x in recent_rows))
        hits_all = int(sum(bool(x["hit"]) for x in timeline))
        predict_for = _as_date(rule.get("predict_for_date", dates[-1] + timedelta(days=1)))
        next_base = predict_for - timedelta(days=lag)
        next_digits = raw_by_date.get(next_base)
        predicts_next = (
            f"{int(10 * int(next_digits[i]) + int(next_digits[j])):02d}"
            if next_digits is not None and i < len(next_digits) and j < len(next_digits)
            else None
        )

        rows.append(
            {
                "mode": mode,
                "rule_kind": rule.get("rule_kind", ""),
                "lag_days": lag,
                "pos_i_index": i,
                "pos_j_index": j,
                "pos_i_code": rule.get("pos_i_code", ""),
                "pos_j_code": rule.get("pos_j_code", ""),
                "path_line": rule.get("path_line", ""),
                "rule_score": float(rule.get("rule_score", 0) or 0),
                "p_mean": float(rule.get("p_mean", 0) or 0),
                "current_streak": int(float(rule.get("current_streak", 0) or 0)),
                "max_streak": int(float(rule.get("max_streak", 0) or 0)),
                "predict_for_date": predict_for.isoformat(),
                "predicts_next": predicts_next,
                "timeline_trials": len(timeline),
                "timeline_hits": hits_all,
                "timeline_hit_rate": hits_all / len(timeline) if timeline else None,
                "recent_trials": len(recent_rows),
                "recent_hits": hits_recent,
                "recent_hit_rate": hits_recent / len(recent_rows) if recent_rows else None,
                "timeline_recent_json": json.dumps(recent_rows, ensure_ascii=False),
                "note": (
                    "Timeline is retrospective explainability only. The candidate for target date D "
                    "uses raw digits from D-lag and never uses D's outcome to construct the candidate."
                ),
            }
        )

    return pd.DataFrame(rows)


def run(
    *,
    data_dir: Path | str = "data",
    evidence_dir: Path | str = "data/ai_ml",
    out_dir: Path | str = "data/research/path_timelines",
    recent: int = 20,
) -> list[Path]:
    _ = Path(data_dir)  # retained for CLI compatibility; Lottery resolves repository data.
    evidence_root = Path(evidence_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    lot = Lottery()
    lot.load()
    raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    if raw.empty or two.empty:
        raise RuntimeError("No data loaded")

    created: list[Path] = []
    manifest: dict[str, object] = {
        "schema_version": 1,
        "anchor_date": pd.to_datetime(two["date"]).max().date().isoformat(),
        "recent_timeline_length": int(recent),
        "research_only": True,
        "modes": {},
    }
    for mode in ("loto", "de"):
        source = evidence_root / f"cau_position_evidence_{mode}.csv"
        if not source.exists() or source.stat().st_size == 0:
            manifest["modes"][mode] = {"status": "missing_position_evidence", "rows": 0}  # type: ignore[index]
            continue
        positions = pd.read_csv(source, keep_default_na=False)
        table = build_timeline_table(raw, two, positions, mode=mode, recent=recent)  # type: ignore[arg-type]
        target = out / f"path_timeline_{mode}.csv"
        table.to_csv(target, index=False)
        created.append(target)
        manifest["modes"][mode] = {  # type: ignore[index]
            "status": "ok",
            "rows": int(len(table)),
            "source": source.name,
            "output": target.name,
        }

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    created.append(manifest_path)
    return created


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate recent hit/miss timelines for selected positional paths.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--evidence-dir", default="data/ai_ml")
    ap.add_argument("--out-dir", default="data/research/path_timelines")
    ap.add_argument("--recent", type=int, default=20)
    args = ap.parse_args()
    created = run(
        data_dir=args.data_dir,
        evidence_dir=args.evidence_dir,
        out_dir=args.out_dir,
        recent=max(1, args.recent),
    )
    print(f"[OK] path timeline evidence -> {len(created)} artifact(s)")


if __name__ == "__main__":
    main()
