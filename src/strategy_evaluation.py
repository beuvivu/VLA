"""Chấm điểm cuốn chiếu mọi strategy đã đăng ký, luôn đối chứng với baseline.

Đây là thước đo trung thực của kiến trúc plugin: mỗi thuật toán chạy trên đúng
cùng một chuỗi ngày, dự đoán ngày ``t`` chỉ từ dữ liệu tới ngày ``t-1``, rồi
được chấm bằng cùng quy ước logloss/Brier mà :mod:`prob_eval` dùng cho sản xuất.

Điểm kỹ năng (*skill score*) là phần cải thiện tương đối so với đường cơ sở::

    skill = (baseline - model) / baseline

Dương nghĩa là tốt hơn baseline, âm nghĩa là tệ hơn. Với xổ số công bằng, giá
trị kỳ vọng là xấp xỉ 0 hoặc âm; báo cáo này tồn tại để nói ra điều đó bằng số
thay vì bằng cảm tính.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import predictor_algorithms  # noqa: F401  (đăng ký bộ thuật toán mặc định)
from predictor_strategies import (
    NUMBER_SPACE,
    REGISTRY,
    PredictionContext,
    PredictorStrategy,
    predict,
)

logger = logging.getLogger(__name__)

_EPS = 1e-12


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    """Cùng quy ước với ``prob_eval._safe_logloss`` để số liệu so sánh được."""
    q = np.clip(p, _EPS, 1 - _EPS)
    return float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(((p - y) ** 2).mean())


@dataclass(frozen=True)
class StrategyScore:
    """Kết quả tổng hợp của một strategy trên toàn bộ cửa sổ đánh giá."""

    strategy: str
    mode: str
    days: int
    logloss: float
    brier: float
    baseline_logloss: float
    baseline_brier: float

    @property
    def logloss_skill(self) -> float:
        if self.baseline_logloss <= 0:
            return 0.0
        return (self.baseline_logloss - self.logloss) / self.baseline_logloss

    @property
    def brier_skill(self) -> float:
        if self.baseline_brier <= 0:
            return 0.0
        return (self.baseline_brier - self.brier) / self.baseline_brier

    @property
    def beats_baseline(self) -> bool:
        return self.logloss < self.baseline_logloss and self.brier < self.baseline_brier

    def as_row(self) -> dict[str, object]:
        row = asdict(self)
        row["logloss_skill"] = self.logloss_skill
        row["brier_skill"] = self.brier_skill
        row["beats_baseline"] = self.beats_baseline
        return row


def build_hit_matrix(
    dates: Sequence[date], loto_targets: Sequence[set[int]], de_targets: Sequence[int], mode: str
) -> np.ndarray:
    """Dựng ma trận 0/1 ``(số ngày, 100)`` cho chế độ yêu cầu."""
    hits = np.zeros((len(dates), NUMBER_SPACE), dtype=np.float64)
    if mode == "loto":
        for index, numbers in enumerate(loto_targets):
            for number in numbers:
                hits[index, int(number)] = 1.0
    elif mode == "de":
        for index, number in enumerate(de_targets):
            hits[index, int(number)] = 1.0
    else:
        raise ValueError("mode phải là 'loto' hoặc 'de'")
    return hits


def evaluate_strategy(
    strategy: PredictorStrategy,
    *,
    dates: Sequence[date],
    hits: np.ndarray,
    mode: str,
    eval_days: int = 180,
) -> StrategyScore:
    """Chạy cuốn chiếu một strategy và chấm điểm cùng baseline."""
    total = len(dates)
    start = max(1, total - eval_days)
    baseline = REGISTRY.get("baseline")

    losses: list[float] = []
    briers: list[float] = []
    base_losses: list[float] = []
    base_briers: list[float] = []

    for index in range(start, total):
        ctx = PredictionContext(
            mode=mode,
            dates=dates,
            hits=hits,
            anchor_index=index - 1,
            target_date=dates[index],
        )
        truth = hits[index]
        try:
            probabilities = predict(strategy, ctx)
        except Exception:
            # Một thuật toán hỏng không được làm sập cả báo cáo; nó bị coi như
            # không phát biểu gì và lùi về baseline cho đúng ngày đó.
            logger.exception("strategy %s lỗi ở ngày %s", strategy.name, dates[index])
            probabilities = predict(baseline, ctx)

        losses.append(_logloss(probabilities, truth))
        briers.append(_brier(probabilities, truth))

        base = predict(baseline, ctx)
        base_losses.append(_logloss(base, truth))
        base_briers.append(_brier(base, truth))

    if not losses:
        raise ValueError("không có ngày nào để đánh giá")

    return StrategyScore(
        strategy=strategy.name,
        mode=mode,
        days=len(losses),
        logloss=float(np.mean(losses)),
        brier=float(np.mean(briers)),
        baseline_logloss=float(np.mean(base_losses)),
        baseline_brier=float(np.mean(base_briers)),
    )


def evaluate_all(
    *,
    dates: Sequence[date],
    loto_targets: Sequence[set[int]],
    de_targets: Sequence[int],
    modes: Sequence[str] = ("loto", "de"),
    eval_days: int = 180,
) -> list[StrategyScore]:
    """Chấm điểm toàn bộ strategy đã đăng ký trên mọi chế độ."""
    scores: list[StrategyScore] = []
    for mode in modes:
        hits = build_hit_matrix(dates, loto_targets, de_targets, mode)
        for strategy in REGISTRY.all():
            scores.append(
                evaluate_strategy(
                    strategy, dates=dates, hits=hits, mode=mode, eval_days=eval_days
                )
            )
    return scores


def scores_to_frame(scores: Sequence[StrategyScore]) -> pd.DataFrame:
    frame = pd.DataFrame([s.as_row() for s in scores])
    if frame.empty:
        return frame
    return frame.sort_values(["mode", "logloss_skill"], ascending=[True, False])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chấm điểm cuốn chiếu các thuật toán phỏng đoán so với đường cơ sở."
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--eval-days", type=int, default=180)
    parser.add_argument("--out", default="data/research/strategy_scores.csv")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from lottery import Lottery
    from path_models import build_daily_targets

    # Dùng loader chuẩn của dự án thay vì tự mở tệp: nó là nơi duy nhất biết
    # bố cục dữ liệu chính tắc, nên báo cáo này không lệch khỏi sản xuất.
    lottery = Lottery()
    lottery.load()
    frame_2d = lottery.get_2_digits_data()
    if frame_2d.empty:
        raise SystemExit("Chưa có dữ liệu. Hãy chạy src/sync.py trước.")
    dates, loto_targets, de_targets = build_daily_targets(frame_2d)

    scores = evaluate_all(
        dates=dates,
        loto_targets=loto_targets,
        de_targets=de_targets,
        eval_days=args.eval_days,
    )
    frame = scores_to_frame(scores)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)

    print(f"\nĐánh giá {args.eval_days} ngày gần nhất — điểm kỹ năng so với baseline")
    print("(dương = tốt hơn baseline, âm = tệ hơn)\n")
    for mode in frame["mode"].unique():
        print(f"--- {mode} ---")
        subset = frame[frame["mode"] == mode]
        for _, row in subset.iterrows():
            flag = "✓" if row["beats_baseline"] else "✗"
            print(
                f"  {flag} {row['strategy']:<20} "
                f"logloss={row['logloss']:.6f} (skill {row['logloss_skill']:+.4%})  "
                f"brier={row['brier']:.6f} (skill {row['brier_skill']:+.4%})"
            )
    print(f"\nĐã ghi: {out}")
    print(json.dumps({"beats_baseline": int(frame["beats_baseline"].sum()), "total": len(frame)}))


if __name__ == "__main__":
    main()
