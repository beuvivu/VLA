"""Đo ngoài mẫu tầng trộn và tầng phán đoán của ``ml_engine``.

Chạy ``ContinuousLearningPipeline`` (cấu hình mặc định, đủ sáu cánh tay) trên
``--last`` kỳ cuối của ``data/xsmb.csv`` và ghi điểm từng kỳ của dự báo CUỐI
(sau trộn và sau chế độ an toàn) cùng điểm của hằng số nền trên cùng kỳ.

Luật quyết định chốt TRƯỚC khi đo (20-10-2026), khi thay bandit Thompson bằng
trọng số mũ trên log-loss và cổng độ tin ``model_trust``: bản mới được nhận khi
nó không kém hằng số với z ≤ −2 VÀ không kém bản cũ với z ≤ −2 (chênh log-loss
ghép cặp theo kỳ, sai số lấy max(theo ngày, khối 7 kỳ) như cổng đề bạt của
``online_learning``). Bản cũ đo bằng chính tệp này chạy trên mã của ``main``.

    PYTHONPATH=src python3 scripts/research/benchmark_ml_engine_aggregation.py \\
        --last 1000 --days-out /tmp/moi.csv [--against /tmp/cu.csv --against-label cu]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from research.ml_engine.main_pipeline import ContinuousLearningPipeline, PipelineConfig  # noqa: E402
from research.ml_engine.metrics import score_day  # noqa: E402
from research.ml_engine.schema import ObservationMatrix  # noqa: E402

OUT = ROOT / "data" / "research" / "ml_engine_aggregation.json"
BLOCK = 7


def paired(gain: np.ndarray) -> dict:
    """Trung bình chênh và z, sai số lấy max(theo ngày, khối ``BLOCK`` kỳ liên tiếp)."""
    gain = np.asarray(gain, dtype=float)
    n = len(gain)
    day_se = float(gain.std(ddof=1) / np.sqrt(n))
    blocks = np.array([gain[i:i + BLOCK].mean() for i in range(0, n - BLOCK + 1, BLOCK)])
    block_se = float(blocks.std(ddof=1) / np.sqrt(len(blocks))) if len(blocks) > 1 else day_se
    se = max(day_se, block_se)
    return {"n": n, "mean": float(gain.mean()), "se": se,
            "z": float(gain.mean() / se) if se > 0 else 0.0}


def run(raw: Path, last: int) -> pd.DataFrame:
    observations = ObservationMatrix.from_frame(pd.read_csv(raw))
    pipeline = ContinuousLearningPipeline(observations, PipelineConfig())
    stop = observations.n_days
    rows = []
    for result in pipeline.run(start=stop - last, stop=stop):
        outcome = (observations.counts[result.day_index] > 0).astype(float)
        score = score_day(result.probabilities, outcome)
        rows.append({
            "date": result.date.date().isoformat(),
            "logloss": score.logloss,
            "brier": score.brier,
            "baseline_logloss": score.baseline_logloss,
            "baseline_brier": score.baseline_brier,
            "mode": result.mode,
        })
    return pd.DataFrame(rows)


def summary(days: pd.DataFrame) -> dict:
    loss, base = days["logloss"].to_numpy(), days["baseline_logloss"].to_numpy()
    brier, base_brier = days["brier"].to_numpy(), days["baseline_brier"].to_numpy()
    return {
        "days": len(days),
        "first_date": days["date"].iloc[0],
        "last_date": days["date"].iloc[-1],
        "logloss_skill": float((base.mean() - loss.mean()) / base.mean()),
        "brier_skill": float((base_brier.mean() - brier.mean()) / base_brier.mean()),
        "vs_constant": paired(base - loss),
        "safe_days": int((days["mode"] == "safe").sum()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "xsmb.csv")
    parser.add_argument("--last", type=int, default=1000)
    parser.add_argument("--label", default="moi")
    parser.add_argument("--days-out", type=Path, required=True,
                        help="CSV điểm từng kỳ của lượt này")
    parser.add_argument("--against", type=Path, default=None,
                        help="CSV điểm từng kỳ của bản khác, cùng các kỳ")
    parser.add_argument("--against-label", default="cu")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    days = run(args.raw, args.last)
    args.days_out.parent.mkdir(parents=True, exist_ok=True)
    days.to_csv(args.days_out, index=False)
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "last": args.last,
        "config": "PipelineConfig() mặc định, đủ sáu cánh tay",
        args.label: summary(days),
    }
    if args.against is not None:
        other = pd.read_csv(args.against)
        if other["date"].tolist() != days["date"].tolist():
            raise SystemExit("hai lượt phải chấm đúng cùng các kỳ")
        report[args.against_label] = summary(other)
        gain = other["logloss"].to_numpy() - days["logloss"].to_numpy()
        report[f"{args.label}_vs_{args.against_label}"] = paired(gain)
        accepted = (report[args.label]["vs_constant"]["z"] > -2.0
                    and report[f"{args.label}_vs_{args.against_label}"]["z"] > -2.0)
        report["decision"] = {"rule": "không kém hằng số và không kém bản cũ với z ≤ −2",
                              "accepted": bool(accepted)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
