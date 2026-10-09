"""Chạy nguyên bước tóm tắt; dữ liệu lỗi không được lộ bí mật vào log."""
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/vlm-results.yml'
SECRET = 'https://private.invalid/?token=DO_NOT_EXPOSE'


def run_summary(tmp_path):
    steps = yaml.safe_load(WORKFLOW.read_text())['jobs']['results']['steps']
    matches = [s for s in steps if s.get('id') == 'update_summary']
    assert matches, 'thiếu bước tóm tắt trạng thái cập nhật'
    step = matches[0]
    assert step['if'] == 'always()'
    summary = tmp_path / 'summary.md'
    result = subprocess.run(['bash', '-eo', 'pipefail', '-c', step['run']],
                            cwd=tmp_path, env={**os.environ, 'GITHUB_STEP_SUMMARY': str(summary)},
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    text = summary.read_text()
    assert result.stdout == text
    assert SECRET not in result.stdout + result.stderr + text
    return text


def test_summary_reports_product_health_without_free_form_fields(tmp_path):
    data = {'worker_error': SECRET, 'products': {
        'mega645': {'last_draw_id': 1572, 'last_draw_date': '2026-10-07',
                    'freshness': {'status': 'caught_up', 'note': SECRET}, 'error': None},
        'lotto535': {'last_draw_id': SECRET, 'last_draw_date': SECRET,
                     'freshness': {'status': SECRET}, 'error': SECRET},
        SECRET: {'error': SECRET}}}
    (tmp_path / 'results-status.json').write_text(json.dumps(data))
    text = run_summary(tmp_path)
    assert '| mega645 | 1572 | 2026-10-07 | caught_up | không |' in text
    assert '| lotto535 | — | — | unavailable | có |' in text
    assert 'Lỗi worker: có' in text


@pytest.mark.parametrize('raw', [None, '{broken ' + SECRET, '[]', '{"products": []}'])
def test_summary_reports_unavailable_for_missing_or_malformed_status(tmp_path, raw):
    if raw is not None:
        (tmp_path / 'results-status.json').write_text(raw)
    assert 'Trạng thái cập nhật: unavailable' in run_summary(tmp_path)


def test_summary_falls_back_to_checkpoint_when_update_output_is_invalid(tmp_path):
    (tmp_path / 'results-status.json').write_text('{broken')
    checkpoint = tmp_path / 'data/results/status.json'
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(json.dumps({'products': {'keno': {
        'last_draw_id': 245, 'last_draw_date': '2026-10-09',
        'freshness': {'status': 'behind_schedule'}, 'error': SECRET}}}))
    text = run_summary(tmp_path)
    assert 'Nguồn tóm tắt: checkpoint' in text
    assert '| keno | 245 | 2026-10-09 | behind_schedule | có |' in text
