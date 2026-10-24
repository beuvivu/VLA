"""Chuyên gia mẫu hình phải học từ quá khứ và bỏ qua kỳ chưa quan sát."""
from copy import deepcopy
import importlib
import json

import numpy as np
import pytest


def _model(nodes=2, base=.5):
    return importlib.import_module('vlm.forecast.patterns').PatternExperts(nodes, base)


def test_cold_start_and_prediction_do_not_mutate_state():
    model = _model(3, .2)
    before = deepcopy(model.to_dict())
    prediction = model.predict()
    np.testing.assert_array_equal(prediction, np.full((4, 3), .2))
    prediction[:] = 0
    assert model.to_dict() == before
    assert model.seen == 0 and model.last_id is None


def test_bayesian_experts_learn_bias_and_short_expert_tracks_new_regime():
    model = _model()
    for draw_id in range(1, 601):
        model.observe(np.array([1., 0.]), draw_id)
    prediction = model.predict()
    assert np.all(prediction[:2, 0] > .7)
    assert np.all(prediction[:2, 1] < .3)
    for draw_id in range(601, 665):
        model.observe(np.array([0., 1.]), draw_id)
    assert model.predict()[0, 1] > model.predict()[1, 1] + .15


def test_markov_expert_learns_alternation_before_receiving_next_outcome():
    model = _model(1)
    for draw_id in range(1, 513):
        model.observe(np.array([float(draw_id % 2)]), draw_id)
    assert model.predict()[2, 0] > .9
    model.observe(np.ones(1), 513)
    assert model.predict()[2, 0] < .1


def test_gap_expert_learns_observed_cycle_without_making_unseen_numbers_due():
    model = _model(1)
    for draw_id in range(1, 901):
        model.observe(np.array([float(draw_id % 3 == 0)]), draw_id)
    assert model.predict()[3, 0] < .15
    model.observe(np.zeros(1), 901)
    assert model.predict()[3, 0] < .15
    model.observe(np.zeros(1), 902)
    assert model.predict()[3, 0] > .85
    unseen = _model(1, .1)
    for draw_id in range(1, 301):
        unseen.observe(np.zeros(1), draw_id)
    assert unseen.predict()[3, 0] == .1


def test_missing_ids_decay_observed_frequency_without_inventing_zero_outcomes():
    close, distant = _model(1), _model(1)
    for model in (close, distant):
        model.observe(np.ones(1), 1)
    close.observe(np.zeros(1), 2)
    distant.observe(np.zeros(1), 1000)
    assert close.predict()[0, 0] > distant.predict()[0, 0]
    # Một quan sát 0 sau khoảng mất rất dài: posterior = 16 / 33.
    assert distant.predict()[0, 0] == pytest.approx(16 / 33)
    assert distant.seen == 2


def test_missing_ids_skip_transitions_and_censor_gap_until_new_observed_hit():
    model = _model(1)
    model.observe(np.ones(1), 1)
    model.observe(np.zeros(1), 20)
    assert model.predict()[2, 0] == .5
    assert model.predict()[3, 0] == .5
    model.observe(np.zeros(1), 21)
    model.observe(np.ones(1), 22)
    assert model.predict()[3, 0] == .5
    model.observe(np.zeros(1), 23)
    assert model.predict()[3, 0] == .5  # Chưa từng chấm tuổi 2.


def test_two_hits_separated_by_missing_ids_are_not_a_learned_repeat():
    model = _model(1)
    model.observe(np.ones(1), 1)
    model.observe(np.ones(1), 20)
    np.testing.assert_array_equal(model.predict()[2:, 0], [.5, .5])


def test_future_target_across_missing_ids_does_not_use_stale_transition_or_gap():
    model = _model(1)
    for draw_id in range(1, 301):
        model.observe(np.ones(1), draw_id)
    before = deepcopy(model.to_dict())
    assert model.predict()[2, 0] > .9 and model.predict()[3, 0] > .9
    far = model.predict(next_id=1000)
    np.testing.assert_array_equal(far[2:, 0], [.5, .5])
    assert .5 <= far[0, 0] < model.predict()[0, 0]
    assert model.to_dict() == before
    np.testing.assert_array_equal(model.predict(next_id=301), model.predict())


@pytest.mark.parametrize('next_id', [0, 1, True, 1.5, '2'])
def test_invalid_prediction_target_is_rejected_without_mutation(next_id):
    model = _model()
    model.observe(np.array([1., 0.]), 1)
    before = deepcopy(model.to_dict())
    with pytest.raises((TypeError, ValueError)):
        model.predict(next_id=next_id)
    assert model.to_dict() == before


def test_fractional_targets_keep_presence_conditioning_and_finite_probabilities():
    model = _model(3, .1)
    for draw_id in range(1, 101):
        model.observe(np.array([.25, .5, 0.]), draw_id)
    prediction = model.predict()
    assert prediction.shape == (4, 3)
    assert np.isfinite(prediction).all()
    assert np.all((prediction > 0) & (prediction < 1))
    assert prediction[2, 0] > .2 and prediction[2, 1] > .35
    assert prediction[3, 0] > .18 and prediction[3, 1] > .3


def test_json_roundtrip_and_chunked_replay_are_bit_exact():
    rng = np.random.default_rng(17)
    rows = rng.integers(0, 5, size=(80, 3)) / 4
    whole, split = _model(3, .2), _model(3, .2)
    ids = np.arange(1, 81) + np.arange(80) // 9
    for row, draw_id in zip(rows, ids):
        whole.observe(row, int(draw_id))
    for row, draw_id in zip(rows[:37], ids[:37]):
        split.observe(row, int(draw_id))
    cls = type(split)
    split = cls.from_dict(json.loads(json.dumps(split.to_dict(), allow_nan=False)), nodes=3, base=.2)
    for row, draw_id in zip(rows[37:], ids[37:]):
        split.observe(row, int(draw_id))
    assert split.to_dict() == whole.to_dict()
    np.testing.assert_array_equal(split.predict(), whole.predict())


@pytest.mark.parametrize('nodes,base', [(0, .5), (True, .5), (2., .5), (2, 0), (2, 1), (2, True), (2, np.nan), (2, np.inf)])
def test_invalid_configuration_is_rejected(nodes, base):
    with pytest.raises((TypeError, ValueError)):
        _model(nodes, base)


@pytest.mark.parametrize('target,draw_id', [([1.], 2), ([[1., 0.]], 2), ([np.nan, 0], 2),
    ([np.inf, 0], 2), ([-.1, 0], 2), ([1.1, 0], 2), (['1', '0'], 2), ([1, 0], True),
    ([1, 0], 0), ([1, 0], 1), ([1, 0], 2.)])
def test_bad_observation_preserves_all_state(target, draw_id):
    model = _model()
    model.observe(np.array([1., 0.]), 1)
    before = deepcopy(model.to_dict())
    with pytest.raises((TypeError, ValueError)):
        model.observe(target, draw_id)
    assert model.to_dict() == before


def test_checkpoint_rejects_configuration_mismatch_missing_and_unknown_fields():
    model = _model()
    cls = type(model)
    for nodes, base in ((3, .5), (2, .2)):
        with pytest.raises(ValueError):
            cls.from_dict(model.to_dict(), nodes=nodes, base=base)
    for changed in ({}, {**model.to_dict(), 'executable': 'payload'}):
        with pytest.raises((TypeError, ValueError)):
            cls.from_dict(changed, nodes=2, base=.5)


def test_serialized_state_is_detached_and_bad_counters_are_rejected():
    model = _model()
    model.observe(np.array([.5, 0.]), 1)
    before = deepcopy(model.to_dict())
    for key, value in (('seen', True), ('seen', -1), ('seen', 2), ('last_id', 0), ('last_id', None)):
        state = deepcopy(before)
        state[key] = value
        with pytest.raises((TypeError, ValueError)):
            type(model).from_dict(state, nodes=2, base=.5)
    detached = model.to_dict()
    detached['seen'] = 0
    assert model.to_dict() == before


@pytest.mark.parametrize('field,value', [('version', True), ('nodes', True), ('base', '0.5'),
    ('frequency_mass', [np.inf, 1]), ('frequency_mass', [1]), ('frequency_mass', ['1', '1']),
    ('frequency_mass', [True, True]), ('frequency_success', [[2, 0], [1, 0]]),
    ('frequency_success', [[np.nan, 0], [1, 0]]), ('frequency_success', [[-.1, 0], [1, 0]]),
    ('markov_total', [[.5, 0], [0, 0]]), ('markov_success', [[1, 0], [0, 0]]),
    ('gap_age', [1e100, 0]), ('gap_age', [1e20, 0]), ('gap_age', [-1, 0]), ('previous_present', [1, 0]),
    ('gap_known', [False, False])])
def test_malformed_checkpoint_arrays_or_configuration_are_rejected(field, value):
    model = _model()
    model.observe(np.array([1., 0.]), 1)
    state = model.to_dict()
    state[field] = value
    with pytest.raises((TypeError, ValueError)):
        type(model).from_dict(state, nodes=2, base=.5)


def test_checkpoint_gap_age_cannot_exceed_observed_history_length():
    model = _model(1)
    model.observe(np.ones(1), 1)
    model.observe(np.zeros(1), 2)
    state = model.to_dict()
    state['gap_age'] = [64]
    with pytest.raises(ValueError):
        type(model).from_dict(state, nodes=1, base=.5)
