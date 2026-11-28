from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ensemble.ensemble_utils import (
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    skill_score,
)
from core.xsmb_domain import baseline_rate

BASELINE_COLUMNS = (
    "baseline_logloss",
    "baseline_brier",
    "logloss_skill",
    "brier_skill",
)


def load_labels(history_path: Path) -> dict[str, np.ndarray]:
    if not history_path.exists() or history_path.stat().st_size == 0:
        return {}

    frame = pd.read_csv(history_path)
    if not {"target_date", "number", "y"}.issubset(frame.columns):
        return {}

    labels: dict[str, np.ndarray] = {}
    for day, sub in frame.groupby("target_date", sort=True):
        numbers = pd.to_numeric(sub["number"], errors="coerce")
        y = pd.to_numeric(sub["y"], errors="coerce")
        if len(sub) != 100 or numbers.isna().any() or y.isna().any():
            continue
        n = numbers.to_numpy(dtype=float)
        if not np.all(np.isfinite(n)) or not np.all(n == np.floor(n)):
            continue
        if set(numbers.astype(int).tolist()) != set(range(100)):
            continue
        ordered = sub.assign(_n=numbers.astype(int)).sort_values("_n", kind="stable")
        yi = pd.to_numeric(ordered["y"]).to_numpy(dtype=float)
        if not np.all(np.isin(yi, [0.0, 1.0])):
            continue
        labels[str(day)] = yi.astype(int)
    return labels


def brier_is_comparable(mode: str, logloss: float, brier: float) -> bool:
    if mode != "de":
        return True
    if not np.isfinite(logloss) or not np.isfinite(brier):
        return False
    winner = float(np.exp(-logloss))
    lower_bound = (1.0 - winner) ** 2
    return brier >= lower_bound * (1.0 - 1e-6)


def baseline_metrics(mode: str, y: np.ndarray) -> tuple[float, float] | None:
    const = np.full(len(y), baseline_rate(mode), dtype=np.float64)
    if mode == "de":
        if int(y.sum()) != 1:
            return None
        idx = int(np.argmax(y))
        return float(categorical_logloss(const, idx)), float(categorical_brier(const, idx))
    return float(bernoulli_logloss(const, y)), float(bernoulli_brier(const, y))


def backfill(
    history: pd.DataFrame,
    labels_by_mode: dict[str, dict[str, np.ndarray]],
    *,
    overwrite: bool = False,
) -> tuple[pd.DataFrame, int, list[str]]:
    out = history.copy()
    for column in BASELINE_COLUMNS:
        if column not in out.columns:
            out[column] = np.nan
        else:
            out[column] = pd.to_numeric(out[column], errors="coerce")

    filled = 0
    skipped: list[str] = []
    incomparable: list[str] = []
    for position, row in out.iterrows():
        mode = str(row["mode"])
        day = str(row["target_date"])
        if not overwrite and pd.notna(row.get("baseline_logloss")):
            continue

        y = labels_by_mode.get(mode, {}).get(day)
        if y is None:
            skipped.append(f"{mode} {day}: không có nhãn hợp lệ")
            continue
        metrics = baseline_metrics(mode, y)
        if metrics is None:
            skipped.append(f"{mode} {day}: hợp đồng nhãn Đặc Biệt không hợp lệ")
            continue

        base_ll, base_br = metrics
        model_ll = pd.to_numeric(row["logloss"], errors="coerce")
        model_br = pd.to_numeric(row["brier"], errors="coerce")
        if pd.isna(model_ll) or pd.isna(model_br):
            skipped.append(f"{mode} {day}: dòng thiếu điểm mô hình")
            continue

        out.at[position, "baseline_logloss"] = base_ll
        out.at[position, "logloss_skill"] = skill_score(float(model_ll), base_ll)

        if brier_is_comparable(mode, float(model_ll), float(model_br)):
            out.at[position, "baseline_brier"] = base_br
            out.at[position, "brier_skill"] = skill_score(float(model_br), base_br)
        else:
            incomparable.append(f"{mode} {day}")
        filled += 1

    if incomparable:
        print(
            f"[QUY ƯỚC] bỏ trống Brier ở {len(incomparable)} dòng ghi theo quy ước "
            f"cũ (mean thay vì sum); logloss không bị ảnh hưởng"
        )
    return out, filled, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sinh lại cột đối chứng đường cơ sở cho lịch sử đánh giá cũ."
    )
    parser.add_argument("--history", default="data/evaluation/prob_eval/ensemble_history.csv")
    parser.add_argument("--history-dir", default="data/evaluation/history")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Tính lại cả những dòng đã có sẵn cột đối chứng.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ báo cáo, không ghi.")
    args = parser.parse_args()

    path = Path(args.history)
    if not path.exists() or path.stat().st_size == 0:
        print(f"[BỎ QUA] chưa có lịch sử đánh giá: {path}")
        return 0

    history = pd.read_csv(path)
    labels_by_mode = {
        mode: load_labels(Path(args.history_dir) / f"pred_{mode}.csv")
        for mode in sorted(history["mode"].astype(str).unique())
    }
    for mode, labels in labels_by_mode.items():
        print(f"[NHÃN] {mode}: {len(labels)} ngày hợp lệ")

    result, filled, skipped = backfill(history, labels_by_mode, overwrite=args.overwrite)

    for note in skipped:
        print(f"[BỎ QUA] {note}")
    print(f"[KẾT QUẢ] điền {filled} dòng, bỏ {len(skipped)} dòng")

    for mode, group in result.groupby("mode"):
        skill = pd.to_numeric(group["logloss_skill"], errors="coerce").dropna()
        if skill.empty:
            continue
        print(
            f"[KỸ NĂNG] {mode}: {len(skill)} ngày, trung bình {skill.mean():+.2%}, "
            f"7 ngày cuối {skill.tail(7).mean():+.2%}"
        )

    if args.dry_run:
        print("[DRY-RUN] không ghi tệp")
        return 0

    result = result.sort_values(["mode", "target_date"])
    result.to_csv(path, index=False)
    print(f"[OK] đã ghi {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
