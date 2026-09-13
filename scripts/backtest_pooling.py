"""Walk-forward so cách HỢP tín hiệu, trên dữ liệu thật.

Đây là thước đo cho toàn bộ đợt nâng cấp kiến trúc. Mọi thay đổi cách hợp tín
hiệu đều phải qua đây, và thay đổi nào không nâng được biên tách thì bị hoàn
tác — đó là ràng buộc do chính đề bài đặt ra.

Đo trên các thành phần của TẦNG 2 (``statistical_signal``) vì chúng tính lại
được cho mọi kỳ trong lịch sử, khác với các thành phần tầng trên vốn chỉ còn
ảnh chụp của kỳ mới nhất. Tầng 2 cũng chính là một trong bốn tầng trộn cần sửa,
nên kết quả ở đây áp dụng trực tiếp.

Chạy:
    PYTHONPATH=src python3 scripts/backtest_pooling.py --eval-days 600
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opinion_pool import PoolParams, apply_pool, fit_pool  # noqa: E402
from statistical_signal import _eb_posterior, _exp_weights  # noqa: E402

#: Trọng số ĐANG DÙNG ở tầng 2, đặt tay: 0,55·ewm + 0,25·weekday + 0,20·p90.
PRODUCTION_WEIGHTS = np.array([0.55, 0.25, 0.20])
COMPONENT_NAMES = ("ewm", "weekday", "p90")


def _components(hit: np.ndarray, dates: pd.Series, t: int, half_life: int) -> np.ndarray:
    """Ba thành phần của tầng 2, tính CHỈ từ [0, t) — không nhìn kỳ t."""
    past = hit[:t]
    n = past.shape[0]
    w = _exp_weights(n, half_life)
    ewm = _eb_posterior((past * w[:, None]).sum(axis=0), float(w.sum()), None)

    target_weekday = int(pd.Timestamp(dates.iloc[t]).weekday())
    mask = np.array([pd.Timestamp(d).weekday() == target_weekday for d in dates.iloc[:t]])
    wk = past[mask]
    weekday = _eb_posterior(
        wk.sum(axis=0) if len(wk) else np.zeros(100), float(len(wk)), None
    )

    window = past[-min(90, n):]
    p90 = _eb_posterior(window.sum(axis=0), float(len(window)), None)
    return np.vstack([ewm, weekday, p90])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eval-days", type=int, default=600)
    ap.add_argument("--half-life", type=int, default=45)
    ap.add_argument("--holdout", type=float, default=0.30)
    ap.add_argument(
        "--inject-lift", type=float, default=0.0,
        help="Tiêm tín hiệu: nâng tỉ lệ của một con lên (nền × (1 + lift)).",
    )
    ap.add_argument("--inject-number", type=int, default=42)
    args = ap.parse_args()

    sparse = pd.read_json(ROOT / "data" / "xsmb-sparse.json")
    sparse["date"] = pd.to_datetime(sparse["date"])
    sparse = sparse.sort_values("date").reset_index(drop=True)
    cols = [c for c in sparse.columns if c != "date"]
    hit = (sparse[cols].to_numpy(dtype=float) > 0).astype(float)
    dates = sparse["date"]

    if args.inject_lift > 0.0:
        # TIÊM TÍN HIỆU ĐÃ BIẾT.
        #
        # Trên dữ liệu thật, mọi cách hợp đều không phân biệt được vì không có
        # gì để hợp. Câu hỏi thật sự cần trả lời khác hẳn: NẾU có tín hiệu thì
        # kiến trúc nào GIỮ được nó, và giữ được bao nhiêu phần? Không tiêm thì
        # câu ấy không đo được, và ta chỉ đang so các cách làm mờ nhiễu.
        rng = np.random.default_rng(20260914)
        base = float(hit.mean())
        target = min(0.95, base * (1.0 + args.inject_lift))
        column = args.inject_number
        hit[:, column] = (rng.random(hit.shape[0]) < target).astype(float)
        print(f"[TIÊM] con {column:02d}: tỉ lệ {base:.4f} -> {target:.4f} "
              f"(+{args.inject_lift*100:.0f}% tương đối)\n")
    total = hit.shape[0]
    start = max(400, total - args.eval_days)

    print(f"{total} kỳ; chấm điểm {total - start} kỳ từ {dates.iloc[start].date()}")
    print("Mỗi kỳ: thành phần tính từ [0, t), nhãn là kỳ t. Không kỳ nào nhìn thấy tương lai.\n")

    cube, labels = [], []
    for t in range(start, total):
        cube.append(_components(hit, dates, t, args.half_life))
        labels.append(hit[t])
    cube = np.stack(cube)
    labels = np.stack(labels)

    split = int(round(len(cube) * (1.0 - args.holdout)))
    baseline_rate = float(labels[:split].mean())
    y_test = labels[split:]
    p_base = np.full_like(y_test, baseline_rate)
    b0 = float(np.mean((p_base - y_test) ** 2))

    def score(name: str, params: PoolParams) -> tuple[str, float, float, float]:
        p = np.vstack([apply_pool("loto", day, params) for day in cube[split:]])
        brier = float(np.mean((p - y_test) ** 2))
        # Biên tách: dải giá trị trung bình mỗi kỳ. Một phép hợp làm cùn tín
        # hiệu sẽ có biên tách nhỏ, kể cả khi Brier trông không tệ.
        edge = float(np.mean(p.max(axis=1) - p.min(axis=1)))
        return name, brier, 1.0 - brier / b0, edge

    rows = [
        score("trộn số học (0,55/0,25/0,20 — ĐANG DÙNG)",
              PoolParams("linear", tuple(PRODUCTION_WEIGHTS), baseline_rate)),
        score("trộn số học (đều)", PoolParams("linear", (1, 1, 1), baseline_rate)),
    ]
    for s in (0.3, 0.5, 1.0, 1.5, 2.0, 3.0):
        rows.append(score(f"log-odds s={s:g}",
                          PoolParams("log", tuple(PRODUCTION_WEIGHTS), baseline_rate, s)))

    fitted, audit = fit_pool("loto", cube, labels, PRODUCTION_WEIGHTS,
                             holdout_fraction=args.holdout)
    rows.append(score(f"CHỌN TỰ ĐỘNG -> {fitted.kind} s={fitted.sharpness:g}", fitted))

    print(f"Đường nền (hằng số {baseline_rate:.4f}): Brier {b0:.8f}, biên tách 0\n")
    print(f"{'phép hợp':46} {'Brier':>12} {'skill':>11} {'biên tách':>11}")
    print("-" * 84)
    for name, brier, skill, edge in sorted(rows, key=lambda r: r[1]):
        print(f"{name:46} {brier:12.8f} {skill:11.5f} {edge:11.5f}")

    print(f"\n{audit.describe()}")
    print("\nĐọc bảng: skill > 0 là hơn đường nền. 'Biên tách' là dải xác suất")
    print("trung bình mỗi kỳ — phép hợp làm cùn tín hiệu sẽ có biên tách nhỏ.")

    if args.inject_lift > 0.0:
        column = args.inject_number
        true_lift = baseline_rate * args.inject_lift
        print(f"\n{'=' * 84}")
        print(f"THU HỒI TÍN HIỆU — con {column:02d} được tiêm +{args.inject_lift*100:.0f}%")
        print(f"Mức nâng thật trên thang xác suất: {true_lift:+.5f}\n")
        print(f"{'phép hợp':46} {'nâng thu được':>15} {'% thu hồi':>11}")
        print("-" * 76)
        recovery = []
        for name, params in (
            ("trộn số học (0,55/0,25/0,20 — ĐANG DÙNG)",
             PoolParams("linear", tuple(PRODUCTION_WEIGHTS), baseline_rate)),
            *[(f"log-odds s={s:g}",
               PoolParams("log", tuple(PRODUCTION_WEIGHTS), baseline_rate, s))
              for s in (0.5, 0.7, 1.0, 1.5, 2.0, 3.0)],
            (f"CHỌN TỰ ĐỘNG -> {fitted.kind} s={fitted.sharpness:g}", fitted),
        ):
            p = np.vstack([apply_pool("loto", day, params) for day in cube[split:]])
            others = np.delete(p, column, axis=1).mean(axis=1)
            gained = float(np.mean(p[:, column] - others))
            recovery.append((name, gained, gained / true_lift * 100.0))
        for name, gained, pct in sorted(recovery, key=lambda r: -r[1]):
            print(f"{name:46} {gained:+15.5f} {pct:10.1f}%")
        print("\nĐây mới là thước đo quyết định: phép hợp nào GIỮ được nhiều tín hiệu")
        print("nhất khi tín hiệu thật sự tồn tại.")


if __name__ == "__main__":
    main()
