"""Score-before-learn ensemble; retrospective skill is never live certification."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from copy import deepcopy
from datetime import date, datetime, time, timezone
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from scipy.special import logsumexp

from vietlott_engine.core.products import PRODUCT_INFO, ProductCode, get_product
from vietlott_engine.forecast.data import CONFIGS, DigitSpec, Series, SetSpec
from vietlott_engine.forecast.schedule import FAST, MARGIN, VN, WEEKLY, target_draw_time
from vlm.forecast.distribution import Law
from vlm.forecast.features import FeatureState
from vlm.forecast.models import GRU, OnlineLogistic, TreeExpert
from vlm.forecast.adaptation import RunningFeatureStats
from vlm.forecast.recovery import NumericalModelError, RecoveryLog, auto_patch_and_retry, require_finite

VERSION = 2
LIVE_THRESHOLD = float(np.log(140))  # seven active products, family alpha .05


class MLConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    bootstrap: int = Field(1000, ge=1, le=1000)
    warmup: int = Field(32, ge=1, le=1000)
    tree_every: int = Field(64, ge=1, le=1000)
    tree_buffer: int = Field(64, ge=8, le=500)
    search_nodes: int = Field(1000, ge=1, le=20000)
    backends: tuple[str, ...] = ('rf',)
    seed: int = 20261003
    adaptive: bool = Field(False, strict=True)


def _validate_series(series: Series, now: datetime) -> None:
    if now.tzinfo is None:
        raise ValueError('Validation clock must have a timezone')
    now = now.astimezone(VN)
    ids = np.asarray(series.draw_ids)
    if ids.shape != (len(series),) or not np.issubdtype(ids.dtype, np.integer) or (ids < 1).any() or (np.diff(ids) <= 0).any():
        raise ValueError('Draw IDs must be positive, unique and increasing')
    if np.asarray(series.dates).shape != ids.shape:
        raise ValueError('Invalid date array')
    days = np.asarray(series.dates).astype('datetime64[D]')
    if np.isnat(days).any() or (days > np.datetime64(now.date())).any():
        raise ValueError('Invalid or future draw dates')
    config = CONFIGS[series.product]
    if set(series.obs) != set(config.components):
        raise ValueError('Missing or unknown product components')
    for name, spec in config.components.items():
        obs = series.obs[name]
        if isinstance(spec, SetSpec):
            x = np.asarray(obs['X'])
            if x.shape != (len(series), spec.n) or not np.isin(x, [0, 1]).all() or not (x.sum(axis=1) == spec.k).all():
                raise ValueError('Invalid set history')
            if spec.bonus_same_drum:
                b = np.asarray(obs['bonus'])
                if b.shape != ids.shape or not np.issubdtype(b.dtype, np.integer) or (b < 1).any() or (b > spec.n).any() or x[np.arange(len(x)), b - 1].any():
                    raise ValueError('Invalid Power bonus history')
        else:
            c = np.asarray(obs['C'])
            if c.shape != (len(series), spec.positions, spec.alphabet) or not np.isfinite(c).all() or (c < 0).any() or (c != np.floor(c)).any() or not (c.sum(axis=2) == spec.per_draw).all():
                raise ValueError('Invalid digit history')


def _prefix_digest(series: Series, count: int) -> str:
    h = hashlib.sha256(series.product.value.encode())
    h.update(series.draw_ids[:count].astype('<i8').tobytes())
    h.update(np.asarray(series.dates[:count]).astype('datetime64[D]').astype('<i8').tobytes())
    for name in sorted(series.obs):
        for key in sorted(series.obs[name]):
            h.update((name + ':' + key).encode())
            h.update(np.asarray(series.obs[name][key][:count]).astype('<i2').tobytes())
    return h.hexdigest()


class MLComponent:
    def __init__(self, spec: SetSpec | DigitSpec, config: MLConfig):
        self.spec, self.config = spec, config
        self.features = FeatureState(spec)
        f = len(self.features.names)
        self.logistics = [OnlineLogistic(f, self.features.base, l2=l2) for l2 in (.001, .01)]
        if config.adaptive:
            self.logistics.append(OnlineLogistic(f, self.features.base, l2=.005))
        self.gru = GRU(f, base=self.features.base, seed=config.seed)
        self.trees = [TreeExpert(backend, self.features.base, seed=config.seed) for backend in config.backends]
        if len(set(config.backends)) != len(config.backends):
            raise ValueError('Tree backends must be unique')
        self.names = ['uniform', 'logistic_l2_.001', 'logistic_l2_.01',
                      *(['adaptive_logistic'] if config.adaptive else []), 'gru', *config.backends]
        self.statistics = RunningFeatureStats(f)
        self.recovery = RecoveryLog()
        self.prior = np.full(len(self.names), .5 / (len(self.names) - 1))
        self.prior[0] = .5
        self.weights = self.prior.copy()
        self.frames: list[np.ndarray] = []
        self.buffer: list[tuple[np.ndarray, np.ndarray]] = []
        self.scored = 0
        self.log_gain = 0.
        self.expert_nll = np.zeros(len(self.names))
        self.brier = self.brier_fair = 0.
        self.reliability = np.zeros((10, 3))  # count, sum predicted, sum observed
        self.recent_gain: list[float] = []

    def _input(self, next_date: str | None = None) -> tuple[np.ndarray, np.ndarray]:
        fid = (self.features.last_id or 0) + 1
        day = next_date or self.features.last_date or '1970-01-01'
        x = self.features.snapshot(fid, day)
        frames = (self.frames + [x])[-8:]
        seq = np.stack([np.zeros_like(x)] * (8-len(frames)) + frames)
        return x, seq

    def law(self, next_date: str | None = None, *, next_id: int | None = None) -> Law:
        x, seq = self._input(next_date)
        if next_id is not None and next_id != (self.features.last_id or 0) + 1:
            x = self.features.snapshot(next_id, next_date or self.features.last_date or '1970-01-01')
            frames = (self.frames + [x])[-8:]
            seq = np.stack([np.zeros_like(x)] * (8-len(frames)) + frames)
        nodes = self.features.nodes
        probabilities = [np.full(nodes, self.features.base)]
        models = [*self.logistics, self.gru, *self.trees]
        for name, model in zip(self.names[1:], models):
            try:
                data = seq if model is self.gru else self.statistics.normalize(x) if name == 'adaptive_logistic' else x
                prediction = np.asarray(model.predict(data), dtype=float)
                if prediction.shape != (nodes,) or ((prediction < 0) | (prediction > 1)).any():
                    raise NumericalModelError('Invalid expert probability vector')
                require_finite(prediction, 'expert probability')
            except (MemoryError, FloatingPointError) as error:
                self.recovery.record('prediction_fallback', name, next_id or (self.features.last_id or 0) + 1, error)
                prediction = np.full(nodes, self.features.base)
            probabilities.append(prediction)
        p = np.clip(np.stack(probabilities), .001, .999)
        if isinstance(self.spec, SetSpec):
            # Bounded log odds prevent a neural overfit from assigning near-zero support.
            z = np.log(p) - np.log1p(-p)
            z = np.clip(z - z.mean(axis=1, keepdims=True), -2, 2)
            values = np.exp(z)
        else:
            values = p.reshape(-1, self.spec.positions, self.spec.alphabet)
        return Law(self.spec, values, self.weights)

    def observe(self, row: np.ndarray, draw_id: int, draw_date: str, bonus: int = 0) -> float:
        """Commit đúng một observation; lỗi ngoài phạm vi phục hồi giữ component cũ."""
        self.features.validate(row)
        candidate = deepcopy(self)
        gain = candidate._observe_staged(row, draw_id, draw_date, bonus)
        self.__dict__.update(candidate.__dict__)
        return gain

    def _observe_staged(self, row: np.ndarray, draw_id: int, draw_date: str, bonus: int = 0) -> float:
        """Học trên candidate riêng; forecaster chỉ commit khi mọi component thành công."""
        row = self.features.validate(row)
        x = self.features.snapshot(draw_id, draw_date)
        frames = (self.frames + [x])[-8:]
        seq = np.stack([np.zeros_like(x)] * (8-len(frames)) + frames)
        law = self.law(draw_date, next_id=draw_id)
        ll = law.expert_log_likelihood(row, bonus)
        mix_ll = float(logsumexp(law.log_mix + ll))
        gain = mix_ll - law.null_log_likelihood(row, bonus)
        divisor = 1 if isinstance(self.spec, SetSpec) else self.spec.per_draw
        target = row / divisor
        if self.features.seen >= self.config.warmup:
            self.scored += 1
            self.log_gain += gain
            self.expert_nll -= ll
            marginals = law.marginals()
            self.brier += float(np.mean((marginals - target)**2))
            self.brier_fair += float(np.mean((self.features.base - target)**2))
            bins = np.minimum((marginals * 10).astype(int), 9)
            np.add.at(self.reliability[:, 0], bins, 1)
            np.add.at(self.reliability[:, 1], bins, marginals)
            np.add.at(self.reliability[:, 2], bins, target)
            self.recent_gain = (self.recent_gain + [gain])[-500:]
        # Full-information policy feedback, proper reward; no draw can affect its own score.
        posterior = np.exp(law.log_mix + ll - mix_ll)
        self.weights = .999 * posterior + .001 * self.prior
        for name, model in zip(self.names[1:1+len(self.logistics)], self.logistics):
            data = self.statistics.normalize(x) if name == 'adaptive_logistic' else x
            self._learn_safely(model, name, data, target, draw_id)
        self._learn_safely(self.gru, 'gru', seq, target, draw_id)
        self.buffer = (self.buffer + [(x.copy(), target.copy())])[-self.config.tree_buffer:]
        self.features.observe(row, draw_id, draw_date)
        self.frames = frames
        if self.features.seen >= self.config.warmup and self.features.seen % self.config.tree_every == 0:
            for tree in self.trees:
                self._fit_tree_safely(tree, draw_id)
        self.statistics.update(x)
        return gain

    def _learn_safely(self, model: OnlineLogistic | GRU, name: str, x: np.ndarray,
                      target: np.ndarray, draw_id: int) -> None:
        """Giữ optimizer tốt trước lỗi; rate backoff có sàn, không học lại nhãn vô hạn."""
        try:
            model.learn(x, target)
        except (MemoryError, FloatingPointError) as error:
            model.rate_scale = max(1/32, model.rate_scale/2)
            self.recovery.record('training_skip', name, draw_id, error)

    def _fit_tree_safely(self, tree: TreeExpert, draw_id: int) -> None:
        """Tree OOM thử lại một lần với nửa số draw; fit lỗi vẫn giữ model cũ."""
        replay = self.buffer
        def reduce_replay(error: MemoryError | FloatingPointError, attempt: int) -> bool:
            nonlocal replay
            if not isinstance(error, MemoryError) or len(replay) < 2:
                return False
            replay = replay[-max(1, len(replay)//2):]
            self.recovery.record('tree_retry', tree.backend, draw_id, error)
            return True
        @auto_patch_and_retry(on_error=reduce_replay, max_retries=1)
        def fit_tree() -> None:
            tree.fit(np.concatenate([xy[0] for xy in replay]), np.concatenate([xy[1] for xy in replay]))
        try:
            fit_tree()
        except (MemoryError, FloatingPointError) as error:
            self.recovery.record('training_skip', tree.backend, draw_id, error)

    def metrics(self) -> dict:
        denominator = max(1, self.scored)
        return {'scored_draws':self.scored, 'mean_log_gain_nats':self.log_gain/denominator,
                'log10_likelihood_ratio_exploratory':self.log_gain/np.log(10),
                'brier_observed_rates':self.brier/denominator, 'brier_fair':self.brier_fair/denominator,
                'expert_mean_nll':dict(zip(self.names, (self.expert_nll/denominator).tolist())),
                'reliability':[{'count':int(c), 'predicted':p/c if c else None, 'observed':o/c if c else None}
                               for c, p, o in self.reliability],
                'evaluation':'retrospective_prequential_exploratory',
                'recovery':self.recovery.to_dict(), 'feature_statistics':self.statistics.report(),
                'learning_rate_scales':dict(zip(self.names[1:1+len(self.logistics)], [m.rate_scale for m in self.logistics])) | {'gru':self.gru.rate_scale}}

    def to_dict(self) -> dict:
        return {'features':self.features.to_dict(), 'logistics':[m.to_dict() for m in self.logistics],
                'gru':self.gru.to_dict(), 'trees':[m.to_dict() for m in self.trees], 'weights':self.weights.tolist(),
                'frames':[x.tolist() for x in self.frames], 'buffer':[[x.tolist(), y.tolist()] for x, y in self.buffer],
                'scored':self.scored, 'log_gain':self.log_gain, 'expert_nll':self.expert_nll.tolist(),
                'brier':self.brier, 'brier_fair':self.brier_fair, 'reliability':self.reliability.tolist(),
                'recent_gain':self.recent_gain, 'statistics':self.statistics.to_dict(), 'recovery':self.recovery.to_dict()}

    @classmethod
    def from_dict(cls, spec: SetSpec | DigitSpec, config: MLConfig, data: dict) -> MLComponent:
        out = cls(spec, config)
        out.features = FeatureState.from_dict(data['features'], expected_spec=spec)
        if out.features.spec != spec:
            raise ValueError('Incompatible feature spec')
        blueprints = {'logistics':[m.to_dict() for m in out.logistics], 'gru':out.gru.to_dict(),
                      'trees':[m.to_dict() for m in out.trees]}
        if len(data['logistics']) != len(out.logistics) or len(data['trees']) != len(out.trees):
            raise ValueError('Incompatible expert count')
        for actual, expected in zip(data['logistics'], blueprints['logistics']):
            if any(actual[k] != expected[k] for k in ('features', 'base', 'l2')):
                raise ValueError('Incompatible logistic architecture')
        if any(data['gru'][k] != blueprints['gru'][k] for k in ('features', 'hidden', 'base', 'seed', 'l2', 'lr')):
            raise ValueError('Incompatible GRU architecture')
        for actual, expected in zip(data['trees'], blueprints['trees']):
            if any(actual[k] != expected[k] for k in ('backend', 'base', 'seed', 'depth')):
                raise ValueError('Incompatible tree architecture')
        out.logistics = [OnlineLogistic.from_dict(d) for d in data['logistics']]
        out.gru = GRU.from_dict(data['gru'])
        out.trees = [TreeExpert.from_dict(d, features=len(out.features.names)) for d in data['trees']]
        if 'statistics' in data:
            out.statistics = RunningFeatureStats.from_dict(data['statistics'], features=len(out.features.names))
            if out.statistics.updates > out.features.seen or out.statistics.samples != out.statistics.updates * out.features.nodes:
                raise ValueError('Inconsistent feature statistics history')
        if 'recovery' in data:
            out.recovery = RecoveryLog.from_dict(data['recovery'], names=out.names)
        for key in ('weights', 'expert_nll', 'reliability'):
            previous = getattr(out, key)
            value = np.array(data[key], dtype=float)
            if value.shape != previous.shape or not np.isfinite(value).all():
                raise ValueError('Invalid ensemble checkpoint')
            setattr(out, key, value)
        if (out.weights < 0).any() or not np.isclose(out.weights.sum(), 1):
            raise ValueError('Invalid ensemble weights')
        out.frames = [np.array(x, dtype=float) for x in data['frames']]
        out.buffer = [(np.array(x, dtype=float), np.array(y, dtype=float)) for x, y in data['buffer']]
        if len(out.frames) > 8 or len(out.buffer) > config.tree_buffer:
            raise ValueError('Invalid replay buffer')
        shape = (out.features.nodes, len(out.features.names))
        if any(x.shape != shape or not np.isfinite(x).all() for x in out.frames):
            raise ValueError('Invalid replay frame')
        if any(x.shape != shape or y.shape != (out.features.nodes,) or not np.isfinite(x).all()
               or not np.isfinite(y).all() or (y < 0).any() or (y > 1).any() for x, y in out.buffer):
            raise ValueError('Invalid replay target')
        for key in ('scored', 'log_gain', 'brier', 'brier_fair', 'recent_gain'):
            setattr(out, key, data[key])
        if (type(out.scored) is not int or not 0 <= out.scored <= out.features.seen
            or not np.isfinite([out.log_gain, out.brier, out.brier_fair]).all()
            or min(out.brier, out.brier_fair) < 0 or len(out.recent_gain) > min(out.scored, 500)
            or not np.isfinite(out.recent_gain).all()):
            raise ValueError('Invalid component metrics')
        return out


class MLForecaster:
    def __init__(self, product: str | ProductCode, config: MLConfig | None = None):
        self.product = get_product(product)
        self.config = config or MLConfig()
        self.components = {name:MLComponent(spec, self.config) for name, spec in CONFIGS[self.product].components.items()}
        self.last_id: int | None = None
        self.last_date: str | None = None
        self.draws_on_last_date = 0
        self.prefix_hash = ''
        self.prefix_count = 0
        self.available = self.learned = self.missing = 0
        self.date_anomalies = 0
        self.first_learned_id: int | None = None
        self.live_log_e = self.max_live_log_e = 0.
        self.live_scored = 0
        self.live_recent: list[float] = []
        self.pending: dict | None = None
        self.warnings: list[str] = []
        self.last_live_scores: list[dict] = []

    def update(self, series: Series, now: datetime | None = None) -> int:
        if series.product != self.product:
            raise ValueError('Product mismatch')
        _validate_series(series, now or datetime.now(timezone.utc))
        self.last_live_scores = []
        previous_count = int(np.searchsorted(series.draw_ids, self.last_id, side='right')) if self.last_id is not None else 0
        revised = self.last_id is not None and (previous_count != self.prefix_count or _prefix_digest(series, previous_count) != self.prefix_hash)
        prospective_start = max(0, len(series)-self.config.bootstrap) if self.last_id is None or revised else previous_count
        check_start = prospective_start if self.last_id is None or revised else max(0, prospective_start-1)
        dates = np.asarray(series.dates).astype('datetime64[D]')
        if (np.diff(dates[check_start:]).astype('int64') < 0).any():
            raise ValueError('Descending dates in the actual training window')
        if revised:
            warnings = list(dict.fromkeys([*self.warnings, 'history_revised']))
            self.__init__(self.product, self.config)
            self.warnings = warnings
        if not self.pending_valid():
            self.pending = None
            self.warnings = list(dict.fromkeys([*self.warnings, 'unverified_issued_target']))
        start = int(np.searchsorted(series.draw_ids, self.last_id, side='right')) if self.last_id is not None else max(0, len(series)-self.config.bootstrap)
        learned = 0
        missing = int(np.sum(np.diff(series.draw_ids)-1)) if len(series) else 0
        date_anomalies = int(np.sum(np.diff(dates).astype('int64') < 0))
        try:
            for t in range(start, len(series)):
                did, day = int(series.draw_ids[t]), str(series.dates[t])[:10]
                score = None
                warnings = list(self.warnings)
                consume_pending = self.pending is not None and did >= self.pending['target_id']
                # Chấm law frozen trước khi candidate nào thấy kết quả, nhưng chưa commit score.
                if consume_pending:
                    if not self.pending_valid():
                        warnings.append('unverified_issued_target')
                    elif did == self.pending['target_id'] and day == self.pending['target_date']:
                        gain = 0.
                        for name, comp in self.components.items():
                            issued = self.pending['laws'][name]
                            law = Law(comp.spec, np.array(issued['values']), np.array(issued['mixture']))
                            obs = series.obs[name]
                            row = obs['X'][t] if isinstance(comp.spec, SetSpec) else obs['C'][t].ravel()
                            bonus = int(obs['bonus'][t]) if isinstance(comp.spec, SetSpec) and comp.spec.bonus_same_drum else 0
                            gain += law.log_likelihood(row, bonus) - law.null_log_likelihood(row, bonus)
                        require_finite(gain, 'issued forecast score')
                        score = {'target_id':did, 'draw_date':day, 'gain_nats':gain,
                            'history_sha256':self.pending['history_sha256'], 'issued_at':self.pending['made_at'],
                            'target_time':self.pending['target_time'], 'scored_at':datetime.now(timezone.utc).isoformat()}
                    else:
                        warnings.append('issued_target_missing_or_date_mismatch')
                candidates = {name:deepcopy(comp) for name, comp in self.components.items()}
                for name, comp in candidates.items():
                    obs = series.obs[name]
                    row = obs['X'][t] if isinstance(comp.spec, SetSpec) else obs['C'][t].ravel()
                    bonus = int(obs['bonus'][t]) if isinstance(comp.spec, SetSpec) and comp.spec.bonus_same_drum else 0
                    comp._observe_staged(row, did, day, bonus)
                # Commit mọi component/cursor/evidence đúng một lần; lỗi trên giữ trạng thái cũ.
                self.components.update(candidates)
                if score is not None:
                    self.live_log_e += score['gain_nats']
                    self.max_live_log_e = max(self.max_live_log_e, self.live_log_e)
                    self.live_scored += 1
                    self.live_recent = (self.live_recent + [score['gain_nats']])[-100:]
                    self.last_live_scores.append(score)
                if consume_pending:
                    self.pending = None
                self.warnings = list(dict.fromkeys(warnings))
                self.last_id, self.last_date = did, day
                self.draws_on_last_date = int(np.sum(dates[:t+1] == np.datetime64(day)))
                self.prefix_count = t + 1
                if self.first_learned_id is None:
                    self.first_learned_id = did
                self.learned += 1
                learned += 1
        finally:
            # Hash đúng prefix đã commit kể cả khi batch sau lỗi; retry không replay prefix.
            # Chỉ hash một lần/call, tránh quét lịch sử Keno hàng trăm nghìn kỳ mỗi draw.
            if learned:
                self.prefix_hash = _prefix_digest(series, self.prefix_count)
                self.available = len(series)
                self.missing, self.date_anomalies = missing, date_anomalies
                if date_anomalies:
                    self.warnings = list(dict.fromkeys([*self.warnings, 'history_date_anomalies']))
        if not learned:
            self.prefix_count = self.available = len(series)
            self.prefix_hash = _prefix_digest(series, len(series))
        self.draws_on_last_date = int(np.sum(dates == np.datetime64(self.last_date))) if self.last_date else 0
        self.missing, self.date_anomalies = missing, date_anomalies
        if self.date_anomalies:
            self.warnings = list(dict.fromkeys([*self.warnings, 'history_date_anomalies']))
        return learned

    def _verified_target(self, target: datetime, made: datetime) -> bool:
        """Core invariant shared by issue, restore and scoring; dates alone cannot verify fast draws."""
        if (self.last_id is None or self.last_date is None or self.product in (*FAST, ProductCode.MAX4D)
            or target.tzinfo is None or made.tzinfo is None):
            return False
        last = date.fromisoformat(self.last_date)
        if self.product in WEEKLY and last.weekday() not in WEEKLY[self.product]:
            return False
        if self.product == ProductCode.LOTTO_535 and self.draws_on_last_date not in (1, 2):
            return False
        expected = target_draw_time(self.product, last, self.draws_on_last_date)
        previous_hour = (13 if self.draws_on_last_date == 1 else 21) if self.product == ProductCode.LOTTO_535 else 18
        previous = datetime.combine(last, time(previous_hour), VN)
        return expected is not None and target == expected and previous <= made < expected - MARGIN

    def pending_valid(self) -> bool:
        if self.pending is None:
            return True
        try:
            p = self.pending
            target, made = datetime.fromisoformat(p['target_time']), datetime.fromisoformat(p['made_at'])
            if (not self._verified_target(target, made) or p['target_id'] != self.last_id + 1
                or p['target_date'] != target.astimezone(VN).date().isoformat()
                or p['based_on_id'] != self.last_id or p['based_on_date'] != self.last_date
                or p['draws_on_last_date'] != self.draws_on_last_date or p['history_sha256'] != self.prefix_hash
                or set(p['laws']) != set(self.components)):
                return False
            for name, comp in self.components.items():
                law = p['laws'][name]
                Law(comp.spec, np.array(law['values']), np.array(law['mixture']))
            return True
        except (ValueError, KeyError, TypeError, AttributeError):
            return False

    def issue(self, target_time: str, made_at: str | None = None) -> bool:
        target = datetime.fromisoformat(target_time)
        made = datetime.fromisoformat(made_at) if made_at else datetime.now(timezone.utc)
        if not self._verified_target(target, made):
            return False
        target_id = self.last_id + 1
        if self.pending is not None and self.pending_valid():
            return True  # retain the first issued distribution for honest live scoring
        day = target.astimezone(VN).date().isoformat()
        self.pending = {'target_id':target_id, 'target_date':day, 'target_time':target.isoformat(),
                        'based_on_id':self.last_id, 'based_on_date':self.last_date,
                        'draws_on_last_date':self.draws_on_last_date, 'history_sha256':self.prefix_hash,
                        'made_at':made.isoformat(), 'laws':{name:comp.law(day, next_id=target_id).to_dict() for name, comp in self.components.items()}}
        return True

    def _target_context(self) -> dict:
        """Một ngữ cảnh cho law và features; ngày riêng lẻ không xác minh slot FAST."""
        if not self.pending_valid():
            raise ValueError('Unverified issued checkpoint')
        if self.pending is not None:
            return {key:self.pending[key] for key in ('target_id', 'target_date', 'target_time')}
        target_id = self.last_id + 1 if self.last_id is not None and self.product != ProductCode.MAX4D else None
        target = None
        if (self.last_date is not None and self.product not in (*FAST, ProductCode.MAX4D)
            and (self.product != ProductCode.LOTTO_535 or self.draws_on_last_date in (1, 2))):
            target = target_draw_time(self.product, date.fromisoformat(self.last_date), self.draws_on_last_date)
        return {'target_id':target_id, 'target_date':target.date().isoformat() if target else self.last_date,
                'target_time':target.isoformat() if target else None}

    def _target_law(self, name: str, context: dict) -> Law:
        """Đọc law đã issue đầu tiên, hoặc dự báo với ngày/ID đã phân giải."""
        comp = self.components[name]
        if self.pending is not None:
            issued = self.pending['laws'][name]
            return Law(comp.spec, np.array(issued['values']), np.array(issued['mixture']))
        return comp.law(context['target_date'], next_id=context['target_id'])

    def confidence(self) -> dict:
        validated = (self.live_scored >= 100 and self.live_log_e >= LIVE_THRESHOLD and
                     sum(self.live_recent) > 0 and self.missing == 0 and self.date_anomalies == 0
                     and self.product not in (*FAST, ProductCode.MAX4D))
        if any(w in self.warnings for w in ('issued_target_missing_or_date_mismatch', 'simulation_clock', 'unverified_issued_target',
                                           'live_evidence_unverified')):
            validated = False
        return {'validated':bool(validated), 'status':'live_evidence' if validated else 'insufficient_live_evidence',
                'scored_live':self.live_scored, 'log10_e_current':self.live_log_e/np.log(10),
                'log10_e_max':self.max_live_log_e/np.log(10), 'threshold_e':140,
                'family_adjusted_anytime_p':float(min(1, 7*np.exp(-max(self.max_live_log_e, 0)))),
                'confidence_score':None,
                'note':'Chỉ kiểm định live đã ghi trước kỳ quay; đây không phải xác suất trúng vé. Backtest hồi cứu là thử nghiệm.'}

    def report(self, top_n: int = 5, budget: int = 0) -> dict:
        if budget < 0:
            raise ValueError('Budget must not be negative')
        context = self._target_context()
        confidence = self.confidence()
        components = []
        for name, comp in self.components.items():
            law = self._target_law(name, context)
            feature_input = comp.features.snapshot(context['target_id'] or (comp.features.last_id or 0)+1,
                                                   context['target_date'] or '1970-01-01')
            top, exact = law.top(top_n, self.config.search_nodes)
            marginals = law.marginals()
            for ticket in top:
                ticket['p_deployed'] = ticket['p_model'] if confidence['validated'] else ticket['p_fair']
                ticket['explanation'] = ('Xếp hạng theo mixture của các expert được chấm trước khi học. '
                                         'Hot/cold và gap là đặc trưng mô tả, không chứng minh số đến hạn.')
                if isinstance(comp.spec, SetSpec):
                    selected = np.array(ticket['numbers'])-1
                else:
                    selected = np.arange(comp.spec.positions)*comp.spec.alphabet + np.array(ticket['numbers'])-comp.spec.symbol_offset
                diagnostics = feature_input[selected].mean(axis=0)
                ticket['feature_support'] = {key:float(diagnostics[comp.features.names.index(key)])
                    for key in ('freq_all', 'ema10', 'ema100', 'log_gap', 'gap_censored', 'pair_link', 'triple_link')}
            components.append({'name':name, 'kind':comp.spec.kind,
                'scope':'main_draw_set' if isinstance(comp.spec, SetSpec) else 'one_position_tuple',
                'top':top, 'ranking_exact':exact,
                'marginals_model':marginals.tolist(),
                'marginals_deployed':marginals.tolist() if confidence['validated'] else np.full(comp.features.nodes, comp.features.base).tolist(),
                'expert_weights':dict(zip(comp.names, comp.weights.tolist())),
                'metrics':comp.metrics(), 'features':dict(zip(comp.features.names, feature_input.mean(axis=0).tolist())),
                'assumptions':('Weighted sampling without replacement; main-set probabilities marginalize Power bonus.'
                               if isinstance(comp.spec, SetSpec) else 'Independent categorical positions; Max tier occurrences are pooled, not prize-value predictions.')})
        portfolio = self.portfolio(top_n, budget)
        return {'product':self.product.value, 'display_name':PRODUCT_INFO[self.product].display_name,
                'version':VERSION, 'made_at':datetime.now(timezone.utc).isoformat(),
                'last_id':self.last_id, 'last_date':self.last_date,
                **context,
                'draws_learned':self.learned, 'first_learned_id':self.first_learned_id,
                'historical_draws_available':self.available, 'missing_ids_inside_range':self.missing,
                'date_anomalies':self.date_anomalies,
                'history_sha256':self.prefix_hash, 'config':self.config.model_dump(mode='json'),
                'confidence':confidence, 'warnings':self.warnings, 'components':components,
                'portfolio':portfolio}

    def portfolio(self, top_n: int, budget: int) -> dict:
        context = self._target_context()
        out = {'budget_vnd':budget, 'spent_vnd':0, 'tickets':[],
               'note':'Đa dạng coverage trong ngân sách; ít giao số không làm tăng xác suất một vé hoặc bảo đảm sinh lời.'}
        if self.product not in (ProductCode.MEGA_645, ProductCode.POWER_655, ProductCode.LOTTO_535):
            out['note'] = 'Không chuyển tuple/chọn 20 số kết quả thành vé chơi; dùng bảng luật đúng bậc hoặc cặp số của sản phẩm.'
            return out
        count = min(top_n, budget//10_000, 100)
        if count <= 0:
            return out
        comp = self.components['main']
        law = self._target_law('main', context)
        sp = comp.spec
        top, _ = law.top(max(5, count), min(self.config.search_nodes, 100))
        rng = np.random.default_rng(self.config.seed + (self.last_id or 0))
        candidates = {tuple(t['numbers']) for t in top}
        for _ in range(max(100, count*8)):
            candidates.add(tuple(sorted(rng.choice(np.arange(1, sp.n+1), sp.k, replace=False).tolist())))
        ranked = {c:law.probability(list(c)) for c in candidates}
        chosen: list[tuple[int, ...]] = []
        for _ in range(count):
            def key(c):
                overlap = max((len(set(c) & set(old)) for old in chosen), default=0)
                return (overlap, -ranked[c], c)
            best = min(ranked, key=key)
            chosen.append(best)
            special = None
            probability = ranked.pop(best)
            fair = law.fair
            if self.product == ProductCode.LOTTO_535:
                special_law = self._target_law('special', context)
                special = int(np.argmax(special_law.marginals())) + 1
                probability *= special_law.probability([special])
                fair /= 12
            out['tickets'].append({'numbers':list(best), 'special':special,
                'p_jackpot_model':probability, 'p_jackpot_fair':fair,
                'p_jackpot_deployed':probability if self.confidence()['validated'] else fair,
                'cost_vnd':10_000})
        out['spent_vnd'] = count * 10_000
        out['p_jackpot_any_ticket_fair'] = sum(t['p_jackpot_fair'] for t in out['tickets'])
        return out

    def to_dict(self) -> dict:
        fields = ('last_id', 'last_date', 'draws_on_last_date', 'prefix_hash', 'prefix_count', 'available', 'learned', 'missing', 'date_anomalies',
                  'first_learned_id', 'live_log_e', 'max_live_log_e', 'live_scored', 'live_recent', 'pending', 'warnings')
        return {'version':VERSION, 'product':self.product.value, 'config':self.config.model_dump(mode='json'),
                **{k:getattr(self, k) for k in fields},
                'components':{k:c.to_dict() for k, c in self.components.items()}}

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = gzip.compress(json.dumps(self.to_dict(), separators=(',', ':'), allow_nan=False).encode(), mtime=0)
        filename = None
        try:
            with tempfile.NamedTemporaryFile('wb', dir=path.parent, delete=False) as file:
                filename = file.name
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(filename, path)
        finally:
            if filename and os.path.exists(filename):
                os.unlink(filename)

    @classmethod
    def load(cls, path: Path) -> MLForecaster:
        with gzip.open(path, 'rb') as file:
            raw = file.read(128 * 1024 * 1024 + 1)
        if len(raw) > 128 * 1024 * 1024:
            raise ValueError('Checkpoint too large')
        data = json.loads(raw)
        if data['version'] != VERSION:
            raise ValueError('Incompatible ML checkpoint')
        json.dumps(data, allow_nan=False)
        out = cls(data['product'], MLConfig.model_validate(data['config']))
        if set(data['components']) != set(out.components):
            raise ValueError('Incompatible ML components')
        out.components = {k:MLComponent.from_dict(c.spec, out.config, data['components'][k]) for k, c in out.components.items()}
        for key in ('last_id', 'last_date', 'draws_on_last_date', 'prefix_hash', 'prefix_count', 'available', 'learned', 'missing', 'date_anomalies',
                    'first_learned_id', 'live_log_e', 'max_live_log_e', 'live_scored', 'live_recent', 'pending', 'warnings'):
            setattr(out, key, data[key])
        counters = ('draws_on_last_date', 'prefix_count', 'available', 'learned', 'missing', 'date_anomalies', 'live_scored')
        if (any(type(getattr(out, key)) is not int or getattr(out, key) < 0 for key in counters)
            or not out.learned <= out.prefix_count <= out.available
            or out.live_scored > max(0, out.learned-1)
            or len(out.live_recent) != min(100, out.live_scored)
            or not np.isfinite([out.live_log_e, out.max_live_log_e, *out.live_recent]).all()
            or out.max_live_log_e < max(0., out.live_log_e)
            or out.live_scored == 0 and (out.live_log_e != 0 or out.max_live_log_e != 0)
            or out.live_scored <= 100 and not np.isclose(out.live_log_e, sum(out.live_recent), rtol=1e-10, atol=1e-10)):
            raise ValueError('Invalid ML counters')
        if (out.learned and (type(out.last_id) is not int or type(out.first_learned_id) is not int
                            or out.first_learned_id < 1 or out.last_id-out.first_learned_id+1 < out.learned)
            or not out.learned and (out.last_id is not None or out.last_date is not None or out.first_learned_id is not None)):
            raise ValueError('Invalid ML history bounds')
        if any(c.features.last_id != out.last_id or c.features.last_date != out.last_date
               or c.features.seen != out.learned for c in out.components.values()):
            raise ValueError('Inconsistent component history')
        if not out.pending_valid():
            raise ValueError('Unverified issued checkpoint')
        return out
