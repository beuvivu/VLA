"""Chuyên gia hỗn hợp Bayes của bộ chữ số trong ensemble ML (``vlm.forecast.bayes_expert``)."""
import gzip
import json
from datetime import datetime, timezone

import numpy as np
import pytest

from vietlott_engine.core.products import ProductCode
from vietlott_engine.forecast.data import CONFIGS, Series
from vietlott_engine.forecast.engine import Forecaster
from vlm.forecast.bayes_expert import NAME, BayesMixtureExpert
from vlm.forecast.pipeline import MLConfig, MLForecaster

NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)


def max3d_series(size: int, *, six: float = 0.1, seed: int = 3) -> Series:
    """Lịch sử Max 3D giả lập: 20 bộ ba mỗi kỳ; chữ số 6 ở hàng đơn vị về với xác suất ``six``."""
    rng = np.random.default_rng(seed)
    units = np.full(10, (1 - six) / 9)
    units[6] = six
    counts = np.zeros((size, 3, 10))
    for t in range(size):
        counts[t, 0] = np.bincount(rng.integers(0, 10, 20), minlength=10)
        counts[t, 1] = np.bincount(rng.integers(0, 10, 20), minlength=10)
        counts[t, 2] = np.bincount(rng.choice(10, 20, p=units), minlength=10)
    dates = np.datetime64('2020-01-01') + np.arange(size)
    return Series(ProductCode.MAX3D, np.arange(1, size + 1), dates.astype(str), {'digits': {'C': counts}})


def config() -> MLConfig:
    return MLConfig(bootstrap=400, warmup=8, tree_every=64, tree_buffer=32, search_nodes=50)


def test_the_ensemble_learns_a_small_stable_digit_bias_through_the_bayes_expert():
    model = MLForecaster('max3d', config())
    model.update(max3d_series(400, six=0.13), now=NOW)
    comp = model.components['digits']
    assert comp.names[-1] == NAME
    metrics = comp.metrics()
    assert metrics['mean_log_gain_nats'] > 0
    assert comp.weights[-1] > 0.5
    law = comp.law()
    assert law.marginals().reshape(3, 10)[2, 6] > 0.115
    top, exact = law.top(5)
    assert exact and all(t['numbers'][-1] == 6 for t in top)


def test_without_a_bias_the_bayes_expert_keeps_the_law_near_fair():
    model = MLForecaster('max3d', config())
    model.update(max3d_series(400, six=0.1, seed=11), now=NOW)
    law = model.components['digits'].law()
    assert np.abs(law.marginals() - 0.1).max() < 0.01


def test_the_expert_is_exactly_the_legacy_mixture_posterior_predictive():
    series = max3d_series(150, six=0.13)
    expert = BayesMixtureExpert(ProductCode.MAX3D, 'digits', CONFIGS[ProductCode.MAX3D].components['digits'])
    for t in range(len(series)):
        expert.learn(series.obs['digits']['C'][t], int(series.draw_ids[t]))
    legacy = Forecaster('max3d')
    legacy.update(series)
    rep = legacy.forecast().components[0].digit
    expected = np.zeros((3, 10))
    for pos, row in enumerate(rep.positions):
        for sym in row.symbols:
            expected[pos, int(sym.symbol)] = sym.p
    np.testing.assert_allclose(expert.predict().reshape(3, 10), expected, atol=1e-6)


def test_checkpoints_round_trip_and_digit_checkpoints_from_older_versions_are_refused(tmp_path):
    model = MLForecaster('max3d', config())
    model.update(max3d_series(120, six=0.13), now=NOW)
    path = tmp_path / 'max3d.json.gz'
    model.save(path)
    again = MLForecaster.load(path)
    np.testing.assert_allclose(again.components['digits'].law().values, model.components['digits'].law().values)

    data = json.loads(gzip.decompress(path.read_bytes()))
    data['version'] = 4
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    with pytest.raises(ValueError, match='Incompatible ML checkpoint'):
        MLForecaster.load(path)

    data['version'] = model.to_dict()['version']
    data['components']['digits']['bayes']['state']['draws'] += 1
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    with pytest.raises(ValueError, match='hỗn hợp Bayes'):
        MLForecaster.load(path)


def test_set_only_products_keep_loading_checkpoints_from_version_four(tmp_path):
    rng = np.random.default_rng(1)
    x = np.zeros((40, 45), dtype=bool)
    for row in x:
        row[rng.choice(45, 6, replace=False)] = True
    series = Series(ProductCode.MEGA_645, np.arange(1, 41), np.full(40, '2026-01-02'),
                    {'main': {'X': x, 'bonus': np.zeros(40, dtype=int)}})
    model = MLForecaster('mega645', MLConfig(bootstrap=40, warmup=8, tree_buffer=16, search_nodes=20))
    model.update(series, now=NOW)
    assert NAME not in model.components['main'].names
    path = tmp_path / 'mega645.json.gz'
    model.save(path)
    data = json.loads(gzip.decompress(path.read_bytes()))
    data['version'] = 4
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    assert MLForecaster.load(path).last_id == 40
