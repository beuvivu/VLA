from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression


class PlattCalibratedClassifier(BaseEstimator, ClassifierMixin):
    """Histogram gradient boosting followed by out-of-sample Platt scaling.

    ``sample_weight`` support is deliberate: lottery history is a time series, so
    daily retraining can emphasize recent observations without discarding older
    regimes. Calibration is fitted on an untouched temporal calibration block;
    downsampling that block would distort the real event prevalence.
    """

    def __init__(self, base: HistGradientBoostingClassifier | None = None):
        self.base = base

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> "PlattCalibratedClassifier":
        if self.base is None:
            self.base_ = HistGradientBoostingClassifier(
                max_depth=3,
                learning_rate=0.06,
                max_iter=140,
                l2_regularization=0.2,
                early_stopping=True,
                random_state=42,
            )
        else:
            self.base_ = clone(self.base)
        self.base_.fit(X, y, sample_weight=sample_weight)
        return self

    def fit_platt(
        self,
        p: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> None:
        p = np.clip(p, 1e-6, 1 - 1e-6)
        z = np.log(p / (1 - p)).reshape(-1, 1)
        self.platt_ = LogisticRegression(solver="lbfgs", max_iter=1000)
        self.platt_.fit(z, y, sample_weight=sample_weight)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        p = self.base_.predict_proba(X)[:, 1]
        p = np.clip(p, 1e-6, 1 - 1e-6)
        z = np.log(p / (1 - p)).reshape(-1, 1)
        p_cal = self.platt_.predict_proba(z)[:, 1]
        return np.vstack([1 - p_cal, p_cal]).T

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
