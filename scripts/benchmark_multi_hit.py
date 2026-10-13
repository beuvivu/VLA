"""Lượt thử thứ hai cho "lô nhiều nháy": lớp vỏ dòng lệnh của ``src/multi_hit_benchmark.py``.

    python3 scripts/benchmark_multi_hit.py --until 2026-10-12 --power-check   # ~2 phút, 4 lõi
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from multi_hit_benchmark import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
