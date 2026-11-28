from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from soi_cau.bridges import DigitTensor
from soi_cau.features import FeatureContext, default_registry
from core.xsmb_domain import LOTO_DRAWS_PER_DAY, baseline_rate

SIGNIFICANCE_T = 1.96


def evaluate(
    tensor: DigitTensor, *, warmup_days: int = 180, top_k: int = LOTO_DRAWS_PER_DAY
) -> pd.DataFrame:
    registry = default_registry()
    hits = tensor.loto_hits()
    baseline = baseline_rate("loto")

    columns: tuple[str, ...] | None = None
    groups: dict[str, tuple[int, int]] = {}
    per_day: list[np.ndarray] = []

    for anchor in range(warmup_days, tensor.n_days - 1):
        matrix = registry.build_matrix(FeatureContext(tensor=tensor, anchor_index=anchor))
        if columns is None:
            columns, groups = matrix.columns, matrix.groups
        target = hits[anchor + 1]
        order = np.lexsort(
            (
                np.broadcast_to(np.arange(matrix.values.shape[0])[:, None], matrix.values.shape),
                -matrix.values,
            ),
            axis=0,
        )
        chosen = order[:top_k]
        per_day.append(target[chosen].mean(axis=0))

    if not per_day:
        raise ValueError("cửa sổ kiểm rỗng; giảm warmup_days")

    precision = np.vstack(per_day)
    n_days = precision.shape[0]
    mean = precision.mean(axis=0)
    stderr = precision.std(axis=0, ddof=1) / np.sqrt(n_days)
    t_stat = np.divide(mean - baseline, stderr, out=np.zeros_like(mean), where=stderr > 1e-12)

    group_of = {
        column: name for name, (start, stop) in groups.items() for column in columns[start:stop]
    }
    frame = pd.DataFrame(
        {
            "feature": columns,
            "group": [group_of[c] for c in columns],
            "days": n_days,
            "precision": mean,
            "baseline": baseline,
            "lift": mean - baseline,
            "stderr": stderr,
            "t_stat": t_stat,
        }
    )
    frame["beats_baseline"] = frame["t_stat"] > SIGNIFICANCE_T
    return frame.sort_values("t_stat", ascending=False).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/xsmb.csv")
    parser.add_argument("--out-dir", default="data/research")
    parser.add_argument("--warmup-days", type=int, default=180)
    args = parser.parse_args()

    tensor = DigitTensor.from_raw(pd.read_csv(args.raw))
    frame = evaluate(tensor, warmup_days=args.warmup_days)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_dir / "feature_scores.csv", index=False)

    winners = frame[frame["beats_baseline"]]
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "features": int(len(frame)),
        "days_evaluated": int(frame["days"].iloc[0]),
        "baseline": float(frame["baseline"].iloc[0]),
        "significance_t": SIGNIFICANCE_T,
        "beating_baseline": int(len(winners)),
        "best_feature": str(frame["feature"].iloc[0]),
        "best_t_stat": float(frame["t_stat"].iloc[0]),
    }
    (out_dir / "feature_scores_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(frame.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(
        f"\n{len(winners)}/{len(frame)} đặc trưng vượt đường cơ sở có ý nghĩa "
        f"(|t| > {SIGNIFICANCE_T}) trên {summary['days_evaluated']} ngày."
    )


if __name__ == "__main__":
    main()
