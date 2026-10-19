"""Nâng cấp chính sách phải giữ issue cũ và không ghi lùi snapshot đã học."""
from copy import deepcopy
import json

import numpy as np
import pytest

from tests.test_vlm_forecast_pipeline import mega_series
from vlm.forecast.distribution import Law
from vlm.forecast.pipeline import MLConfig, MLForecaster
from vlm.forecast.service import _event, refresh_snapshot


def _config(*, multi_agent=False):
    return MLConfig(bootstrap=8, backends=(), search_nodes=1, multi_agent=multi_agent)


def _old_issue(tmp_path):
    series = mega_series(2)
    series.dates[-1] = '2026-01-04'
    model = MLForecaster('mega645', _config())
    model.update(series.head(1))
    assert model.issue('2026-01-04T18:00:00+07:00', '2026-01-04T17:00:00+07:00')
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    event = _event(tmp_path, {'event': 'issue', 'product': 'mega645', 'target_id': 2,
                            'history_sha256': model.prefix_hash, 'pending': deepcopy(model.pending)})
    return series, model, event


def test_upgrade_scores_previously_issued_law_before_retraining(tmp_path):
    series, model, event = _old_issue(tmp_path)
    ledger = tmp_path / 'ml-ledger.jsonl'
    original = ledger.read_bytes()
    frozen = event['pending']['laws']['main']
    law = Law(model.components['main'].spec, np.array(frozen['values']), np.array(frozen['mixture']))
    row = series.obs['main']['X'][1]
    expected = law.log_likelihood(row) - law.null_log_likelihood(row)

    upgraded, _, _ = refresh_snapshot('mega645', series, tmp_path,
                                     config=_config(multi_agent=True), issue=False)

    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert ledger.read_bytes().startswith(original)
    assert len(events) == 2
    assert events[0] == event
    assert events[1]['event'] == 'score' and events[1]['target_id'] == 2
    assert events[1]['gain_nats'] == pytest.approx(expected, abs=1e-12)
    assert upgraded.config.multi_agent
    assert upgraded.components['main'].multi_agent.knowledge.total_observations == 2


def test_upgrade_keeps_unscored_first_issue_before_its_result(tmp_path):
    series, _, event = _old_issue(tmp_path)
    original = (tmp_path / 'ml-ledger.jsonl').read_bytes()

    upgraded, _, _ = refresh_snapshot('mega645', series.head(1), tmp_path,
                                     config=_config(multi_agent=True), issue=False)

    assert upgraded.config.multi_agent
    assert upgraded.pending == event['pending']
    assert upgraded.pending_valid()
    assert (tmp_path / 'ml-ledger.jsonl').read_bytes() == original


def test_upgrade_ignores_older_snapshot_before_resetting_checkpoint(tmp_path):
    series = mega_series(2)
    model = MLForecaster('mega645', _config())
    model.update(series)
    path = tmp_path / 'ml' / 'mega645.json.gz'
    model.save(path)
    original = path.read_bytes()

    restored, learned, summary = refresh_snapshot('mega645', series.head(1), tmp_path,
                                               config=_config(multi_agent=True), issue=False)

    assert learned == 0 and restored.last_id == model.last_id
    assert summary['note'] == 'stale_snapshot_ignored'
    assert path.read_bytes() == original
