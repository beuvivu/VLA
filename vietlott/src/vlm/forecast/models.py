"""Trainable bounded experts. All checkpoints are data, never executable pickle."""
from __future__ import annotations

import importlib.util
import json

import numpy as np
from scipy.special import expit, logit

from vlm.forecast.recovery import NumericalModelError, require_finite


class OnlineLogistic:
    def __init__(self, features: int, base: float, l2: float = .001) -> None:
        if type(features) is not int or features < 1 or not np.isfinite([base, l2]).all() or not 0 < base < 1 or l2 < 0:
            raise ValueError('Invalid logistic configuration')
        self.features, self.base, self.l2 = features, base, l2
        self.theta = np.zeros(features + 1)
        self.acc = np.zeros_like(self.theta)
        self.rate_scale = 1.

    def _input(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        if x.ndim != 2 or x.shape[1] != self.features or not len(x) or not np.isfinite(x).all():
            raise ValueError('Invalid logistic input')
        return x

    @np.errstate(over='raise', invalid='raise', divide='raise')
    def predict(self, x: np.ndarray) -> np.ndarray:
        x = self._input(x)
        require_finite(self.theta, 'logistic parameters')
        prediction = expit(x @ self.theta[:-1] + self.theta[-1] + logit(self.base))
        require_finite(prediction, 'logistic prediction')
        return prediction

    @np.errstate(over='raise', invalid='raise', divide='raise')
    def learn(self, x: np.ndarray, y: np.ndarray) -> None:
        """AdaGrad staging: batch hoặc optimizer lỗi không thay trọng số đang dùng."""
        x, y = self._input(x), np.asarray(y, dtype=float)
        if y.shape != (len(x),) or not np.isfinite(y).all() or ((y < 0) | (y > 1)).any():
            raise ValueError('Invalid logistic target')
        require_finite(self.acc, 'AdaGrad accumulator')
        if (self.acc < 0).any() or not np.isfinite(self.rate_scale) or not 0 < self.rate_scale <= 1:
            raise NumericalModelError('Invalid AdaGrad state')
        error = self.predict(x) - y
        gradient = np.append(x.T @ error / len(y), error.mean())
        gradient[:-1] += self.l2 * self.theta[:-1]
        require_finite(gradient, 'logistic gradient')
        gradient = np.clip(gradient, -1, 1)
        acc = self.acc + gradient ** 2
        theta = self.theta - .08 * self.rate_scale * gradient / (np.sqrt(acc) + 1e-8)
        require_finite(acc, 'AdaGrad candidate')
        require_finite(theta, 'logistic candidate')
        self.acc, self.theta = acc, theta

    def to_dict(self) -> dict:
        return {'features':self.features, 'base':self.base, 'l2':self.l2,
                'theta':self.theta.tolist(), 'acc':self.acc.tolist(), 'rate_scale':self.rate_scale}

    @classmethod
    def from_dict(cls, data: dict) -> OnlineLogistic:
        out = cls(data['features'], data['base'], data['l2'])
        for key in ('theta', 'acc'):
            value = np.array(data[key], dtype=float)
            if value.shape != out.theta.shape or not np.isfinite(value).all():
                raise ValueError('Invalid logistic checkpoint')
            setattr(out, key, value)
        if (out.acc < 0).any():
            raise ValueError('Invalid AdaGrad state')
        scale = data.get('rate_scale', 1.)
        if isinstance(scale, bool) or not np.isfinite(scale) or not 0 < scale <= 1:
            raise ValueError('Invalid logistic rate scale')
        out.rate_scale = float(scale)
        return out


class GRU:
    """Shared node GRU, reset-before projection, eight-step truncated BPTT + Adam.

    Hidden state is rebuilt from the causal window, not carried across optimizer
    updates. This makes reload/chunk behavior deterministic and bounds memory.
    """
    def __init__(self, features: int, hidden: int = 8, base: float = .5,
                 seed: int = 20261003, l2: float = .001, lr: float = .006) -> None:
        if (type(features) is not int or features < 1 or type(hidden) is not int or hidden < 1
            or not np.isfinite([base, l2, lr]).all() or not 0 < base < 1 or l2 < 0 or lr <= 0):
            raise ValueError('Invalid GRU configuration')
        self.features, self.hidden, self.base = features, hidden, base
        self.seed, self.l2, self.lr = seed, l2, lr
        self.rate_scale = 1.
        rng = np.random.default_rng(seed)
        self.params = {}
        for gate in ('r', 'z', 'n'):
            self.params['W' + gate] = rng.normal(0, .1 / np.sqrt(features), (features, hidden))
            self.params['U' + gate] = rng.normal(0, .1 / np.sqrt(hidden), (hidden, hidden))
            self.params['b' + gate] = np.zeros(hidden)
        self.params['Wo'] = rng.normal(0, .1, hidden)
        self.params['bo'] = np.zeros(1)
        self.first = {k:np.zeros_like(v) for k, v in self.params.items()}
        self.second = {k:np.zeros_like(v) for k, v in self.params.items()}
        self.steps = 0

    @np.errstate(over='raise', invalid='raise', divide='raise')
    def _forward(self, x: np.ndarray) -> tuple[np.ndarray, list]:
        x = np.asarray(x, dtype=float)
        if x.ndim != 3 or x.shape[-1] != self.features or len(x) == 0 or x.shape[1] == 0 or not np.isfinite(x).all():
            raise ValueError('Invalid GRU input')
        p = self.params
        for value in p.values():
            require_finite(value, 'GRU parameters')
        h = np.zeros((x.shape[1], self.hidden))
        cache = []
        for frame in x:
            previous = h
            r = expit(frame @ p['Wr'] + previous @ p['Ur'] + p['br'])
            z = expit(frame @ p['Wz'] + previous @ p['Uz'] + p['bz'])
            candidate = np.tanh(frame @ p['Wn'] + (r * previous) @ p['Un'] + p['bn'])
            h = (1 - z) * previous + z * candidate
            cache.append((frame, previous, r, z, candidate, h))
        logits = h @ p['Wo'] + p['bo'][0] + logit(self.base)
        require_finite(logits, 'GRU logits')
        return logits, cache

    def predict(self, x: np.ndarray) -> np.ndarray:
        logits, _ = self._forward(x)
        return expit(logits)

    @np.errstate(over='raise', invalid='raise', divide='raise')
    def loss_and_gradients(self, x: np.ndarray, y: np.ndarray) -> tuple[float, dict[str, np.ndarray]]:
        logits, cache = self._forward(x)
        y = np.asarray(y, dtype=float)
        if y.shape != logits.shape or not np.isfinite(y).all() or (y < 0).any() or (y > 1).any():
            raise ValueError('Invalid GRU target')
        p = self.params
        loss = float(np.mean(np.logaddexp(0, logits) - y * logits))
        g = {k:np.zeros_like(v) for k, v in p.items()}
        dl = (expit(logits) - y) / len(y)
        g['Wo'] = cache[-1][-1].T @ dl
        g['bo'][0] = dl.sum()
        dh = dl[:, None] * p['Wo'][None, :]
        for frame, previous, r, z, candidate, _ in reversed(cache):
            dn = dh * z * (1 - candidate**2)
            dz = dh * (candidate - previous) * z * (1 - z)
            drh = dn @ p['Un'].T
            dr = drh * previous * r * (1 - r)
            for gate, gradient, recurrent in [('n', dn, r * previous), ('z', dz, previous), ('r', dr, previous)]:
                g['W' + gate] += frame.T @ gradient
                g['U' + gate] += recurrent.T @ gradient
                g['b' + gate] += gradient.sum(axis=0)
            dh = dh * (1 - z) + drh * r + dz @ p['Uz'].T + dr @ p['Ur'].T
        for key in p:
            if not key.startswith('b'):
                loss += .5 * self.l2 * float(np.sum(p[key] ** 2))
                g[key] += self.l2 * p[key]
        return loss, g

    @np.errstate(over='raise', invalid='raise', divide='raise')
    def learn(self, x: np.ndarray, y: np.ndarray) -> None:
        """Adam staging, kiểm loss/gradient và clip norm không tự overflow."""
        loss, gradients = self.loss_and_gradients(x, y)
        require_finite(loss, 'GRU loss')
        for gradient in gradients.values():
            require_finite(gradient, 'GRU gradient')
        maximum = max(float(np.max(np.abs(g))) for g in gradients.values())
        normalized_norm = np.sqrt(sum(float(np.sum((g / maximum)**2)) for g in gradients.values())) if maximum else 0.
        scale = min(1., (1. / maximum) / max(normalized_norm, 1e-12)) if maximum > 1e-12 else 1.
        steps = self.steps + 1
        first, second, params = {}, {}, {}
        if not np.isfinite(self.rate_scale) or not 0 < self.rate_scale <= 1:
            raise NumericalModelError('Invalid GRU rate scale')
        for key, gradient in gradients.items():
            gradient = gradient * scale
            first[key] = .9 * self.first[key] + .1 * gradient
            second[key] = .999 * self.second[key] + .001 * gradient**2
            require_finite(first[key], 'Adam first moment')
            require_finite(second[key], 'Adam second moment')
            if (second[key] < 0).any():
                raise NumericalModelError('Invalid Adam variance')
            m = first[key] / (1 - .9 ** steps)
            v = second[key] / (1 - .999 ** steps)
            params[key] = self.params[key] - self.lr * self.rate_scale * m / (np.sqrt(v) + 1e-8)
            require_finite(params[key], 'GRU candidate')
        self.first, self.second, self.params, self.steps = first, second, params, steps

    def to_dict(self) -> dict:
        return {'features':self.features, 'hidden':self.hidden, 'base':self.base,
                'seed':self.seed, 'l2':self.l2, 'lr':self.lr, 'steps':self.steps, 'rate_scale':self.rate_scale,
                **{name:{k:v.tolist() for k, v in getattr(self, name).items()}
                   for name in ('params', 'first', 'second')}}

    @classmethod
    def from_dict(cls, data: dict) -> GRU:
        out = cls(**{k:data[k] for k in ('features', 'hidden', 'base', 'seed', 'l2', 'lr')})
        for name in ('params', 'first', 'second'):
            current = getattr(out, name)
            if set(data[name]) != set(current):
                raise ValueError('Invalid GRU checkpoint')
            for key in current:
                value = np.array(data[name][key], dtype=float)
                if value.shape != current[key].shape or not np.isfinite(value).all():
                    raise ValueError('Invalid GRU parameter')
                current[key] = value
        out.steps = data['steps']
        if type(out.steps) is not int or out.steps < 0 or any((v < 0).any() for v in out.second.values()):
            raise ValueError('Invalid Adam checkpoint')
        scale = data.get('rate_scale', 1.)
        if isinstance(scale, bool) or not np.isfinite(scale) or not 0 < scale <= 1:
            raise ValueError('Invalid GRU rate scale')
        out.rate_scale = float(scale)
        return out


class TreeExpert:
    """Periodic bounded tree fit; RF prediction is persisted as JSON tree arrays."""
    def __init__(self, backend: str, base: float, seed: int = 20261003, depth: int = 4) -> None:
        if backend not in ('rf', 'xgb', 'lgb'):
            raise ValueError('Unknown tree backend')
        if not np.isfinite(base) or not 0 < base < 1 or type(depth) is not int or not 1 <= depth <= 10:
            raise ValueError('Invalid tree configuration')
        module = {'rf':'sklearn', 'xgb':'xgboost', 'lgb':'lightgbm'}[backend]
        if importlib.util.find_spec(module) is None:
            raise ImportError(f'{module} is required; install VLM[ml] for optional boosters')
        self.backend, self.base, self.seed, self.depth = backend, base, seed, depth
        self.trees: list[dict] = []
        self.booster = None
        self.constant: float | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        if x.ndim != 2 or x.shape[1] < 1 or y.shape != (len(x),) or not len(y) or not np.isfinite(x).all() or not np.isfinite(y).all() or (y < 0).any() or (y > 1).any():
            raise ValueError('Invalid tree training data')
        trees, booster, constant = [], None, None
        if np.ptp(y) < 1e-12:
            self.trees, self.booster, self.constant = [], None, float(np.clip(y[0], .001, .999))
            return
        if self.backend == 'rf':
            from sklearn.ensemble import RandomForestRegressor
            forest = RandomForestRegressor(n_estimators=24, max_depth=self.depth,
                min_samples_leaf=max(4, min(64, len(y)//20)), max_features=.7,
                random_state=self.seed, n_jobs=1).fit(x, y)
            trees = [{'left':e.tree_.children_left.tolist(), 'right':e.tree_.children_right.tolist(),
                           'feature':e.tree_.feature.tolist(), 'threshold':e.tree_.threshold.tolist(),
                           'value':e.tree_.value[:, 0, 0].tolist()} for e in forest.estimators_]
        elif self.backend == 'xgb':
            import xgboost as xgb
            booster = xgb.train({'objective':'binary:logistic', 'max_depth':self.depth,
                'eta':.05, 'lambda':10, 'min_child_weight':10, 'subsample':.8,
                'colsample_bytree':.7, 'seed':self.seed, 'nthread':1,
                'base_score':self.base, 'tree_method':'hist'}, xgb.DMatrix(x, label=y), num_boost_round=24)
        else:
            import lightgbm as lgb
            booster = lgb.train({'objective':'cross_entropy', 'max_depth':self.depth,
                'num_leaves':2 ** self.depth, 'learning_rate':.05, 'lambda_l2':10,
                'min_data_in_leaf':max(4, min(64, len(y)//20)), 'feature_fraction':.7,
                'seed':self.seed, 'num_threads':1, 'verbosity':-1}, lgb.Dataset(x, label=y), num_boost_round=24)
        # Chỉ thay expert đang chạy sau khi candidate vượt kiểm tra state và prediction.
        candidate = object.__new__(TreeExpert)
        candidate.__dict__ = {**self.__dict__, 'trees':trees, 'booster':booster, 'constant':constant}
        if self.backend == 'rf':
            try:
                if not trees:
                    raise ValueError('Empty fitted forest')
                self._validate_rf(trees, self.depth, x.shape[1])
            except (ValueError, TypeError, IndexError) as error:
                raise NumericalModelError('Invalid fitted RF state') from error
        candidate.predict(x[:128])
        self.trees, self.booster, self.constant = trees, booster, constant

    def predict(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        if x.ndim != 2 or x.shape[1] < 1 or not len(x) or not np.isfinite(x).all():
            raise ValueError('Invalid tree prediction input')
        if self.constant is not None:
            return np.full(len(x), self.constant)
        if self.trees:
            result = np.zeros(len(x))
            for tree in self.trees:
                left, right = np.array(tree['left']), np.array(tree['right'])
                feature, threshold, value = np.array(tree['feature']), np.array(tree['threshold']), np.array(tree['value'])
                node = np.zeros(len(x), dtype=int)
                for _ in range(self.depth + 1):
                    active = left[node] != -1
                    if not active.any():
                        break
                    indices = np.flatnonzero(active)
                    nd = node[active]
                    go_left = x[indices, feature[nd]] <= threshold[nd]
                    node[indices] = np.where(go_left, left[nd], right[nd])
                result += value[node]
            require_finite(result, 'RF prediction')
            return np.clip(result / len(self.trees), .001, .999)
        if self.booster is not None:
            if self.backend == 'xgb':
                import xgboost as xgb
                prediction = self.booster.predict(xgb.DMatrix(x))
            else:
                prediction = self.booster.predict(x)
            require_finite(prediction, 'tree prediction')
            if np.asarray(prediction).shape != (len(x),):
                raise NumericalModelError('Invalid tree prediction shape')
            if (np.asarray(prediction) < 0).any() or (np.asarray(prediction) > 1).any():
                raise NumericalModelError('Invalid tree prediction range')
            return np.clip(prediction, .001, .999)
        return np.full(len(x), self.base)

    def to_dict(self) -> dict:
        raw = None
        if self.booster is not None:
            raw = self.booster.save_raw(raw_format='json').decode() if self.backend == 'xgb' else self.booster.model_to_string()
        return {'backend':self.backend, 'base':self.base, 'seed':self.seed, 'depth':self.depth,
                'trees':self.trees, 'constant':self.constant, 'booster':raw}

    @staticmethod
    def _validate_rf(trees: list[dict], depth_limit: int, features: int | None) -> None:
        """Kiểm cấu trúc và giá trị RF cho cả candidate lẫn checkpoint."""
        if len(trees) > 24:
            raise ValueError('Invalid RF count')
        for tree in trees:
            length = len(tree['left'])
            if length < 1 or any(len(tree[k]) != length for k in ('right', 'feature', 'threshold', 'value')):
                raise ValueError('Invalid RF tree')
            if any(not -1 <= int(c) < length for k in ('left', 'right') for c in tree[k]):
                raise ValueError('Invalid RF child')
            if any(type(v) is not int for k in ('left', 'right', 'feature') for v in tree[k]):
                raise ValueError('Invalid RF index')
            if not np.isfinite(tree['threshold']).all() or not np.isfinite(tree['value']).all() or any(not 0 <= v <= 1 for v in tree['value']):
                raise ValueError('Invalid RF value')
            visited, stack = set(), [(0, 0)]
            while stack:
                node, depth = stack.pop()
                if node in visited or depth > depth_limit:
                    raise ValueError('Invalid RF topology')
                visited.add(node)
                left, right = tree['left'][node], tree['right'][node]
                if left == -1:
                    if right != -1:
                        raise ValueError('Invalid RF leaf')
                else:
                    feature = tree['feature'][node]
                    if right == -1 or feature < 0 or features is not None and feature >= features:
                        raise ValueError('Invalid RF split')
                    stack.extend([(left, depth + 1), (right, depth + 1)])
            if len(visited) != length:
                raise ValueError('Unreachable RF nodes')

    @classmethod
    def from_dict(cls, data: dict, *, features: int | None = None) -> TreeExpert:
        out = cls(**{k:data[k] for k in ('backend', 'base', 'seed', 'depth')})
        out.trees, out.constant = data['trees'], data['constant']
        if (type(out.depth) is not int or not 1 <= out.depth <= 10
            or out.constant is not None and not 0 <= out.constant <= 1
            or out.trees and (out.backend != 'rf' or data['booster'] is not None)):
            raise ValueError('Invalid tree checkpoint')
        cls._validate_rf(out.trees, out.depth, features)
        if data['booster'] is not None:
            if out.backend == 'xgb':
                import xgboost as xgb
                out.booster = xgb.Booster()
                out.booster.load_model(bytearray(data['booster'], 'utf-8'))
            else:
                import lightgbm as lgb
                out.booster = lgb.Booster(model_str=data['booster'])
        # Reject NaN/Infinity even in unused tree fields.
        json.dumps(data, allow_nan=False)
        return out
