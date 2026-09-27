"""Chốt ranh giới chọn trọng số và hiệu chuẩn, không dùng lại nhãn."""
import numpy as np
import pandas as pd
import pytest

from calibration import CalibParams, MIN_SELECTION_DAYS, select_calibration
import learn_ensemble_weights as learner
from ensemble_utils import DEFAULT_ENSEMBLE_WEIGHTS


def _history(days=180):
    rng = np.random.default_rng(123)
    arrays = {name: rng.uniform(.12, .35, (days, 100)) for name in learner.COMPONENT_COLS}
    labels = (rng.random((days, 100)) < .24).astype(float)
    dates = pd.date_range('2025-01-01', periods=days).strftime('%Y-%m-%d').tolist()
    return arrays, labels, dates


def test_short_calibration_cannot_publish_in_sample_fit():
    probs = np.full((MIN_SELECTION_DAYS - 1, 100), .8)
    labels = np.zeros_like(probs)
    params, audit = select_calibration('loto', probs, labels)
    assert params == CalibParams(mode='loto')
    assert audit.chosen == 'identity'
    assert not audit.selected


def test_calibration_suffix_does_not_change_chosen_weights(monkeypatch):
    seen = []
    real = learner.learn_with_holdout
    def observe(mode, arrays, labels, dates, half_life, incumbent):
        seen.append((labels.copy(), list(dates)))
        return real(mode, arrays, labels, dates, half_life, incumbent)
    monkeypatch.setattr(learner, 'learn_with_holdout', observe)
    arrays, labels, dates = _history()
    first = learner.learn_chronological_stack('loto', arrays, labels, dates, 45, DEFAULT_ENSEMBLE_WEIGHTS)
    changed = labels.copy()
    changed[108:] = 1 - changed[108:]
    second = learner.learn_chronological_stack('loto', arrays, changed, dates, 45, DEFAULT_ENSEMBLE_WEIGHTS)
    np.testing.assert_array_equal(seen[0][0], seen[1][0])
    assert seen[0][1][-1] < first[4]['calibration_first_day']
    assert first[0] == second[0]
    assert first[1] == second[1]
    audit = first[4]
    assert audit['weight_last_day'] < audit['calibration_first_day']
    assert audit['weight_days'] == 108
    assert audit['calibration_days'] == 72


def test_no_time_reversal_across_stack_boundaries():
    arrays, labels, dates = _history()
    dates[-1] = dates[0]
    with pytest.raises(ValueError, match='ngày|day'):
        learner.learn_chronological_stack('loto', arrays, labels, dates, 45, DEFAULT_ENSEMBLE_WEIGHTS)


@pytest.mark.parametrize('corruption', ['nan', 'infinity', 'label', 'shape', 'weight'])
def test_calibration_rejects_invalid_training_data(corruption):
    probs = np.full((100, 100), .24)
    labels = np.zeros_like(probs)
    weights = np.ones(100)
    if corruption == 'nan': probs[0, 0] = np.nan
    if corruption == 'infinity': probs[0, 0] = np.inf
    if corruption == 'label': labels[0, 0] = .5
    if corruption == 'shape': probs, labels = probs[:, :50], labels[:, :50]
    if corruption == 'weight': weights[0] = -1
    with pytest.raises(ValueError):
        select_calibration('loto', probs, labels, weights)


@pytest.mark.parametrize('kind', ['nan_label', 'fractional_label', 'bad_prob', 'bad_mode', 'bad_date', 'de_label'])
def test_stack_rejects_invalid_weight_fit_prefix(kind):
    arrays, labels, dates = _history()
    mode = 'loto'
    if kind == 'nan_label': labels[0, 0] = np.inf
    if kind == 'fractional_label': labels[0, 0] = .5
    if kind == 'bad_prob': arrays[learner.COMPONENT_COLS[0]][0, 0] = np.nan
    if kind == 'bad_mode': mode = 'invalid'
    if kind == 'bad_date': dates[-1] = 'invalid'
    if kind == 'de_label': mode = 'de'
    with pytest.raises(ValueError):
        learner.learn_chronological_stack(mode, arrays, labels, dates, 45, DEFAULT_ENSEMBLE_WEIGHTS)
