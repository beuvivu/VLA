"""Trang public hiển thị chẩn đoán thật và không biến backtest thành bằng chứng live."""
import json
import subprocess
from pathlib import Path

from bs4 import BeautifulSoup
import yaml

import build_vietlott_results as b


def diagnostic():
    return {'last_id': 1571, 'last_date': '2026-10-16',
            'confidence': {'validated': False, 'scored_live': 2},
            'components': {'main': {'observations': 128, 'temperature': 2.0,
                'context': 'stable', 'short_window': 30, 'retained_observations': 128,
                'weights': {'statistical': .2, 'bayesian_markov_graph': .3, 'temporal_neural': .4, 'uniform': .1},
                'memory_matches': [{'support': 4, 'similarity': .95}],
                'source': 'SECRET-SOURCE', 'note': 'https://SECRET-SOURCE.example'}}}


def test_multi_agent_markup_exposes_weights_and_real_training_cutoff():
    html = b.multi_agent_markup(diagnostic())
    soup = BeautifulSoup(html, 'html.parser')
    assert soup.select_one('#app-multi-agent') is not None
    text = soup.get_text(' ', strip=True)
    assert '128' in text and '#1571' in text
    assert '20,0%' in text and '30,0%' in text and '40,0%' in text
    assert 'Chưa đủ bằng chứng live' in text
    assert 'SECRET-SOURCE' not in html
    assert 'https://' not in html
    assert 'title=' not in html


def test_multi_agent_section_uses_allowlisted_confidence_status():
    data = diagnostic()
    data['confidence']['validated'] = True
    html = b.multi_agent_markup(data)
    assert 'Đạt cổng kiểm chứng live' in html
    assert '95%' not in html
    assert b.multi_agent_markup(None) == ''


def test_product_page_renders_multi_agent_section_without_changing_the_shell():
    from test_vietlott_results import _dashboard
    dashboard = _dashboard()
    dashboard['analysis']['mega645']['multi_agent'] = diagnostic()
    page = b.page('mega645', dashboard['products'][0], dashboard['analysis']['mega645'])
    soup = BeautifulSoup(page, 'html.parser')
    assert soup.select_one('#app-multi-agent') is not None
    assert soup.select_one('#vl-next') is not None


def test_page_workflow_cannot_publish_a_stale_cached_summary(tmp_path):
    """Chạy chính shell của workflow sau khi giả lập cache ghi đè bản mới."""
    workflow = yaml.safe_load((Path(b.ROOT) / '.github/workflows/vietlott-results.yml').read_text())
    steps = workflow['jobs']['build']['steps']
    restore = next(i for i, s in enumerate(steps) if s.get('uses', '').startswith('actions/cache/restore'))
    build = next(i for i, s in enumerate(steps) if 'src/build_vietlott_results.py' in s.get('run', ''))
    fixes = [s['run'] for s in steps[restore + 1:build] if 'git restore' in s.get('run', '')]
    assert len(fixes) == 1
    def git(*args):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    target = tmp_path / 'vietlott/data/forecast/multi-agent-summary.json'
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({'products': {'mega645': {'last_id': 1576}}}))
    git('add', '.')
    git('commit', '-qm', 'bản công bố')
    target.write_text(json.dumps({'products': {'mega645': {'last_id': 1569}}}))
    subprocess.run(['bash', '-e', '-c', fixes[0]], cwd=tmp_path, check=True)
    assert json.loads(target.read_text())['products']['mega645']['last_id'] == 1576
