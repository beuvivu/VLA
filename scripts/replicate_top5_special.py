"""Kiểm lặp lại: Top-5 Đặc Biệt của mô hình mới trên hai khối 1 000 kỳ liền nhau.

Chạy:  PYTHONPATH=src python3 scripts/replicate_top5_special.py

Cùng mã, cùng luật với ``benchmark_probability_models.py``: học lại mỗi 50 kỳ,
loại các kỳ ngay sau một quãng nghỉ. Ghi
``data/research/model_overhaul/top5_replication.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vla.backtest import evaluator, walk_forward  # noqa: E402
from vla.features.engineer import build_features, load_history  # noqa: E402
from vla.models.bayesian_lgb import BayesianLGBModel  # noqa: E402

TESTS_READ = 30  # 5 mô hình × 3 mức K × 2 kiểu, đọc sau khi chạy


def main() -> None:
    history = load_history(ROOT / "data")
    T = len(history)
    feats = build_features(history, "de")
    hit = history.hits("de")
    dates = pd.to_datetime(list(history.dates))
    blocks = {}
    for label, lo, hi in (("1000_ky_cuoi", T - 1000, T - 1), ("1000_ky_truoc_do", T - 2000, T - 1001)):
        res = walk_forward.run(lambda: BayesianLGBModel("de"), feats.X, hit, lo, hi, refit_every=50)
        keep = np.asarray((dates[res.targets] - dates[res.targets - 1]).days == 1)
        got = (evaluator.top_k(res.probs, 5) == history.special[res.targets][:, None]).any(axis=1)[keep]
        n, x = int(got.size), int(got.sum())
        p = float(binom.sf(x - 1, n, 0.05))
        blocks[label] = {
            "first_target": history.dates[lo], "last_target": history.dates[hi],
            "scored": n, "hits": x, "rate": x / n, "p_one_sided": p,
            "p_bonferroni": min(1.0, TESTS_READ * p),
            "halves": [float(got[: n // 2].mean()), float(got[n // 2 :].mean())],
        }
        print(label, blocks[label], flush=True)
    out = ROOT / "data" / "research" / "model_overhaul" / "top5_replication.json"
    out.write_text(json.dumps(blocks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {out}")


if __name__ == "__main__":
    main()
