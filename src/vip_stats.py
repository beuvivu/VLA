from __future__ import annotations

"""Compatibility entrypoint for the historical ``vip_stats.py`` command.

The legacy module used a second implementation of head/sum/touch statistics and
interpreted ``lookback-days`` as a row count. The canonical implementation now
lives in :mod:`descriptive_extensions`; this wrapper preserves the old CLI and
artifact names without maintaining a divergent statistics engine.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from descriptive_extensions import _group_gap_rows, build_head_table
from lottery import Lottery


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Compatibility wrapper for VIP descriptive statistics; delegates to "
            "the canonical descriptive_extensions implementation."
        )
    )
    ap.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Inclusive calendar-day window for the head table.",
    )
    ap.add_argument("--out-dir", default="data/vip")
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    if two.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    days = max(1, int(args.lookback_days))

    head = build_head_table(two, lookback_days=days)
    head.to_csv(out / f"head_table_{days}d.csv", index=False)
    head.to_json(
        out / f"head_table_{days}d.json",
        orient="records",
        indent=2,
        force_ascii=False,
    )

    for mode in ("loto", "de"):
        raw_sum, _mod_sum, touch = _group_gap_rows(two, mode=mode)
        # Preserve historical VIP filenames while using the canonical tables.
        raw_sum.rename(columns={"digit_sum": "sum"}).to_csv(
            out / f"gap_sum_{mode}.csv", index=False
        )
        touch.to_csv(out / f"gap_touch_{mode}.csv", index=False)

    manifest = {
        "schema_version": 2,
        "compatibility_wrapper": True,
        "canonical_module": "descriptive_extensions.py",
        "latest_date": pd.to_datetime(two["date"]).max().date().isoformat(),
        "lookback_days": days,
        "window_semantics": "inclusive calendar days",
        "note": "Legacy VIP filenames retained; statistics are computed only by the canonical descriptive engine.",
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] VIP compatibility outputs -> {out}")


if __name__ == "__main__":
    main()
