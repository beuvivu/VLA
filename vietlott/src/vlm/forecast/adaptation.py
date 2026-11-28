from __future__ import annotations

import numpy as np

from vlm.forecast.recovery import require_finite


class RunningFeatureStats:

    def __init__(self, features: int) -> None:
        if type(features) is not int or features < 1:
            raise ValueError('features must be a positive integer')
        self.features = features
        self.samples = self.updates = 0
        self.mean = np.zeros(features)
        self.m2 = np.zeros(features)
        self.drift_score = 0.

    @property
    def std(self) -> np.ndarray:
        return np.sqrt(self.m2 / self.samples) if self.samples else np.ones(self.features)

    def _batch(self, x: np.ndarray) -> np.ndarray:
        batch = np.asarray(x, dtype=np.float64)
        if batch.ndim != 2 or batch.shape[1] != self.features or not len(batch) or not np.isfinite(batch).all():
            raise ValueError('Invalid feature statistics batch')
        return batch

    def normalize(self, x: np.ndarray) -> np.ndarray:
        batch = self._batch(x)
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            normalized = (batch - self.mean) / np.maximum(self.std, .05) if self.samples else batch.copy()
        require_finite(normalized, 'normalized features')
        return np.clip(normalized, -5, 5)

    def update(self, x: np.ndarray) -> None:
        batch = self._batch(x)
        count = len(batch)
        total = self.samples + count
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            batch_mean = batch.mean(axis=0)
            difference = batch_mean - self.mean
            centered = batch - batch_mean
            next_mean = self.mean + difference * (count / total)
            next_m2 = self.m2 + np.sum(centered**2, axis=0) + difference**2 * (self.samples * count / total)
            shift = float(np.max(np.abs(difference) / np.maximum(self.std, .05))) if self.samples else 0.
            drift = .9 * self.drift_score + .1 * min(shift, 100.)
        require_finite(next_mean, 'running mean')
        require_finite(next_m2, 'running variance')
        self.mean, self.m2 = next_mean, np.maximum(next_m2, 0.)
        self.samples, self.updates, self.drift_score = total, self.updates + 1, drift

    def report(self) -> dict:
        return {'samples':self.samples, 'updates':self.updates, 'mean':self.mean.tolist(),
                'std':self.std.tolist(), 'drift_score':self.drift_score,
                'drift_alert':bool(self.updates >= 8 and self.drift_score >= 3),
                'evaluation':'descriptive_feature_shift_not_a_significance_test'}

    def to_dict(self) -> dict:
        return {'features':self.features, 'samples':self.samples, 'updates':self.updates,
                'mean':self.mean.tolist(), 'm2':self.m2.tolist(), 'drift_score':self.drift_score}

    @classmethod
    def from_dict(cls, data: dict, *, features: int) -> RunningFeatureStats:
        out = cls(features)
        if data['features'] != features:
            raise ValueError('Incompatible feature statistics')
        for key in ('samples', 'updates'):
            value = data[key]
            if type(value) is not int or value < 0:
                raise ValueError('Invalid statistics counter')
            setattr(out, key, value)
        if (out.samples == 0) != (out.updates == 0) or out.samples < out.updates:
            raise ValueError('Inconsistent statistics counters')
        for key in ('mean', 'm2'):
            value = np.asarray(data[key], dtype=float)
            if value.shape != (features,) or not np.isfinite(value).all():
                raise ValueError('Invalid feature statistics')
            setattr(out, key, value)
        drift = data['drift_score']
        if (out.m2 < 0).any() or isinstance(drift, bool) or not np.isfinite(drift) or not 0 <= drift <= 100:
            raise ValueError('Invalid feature variance or drift')
        if not out.samples and (out.mean.any() or out.m2.any() or drift):
            raise ValueError('Invalid empty statistics')
        out.drift_score = float(drift)
        return out
