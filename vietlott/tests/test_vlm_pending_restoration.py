"""Khôi phục phải đối chiếu law phát hành đầu tiên trước khi nhận kết quả mới."""
from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from tests.test_vlm_forecast_pipeline import mega_series
from vlm.forecast.distribution import Law
from vlm.forecast.pipeline import MLConfig, MLForecaster
from vlm.forecast.service import refresh_snapshot


@pytest.fixture
def issued_history():
    series = mega_series(2)
    series.dates[-1] = '2026-01-04'
    model = MLForecaster('mega645', MLConfig(bootstrap=8, backends=(), search_nodes=1))
    model.update(series.head(1))
    assert model.issue('2026-01-04T18:00:00+07:00', '2026-01-04T17:00:00+07:00')
    event = {'event':'issue', 'product':'mega645', 'target_id':2,
             'history_sha256':model.prefix_hash, 'pending':copy.deepcopy(model.pending)}
    law = Law(model.components['main'].spec, np.array(model.pending['laws']['main']['values']),
              np.array(model.pending['laws']['main']['mixture']))
    row = series.obs['main']['X'][1]
    gain = law.log_likelihood(row) - law.null_log_likelihood(row)
    return series, model, event, gain


def _write_issues(tmp_path, events):
    path = tmp_path / 'ml-ledger.jsonl'
    raw = ''.join(json.dumps(event) + '\n' for event in events).encode()
    path.write_bytes(raw)
    return raw


def _alter_law(pending, series):
    pending['laws']['main'] = {'values':np.where(series.obs['main']['X'][1], 7., .14)[None, :].tolist(),
                               'mixture':[1.]}


def _assert_no_live_score(model, summary, tmp_path, original):
    assert model.live_scored == 0 and model.live_log_e == model.max_live_log_e == 0.
    assert model.live_recent == [] and model.last_live_scores == [] and model.pending is None
    assert 'live_evidence_unverified' in summary['warnings'] and not summary['validated']
    path = tmp_path / 'ml-ledger.jsonl'
    assert (path.read_bytes() if path.exists() else b'') == original
    assert MLForecaster.load(tmp_path / 'ml' / 'mega645.json.gz').live_scored == 0


def test_restored_pending_substitution_scores_only_first_issued_law(tmp_path, issued_history):
    series, model, event, expected = issued_history
    original = _write_issues(tmp_path, [event])
    _alter_law(model.pending, series)
    assert model.pending_valid()
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    restored, learned, summary = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert learned == 1 and restored.live_scored == 1
    assert restored.live_log_e == pytest.approx(expected, abs=1e-12)
    scores = [json.loads(line) for line in (tmp_path / 'ml-ledger.jsonl').read_text().splitlines()]
    assert len(scores) == 2 and scores[0] == event
    assert scores[1]['gain_nats'] == pytest.approx(expected, abs=1e-12)
    assert (tmp_path / 'ml-ledger.jsonl').read_bytes().startswith(original)
    assert 'live_evidence_unverified' not in summary['warnings']
    assert MLForecaster.load(tmp_path / 'ml' / 'mega645.json.gz').live_log_e == restored.live_log_e


def test_restored_pending_without_issue_never_creates_live_score(tmp_path, issued_history):
    series, model, _, _ = issued_history
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    restored, learned, summary = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert learned == 1
    _assert_no_live_score(restored, summary, tmp_path, b'')


@pytest.mark.parametrize('field,value', [
    ('product', 'power655'), ('target_id', 3), ('history_sha256', 'other'),
    ('pending.target_id', 3), ('pending.target_id', 2.),
    ('pending.based_on_id', 0), ('pending.based_on_date', '2026-01-01'),
    ('pending.draws_on_last_date', 2), ('pending.history_sha256', 'other'),
    ('pending.target_date', '2026-01-05'), ('pending.target_time', '2026-01-04T19:00:00+07:00'),
    ('pending.made_at', '2026-01-04T18:00:00+07:00'), ('pending.made_at', None),
    ('pending.laws.main.values', [[1.] * 44]), ('pending.laws.main.values', [[float('inf')] * 45]),
    ('pending.laws.main.values', [[1e308] * 45]), ('pending.laws.main.mixture', 1.),
    ('pending.laws.main.mixture', [1.] * 2), ('pending.laws', []),
    ('pending.laws.main.mixture', [[.25]] * 4),
])
def test_restored_pending_rejects_unverifiable_first_issue(tmp_path, issued_history, field, value):
    series, model, event, _ = issued_history
    target = event
    keys = field.split('.')
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    original = _write_issues(tmp_path, [event])
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    restored, learned, summary = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert learned == 1
    _assert_no_live_score(restored, summary, tmp_path, original)


def test_restored_pending_uses_first_issue_even_when_later_issue_matches_checkpoint(tmp_path, issued_history):
    series, model, event, expected = issued_history
    later = copy.deepcopy(event)
    _alter_law(later['pending'], series)
    model.pending = copy.deepcopy(later['pending'])
    original = _write_issues(tmp_path, [event, later])
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    restored, _, _ = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert restored.live_scored == 1 and restored.live_log_e == pytest.approx(expected, abs=1e-12)
    assert (tmp_path / 'ml-ledger.jsonl').read_bytes().startswith(original)
    rows = [json.loads(line) for line in (tmp_path / 'ml-ledger.jsonl').read_text().splitlines()]
    assert len(rows) == 3 and rows[-1]['gain_nats'] == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize('invalid_field', ['made_at', 'target_id'])
def test_restored_pending_never_skips_invalid_first_issue_for_later_valid_one(tmp_path, issued_history, invalid_field):
    series, model, event, _ = issued_history
    invalid = copy.deepcopy(event)
    if invalid_field == 'made_at':
        invalid['pending']['made_at'] = None
    else:
        invalid['target_id'] = 2.
    original = _write_issues(tmp_path, [invalid, event])
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    restored, _, summary = refresh_snapshot('mega645', series, tmp_path, issue=False)
    _assert_no_live_score(restored, summary, tmp_path, original)


def test_genuine_pending_survives_restart_before_and_after_result(tmp_path, issued_history):
    series, model, event, expected = issued_history
    original = _write_issues(tmp_path, [event])
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    restored, learned, summary = refresh_snapshot('mega645', series.head(1), tmp_path, issue=False)
    assert learned == 0 and restored.pending == event['pending'] and restored.live_scored == 0
    assert (tmp_path / 'ml-ledger.jsonl').read_bytes() == original
    assert 'live_evidence_unverified' not in summary['warnings']
    restored, learned, _ = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert learned == 1 and restored.live_log_e == pytest.approx(expected, abs=1e-12)
    restored, learned, summary = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert learned == 0 and restored.live_scored == 1
    assert 'live_evidence_unverified' not in summary['warnings']


def test_zero_score_checkpoint_does_not_adopt_old_ledger_scores(tmp_path, issued_history):
    series, model, event, _ = issued_history
    previous_score = {'event':'score', 'product':'mega645', 'target_id':1,
                      'history_sha256':'previous-prefix', 'gain_nats':1.}
    original = _write_issues(tmp_path, [previous_score, event])
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    restored, learned, summary = refresh_snapshot('mega645', series.head(1), tmp_path, issue=False)
    assert learned == 0 and restored.pending == event['pending'] and restored.live_scored == 0
    assert restored.live_log_e == 0. and restored.live_recent == []
    assert 'live_evidence_unverified' not in summary['warnings']
    assert (tmp_path / 'ml-ledger.jsonl').read_bytes() == original


def test_pending_restore_does_not_hide_corrupt_middle_ledger(tmp_path, issued_history):
    series, model, event, _ = issued_history
    original = _write_issues(tmp_path, [event]) + b'{broken}\n' + json.dumps(event).encode() + b'\n'
    (tmp_path / 'ml-ledger.jsonl').write_bytes(original)
    path = tmp_path / 'ml' / 'mega645.json.gz'
    model.save(path)
    checkpoint = path.read_bytes()
    with pytest.raises(json.JSONDecodeError):
        refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert path.read_bytes() == checkpoint
    assert (tmp_path / 'ml-ledger.jsonl').read_bytes() == original
