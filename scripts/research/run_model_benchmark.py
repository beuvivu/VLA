from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from soi_cau.bridges import DigitTensor  # noqa: E402
from forecast.modeling.benchmark import (  # noqa: E402
    BetaBinomialShrinkage,
    ClusterRate,
    Evaluation,
    GapHazard,
    MarkovChain,
    ShrinkageEnsemble,
    default_models,
    walk_forward,
)


def proposed_ensemble() -> ShrinkageEnsemble:
    return ShrinkageEnsemble(
        [BetaBinomialShrinkage(), MarkovChain(order=1, pooled=True), GapHazard(), ClusterRate(4)],
        evidence_window=90,
    )


def circular_shift_check(counts: np.ndarray, model, *, warmup: int, shifts: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = counts.shape[0]
    skills = []
    for _ in range(shifts):
        offset = int(rng.integers(warmup // 2, n - warmup // 2))
        shifted = np.roll(counts, offset, axis=0)
        skills.append(walk_forward(shifted, model, warmup=warmup).logloss_skill)
    return {
        "shifts": shifts,
        "mean_skill": float(np.mean(skills)),
        "max_skill": float(np.max(skills)),
        "sd_skill": float(np.std(skills, ddof=1)) if len(skills) > 1 else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/xsmb.csv")
    parser.add_argument("--out-dir", default="data/research")
    parser.add_argument("--warmup", type=int, default=120)
    parser.add_argument("--shifts", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260906)
    args = parser.parse_args()

    tensor = DigitTensor.from_raw(pd.read_csv(args.raw))
    counts = tensor.loto_counts.astype(np.int16)

    results: list[Evaluation] = []
    for model in [*default_models(), proposed_ensemble()]:
        results.append(walk_forward(counts, model, warmup=args.warmup))
        print("  " + results[-1].describe(), flush=True)

    ranked = sorted(results, key=lambda e: -e.logloss_skill)
    best_named = next(r for r in ranked if r.family != "baseline")
    best_model = next(m for m in default_models() if m.name == best_named.name)
    reality = circular_shift_check(
        counts, best_model, warmup=args.warmup, shifts=args.shifts, seed=args.seed
    )

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "days": tensor.n_days,
        "evaluation_days": results[0].days,
        "warmup": args.warmup,
        "baseline_rate": results[0].baseline_logloss,
        "models": [
            {
                "name": r.name,
                "family": r.family,
                "logloss": r.logloss,
                "brier": r.brier,
                "logloss_skill": r.logloss_skill,
                "brier_skill": r.brier_skill,
                "paired_t": r.paired_t,
                "hit_at_27": r.hit_at_27,
                "baseline_hit_at_27": r.baseline_hit_at_27,
                "calibration_error": r.calibration_error,
                "beats_baseline": r.beats_baseline,
            }
            for r in results
        ],
        "models_beating_baseline": sum(r.beats_baseline for r in results),
        "proposed_ensemble_weights": {
            name: float(weight)
            for name, weight in zip(
                [m.name for m in proposed_ensemble().models] + ["nền"],
                proposed_ensemble().weights(counts),
                strict=True,
            )
        },
        "reality_check": {"model": best_named.name, "observed_skill": best_named.logloss_skill}
        | reality,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model_benchmark.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n  Vượt nền có ý nghĩa: {summary['models_beating_baseline']}/{len(results)}")
    print(
        f"\n  Đối chứng xáo trộn ({best_named.name}): thật={best_named.logloss_skill:+.5f}, "
        f"xáo trộn trung bình={reality['mean_skill']:+.5f}, cao nhất={reality['max_skill']:+.5f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
