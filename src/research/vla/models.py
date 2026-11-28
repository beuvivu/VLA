from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from typing import Literal

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from core.xsmb_domain import PRIZE_FIELDS
from ml import ml_train
from ml.ml_features import FeatureParams, build_ml_table_from_history
from research.vla.features import History, decayed_sum

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
    if mode == "de":
        q = normalize_rows(p)
        return -np.log(np.clip((q * y).sum(axis=1), EPS, 1.0))
    q = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q)).mean(axis=1)


@dataclass(frozen=True)
class DirichletPrior:
    mode: Mode
    half_life: float = np.inf
    alpha: float = 100.0

    def matrix(self, hit: np.ndarray) -> np.ndarray:
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
    ) -> DirichletPrior:
        y = hit[rows + 1].astype(np.float64)
        best, best_loss = cls(mode), np.inf
        for h in half_lives:
            for a in alphas:
                cand = cls(mode, float(h), float(a))
                loss = float(row_logloss(mode, cand.matrix(hit)[rows], y).mean())
                if loss < best_loss:
                    best, best_loss = cand, loss
        return best


class Calibrator:

    def __init__(self, method: str = "platt"):
        if method not in {"platt", "isotonic", "none"}:
            raise ValueError(f"phương pháp hiệu chỉnh lạ: {method}")
        self.method = method
        self._model = None

    def fit(self, p: np.ndarray, y: np.ndarray) -> Calibrator:
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


def focal_loss(z: np.ndarray, y: np.ndarray, gamma: float, alpha: float) -> np.ndarray:
    p = np.clip(sigmoid(z), EPS, 1 - EPS)
    pt = np.where(y > 0.5, p, 1 - p)
    w = np.where(y > 0.5, alpha, 1 - alpha)
    return -w * (1 - pt) ** gamma * np.log(pt)


def focal_objective(gamma: float, alpha: float, step: float = 1e-3):

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
    loss: str = "logloss"
    focal_gamma: float = 1.0
    focal_alpha: float = 0.5
    calib_rows: int = 300
    valid_share: float = 0.15
    learning_rate: float = 0.03
    num_leaves: int = 15
    min_data_in_leaf: int = 500
    lambda_l2: float = 10.0
    max_rounds: int = 400
    early_stopping: int = 30
    use_lgb: bool = True
    seed: int = 7
    threads: int = 4


class BayesianLGBModel:

    def __init__(self, mode: Mode, config: ModelConfig | None = None):
        self.mode = mode
        self.config = config or ModelConfig()
        self.prior: DirichletPrior | None = None
        self.booster: lgb.Booster | None = None
        self.calibrator: Calibrator | None = None
        self.rounds = 0

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

    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> BayesianLGBModel:
        cfg = self.config
        rows = np.asarray(rows, dtype=np.int64)
        if rows.size and rows.max() + 1 >= len(hit):
            raise ValueError("hàng huấn luyện phải đã có nhãn (kỳ t+1 đã quay)")
        n_cal = min(cfg.calib_rows, max(len(rows) // 5, 1))
        learn, cal = rows[:-n_cal], rows[-n_cal:]
        use_lgb = cfg.use_lgb and len(learn) >= 50
        if use_lgb:
            n_valid = max(int(len(learn) * cfg.valid_share), 10)
            tr, va = learn[:-n_valid], learn[-n_valid:]
            self.prior = DirichletPrior.fit(self.mode, hit, tr)
        else:
            self.prior = DirichletPrior.fit(self.mode, hit, learn)
        prior = self.prior.matrix(hit)

        if use_lgb:
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

    def __init__(self, mode: Mode, config: ModelConfig | None = None):
        super().__init__(mode, replace(config or ModelConfig(), use_lgb=False))


class ConstantModel:

    def __init__(self, mode: Mode):
        self.mode = mode

    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> ConstantModel:
        return self

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray:
        from research.vla.backtest import cumulative_reference

        return cumulative_reference(self.mode, hit, np.asarray(rows, dtype=np.int64) + 1)


class FrequencyModel:

    def __init__(self, mode: Mode, window: int | None = None):
        if window is not None and window < 1:
            raise ValueError("window phải ≥ 1")
        self.mode = mode
        self.window = window

    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> FrequencyModel:
        return self

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray:
        rows = np.asarray(rows, dtype=np.int64)
        total = np.vstack([np.zeros((1, hit.shape[1])), np.cumsum(hit, axis=0, dtype=np.float64)])
        start = np.zeros_like(rows) if self.window is None else np.maximum(rows + 1 - self.window, 0)
        seen = total[rows + 1] - total[start]
        draws = (rows + 1 - start)[:, None].astype(np.float64)
        if self.mode == "de":
            return normalize_rows((seen + 1.0 / hit.shape[1]) / (draws + 1.0))
        base = (np.cumsum(hit.mean(axis=1)) / np.arange(1, len(hit) + 1))[rows][:, None]
        return np.clip((seen + base) / (draws + 1.0), EPS, 1 - EPS)


@dataclass(frozen=True)
class NeuralConfig:
    hidden: tuple[int, ...] = (32, 16)
    weight_decay: float = 1e-3
    epochs: int = 20
    batch_size: int = 512
    train_rows: int = 1000
    calib_rows: int = 300
    seed: int = 7


class NeuralModel:

    def __init__(self, mode: Mode, config: NeuralConfig | None = None):
        self.mode = mode
        self.config = config or NeuralConfig()
        self.prior: DirichletPrior | None = None
        self.scaler: StandardScaler | None = None
        self.network: MLPClassifier | None = None
        self.calibrator: Calibrator | None = None

    @staticmethod
    def _design(X: np.ndarray, prior: np.ndarray, rows: np.ndarray) -> np.ndarray:
        feats = X[rows].reshape(len(rows) * 100, -1)
        return np.column_stack([feats, logit(prior[rows]).reshape(-1)])

    def _raw(self, X: np.ndarray, prior: np.ndarray, rows: np.ndarray) -> np.ndarray:
        design = self.scaler.transform(self._design(X, prior, rows))
        return np.clip(self.network.predict_proba(design)[:, 1], EPS, 1 - EPS).reshape(len(rows), 100)

    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> NeuralModel:
        cfg = self.config
        rows = np.asarray(rows, dtype=np.int64)
        if rows.size and rows.max() + 1 >= len(hit):
            raise ValueError("hàng huấn luyện phải đã có nhãn (kỳ t+1 đã quay)")
        n_cal = min(cfg.calib_rows, max(len(rows) // 5, 1))
        learn, cal = rows[:-n_cal][-cfg.train_rows:], rows[-n_cal:]
        self.prior = DirichletPrior.fit(self.mode, hit, learn)
        prior = self.prior.matrix(hit)
        design = self._design(X, prior, learn)
        self.scaler = StandardScaler().fit(design)
        self.network = MLPClassifier(
            hidden_layer_sizes=cfg.hidden, alpha=cfg.weight_decay, batch_size=cfg.batch_size,
            max_iter=cfg.epochs, early_stopping=False, shuffle=True, random_state=cfg.seed,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=ConvergenceWarning)
            self.network.fit(self.scaler.transform(design), hit[learn + 1].reshape(-1).astype(np.int64))
        self.calibrator = Calibrator("platt").fit(self._raw(X, prior, cal), hit[cal + 1].astype(np.float64))
        return self

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray:
        rows = np.asarray(rows, dtype=np.int64)
        p = self.calibrator.transform(self._raw(X, self.prior.matrix(hit), rows))
        return normalize_rows(p) if self.mode == "de" else p


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
        self.row = X["date"].map(index).to_numpy(dtype=np.int64)
        self.X = X
        self.F = X[ml_train.FEATURE_COLUMNS].astype(np.float32).to_numpy()
        self.y = y.to_numpy(dtype=int)
        self.dates = pd.to_datetime(X["date"])


    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> ProductionMLModel:
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
                continue
            numbers = self.X.loc[sel, "number"].to_numpy(dtype=int)
            raw = self.clf.predict_proba(self.F[sel])[:, 1]
            out[k, numbers] = self.trust * raw + (1.0 - self.trust) * self.baseline
        if self.mode == "de":
            out = out / out.sum(axis=1, keepdims=True)
        return out
