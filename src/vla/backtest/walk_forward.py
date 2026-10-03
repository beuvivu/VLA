"""Walk-forward cửa sổ mở rộng: không K-fold, không nhìn trước.

Quy ước hàng/kỳ như ``vla.features.engineer``: hàng ``t`` dự báo kỳ ``t+1``.
Để dự báo một khối kỳ đích ``[s, s+R)``, mô hình được huấn luyện lại CHỈ trên
các hàng có nhãn đã biết trước kỳ ``s``, tức hàng ``t ≤ s-2`` (nhãn là kỳ
``t+1 ≤ s-1``). ``run`` kiểm điều đó cho từng khối và ném lỗi nếu vi phạm —
phép kiểm ``test_walk_forward_never_trains_on_a_draw_it_scores`` ghim luật này.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np


class Model(Protocol):
    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> "Model": ...

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray: ...


@dataclass
class WalkForwardResult:
    targets: np.ndarray  # chỉ số kỳ đích
    probs: np.ndarray  # (n, 100)
    refits: list[dict] = field(default_factory=list)


def run(
    factory: Callable[[], Model],
    X: np.ndarray,
    hit: np.ndarray,
    first_target: int,
    last_target: int,
    *,
    refit_every: int = 50,
    max_train_rows: int | None = None,
    on_refit: Callable[[dict], None] | None = None,
) -> WalkForwardResult:
    """Dự báo các kỳ đích ``first_target..last_target`` (bao gồm hai đầu).

    ``max_train_rows`` giới hạn cửa sổ (trượt) cho mô hình cần; mặc định mở rộng.
    """
    if first_target < 2 or last_target >= len(hit) or first_target > last_target:
        raise ValueError("khoảng kỳ đích không hợp lệ")
    targets = np.arange(first_target, last_target + 1)
    probs = np.zeros((len(targets), 100))
    refits: list[dict] = []
    for start in range(first_target, last_target + 1, refit_every):
        stop = min(start + refit_every, last_target + 1)
        train_rows = np.arange(0, start - 1)  # nhãn của hàng t là kỳ t+1 ≤ start-1
        if max_train_rows is not None:
            train_rows = train_rows[-max_train_rows:]
        if train_rows.size and train_rows.max() + 1 >= start:
            raise AssertionError("huấn luyện chạm vào kỳ đang chấm")
        model = factory().fit(X, hit, train_rows)
        pred_rows = np.arange(start - 1, stop - 1)  # hàng t dự báo kỳ t+1 ∈ [start, stop)
        probs[start - first_target : stop - first_target] = model.predict(X, hit, pred_rows)
        info = {"first_target": int(start), "last_target": int(stop - 1), "train_rows": int(train_rows.size),
                "last_label": int(train_rows.max() + 1) if train_rows.size else -1}
        for key in ("rounds",):
            if hasattr(model, key):
                info[key] = getattr(model, key)
        prior = getattr(model, "prior", None)
        if prior is not None:
            info["prior_half_life"] = float(prior.half_life)
            info["prior_alpha"] = float(prior.alpha)
        refits.append(info)
        if on_refit:
            on_refit(info)
    return WalkForwardResult(targets, probs, refits)
