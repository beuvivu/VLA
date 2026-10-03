"""Mô hình ba tầng: tiên nghiệm Bayes → LightGBM tăng cường từ tiên nghiệm → hiệu chỉnh.

Tầng 1 — ``DirichletPrior``. Đặc Biệt là một biến phân loại 100 lớp: tiên
nghiệm Dirichlet đối xứng nồng độ ``α`` cập nhật bằng số đếm có suy giảm
``2^{-(t-s)/h}`` cho xác suất hậu nghiệm dự báo ``(α/100 + S_n)/(α + W)``. LOTO
là 100 biến Bernoulli: tiên nghiệm Beta trung bình ``μ0`` (tỉ lệ nền tích luỹ),
độ mạnh ``α``: ``(α·μ0 + S_n)/(α + W)``. ``(h, α)`` chọn bằng logloss trên khối
huấn luyện — tức Bayes thực nghiệm.

Tầng 2 — LightGBM nhị phân trên từng cặp (kỳ, con số), khởi đầu từ ``logit``
của tiên nghiệm (``init_score``): cây chỉ học PHẦN DƯ so với tiên nghiệm, nên
khi đặc trưng không mang tín hiệu, dừng sớm giữ mô hình ở đúng tiên nghiệm.
Hàm mất mát mặc định là logloss (quy tắc chấm điểm đúng); focal loss có sẵn
nhưng làm méo xác suất, nên chỉ dùng khi có tầng 3 phía sau.

Tầng 3 — hiệu chỉnh Platt hoặc isotonic trên khối thời gian RIÊNG nằm sau khối
huấn luyện. Đặc Biệt được chuẩn hoá lại để mỗi kỳ tổng xác suất bằng 1.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import lightgbm as lgb
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from vla.features.engineer import decayed_sum

Mode = Literal["loto", "de"]
EPS = 1e-6


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def normalize_rows(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, None)
    return p / p.sum(axis=1, keepdims=True)


def row_logloss(mode: Mode, p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Logloss từng kỳ: Bernoulli trung bình (LOTO) hoặc phân loại (Đặc Biệt)."""
    if mode == "de":
        q = normalize_rows(p)
        return -np.log(np.clip((q * y).sum(axis=1), EPS, 1.0))
    q = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q)).mean(axis=1)


# --------------------------------------------------------------------------
# Tầng 1
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DirichletPrior:
    mode: Mode
    half_life: float = np.inf
    alpha: float = 100.0

    def matrix(self, hit: np.ndarray) -> np.ndarray:
        """(T, 100): xác suất hậu nghiệm dự báo cho kỳ t+1 từ các kỳ ≤ t."""
        T = len(hit)
        S = decayed_sum(hit.astype(np.float64), self.half_life)
        W = decayed_sum(np.ones(T), self.half_life)[:, None]
        if self.mode == "de":
            return (self.alpha / 100.0 + S) / (self.alpha + W)
        mu0 = (np.cumsum(hit.mean(axis=1)) / np.arange(1, T + 1))[:, None]
        return (self.alpha * mu0 + S) / (self.alpha + W)

    @classmethod
    def fit(
        cls,
        mode: Mode,
        hit: np.ndarray,
        rows: np.ndarray,
        half_lives: tuple[float, ...] = (30.0, 90.0, 180.0, 365.0, 730.0, np.inf),
        alphas: tuple[float, ...] = (10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0),
    ) -> "DirichletPrior":
        """Chọn (h, α) theo logloss trên các hàng ``rows`` (nhãn = kỳ t+1)."""
        y = hit[rows + 1].astype(np.float64)
        best, best_loss = cls(mode), np.inf
        for h in half_lives:
            for a in alphas:
                cand = cls(mode, float(h), float(a))
                loss = float(row_logloss(mode, cand.matrix(hit)[rows], y).mean())
                if loss < best_loss:
                    best, best_loss = cand, loss
        return best


# --------------------------------------------------------------------------
# Tầng 3
# --------------------------------------------------------------------------


class Calibrator:
    """Platt (hồi quy logistic trên logit) hoặc isotonic; ``none`` = đồng nhất."""

    def __init__(self, method: str = "platt"):
        if method not in {"platt", "isotonic", "none"}:
            raise ValueError(f"phương pháp hiệu chỉnh lạ: {method}")
        self.method = method
        self._model = None

    def fit(self, p: np.ndarray, y: np.ndarray) -> "Calibrator":
        p, y = p.reshape(-1), y.reshape(-1)
        if self.method == "platt":
            self._model = LogisticRegression(C=1e6, max_iter=1000).fit(logit(p)[:, None], y)
        elif self.method == "isotonic":
            self._model = IsotonicRegression(y_min=EPS, y_max=1 - EPS, out_of_bounds="clip").fit(p, y)
        return self

    def transform(self, p: np.ndarray) -> np.ndarray:
        shape = p.shape
        flat = p.reshape(-1)
        if self.method == "platt":
            out = self._model.predict_proba(logit(flat)[:, None])[:, 1]
        elif self.method == "isotonic":
            out = self._model.predict(flat)
        else:
            out = flat
        return np.clip(out, EPS, 1 - EPS).reshape(shape)


# --------------------------------------------------------------------------
# Tầng 2 + ghép
# --------------------------------------------------------------------------


def focal_loss(z: np.ndarray, y: np.ndarray, gamma: float, alpha: float) -> np.ndarray:
    """Focal loss nhị phân theo điểm thô ``z``: ``-w·(1-pt)^γ·log(pt)``."""
    p = np.clip(sigmoid(z), EPS, 1 - EPS)
    pt = np.where(y > 0.5, p, 1 - p)
    w = np.where(y > 0.5, alpha, 1 - alpha)
    return -w * (1 - pt) ** gamma * np.log(pt)


def focal_objective(gamma: float, alpha: float, step: float = 1e-3):
    """Mục tiêu tuỳ biến cho LightGBM: đạo hàm bậc 1, 2 bằng sai phân trung tâm.

    Sai phân trên một hàm vô hướng trơn là chính xác tới ``O(step²)`` và không
    có rủi ro gõ sai công thức giải tích; đạo hàm bậc 2 bị chặn dưới để LightGBM
    không chia cho số âm ở vùng lõm của focal loss.
    """

    def objective(preds: np.ndarray, data: lgb.Dataset) -> tuple[np.ndarray, np.ndarray]:
        y = data.get_label()
        up = focal_loss(preds + step, y, gamma, alpha)
        mid = focal_loss(preds, y, gamma, alpha)
        down = focal_loss(preds - step, y, gamma, alpha)
        grad = (up - down) / (2 * step)
        hess = np.maximum((up - 2 * mid + down) / (step * step), 1e-6)
        return grad, hess

    return objective


def _raw_logloss(preds: np.ndarray, data: lgb.Dataset) -> tuple[str, float, bool]:
    y = data.get_label()
    p = np.clip(sigmoid(preds), EPS, 1 - EPS)
    return "logloss", float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), False


@dataclass(frozen=True)
class ModelConfig:
    calibration: str = "platt"
    loss: str = "logloss"  # hoặc "focal"
    focal_gamma: float = 1.0
    focal_alpha: float = 0.5
    calib_rows: int = 300  # khối hiệu chỉnh: ngần này kỳ cuối của dữ liệu huấn luyện
    valid_share: float = 0.15  # phần cuối khối học dành cho dừng sớm
    learning_rate: float = 0.03
    num_leaves: int = 15
    #: Chọn 500 bằng kiểm độ nhạy trên dữ liệu TỔNG HỢP (2000 không thấy tín hiệu
    #: LOTO cài sẵn, z=1,1; 500 thấy, z=3,0), TRƯỚC khi chạy so sánh trên dữ liệu thật.
    min_data_in_leaf: int = 500
    lambda_l2: float = 10.0
    max_rounds: int = 400
    early_stopping: int = 30
    use_lgb: bool = True
    seed: int = 7
    threads: int = 4


class BayesianLGBModel:
    """Tiên nghiệm Bayes + LightGBM phần dư + hiệu chỉnh. Huấn luyện theo hàng kỳ."""

    def __init__(self, mode: Mode, config: ModelConfig | None = None):
        self.mode = mode
        self.config = config or ModelConfig()
        self.prior: DirichletPrior | None = None
        self.booster: lgb.Booster | None = None
        self.calibrator: Calibrator | None = None
        self.rounds = 0

    # Mỗi hàng t sinh 100 dòng (t, n). Hàng ``rows`` phải đã có nhãn.
    def _design(self, X: np.ndarray, prior: np.ndarray, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        feats = X[rows].reshape(len(rows) * 100, -1)
        base = logit(prior[rows]).reshape(-1)
        return np.column_stack([feats, base]).astype(np.float32), base

    def _raw(self, X: np.ndarray, prior: np.ndarray, rows: np.ndarray) -> np.ndarray:
        design, base = self._design(X, prior, rows)
        z = base.copy()
        if self.booster is not None and self.rounds > 0:
            z = z + self.booster.predict(design, num_iteration=self.rounds, raw_score=True)
        return sigmoid(z).reshape(len(rows), 100)

    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> "BayesianLGBModel":
        cfg = self.config
        rows = np.asarray(rows, dtype=np.int64)
        if rows.size and rows.max() + 1 >= len(hit):
            raise ValueError("hàng huấn luyện phải đã có nhãn (kỳ t+1 đã quay)")
        n_cal = min(cfg.calib_rows, max(len(rows) // 5, 1))
        learn, cal = rows[:-n_cal], rows[-n_cal:]
        self.prior = DirichletPrior.fit(self.mode, hit, learn)
        prior = self.prior.matrix(hit)

        if cfg.use_lgb and len(learn) >= 50:
            n_valid = max(int(len(learn) * cfg.valid_share), 10)
            tr, va = learn[:-n_valid], learn[-n_valid:]
            Xtr, btr = self._design(X, prior, tr)
            Xva, bva = self._design(X, prior, va)
            ytr = hit[tr + 1].reshape(-1).astype(np.float32)
            yva = hit[va + 1].reshape(-1).astype(np.float32)
            params = {
                "learning_rate": cfg.learning_rate,
                "num_leaves": cfg.num_leaves,
                "min_data_in_leaf": cfg.min_data_in_leaf,
                "lambda_l2": cfg.lambda_l2,
                "feature_fraction": 0.8,
                "bagging_fraction": 0.8,
                "bagging_freq": 1,
                "seed": cfg.seed,
                "num_threads": cfg.threads,
                "verbosity": -1,
                "deterministic": True,
                "force_col_wise": True,
            }
            feval = None
            if cfg.loss == "focal":
                # Mục tiêu tuỳ biến: LightGBM trả điểm THÔ cho phép đo, nên dừng
                # sớm theo logloss tự tính trên sigmoid của điểm ấy.
                params["objective"] = focal_objective(cfg.focal_gamma, cfg.focal_alpha)
                params["metric"] = "None"
                feval = _raw_logloss
            else:
                params["objective"] = "binary"
                params["metric"] = "binary_logloss"
            dtr = lgb.Dataset(Xtr, ytr, init_score=btr, free_raw_data=True)
            dva = lgb.Dataset(Xva, yva, init_score=bva, reference=dtr)
            booster = lgb.train(
                params,
                dtr,
                num_boost_round=cfg.max_rounds,
                valid_sets=[dva],
                feval=feval,
                callbacks=[lgb.early_stopping(cfg.early_stopping, verbose=False)],
            )
            self.booster, self.rounds = booster, int(booster.best_iteration or 0)

        self.calibrator = Calibrator(cfg.calibration)
        p_cal = self._raw(X, prior, cal)
        self.calibrator.fit(p_cal, hit[cal + 1].astype(np.float64))
        return self

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray:
        rows = np.asarray(rows, dtype=np.int64)
        prior = self.prior.matrix(hit)
        p = self.calibrator.transform(self._raw(X, prior, rows))
        return normalize_rows(p) if self.mode == "de" else p


class PriorOnlyModel(BayesianLGBModel):
    """Chỉ tầng 1 (+ hiệu chỉnh), để đo phần đóng góp của LightGBM."""

    def __init__(self, mode: Mode, config: ModelConfig | None = None):
        super().__init__(mode, replace(config or ModelConfig(), use_lgb=False))


class ConstantModel:
    """Dự báo hằng số: tỉ lệ nền tích luỹ (LOTO) hoặc 1/100 (Đặc Biệt)."""

    def __init__(self, mode: Mode):
        self.mode = mode

    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> "ConstantModel":
        self.rate = float(hit[np.asarray(rows) + 1].mean()) if len(rows) else 0.01
        return self

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray:
        value = 0.01 if self.mode == "de" else self.rate
        return np.full((len(rows), 100), value)
