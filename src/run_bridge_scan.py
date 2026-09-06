"""Quét họ cầu ghép chéo ngày và ghi báo cáo sàng lọc.

Đầu ra là một báo cáo nghiên cứu, KHÔNG phải đầu vào của sản xuất. Chỉ những
đường cầu qua được cổng trong :mod:`bridges.firewall` mới đủ điều kiện đi tiếp,
và cho tới nay trên dữ liệu thật của kho chưa có đường nào qua.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from bridges import BridgeScanner, DigitTensor
from bridges.firewall import DEFAULT_PERMUTATIONS, DEFAULT_Q_VALUE, FirewallGate
from bridges.spec import TARGET_TYPES

DEFAULT_STREAK = 5


def _json_safe(value: object) -> object:
    """NaN không phải JSON hợp lệ; ghi null để tệp đọc được bằng mọi trình phân tích."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def run(
    raw_path: Path,
    out_dir: Path,
    *,
    max_span: int,
    q_value: float,
    permutations: int,
    min_streak: int = DEFAULT_STREAK,
) -> dict[str, object]:
    tensor = DigitTensor.from_raw(pd.read_csv(raw_path))
    gate = FirewallGate(q_value=q_value, permutations=permutations)

    summary: dict[str, object] = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "days": tensor.n_days,
        "positions": tensor.n_positions,
        "max_span": max_span,
        "q_value": q_value,
        "modes": {},
    }
    out_dir.mkdir(parents=True, exist_ok=True)

    for target_type in TARGET_TYPES:
        scanner = BridgeScanner(max_span=max_span)
        result = scanner.scan(tensor, target_type=target_type)
        survivors = gate.screen(result, tensor, scanner)

        # Con số "chạy dài mà không sống sót" là kết quả chính của báo cáo:
        # nó đo trực tiếp lượng phát hiện giả mà một bộ quét không có cổng
        # kiểm định sẽ phát ra.
        # Kỹ năng lớn nhất của cả họ tính được miễn phí từ bảng kết quả, và nó
        # trả lời trực tiếp câu "có tín hiệu nào không" ngay cả khi cổng loại
        # sạch — nên luôn ghi, không phụ thuộc phép kiểm dịch vòng có chạy hay không.
        family_max_skill = float((result.frame["precision"] - result.frame["expected_rate"]).max())
        summary["modes"][target_type] = {
            "family_max_skill": family_max_skill,
            "hypotheses": result.n_hypotheses,
            "days_evaluated": result.n_days_evaluated,
            "baseline_single_bet": result.baseline,
            f"running_at_least_{min_streak}_unscreened": int(len(result.running(min_streak))),
            "survived_fdr": survivors.survived,
            "observed_max_skill": survivors.observed_max_skill,
            "null_max_skill_p95": survivors.null_max_skill_p95,
            "reality_check_p_value": survivors.reality_check_p_value,
            "permutations": survivors.permutations,
            "verdict": survivors.describe(),
        }
        if not survivors.is_empty:
            survivors.bridges.to_csv(out_dir / f"bridge_survivors_{target_type}.csv", index=False)
        print(f"[{target_type}] {survivors.describe()}")

    (out_dir / "bridge_scan_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_safe).replace(
            "NaN", "null"
        ),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default="data/xsmb.csv")
    parser.add_argument("--out-dir", default="data/research")
    parser.add_argument("--max-span", type=int, default=3)
    parser.add_argument("--q-value", type=float, default=DEFAULT_Q_VALUE)
    parser.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    args = parser.parse_args()

    run(
        Path(args.raw),
        Path(args.out_dir),
        max_span=args.max_span,
        q_value=args.q_value,
        permutations=args.permutations,
    )


if __name__ == "__main__":
    main()
