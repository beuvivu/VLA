"""Chạy bộ điều phối ba tác tử XSMB và ghi báo cáo tiến cứu."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from xsmb_agents import PredictiveEngine
from atomic_io import atomic_write_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--benchmark-last", type=int,
                        help="Chỉ kiểm hồi cứu N kỳ; không ghi sổ hoặc phát dự báo tiến cứu")
    args = parser.parse_args()
    if args.benchmark_last is not None:
        import pandas as pd
        from xsmb_agents.benchmark import walk_forward

        report = walk_forward(pd.read_csv(args.data_dir / "xsmb.csv", dtype=str),
                              last=args.benchmark_last, prediction_dir=args.data_dir / "predict")
        path = args.data_dir / "agents" / "benchmark.json"
        atomic_write_text(path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        print(f"[xsmb-agents] hồi cứu {args.benchmark_last} kỳ; không có kỳ tiến cứu được thêm")
        return 0
    report = PredictiveEngine().run(args.data_dir)
    print(f"[xsmb-agents] {report['target_date']}: {report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
