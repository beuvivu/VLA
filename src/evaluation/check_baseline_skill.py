from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DEFAULT_THRESHOLD = -0.10
DEFAULT_WINDOW = 7
REQUIRED_COLUMNS = ("mode", "target_date", "logloss", "baseline_logloss")


@dataclass(frozen=True)
class SkillCheck:

    mode: str
    days: int
    logloss: float
    baseline_logloss: float
    skill: float
    threshold: float

    @property
    def failed(self) -> bool:
        return self.skill < self.threshold

    def describe(self) -> str:
        flag = "LỖI " if self.failed else "OK  "
        return (
            f"{flag}{self.mode:<5} {self.days:>3} ngày gần nhất: "
            f"logloss={self.logloss:.6f} baseline={self.baseline_logloss:.6f} "
            f"kỹ năng={self.skill:+.2%} (ngưỡng {self.threshold:+.0%})"
        )


def evaluate_history(
    frame: pd.DataFrame,
    *,
    window: int = DEFAULT_WINDOW,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[SkillCheck]:
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(
            "lịch sử đánh giá thiếu cột đối chứng baseline: " + ", ".join(missing)
        )

    checks: list[SkillCheck] = []
    for mode, group in frame.groupby("mode"):
        rows = group.sort_values("target_date", kind="stable").tail(window)
        rows = rows[
            pd.to_numeric(rows["logloss"], errors="coerce").notna()
            & pd.to_numeric(rows["baseline_logloss"], errors="coerce").notna()
        ]
        if rows.empty:
            continue
        model = float(pd.to_numeric(rows["logloss"]).mean())
        base = float(pd.to_numeric(rows["baseline_logloss"]).mean())
        skill = (base - model) / base if base > 0 else 0.0
        checks.append(
            SkillCheck(
                mode=str(mode),
                days=len(rows),
                logloss=model,
                baseline_logloss=base,
                skill=skill,
                threshold=threshold,
            )
        )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Báo động khi mô hình sản xuất tệ hơn đường cơ sở quá ngưỡng."
    )
    parser.add_argument("--history", default="data/evaluation/prob_eval/ensemble_history.csv")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--require-baseline",
        action="store_true",
        help="Thất bại nếu lịch sử chưa có cột baseline (thay vì bỏ qua).",
    )
    args = parser.parse_args()

    path = Path(args.history)
    if not path.exists() or path.stat().st_size == 0:
        print(f"[BỎ QUA] chưa có lịch sử đánh giá: {path}")
        return 1 if args.require_baseline else 0

    frame = pd.read_csv(path)
    try:
        checks = evaluate_history(
            frame, window=args.window, threshold=args.threshold
        )
    except ValueError as exc:
        print(f"[BỎ QUA] {exc}")
        return 1 if args.require_baseline else 0

    if not checks:
        print("[BỎ QUA] chưa có ngày nào chấm được điểm kỹ năng")
        return 1 if args.require_baseline else 0

    for check in checks:
        print(check.describe())

    failed = [c for c in checks if c.failed]
    if failed:
        print(
            "\n[LỖI] mô hình tệ hơn đường cơ sở quá ngưỡng ở: "
            + ", ".join(c.mode for c in failed)
            + "\nĐây là dấu hiệu hồi quy nghiêm trọng, không phải dao động thường."
        )
        return 1

    print("\n[OK] mọi chế độ đều trong ngưỡng cho phép so với đường cơ sở.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
