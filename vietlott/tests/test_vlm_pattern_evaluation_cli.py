"""Kiểm CLI đánh giá chạy chuyên gia thật trên seed tạm, không sửa sổ live."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ('flags', 'patterns', 'multi_agent'),
    [([], False, False), (['--patterns'], True, False),
     (['--multi-agent'], False, True), (['--patterns', '--multi-agent'], True, True)],
)
def test_cli_selects_independent_challengers_and_scores_real_seed(
    tmp_path: Path, flags: list[str], patterns: bool, multi_agent: bool,
) -> None:
    """Bỏ sót hoặc nối nhầm cờ phải hỏng cấu hình hoặc phép chấm thật ngoài mẫu."""
    root = Path(__file__).resolve().parents[1]
    seed = tmp_path / 'seed'
    seed.mkdir()
    rows = [{'id': draw_id, 'date': '2026-01-02', 'result': [1, 2, 3, 4, 5, 6]}
            for draw_id in range(1, 13)]
    (seed / 'power645.jsonl').write_text(
        ''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8',
    )
    output = tmp_path / 'report.json'
    environment = {**os.environ, 'PYTHONPATH': str(root / 'src')}
    completed = subprocess.run(
        [sys.executable, str(root / 'scripts/evaluate_adaptive.py'), '--seed-dir', str(seed),
         '--output', str(output), '--label', 'fixture', '--products', 'mega645',
         '--draws', '12', '--initial-draws', '8', *flags],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['config']['patterns'] is patterns
    assert report['config']['multi_agent'] is multi_agent
    assert report['config']['adaptive'] is False
    assert report['completed_at'] and report['source_provenance']['files']
    assert report['live_certification'] is False
    result = report['results'][0]
    assert [row['id'] for row in result['draws']] == [9, 10, 11, 12]
    assert result['test_draws'] == 4 and result['live_scored'] == 0
    assert result['mean_log_gain_nats'] > 0
    assert all(len(row['ticket']) == 6 for row in result['draws'])
    assert sorted(path.name for path in tmp_path.iterdir()) == ['report.json', 'seed']
