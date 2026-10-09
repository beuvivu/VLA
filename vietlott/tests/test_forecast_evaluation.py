"""Kiểm giao thức đánh giá nhân quả và ghép benchmark cùng kỳ."""
from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from tests.test_vlm_forecast_pipeline import mega_series
from vlm.forecast.evaluation import compare_runs, evaluate_series
from vlm.forecast.pipeline import MLConfig, MLForecaster


def test_evaluation_scores_frozen_prefix_before_learning() -> None:
    series = mega_series(8)
    original = series.obs['main']['X'].copy()
    config = MLConfig(bootstrap=8, backends=(), search_nodes=1)
    prefix = MLForecaster('mega645', config)
    prefix.update(series.head(4))
    row = series.obs['main']['X'][4]
    law = prefix.components['main'].law(str(series.dates[4]), next_id=5)
    expected = law.log_likelihood(row) - law.null_log_likelihood(row)
    result = evaluate_series(series, config, initial_draws=4)
    assert result['draws'][0]['gain_nats'] == pytest.approx(expected)
    assert result['test_draws'] == 4 and result['test_first_id'] == 5
    assert result['live_scored'] == 0 and not result['live_certification']
    np.testing.assert_array_equal(series.obs['main']['X'], original)
    changed = mega_series(8)
    changed.obs['main']['X'][5:] = np.roll(changed.obs['main']['X'][5:], 3, axis=1)
    changed_result = evaluate_series(changed, config, initial_draws=4)
    assert changed_result['draws'][0] == result['draws'][0]
    assert changed_result['data_sha256'] != result['data_sha256']


@pytest.mark.parametrize('problem', ['no_holdout', 'no_train', 'reversed_dates'])
def test_evaluation_rejects_invalid_chronology(problem: str) -> None:
    series = mega_series(8)
    initial = 8 if problem == 'no_holdout' else 0 if problem == 'no_train' else 4
    if problem == 'reversed_dates':
        series.dates[6:] = '2026-01-01'
    with pytest.raises(ValueError):
        evaluate_series(series, MLConfig(backends=()), initial_draws=initial)


def _run(gains: list[float]) -> dict:
    draws = [{'id':i+5, 'date':'2026-01-02', 'gain_nats':gain} for i, gain in enumerate(gains)]
    return {'results':[{'product':'mega645', 'data_sha256':'same', 'test_draws':len(draws), 'draws':draws}]}


def test_comparison_uses_paired_losses_and_reports_fdr() -> None:
    baseline = _run([.1, .2, -.1, -.2, .3, -.3, .2, -.2])
    candidate = _run([.2, .1, .2, -.1, .2, -.2, .3, -.1])
    comparison = compare_runs(baseline, candidate)[0]
    expected = np.mean([b['gain_nats']-a['gain_nats'] for a, b in zip(baseline['results'][0]['draws'], candidate['results'][0]['draws'])])
    assert comparison['mean_log_gain_difference_nats'] == pytest.approx(expected)
    assert comparison['ci95'][0] <= expected <= comparison['ci95'][1]
    assert 0 <= comparison['p_value_greater'] <= comparison['q_value_bh'] <= 1


def test_comparison_resolves_registered_product_aliases() -> None:
    baseline = _run([.1, -.1, .2, -.2])
    candidate = deepcopy(baseline)
    baseline['results'][0]['product'] = 'max3d_pro'
    candidate['results'][0]['product'] = 'max3dpro'
    assert compare_runs(baseline, candidate)[0]['product'] == 'max3dpro'


@pytest.mark.parametrize('problem', ['hash', 'id', 'product', 'count'])
def test_comparison_rejects_unpaired_provenance(problem: str) -> None:
    baseline = _run([.1, -.1, .2, -.2])
    candidate = deepcopy(baseline)
    result = candidate['results'][0]
    if problem == 'hash':
        result['data_sha256'] = 'other'
    elif problem == 'id':
        result['draws'][0]['id'] = 999
    elif problem == 'product':
        result['product'] = 'power655'
    else:
        result['test_draws'] = 2
    with pytest.raises(ValueError):
        compare_runs(baseline, candidate)


def test_cli_rejects_overwriting_its_comparison_baseline(tmp_path, monkeypatch) -> None:
    import json
    import runpy
    from pathlib import Path
    main = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_adaptive.py'))['main']
    monkeypatch.setitem(main.__globals__, 'load_series', lambda *args, **kwargs: mega_series(8))
    path = tmp_path / 'baseline.json'
    original = json.dumps({'label':'incumbent', 'results':[]}).encode()
    path.write_bytes(original)
    with pytest.raises(SystemExit) as exception:
        main(['--seed-dir',str(tmp_path), '--output',str(path), '--compare-with',str(path),
              '--label','candidate', '--draws','8', '--initial-draws','4', '--products','mega645'])
    assert exception.value.code == 2 and path.read_bytes() == original
