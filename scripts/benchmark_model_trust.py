"""Đo ngoài mẫu các luật ``model_trust`` của thành phần ML production.

Walk-forward trên ``--last`` kỳ cuối (học lại mỗi ``--refit-every`` kỳ) bằng
bản tái dựng ``ProductionMLModel``. Mỗi lần học ghi xác suất THÔ và kỹ năng
thẩm định, nên mọi luật trust được chấm trên CÙNG một bộ dự báo thô mà không
phải học lại. Kỳ ngay sau quãng nghỉ (Tết) bị loại như trong benchmark chính.

Luật quyết định chốt TRƯỚC khi đo (03-10-2026): chỉ đổi khi luật mới không kém
luật hiện hành ở cả hai chế độ và thắng với z ≥ 2 ở ít nhất một chế độ.

    PYTHONPATH=src python3 scripts/benchmark_model_trust.py --last 1000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vla.backtest import evaluator, walk_forward  # noqa: E402
from vla.backtest.production_ml import ProductionMLModel  # noqa: E402
from vla.features.engineer import History, load_history  # noqa: E402

OUT = ROOT / "data" / "research" / "model_overhaul" / "trust_floor.json"

RULES = {
    "san_035": lambda s: np.clip(0.35 + 20.0 * np.maximum(0.0, s), 0.35, 1.0),
    "khong_san": lambda s: np.clip(20.0 * np.maximum(0.0, s), 0.0, 1.0),
    "san_0_khi_khong_ky_nang": lambda s: np.where(s > 0, np.clip(0.35 + 20.0 * s, 0.35, 1.0), 0.0),
    "hang_so_nen": lambda s: np.zeros_like(s),
    "mo_hinh_tho": lambda s: np.ones_like(s),
}
CURRENT, CANDIDATE = "san_035", "khong_san"


class RawRecorder(ProductionMLModel):
    """Phát xác suất thô (−1 ở số không có hàng) và ghi kỹ năng thẩm định từng lần học."""

    def __init__(self, mode: str, history: History):
        super().__init__(mode, history)
        self.blocks: list[tuple[int, float, float, float]] = []

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray:
        out = np.full((len(rows), 100), -1.0)
        for k, t in enumerate(rows):
            sel = self.row == t
            if sel.any():
                numbers = self.X.loc[sel, "number"].to_numpy(dtype=int)
                out[k, numbers] = self.clf.predict_proba(self.F[sel])[:, 1]
        self.blocks.append((len(rows), self.baseline, *self.val_skill))
        return out


def shrink(mode: str, raw: np.ndarray, base: np.ndarray, trust: np.ndarray) -> np.ndarray:
    t = trust[:, None]
    p = np.where(raw >= 0, t * raw + (1.0 - t) * base[:, None], base[:, None])
    return p / p.sum(axis=1, keepdims=True) if mode == "de" else p


def run_mode(mode: str, history: History, last: int, refit_every: int) -> dict:
    T = len(history)
    first, final = T - last, T - 1
    targets = np.arange(first, final + 1)
    dates = pd.to_datetime(list(history.dates))
    keep = np.asarray((dates[targets] - dates[targets - 1]).days == 1)
    hit = history.hits(mode)
    model = RawRecorder(mode, history)
    res = walk_forward.run(lambda: model, np.zeros((T, 100, 1), dtype=np.float32), hit, first, final,
                           refit_every=refit_every)
    base = np.concatenate([np.full(n, b) for n, b, _, _ in model.blocks])
    skill = np.concatenate([np.full(n, min(ll, br)) for n, _, ll, br in model.blocks])
    hits = (history.counts[targets] > 0).astype(float) if mode == "loto" else np.eye(100)[history.special[targets]]
    ref = evaluator.daily_logloss(mode, evaluator.cumulative_reference(mode, hit, targets), hits)[keep]

    losses, rules = {}, {}
    for name, rule in RULES.items():
        losses[name] = evaluator.daily_logloss(mode, shrink(mode, res.probs, base, rule(skill)), hits)[keep]
        rules[name] = {"mean_trust": float(rule(skill).mean()), "logloss": float(losses[name].mean()),
                       "vs_constant": evaluator.paired(losses[name], ref)}
    half = int(keep.sum()) // 2
    cand, cur = losses[CANDIDATE], losses[CURRENT]
    return {
        "days": int(keep.sum()),
        "first_target": history.dates[first],
        "last_target": history.dates[final],
        "refits": len(model.blocks),
        "validation_skill": {"min": float(skill.min()), "max": float(skill.max()),
                             "refits_with_skill": int(sum(min(ll, br) > 0 for _, _, ll, br in model.blocks))},
        "rules": rules,
        "candidate_vs_current": evaluator.paired(cand, cur),
        "candidate_vs_current_halves": [evaluator.paired(cand[:half], cur[:half]),
                                        evaluator.paired(cand[half:], cur[half:])],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--last", type=int, default=1000)
    ap.add_argument("--refit-every", type=int, default=50)
    args = ap.parse_args()
    history = load_history(Path(args.data_dir))
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "last": args.last, "refit_every": args.refit_every, "current": CURRENT, "candidate": CANDIDATE}
    for mode in ("loto", "de"):
        report[mode] = run_mode(mode, history, args.last, args.refit_every)
        d = report[mode]["candidate_vs_current"]
        print(f"[{mode}] {CANDIDATE} so với {CURRENT}: z = {d['z']:+.2f}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {OUT}")


if __name__ == "__main__":
    main()
