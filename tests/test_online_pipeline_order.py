"""Kiểm luồng điều phối thật, thay lệnh con bằng bộ ghi nhận lời gọi."""
import sys
import pipeline


def test_online_scoring_runs_after_forecast_before_evaluation(monkeypatch):
    calls=[]
    def capture(argv, **options):
        calls.append((argv, options))
    monkeypatch.setattr(pipeline, '_run', capture)
    monkeypatch.setattr(sys, 'argv', ['pipeline.py', '--skip-sync', '--skip-docs', '--strict'])
    pipeline.main()
    for mode in ('loto','de'):
        def position(script, selected_mode=mode):
            return next(i for i,(cmd,_) in enumerate(calls) if script in cmd and '--mode' in cmd and cmd[cmd.index('--mode')+1] == selected_mode)
        prediction=position('src/predict_nextday_2d.py')
        online=position('src/online_learning.py')
        evaluation=position('src/prob_eval_history.py')
        assert prediction < online < evaluation
        assert calls[online][1]['allow_fail'] is False
