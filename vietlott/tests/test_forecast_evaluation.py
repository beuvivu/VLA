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


def test_cli_records_executable_source_manifest(tmp_path, monkeypatch) -> None:
    """Removing automatic source provenance must make this test fail."""
    import hashlib
    import json
    import runpy
    from pathlib import Path

    from vlm.forecast import pipeline

    script = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_adaptive.py'
    main = runpy.run_path(str(script))['main']
    monkeypatch.setitem(main.__globals__, 'load_series', lambda *args, **kwargs: mega_series(8))
    output = tmp_path / 'report.json'
    assert main(['--seed-dir', str(tmp_path), '--output', str(output), '--label', 'fixture',
                 '--draws', '8', '--initial-draws', '4', '--products', 'mega645']) == 0
    report = json.loads(output.read_text())
    provenance = report['source_provenance']
    source_root = Path(pipeline.__file__).resolve().parents[2]
    expected = {f'src/{path.relative_to(source_root).as_posix()}': path.read_bytes()
                for path in source_root.rglob('*.py')}
    expected['scripts/evaluate_adaptive.py'] = script.read_bytes()
    digest = hashlib.sha256()
    for name, raw in sorted(expected.items()):
        digest.update(name.encode('utf-8') + b'\0' + raw)
    assert provenance['schema_version'] == 1
    assert provenance['hash_algorithm'] == 'sha256(sorted POSIX path + NUL + raw file bytes)'
    assert provenance['files'] == {name: hashlib.sha256(raw).hexdigest()
                                   for name, raw in sorted(expected.items())}
    assert provenance['benchmark_source_tree_sha256'] == digest.hexdigest()
    assert 'completed_at' in report


@pytest.mark.parametrize('changed', ['scorer', 'evaluation', 'new_module', 'runner'])
def test_source_manifest_detects_changed_benchmark_code(tmp_path, changed) -> None:
    """Omitting any scorer, evaluator, dependency or runner must be detected."""
    import runpy
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_adaptive.py'
    namespace = runpy.run_path(str(script))
    source_root = tmp_path / 'src'
    source_root.mkdir()
    scorer = source_root / 'pipeline.py'
    evaluator = source_root / 'evaluation.py'
    runner = tmp_path / 'evaluate_adaptive.py'
    for path in (scorer, evaluator, runner):
        path.write_text('value = 1\n')
    manifest = namespace['_source_provenance']
    before = manifest(source_root, runner)
    paths = {'scorer': scorer, 'evaluation': evaluator,
             'new_module': source_root / 'dependency.py', 'runner': runner}
    paths[changed].write_text('value = 2\n')
    after = manifest(source_root, runner)
    assert after['benchmark_source_tree_sha256'] != before['benchmark_source_tree_sha256']
    assert after['files'] != before['files']
    assert after == manifest(source_root, runner)


def test_cli_does_not_complete_report_when_source_changes_during_run(tmp_path, monkeypatch) -> None:
    """Removing the end-of-run source check must allow this test to catch it."""
    import json
    import runpy
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_adaptive.py'
    copy = tmp_path / 'evaluate_adaptive.py'
    copy.write_bytes(script.read_bytes())
    main = runpy.run_path(str(copy))['main']
    monkeypatch.setitem(main.__globals__, 'load_series', lambda *args, **kwargs: mega_series(8))

    def change_runner(series, config, *, initial_draws):
        result = evaluate_series(series, config, initial_draws=initial_draws)
        copy.write_bytes(copy.read_bytes() + b'\n# changed during benchmark\n')
        return result

    monkeypatch.setitem(main.__globals__, 'evaluate_series', change_runner)
    output = tmp_path / 'partial.json'
    with pytest.raises(RuntimeError, match='source changed'):
        main(['--seed-dir', str(tmp_path), '--output', str(output), '--label', 'fixture',
              '--draws', '8', '--initial-draws', '4', '--products', 'mega645'])
    report = json.loads(output.read_text())
    assert 'completed_at' not in report
    assert report['source_provenance']['files']['scripts/evaluate_adaptive.py']


@pytest.mark.parametrize('problem', ['missing_root', 'file_root', 'unreadable_subtree'])
def test_source_manifest_rejects_incomplete_source_tree(tmp_path, monkeypatch, problem) -> None:
    """A scan that silently drops source files must never certify a benchmark."""
    import os
    import runpy
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_adaptive.py'
    manifest = runpy.run_path(str(script))['_source_provenance']
    source_root = tmp_path / 'src'
    expected = FileNotFoundError
    if problem == 'file_root':
        source_root.write_text('value = 1\n')
        expected = NotADirectoryError
    elif problem == 'unreadable_subtree':
        hidden = source_root / 'hidden'
        hidden.mkdir(parents=True)
        (hidden / 'scorer.py').write_text('value = 1\n')
        scandir = os.scandir

        def deny_subtree(path):
            if Path(path) == hidden:
                raise PermissionError('source subtree cannot be scanned')
            return scandir(path)

        monkeypatch.setattr(os, 'scandir', deny_subtree)
        expected = PermissionError
    with pytest.raises(expected):
        manifest(source_root, script)
