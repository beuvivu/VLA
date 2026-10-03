"""Mô hình ML đang chạy production, huấn luyện lại theo walk-forward để làm đối chứng.

Tái dựng đúng ``ml_train.train_one`` + ``ml_predict``: cùng bảng đặc trưng
(``ml_features.build_ml_table_from_history``), cùng cửa sổ 2 000 ngày, cùng
bốn khối thời gian (huấn luyện | hiệu chỉnh | chọn | thẩm định), cùng ba cấu
hình HistGradientBoosting + Platt, cùng độ tin ``model_trust`` co về tỉ lệ nền,
và Đặc Biệt được chuẩn hoá sau khi co. Chỉ khác: dữ liệu bị cắt tại mốc của
từng khối walk-forward.

Đây là thành phần ``ml`` — một trong năm thành phần của tổ hợp production. Tổ
hợp đầy đủ (cầu, thống kê, hai nhánh đường đi, xếp chồng) không tái dựng được
cho 1 000 kỳ trong thời gian hợp lý; nó được so trên các kỳ có sổ ghi
``data/prob_eval/ensemble_history.csv``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import ml_train
from ml_features import FeatureParams, build_ml_table_from_history
from vla.features.engineer import History
from xsmb_domain import PRIZE_FIELDS


def frames(history: History) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.DataFrame(history.values, columns=list(PRIZE_FIELDS))
    raw.insert(0, "date", pd.to_datetime(list(history.dates)))
    two = raw.copy()
    two[list(PRIZE_FIELDS)] = two[list(PRIZE_FIELDS)] % 100
    return raw, two


class ProductionMLModel:
    def __init__(self, mode: str, history: History, window_days: int = 2000):
        self.mode = mode
        self.window_days = window_days
        raw, two = frames(history)
        X, y = build_ml_table_from_history(mode, FeatureParams(), raw, two)
        index = {d: i for i, d in enumerate(pd.to_datetime(list(history.dates)))}
        self.row = X["date"].map(index).to_numpy(dtype=np.int64)  # hàng neo t của từng dòng
        self.X = X
        self.F = X[ml_train.FEATURE_COLUMNS].astype(np.float32).to_numpy()
        self.y = y.to_numpy(dtype=int)
        self.dates = pd.to_datetime(X["date"])

    def available_rows(self) -> set[int]:
        """Hàng neo có trong bảng production (bỏ các bước qua kỳ nghỉ Tết)."""
        return set(np.unique(self.row).tolist())

    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> "ProductionMLModel":
        last = int(np.max(rows))
        keep = self.row <= last
        days = pd.DatetimeIndex(sorted(self.dates[keep].unique()))
        if len(days) > self.window_days:
            keep &= (self.dates >= days[-self.window_days]).to_numpy()
            days = pd.DatetimeIndex(sorted(self.dates[keep].unique()))
        calib_start, select_start, val_start = ml_train._time_splits(days)
        d = self.dates
        tr = keep & (d < calib_start).to_numpy()
        ca = keep & ((d >= calib_start) & (d < select_start)).to_numpy()
        se = keep & ((d >= select_start) & (d < val_start)).to_numpy()
        va = keep & (d >= val_start).to_numpy()
        w_tr = ml_train._recency_weights(d[tr], half_life_days=365.0)
        w_ca = ml_train._recency_weights(d[ca], half_life_days=120.0)
        neg_ratio = 20 if self.mode == "de" else 10
        Xt, yt, wt = ml_train._downsample(self.F[tr], self.y[tr], w_tr, neg_ratio=neg_ratio, seed=42)
        best = None
        for cfg in ml_train._candidate_configs():
            clf = ml_train._fit_candidate(cfg, Xt, yt, wt, self.F[ca], self.y[ca], w_ca)
            brier, ll = ml_train._metrics(self.y[se], clf.predict_proba(self.F[se])[:, 1])
            score = ll + 0.25 * brier
            if best is None or score < best[0]:
                best = (score, clf)
        self.clf = best[1]
        brier, ll = ml_train._metrics(self.y[va], self.clf.predict_proba(self.F[va])[:, 1])
        pre_val = keep & (d < val_start).to_numpy()
        self.baseline = float(np.clip(self.y[pre_val].mean(), 1e-6, 1 - 1e-6))
        base_brier, base_ll = ml_train._metrics(self.y[va], np.full(int(va.sum()), self.baseline))
        ll_skill = 1.0 - ll / base_ll if base_ll > 0 else 0.0
        br_skill = 1.0 - brier / base_brier if base_brier > 0 else 0.0
        self.val_skill = (float(ll_skill), float(br_skill))
        self.trust = ml_train.model_trust(ll_skill, br_skill)
        return self

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray:
        out = np.full((len(rows), 100), self.baseline)
        for k, t in enumerate(rows):
            sel = self.row == t
            if not sel.any():
                continue  # kỳ sau Tết: hàng không có trong bảng production
            numbers = self.X.loc[sel, "number"].to_numpy(dtype=int)
            raw = self.clf.predict_proba(self.F[sel])[:, 1]
            out[k, numbers] = self.trust * raw + (1.0 - self.trust) * self.baseline
        if self.mode == "de":
            out = out / out.sum(axis=1, keepdims=True)
        return out
