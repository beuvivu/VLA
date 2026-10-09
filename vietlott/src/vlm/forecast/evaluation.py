"""Đánh giá ngoài mẫu theo thứ tự thời gian, không tạo evidence live."""
from __future__ import annotations

import time

import numpy as np
from scipy import stats

from vietlott_engine.analytics.stats import benjamini_hochberg
from vietlott_engine.core.products import get_product
from vietlott_engine.forecast.data import Series, SetSpec
from vietlott_engine.inference.predictive import diebold_mariano
from vlm.forecast.pipeline import MLConfig, MLForecaster, _prefix_digest


def evaluate_series(series: Series, config: MLConfig, *, initial_draws: int = 400) -> dict:
    """Chấm từng kỳ bằng mô hình chỉ được học tiền tố trước kỳ đó.

    Args:
        series: Lịch sử đã kiểm miền, sắp theo ID và ngày tăng dần.
        config: Cấu hình cố định trước khi xem holdout.
        initial_draws: Số kỳ đầu dành cho khởi tạo; phần còn lại là holdout.

    Returns:
        Provenance, điểm từng kỳ và các trung bình mô tả. Kết quả này không
        chứng nhận kỹ năng live; ngày kỳ đích là điều kiện biết trước.

    Raises:
        ValueError: Split rỗng, bootstrap không đủ hoặc ngày bị đảo.
    """
    if type(initial_draws) is not int or not 1 <= initial_draws < len(series) or initial_draws > config.bootstrap:
        raise ValueError('Invalid chronological train/holdout split')
    dates = np.asarray(series.dates).astype('datetime64[D]')
    if np.isnat(dates).any() or (np.diff(dates).astype('int64') < 0).any():
        raise ValueError('Invalid evaluation dates')
    started = time.perf_counter()
    model = MLForecaster(series.product, config)
    model.update(series.head(initial_draws))
    draws: list[dict] = []
    for t in range(initial_draws, len(series)):
        result = {'id':int(series.draw_ids[t]), 'date':str(dates[t]),
                  'gain_nats':0., 'brier':0., 'brier_fair':0., 'hits':0., 'expected_hits':0.}
        for name, component in model.components.items():
            # Tính law trước khi lấy label; model chưa được thấy kỳ t.
            law = component.law(str(dates[t]), next_id=int(series.draw_ids[t]))
            observation = series.obs[name]
            row = observation['X'][t] if isinstance(component.spec, SetSpec) else observation['C'][t].ravel()
            bonus = int(observation['bonus'][t]) if isinstance(component.spec, SetSpec) and component.spec.bonus_same_drum else 0
            divisor = 1 if isinstance(component.spec, SetSpec) else component.spec.per_draw
            target = row / divisor
            probability = law.marginals()
            result['gain_nats'] += law.log_likelihood(row, bonus) - law.null_log_likelihood(row, bonus)
            result['brier'] += float(np.mean((probability-target)**2))
            result['brier_fair'] += float(np.mean((component.features.base-target)**2))
            if isinstance(component.spec, SetSpec):
                top = np.argsort(-probability, kind='stable')[:component.spec.k]
                result['hits'] += float(row[top].sum())
                result['expected_hits'] += component.spec.k**2 / component.spec.n
        if not np.isfinite([result[key] for key in ('gain_nats', 'brier', 'brier_fair', 'hits', 'expected_hits')]).all():
            raise FloatingPointError('Nonfinite evaluation score')
        draws.append(result)
        model.update(series.head(t+1))
    return {'product':series.product.value,
        'train_first_id':int(series.draw_ids[0]), 'train_last_id':int(series.draw_ids[initial_draws-1]),
        'test_first_id':int(series.draw_ids[initial_draws]), 'test_last_id':int(series.draw_ids[-1]),
        'test_first_date':str(dates[initial_draws]), 'test_last_date':str(dates[-1]),
        'data_sha256':_prefix_digest(series, len(series)), 'test_draws':len(draws),
        'mean_log_gain_nats':float(np.mean([d['gain_nats'] for d in draws])),
        'mean_brier':float(np.mean([d['brier'] for d in draws])),
        'mean_brier_fair':float(np.mean([d['brier_fair'] for d in draws])),
        'mean_hits':float(np.mean([d['hits'] for d in draws])),
        'expected_hits':float(np.mean([d['expected_hits'] for d in draws])),
        'seconds':round(time.perf_counter()-started, 3),
        'live_scored':model.live_scored, 'live_certification':False, 'draws':draws}


def compare_runs(benchmark: dict, candidate: dict) -> list[dict]:
    """So sánh log-score ghép cặp; từ chối ghép khác dữ liệu hoặc khác kỳ.

    Args:
        benchmark: Báo cáo chứa results và điểm gain_nats theo kỳ.
        candidate: Báo cáo trên cùng lịch sử và holdout.

    Returns:
        Mean differential, khoảng tin cậy HAC 95%, DM một phía và BH-FDR
        trên các sản phẩm được so sánh. Đây là kiểm định retrospective.

    Raises:
        ValueError: Provenance/ID/count không khớp hoặc điểm không hữu hạn.
    """
    a = {get_product(row['product']).value:row for row in benchmark['results']}
    b = {get_product(row['product']).value:row for row in candidate['results']}
    if set(a) != set(b) or not a or len(a) != len(benchmark['results']) or len(b) != len(candidate['results']):
        raise ValueError('Unpaired product set')
    comparisons = []
    for product, baseline in a.items():
        other = b[product]
        left, right = baseline['draws'], other['draws']
        if (baseline['data_sha256'] != other['data_sha256']
            or type(baseline['test_draws']) is not int or type(other['test_draws']) is not int
            or len(left) < 2 or len(left) != baseline['test_draws'] or len(right) != other['test_draws']
            or [(d['id'], d['date']) for d in left] != [(d['id'], d['date']) for d in right]):
            raise ValueError('Unpaired evaluation provenance')
        differential = np.array([y['gain_nats']-x['gain_nats'] for x, y in zip(left, right)])
        if not np.isfinite(differential).all():
            raise ValueError('Invalid paired scores')
        dm = diebold_mariano(differential)
        radius = float(stats.t.ppf(.975, len(differential)-1) * dm.hac_standard_error)
        comparisons.append({'product':product, 'observations':len(differential),
            'mean_log_gain_difference_nats':dm.mean_differential,
            'hac_standard_error':dm.hac_standard_error,
            'ci95':[dm.mean_differential-radius, dm.mean_differential+radius],
            'p_value_greater':dm.p_value_greater, 'hac_lag':dm.lag})
    for row, q_value in zip(comparisons, benjamini_hochberg([r['p_value_greater'] for r in comparisons])):
        row['q_value_bh'] = float(q_value)
    return comparisons
