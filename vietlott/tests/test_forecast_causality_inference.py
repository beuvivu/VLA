"""Hồi quy cho ngữ cảnh nhân quả, lịch sử sửa và đơn vị suy luận kỳ quay."""
from copy import deepcopy
from datetime import date
from itertools import combinations
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import stats

from vietlott_engine.api.routers.analytics import gcn_next, gcn_skill
from vietlott_engine.api.routers.catalog import catalogue
from vietlott_engine.core.exceptions import InsufficientDataError
from vietlott_engine.core.games import LOTTO_535, MEGA_645, POWER_655
from vietlott_engine.core.history import DrawHistory
from vietlott_engine.core.products import ProductCode
from vietlott_engine.forecast.data import Series, SetSpec, matrix_series
from vietlott_engine.forecast.engine import Forecaster, record, refresh, score_ledger, scoreboard, state_path
from vietlott_engine.forecast.schedule import target_draw_time
from vietlott_engine.inference.changepoint import changepoint_report
from vietlott_engine.inference.multiple_testing import per_number_deviations
from vietlott_engine.inference.power import odds_for_inclusion, power_equivalence_report, ticket_match_distribution
from vietlott_engine.inference.predictive import calibration, diebold_mariano, newey_west_variance, spiegelhalter_z
from vietlott_engine.inference.report import inference_report
from vietlott_engine.ml_models.features import SnapshotBuilder, build_snapshots
from vietlott_engine.ml_models.gcn import GCNConfig, GCNPredictor, walk_forward_skill
from vlm.forecast.features import FeatureState
from vlm.forecast.pipeline import MLConfig, MLForecaster
from tests.conftest import make_history


def test_pmi_never_invents_edges_for_unobserved_pairs():
    b = SnapshotBuilder(6, 2)
    b.update(np.array([1, 1, 0, 0, 0, 0]))
    graph = b.snapshots().a_hat[-1]
    unseen = graph[2:].copy()
    unseen[np.arange(4), np.arange(2, 6)] = 0
    assert not unseen.any()
    assert np.isfinite(graph).all()
    np.testing.assert_array_equal(graph, graph.T)
    b.update(np.array([0, 0, 1, 1, 0, 0]))
    planted = b.snapshots().a_hat[-1]
    assert planted[0, 1] > 0 and planted[2, 3] > 0
    assert planted[0, 2] == 0
    prefix = b.snapshots().a_hat.copy()
    b.update(np.array([0, 0, 0, 0, 1, 1]))
    np.testing.assert_array_equal(prefix, b.snapshots().a_hat[:3])


def test_cluster_rate_averages_only_observed_neighbors():
    f = FeatureState(SetSpec(6, 2))
    f.observe(np.array([1, 1, 0, 0, 0, 0]), 1, '2026-01-02')
    cluster = f.snapshot(2, '2026-01-03')[:, f.names.index('cluster_rate')]
    np.testing.assert_array_equal(cluster, [1, 1, 0, 0, 0, 0])


def _scheduled_series(product, on_day=1):
    n, k = (35, 5) if product == 'lotto535' else (45, 6)
    x = np.zeros((on_day, n), bool)
    x[:, :k] = True
    obs = {'main':{'X':x, 'bonus':np.zeros(on_day, int)}}
    if product == 'lotto535':
        c = np.zeros((on_day, 1, 12), int)
        c[:, 0, 0] = 1
        obs['special'] = {'C':c}
    return Series(ProductCode(product), np.arange(1, on_day+1), np.full(on_day, '2026-01-02'), obs)


@pytest.mark.parametrize('product,on_day', [('mega645', 1), ('lotto535', 1), ('lotto535', 2)])
def test_report_portfolio_and_issue_share_scheduled_law(product, on_day):
    f = MLForecaster(product, MLConfig(backends=(), bootstrap=8, warmup=1, search_nodes=8))
    f.update(_scheduled_series(product, on_day))
    # Ngày target ảnh hưởng trực tiếp tới law, đủ mạnh để phát hiện caller bỏ ngữ cảnh.
    comp = f.components['main']
    idx = comp.features.names.index('elapsed_days')
    comp.logistics[0].theta[idx] = 3
    comp.logistics[0].theta[0] = 1
    target = target_draw_time(f.product, date(2026, 1, 2), on_day)
    target_day = target.date().isoformat()
    expected = comp.law(target_day).marginals()
    before = f.report(top_n=2, budget=20_000)
    np.testing.assert_array_equal(before['components'][0]['marginals_model'], expected)
    assert before['components'][0]['features']['elapsed_days'] == pytest.approx((target.date()-date(2026, 1, 2)).days / 7)
    assert before['target_date'] == target_day
    assert before['target_time'] == target.isoformat()
    made = '2026-01-02T14:00:00+07:00' if product == 'lotto535' and on_day == 1 else '2026-01-02T22:00:00+07:00'
    assert f.issue(target.isoformat(), made)
    after = f.report(top_n=2, budget=20_000)
    np.testing.assert_allclose(after['components'][0]['marginals_model'], expected, rtol=1e-12, atol=0)
    for old, new in zip(before['components'][0]['top'], after['components'][0]['top'], strict=True):
        assert old['numbers'] == new['numbers']
        assert old['p_model'] == pytest.approx(new['p_model'], rel=1e-12, abs=0)
        assert old['feature_support'] == new['feature_support']
    for old, new in zip(before['portfolio']['tickets'], after['portfolio']['tickets'], strict=True):
        assert old['numbers'] == new['numbers'] and old['special'] == new['special']
        assert old['p_jackpot_model'] == pytest.approx(new['p_jackpot_model'], rel=1e-12, abs=0)
    first = deepcopy(f.pending)
    comp.logistics[0].theta[:] = 9
    assert f.issue(target.isoformat(), made)
    assert f.pending == first
    assert f.report(top_n=2, budget=20_000)['components'][0]['top'] == after['components'][0]['top']


def test_portfolio_rejects_invalid_pending_instead_of_reading_its_law():
    f = MLForecaster('mega645', MLConfig(backends=(), search_nodes=1))
    f.update(_scheduled_series('mega645'))
    assert f.issue('2026-01-04T18:00:00+07:00', '2026-01-02T22:00:00+07:00')
    f.pending['history_sha256'] = 'forged'
    with pytest.raises(ValueError, match='Unverified'):
        f.portfolio(1, 10_000)


class EmptyProductState:
    repository = SimpleNamespace(load=lambda code: [])

    def product_history(self, code):
        raise InsufficientDataError('empty')


def test_catalogue_handles_missing_history_only():
    assert all(e.stored_draws == 0 for e in catalogue(EmptyProductState()))


@pytest.mark.parametrize('error', [PermissionError('denied'), ValueError('corrupt')])
def test_catalogue_does_not_hide_store_failures(error):
    class Broken(EmptyProductState):
        def product_history(self, code):
            raise error
    with pytest.raises(type(error)):
        catalogue(Broken())


@pytest.mark.parametrize('change', ['numbers', 'date', 'backfill', 'bonus', 'old_checkpoint'])
def test_legacy_corrected_prefix_refits_without_rewriting_issued_ledger(tmp_path, change):
    spec = POWER_655 if change == 'bonus' else MEGA_645
    original = matrix_series(make_history(spec, 12, seed=2))
    if change == 'backfill':
        original.draw_ids += 1
    f = Forecaster(spec.code.value)
    f.update(original)
    record(tmp_path, f.forecast())
    ledger = (tmp_path/'ledger.jsonl').read_bytes()
    if change == 'old_checkpoint':
        f.state.pop('prefix_hash', None)
        f.state.pop('prefix_count', None)
    f.save(state_path(tmp_path, f.product))
    revised = deepcopy(original)
    if change == 'numbers':
        revised.obs['main']['X'][0] = revised.obs['main']['X'][1]
    elif change == 'date':
        revised.dates[0] -= np.timedelta64(1, 'D')
    elif change == 'bonus':
        revised.obs['main']['bonus'][0] = np.flatnonzero(~revised.obs['main']['X'][0])[0] + 1
        if revised.obs['main']['bonus'][0] == original.obs['main']['bonus'][0]:
            revised.obs['main']['bonus'][0] = np.flatnonzero(~revised.obs['main']['X'][0])[1] + 1
    elif change == 'backfill':
        revised = Series(revised.product, np.r_[1, revised.draw_ids], np.r_[revised.dates[0]-np.timedelta64(1, 'D'), revised.dates],
                         {'main':{k:np.concatenate([v[:1], v]) for k, v in revised.obs['main'].items()}})
    updated, learned, scored = refresh(f.product, revised, tmp_path)
    assert learned == len(revised)
    assert scored == [] and (tmp_path/'ledger.jsonl').read_bytes() == ledger
    reference = Forecaster(f.product)
    reference.update(revised)
    assert updated.to_dict() == reference.to_dict()
    assert updated.state['draws'] == len(revised)


@pytest.mark.parametrize('start,end', [(4, 4), (6, 4), (0, 1), (-1, 5), (0, 9)])
def test_gcn_rejects_empty_invalid_or_no_train_split(start, end):
    snaps = build_snapshots(make_history(MEGA_645, 8))
    model = GCNPredictor(6, GCNConfig(epochs=1))
    before = model.params.copy()
    with pytest.raises(ValueError):
        model.fit(snaps, start, end)
    for old, new in zip(before.as_list(), model.params.as_list()):
        np.testing.assert_array_equal(old, new)
    assert model.history == []


@pytest.mark.parametrize('model', ['gcn', 'logistic'])
def test_walk_forward_rejects_no_training_or_short_scoring_block(model):
    snaps = build_snapshots(make_history(MEGA_645, 25))
    with pytest.raises(ValueError, match='train|test|draw'):
        walk_forward_skill(snaps, 6, 5, model=model)


@pytest.mark.parametrize('endpoint', [gcn_skill, gcn_next])
def test_analytics_does_not_report_untrained_gcn_for_25_draws(endpoint):
    state = SimpleNamespace(history=lambda spec: make_history(spec, 25))
    with pytest.raises(InsufficientDataError):
        if endpoint is gcn_skill:
            endpoint(spec=MEGA_645, first_test=100, refit_every=20, model='gcn', state=state)
        else:
            endpoint(spec=MEGA_645, state=state)


@pytest.mark.parametrize('target', [[1, 1, 0, 0], [1, .5, .5, 0]])
def test_boundary_inclusion_odds_are_finite_and_approach_valid_simplex(target):
    w = odds_for_inclusion(np.array(target), 2)
    assert np.isfinite(w).all() and (w > 0).all()
    subsets = list(combinations(range(4), 2))
    q = np.array([np.prod(w[list(s)]) for s in subsets])
    q /= q.sum()
    marginal = np.array([sum(q[j] for j, s in enumerate(subsets) if i in s) for i in range(4)])
    np.testing.assert_allclose(marginal, target, atol=1e-5)
    assert ticket_match_distribution(w, np.array([1, 2]), 2).sum() == pytest.approx(1)


@pytest.mark.parametrize('target', [[1.1, .9, 0, 0], [0.5]*4+[0.1], [float('nan'), 1, 1, 0], [float('inf'), 0, 0, 0]])
def test_inclusion_odds_reject_invalid_simplex(target):
    with pytest.raises(ValueError):
        odds_for_inclusion(np.array(target), 2)


def test_power_report_remains_finite_for_twenty_identical_draws():
    h = DrawHistory.from_arrays(POWER_655, np.tile(np.arange(1, 7), (20, 1)))
    rep = power_equivalence_report(h)
    assert np.isfinite(rep.best_case_ticket_rtp) and np.isfinite(rep.fair_ticket_rtp)
    assert 'regulariz' in rep.interpretation.lower() or 'co nhẹ' in rep.interpretation.lower()


def test_calibration_uses_draw_covariance_and_serial_hac_for_one_of_four():
    p = np.tile([.1, .2, .3, .4], (400, 1))
    choice = np.repeat(np.random.default_rng(7).choice(4, 100, p=p[0]), 4)
    y = np.eye(4)[choice]
    residual = ((y-p)*(1-2*p)).sum(axis=1)
    z_expected = residual.mean()/np.sqrt(newey_west_variance(residual)/len(residual))
    z, pv = spiegelhalter_z(p, y)
    assert z == pytest.approx(z_expected)
    assert pv == pytest.approx(2*stats.norm.sf(abs(z_expected)))
    rep = calibration(p, y)
    assert sum(b['count'] for b in rep.bins) == y.size


def test_uniform_fixed_size_draw_has_zero_calibration_residual():
    p = np.full((100, 4), .25)
    y = np.eye(4)[np.arange(100) % 4]
    assert spiegelhalter_z(p, y) == (0, 1)


def test_calibration_one_dimensional_retains_bernoulli_contract():
    p = np.full(100, .2)
    y = np.r_[np.ones(25), np.zeros(75)]
    expected = ((y-p)*(1-2*p)).sum()/np.sqrt(((1-2*p)**2*p*(1-p)).sum())
    assert spiegelhalter_z(p, y)[0] == pytest.approx(expected)


@pytest.mark.parametrize('sample', [[], [1.]])
def test_dm_rejects_empty_or_single_observation(sample):
    with pytest.raises(ValueError, match='at least|observations'):
        diebold_mariano(np.array(sample))


def test_per_number_uses_requested_alpha():
    h = make_history(MEGA_645, 60, seed=3)
    rep = per_number_deviations(h, sims=30, seed=3, alpha=.25)
    assert rep.any_significant_fwer == (rep.min_westfall_young_p < .25)
    assert rep.min_westfall_young_p > .05 and rep.any_significant_fwer


def test_changepoint_uses_requested_alpha():
    h = make_history(MEGA_645, 60, seed=8)
    rep = changepoint_report(h, sims=30, seed=3, alpha=.25)
    assert .05 < min(rep.window_scan.p_value, rep.cusum.p_value) < .25
    assert 'Significant after scan adjustment' in rep.interpretation


@pytest.mark.parametrize('seed', [3, 8])
def test_inference_report_forwards_alpha_to_both_decision_subreports(seed):
    h = make_history(MEGA_645, 60, seed=seed)
    alpha = .25
    rep = inference_report(h, sims=30, seed=3, alpha=alpha)
    assert rep.per_number.any_significant_fwer == (rep.per_number.min_westfall_young_p < alpha)
    cp_significant = min(rep.changepoints.window_scan.p_value, rep.changepoints.cusum.p_value) < alpha
    assert ('Significant after scan adjustment' in rep.changepoints.interpretation) == cp_significant
    assert rep.per_number.any_significant_fwer or cp_significant


def test_legacy_atomic_save_failure_keeps_old_pack_and_removes_staging(tmp_path, monkeypatch):
    import os
    path = tmp_path/'legacy.json'
    f = Forecaster('mega645')
    f.update(matrix_series(make_history(MEGA_645, 2)))
    f.save(path)
    original = path.read_bytes()
    f.update(matrix_series(make_history(MEGA_645, 3)))
    def fail_replace(src, dst):
        raise OSError('replace failed')
    monkeypatch.setattr(os, 'replace', fail_replace)
    with pytest.raises(OSError, match='replace failed'):
        f.save(path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('p,y', [(np.zeros((2, 4)), np.zeros((4, 2))),
                                (np.full((1, 4), .25), np.array([[1, 0, 0, 0]])),
                                (np.full((2, 4), np.nan), np.zeros((2, 4)))])
def test_calibration_rejects_invalid_or_short_draw_matrices(p, y):
    with pytest.raises(ValueError):
        calibration(p, y)


@pytest.mark.parametrize('sample,horizon', [(np.array([1., np.nan]), 1), (np.ones((2, 2)), 1), (np.ones(2), 2)])
def test_dm_rejects_nonfinite_vector_or_unavailable_horizon(sample, horizon):
    with pytest.raises(ValueError):
        diebold_mariano(sample, horizon=horizon)


@pytest.mark.parametrize('spec', [MEGA_645, POWER_655, LOTTO_535])
def test_uniform_fixed_size_calibration_does_not_treat_roundoff_as_signal(spec):
    h = make_history(spec, 400, seed=8)
    p = np.full(h.incidence.shape, spec.pick/spec.pool_size)
    assert spiegelhalter_z(p, h.incidence) == (0, 1)


def test_nonzero_constant_draw_residual_is_not_erased_by_roundoff_guard():
    p = np.full((100, 4), .2)
    y = np.eye(4)[np.arange(100) % 4]
    z, pv = spiegelhalter_z(p, y)
    assert np.isfinite(z) and z > 10 and pv < .001


@pytest.mark.parametrize('failure', ['partial_write', 'replace'])
def test_legacy_ledger_write_failure_preserves_issued_laws_and_scores_once_on_retry(tmp_path, monkeypatch, failure):
    import json
    import os
    from pathlib import Path
    series = matrix_series(make_history(MEGA_645, 10, seed=13))
    f = Forecaster('mega645')
    f.update(series.head(9))
    issued = record(tmp_path, f.forecast())
    path = tmp_path/'ledger.jsonl'
    original = path.read_bytes()
    def fail_replace(src, dst):
        raise OSError('replace failed')
    original_write = Path.write_text
    original_fdopen = os.fdopen
    def partial_path_write(target, data, *args, **kw):
        original_write(target, data[:30], *args, **kw)
        raise OSError('partial write failed')
    class PartialStream:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def write(self, data):
            self.stream.write(data[:30])
            self.stream.flush()
            raise OSError('partial write failed')
        def __getattr__(self, name):
            return getattr(self.stream, name)
    with monkeypatch.context() as inject:
        if failure == 'partial_write':
            inject.setattr(Path, 'write_text', partial_path_write)
            inject.setattr(os, 'fdopen', lambda *args, **kw: PartialStream(original_fdopen(*args, **kw)))
        else:
            inject.setattr(os, 'replace', fail_replace)
        with pytest.raises(OSError):
            score_ledger(tmp_path, series)
        assert path.read_bytes() == original
        assert not list(tmp_path.glob('*.tmp'))
    scored = score_ledger(tmp_path, series)
    assert len(scored) == 1 and scored[0]['target_id'] == 10
    assert {k:v for k, v in scored[0].items() if k != 'score'} == {k:v for k, v in issued.items() if k != 'score'}
    assert score_ledger(tmp_path, series) == []
    assert len(path.read_text().splitlines()) == 1
    assert json.loads(path.read_text()) == scored[0]
    assert scoreboard(tmp_path)[0]['scored'] == 1


def test_pmi_stays_finite_when_positive_degree_products_underflow():
    builder = SnapshotBuilder(6, 2, graph_decay=1e-200)
    builder.update(np.array([1, 1, 0, 0, 0, 0]))
    builder.update(np.array([0, 0, 1, 1, 0, 0]))
    graph = builder.snapshots().a_hat[-1]
    assert np.isfinite(graph).all()
    np.testing.assert_array_equal(graph, graph.T)
    assert graph[0, 1] > 0 and graph[2, 3] == 0
    assert graph[0, 2] == 0 and graph[4, 5] == 0 and graph[4, 4] == 1


def test_pmi_is_symmetric_when_zero_signal_rounds_near_machine_precision():
    builder = SnapshotBuilder(3, 2, graph_decay=1)
    for row in [[1, 1, 0], [0, 1, 1]] * 2:
        builder.update(np.array(row))
    graph = builder.snapshots().a_hat[-1]
    np.testing.assert_array_equal(graph, graph.T)
