"""Sinh lại cột đối chứng đường cơ sở cho các dòng lịch sử đánh giá đã có.

``prob_eval_history`` chỉ ghi ``baseline_logloss``/``baseline_brier``/
``logloss_skill``/``brier_skill`` cho những ngày nó chấm từ nay về sau. 219 dòng
lịch sử cũ vì thế trống, khiến trang Chất lượng mô hình chưa hiện cột kỹ năng và
cổng ``check_baseline_skill`` còn bỏ qua cho tới khi tích đủ cửa sổ.

Không cần chờ. Đường cơ sở là **hằng số**: điểm của nó phụ thuộc duy nhất vào
nhãn kết quả của ngày đó, không phụ thuộc artifact dự đoán. Nhãn đó nằm sẵn
trong ``data/history/pred_{mode}.csv`` cho cả 219 ngày, nên baseline tính lại
được đúng bằng giá trị mà pipeline sẽ ghi nếu nó đã có mặt từ đầu — dùng đúng
các hàm đo của mô hình, nên hai con số so sánh trực tiếp được.

Điều kiện tính: ngày phải có đủ 100 số 0–99, nhãn ``y`` chỉ nhận 0/1, và với ĐB
phải có đúng một nhãn dương. Ngày không đạt bị bỏ trống chứ không đoán bừa.

Một cái bẫy riêng với Brier ĐB: ``categorical_brier`` từng dùng ``mean`` thay vì
``sum``, nên các dòng ghi trước bản sửa nhỏ hơn quy ước hiện hành đúng 100 lần.
Đem baseline tính theo quy ước mới chia cho điểm mô hình theo quy ước cũ sẽ cho
kỹ năng ~+99% — mô hình trông vượt trội ngoạn mục vì lệch đơn vị, đúng loại tín
hiệu giả mà lớp đối chứng này sinh ra để chặn. :func:`brier_is_comparable` phát
hiện việc đó bằng một bất biến toán học thay vì mốc ngày cứng.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ensemble_utils import (
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    skill_score,
)
from xsmb_domain import baseline_rate

BASELINE_COLUMNS = (
    "baseline_logloss",
    "baseline_brier",
    "logloss_skill",
    "brier_skill",
)


def load_labels(history_path: Path) -> dict[str, np.ndarray]:
    """Trả về nhãn 0/1 theo thứ tự số 0–99 cho mỗi ngày hợp lệ."""
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
        ordered = sub.assign(_n=numbers.astype(int)).sort_values("_n")
        yi = pd.to_numeric(ordered["y"]).to_numpy(dtype=float)
        if not np.all(np.isin(yi, [0.0, 1.0])):
            continue
        labels[str(day)] = yi.astype(int)
    return labels


def brier_is_comparable(mode: str, logloss: float, brier: float) -> bool:
    """Điểm Brier đã lưu có cùng quy ước với baseline hiện hành không.

    Với ĐB, logloss đã lưu xác định xác suất mà mô hình đặt lên số trúng:
    ``p = exp(-logloss)``. Theo quy ước ``sum`` hiện hành, riêng số hạng của số
    trúng đã là ``(1 - p)^2``, nên Brier bắt buộc ``>= (1 - p)^2``. Điểm ghi theo
    quy ước ``mean`` cũ nhỏ hơn 100 lần nên rơi thẳng xuống dưới cận đó và bị
    loại — không cần biết nó được ghi ngày nào.

    Lô tô dùng ``bernoulli_brier`` (trung bình trên 100 biên) và chưa từng đổi
    quy ước, nên luôn so sánh được.
    """
    if mode != "de":
        return True
    if not np.isfinite(logloss) or not np.isfinite(brier):
        return False
    winner = float(np.exp(-logloss))
    lower_bound = (1.0 - winner) ** 2
    return brier >= lower_bound * (1.0 - 1e-6)


def baseline_metrics(mode: str, y: np.ndarray) -> tuple[float, float] | None:
    """Điểm logloss/Brier của đường cơ sở hằng số trên nhãn của một ngày."""
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
    """Điền cột đối chứng cho các dòng còn trống. Trả về (bảng, số dòng, ngày bỏ)."""
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
            skipped.append(f"{mode} {day}: hợp đồng nhãn ĐB không hợp lệ")
            continue

        base_ll, base_br = metrics
        model_ll = pd.to_numeric(row["logloss"], errors="coerce")
        model_br = pd.to_numeric(row["brier"], errors="coerce")
        if pd.isna(model_ll) or pd.isna(model_br):
            skipped.append(f"{mode} {day}: dòng thiếu điểm mô hình")
            continue

        out.at[position, "baseline_logloss"] = base_ll
        out.at[position, "logloss_skill"] = skill_score(float(model_ll), base_ll)

        # Chỉ chấm Brier khi hai bên cùng quy ước. Bỏ trống trung thực hơn nhiều
        # so với một con số +99% do lệch đơn vị.
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
    parser.add_argument("--history", default="data/prob_eval/ensemble_history.csv")
    parser.add_argument("--history-dir", default="data/history")
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

    result.sort_values(["mode", "target_date"], inplace=True)
    result.to_csv(path, index=False)
    print(f"[OK] đã ghi {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
