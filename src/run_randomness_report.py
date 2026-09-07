"""Chạy bộ kiểm định cấu trúc và phân tích công suất, ghi báo cáo tái lập được.

Đây là bước NÊN chạy trước khi đầu tư vào bất kỳ mô hình nào. Nó trả lời hai
câu hỏi mà mọi lựa chọn thuật toán phía sau đều phụ thuộc vào:

1. Dữ liệu có mang cấu trúc nào để học không?
2. Với lịch sử hiện có, hiệu ứng nhỏ nhất ta đủ sức phát hiện là bao nhiêu?

Câu hỏi thứ hai quan trọng hơn người ta thường nghĩ. Nếu ngưỡng phát hiện cao
hơn mọi hiệu ứng hợp lý trong miền, thì mọi kết quả dương tính sẽ là dương tính
giả, và việc so sánh mô hình trở thành so sánh may rủi.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from bridges import DigitTensor
from randomness_battery import (
    DEFAULT_SIMULATIONS,
    lag1_mutual_information,
    minimum_detectable_lift,
    run_battery,
    simulate_draws,
)
from xsmb_domain import baseline_rate

#: Số giả thuyết của các họ đã quét trong kho, dùng cho phân tích công suất.
HYPOTHESIS_FAMILIES: tuple[tuple[str, int], ...] = (
    ("một mô hình duy nhất", 1),
    ("20 đặc trưng đã xây", 20),
    ("một giả thuyết mỗi con số", 100),
    ("họ cầu ghép chéo ngày", 412_164),
)


def replication_check(counts: np.ndarray, *, simulations: int, seed: int) -> dict:
    """Tín hiệu ở nửa đầu lịch sử có lặp lại ở nửa sau không.

    Phép kiểm quyết định cho bất kỳ phát hiện nào. Cấu trúc thật thì lặp lại;
    nhiễu được khớp quá mức thì không. Đây là thứ phân biệt được hai trường hợp
    mà giá trị p trên toàn bộ dữ liệu không phân biệt nổi.
    """
    half = counts.shape[0] // 2
    rng = np.random.default_rng(seed)
    null = np.array(
        [lag1_mutual_information(simulate_draws(half, rng)) for _ in range(simulations)]
    )
    mean, sd = float(null.mean()), float(null.std(ddof=1))

    def z(value: float) -> float:
        return (value - mean) / sd if sd > 0 else 0.0

    first = lag1_mutual_information(counts[:half])
    second = lag1_mutual_information(counts[half:])
    return {
        "first_half_days": half,
        "second_half_days": int(counts.shape[0] - half),
        "first_half_z": z(first),
        "second_half_z": z(second),
        "replicates": bool(z(first) > 1.5 and z(second) > 1.5),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default="data/xsmb.csv")
    parser.add_argument("--out-dir", default="data/research")
    parser.add_argument("--simulations", type=int, default=DEFAULT_SIMULATIONS)
    parser.add_argument("--seed", type=int, default=20260906)
    args = parser.parse_args()

    tensor = DigitTensor.from_raw(pd.read_csv(args.raw))
    counts = tensor.loto_counts.astype(np.int16)

    results = run_battery(counts, simulations=args.simulations, seed=args.seed)
    base = baseline_rate("loto")
    power = {
        label: minimum_detectable_lift(tensor.n_days, baseline=base, hypotheses=count)
        for label, count in HYPOTHESIS_FAMILIES
    }
    replication = replication_check(
        counts, simulations=max(200, args.simulations // 5), seed=args.seed + 1
    )

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "days": tensor.n_days,
        "simulations": args.simulations,
        "baseline": base,
        "tests": [
            {
                "name": r.name,
                "question": r.question,
                "statistic": r.statistic,
                "null_mean": r.null_mean,
                "null_sd": r.null_sd,
                "z_score": r.z_score,
                "p_value": r.p_value,
                "significant_uncorrected": r.significant,
            }
            for r in results
        ],
        "significant_uncorrected": sum(r.significant for r in results),
        "bonferroni_threshold": 0.05 / len(results),
        "significant_after_bonferroni": sum(r.p_value < 0.05 / len(results) for r in results),
        "power": {
            label: {
                "hypotheses": pa.hypotheses,
                "detectable_lift": pa.detectable_lift,
                "relative_lift": pa.relative_lift,
            }
            for label, pa in power.items()
        },
        "replication": replication,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "randomness_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Bộ kiểm định cấu trúc — {tensor.n_days} kỳ, {args.simulations} mô phỏng\n")
    for r in results:
        print("  " + r.describe())
    print(
        f"\n  Bác bỏ ngẫu nhiên: {summary['significant_uncorrected']}/{len(results)} thô, "
        f"{summary['significant_after_bonferroni']}/{len(results)} sau Bonferroni"
    )
    print("\nCông suất — hiệu ứng nhỏ nhất phát hiện được:")
    for label, pa in power.items():
        print(f"  {label:<28} {pa.describe()}")
    print(
        f"\nLặp lại nửa sau: nửa đầu z={replication['first_half_z']:+.2f}, "
        f"nửa sau z={replication['second_half_z']:+.2f} → "
        f"{'CÓ lặp lại' if replication['replicates'] else 'KHÔNG lặp lại'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
