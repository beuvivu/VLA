"""Giao thức kiểm chứng xác suất và số khớp H cho Mega 6/45 và Power 6/55.

Đăng ký ngày 13-10-2026, TRƯỚC khi chạy phần test. Cấu hình trong ``PROTOCOL`` là luật; đổi nó thì
đăng ký giao thức mới với ngày mới, không chạy lại rồi vẫn gọi phần test là độc lập.

Trình tự (walk-forward, đơn vị là KỲ QUAY):

1. ``WARMUP`` kỳ đầu chỉ để đặc trưng và mô hình có lịch sử; không chấm.
2. Phần còn lại tới ``FROZEN_LAST_ID`` chia liền nhau: dev 50% · validation 20% · test 30%.
3. Challenger chọn siêu tham số trên dev, bỏ nhóm đặc trưng không ổn định qua các fold của
   dev + validation (ablation), hiệu chuẩn nhiệt độ trên validation — rồi CHỐT.
4. Mỗi kỳ test được dự báo trước khi mô hình thấy kết quả của nó; học lại sau nhãn chỉ ảnh hưởng
   các kỳ sau. Test được nhìn MỘT lần.

Thước đo chính là log-likelihood của cả kỳ quay (bộ chính, và số đặc biệt Power chấm riêng) so
với luật công bằng, kiểm bằng Diebold–Mariano HAC theo kỳ, Holm cho mọi ứng viên × sản phẩm. Brier,
độ tin cậy (reliability) và phân bố H đi kèm; H ≥ 4 KHÔNG được dùng để đề bạt vì không đủ công
suất (xem ``hits.detectable_lift``). Lưu ý trung thực: cửa sổ này từng được xem trong các báo cáo
khám phá trước (03-10-2026); việc chọn cấu hình ở đây chỉ dùng dev/validation, nhưng bằng chứng
thật chỉ đến từ các kỳ SAU ngày đăng ký (luồng live có sẵn của engine).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import subprocess
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib import metadata
from pathlib import Path

import numpy as np

from vietlott_engine.core.games import GameCode, get_game
from vietlott_engine.core.history import DrawHistory
from vietlott_engine.core.models import Draw
from vietlott_engine.forecast.data import CONFIGS, Series, SetSpec, matrix_series
from vietlott_engine.forecast.engine import VERSION as LEGACY_VERSION
from vietlott_engine.forecast.engine import Forecaster
from vietlott_engine.inference.multiple_testing import holm
from vietlott_engine.inference.predictive import diebold_mariano
from vlm.database.schema import DrawRecord
from vlm.forecast import challengers as ch
from vlm.forecast.distribution import Law
from vlm.forecast.hits import detectable_lift, draws_needed, fair_hit_pmf, portfolio_summary, summarize_hits
from vlm.forecast.pipeline import VERSION as ML_VERSION
from vlm.forecast.pipeline import MLConfig, MLForecaster, _prefix_digest

PROTOCOL: dict = {
    'registered_at': '2026-10-13',
    'products': ('mega645', 'power655'),
    'frozen_last_id': {'mega645': 1574, 'power655': 1409},
    'warmup': 300,
    'split': {'dev': 0.5, 'validation': 0.2, 'test': 0.3},
    'refit_every': 26,
    'l2_grid': (0.01, 0.1, 1.0, 10.0),
    'shrink_half_lives': (None, 500, 100, 30),
    'shrink_priors': (20.0, 100.0, 500.0),
    'ablation_folds': 4,
    'ablation_min_positive_folds': 3,
    'temperature_bounds': (0.0, 2.0),
    'alpha': 0.05,
    'portfolio_tickets': 5,
    'monte_carlo': 20_000,
    'seed': 20261013,
    'promotion': {
        'beats_fair_holm': 'Δ log-score so với công bằng trên test > 0, DM HAC một phía, Holm trên mọi ứng viên × sản phẩm, p < α',
        'beats_incumbents': 'Δ so với TỪNG mô hình đang chạy (legacy, ML) trên test > 0, DM một phía p < α',
        'validation_positive': 'Δ so với công bằng trên validation > 0',
        'stable_thirds': 'Δ so với công bằng > 0 ở ít nhất 2 trong 3 đoạn liền của test',
        'brier_not_worse': 'Brier biên trên test ≤ Brier công bằng',
        'then': 'Đạt cả năm: đủ điều kiện CHẠY THỬ TIẾN CỨU; xác suất triển khai chỉ đổi khi qua cổng live hiện có',
    },
}
CANDIDATES = ('legacy_tempered', 'ml_tempered', 'shrink', 'causal')
TICKET_PRICE_VND = 10_000
INCUMBENTS = ('legacy', 'ml')


# ============================================================================ dữ liệu
def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def load_frozen_series(product: str, root: Path) -> tuple[Series, dict]:
    """Lịch sử seed + nhật ký kết quả đã xác thực, cắt đúng ``frozen_last_id``; ID phải liền từ 1.

    Raises:
        ValueError: Nhật ký mâu thuẫn seed, thiếu kỳ hoặc lệch ngày.
    """
    from vietlott_engine.crawler.sources.mirror import JsonlFileSource

    root = Path(root)
    spec = get_game(GameCode(product))
    seed_dir = root / 'data' / 'seed'
    draws = {d.draw_id: d for d in asyncio.run(JsonlFileSource(seed_dir).fetch(spec)).draws}
    journal = root / 'data' / 'results' / 'results.jsonl'
    if journal.exists():
        for line in journal.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            if raw.get('game_type') != product:
                continue
            record = DrawRecord.model_validate(raw)
            draw = Draw(game=product, draw_id=record.draw_id, draw_date=record.draw_date.date(),
                        numbers=tuple(record.winning_numbers), bonus=record.bonus_number, source='journal')
            known = draws.get(draw.draw_id)
            if known is not None and (known.draw_date, sorted(known.numbers), known.bonus) != (draw.draw_date, sorted(draw.numbers), draw.bonus):
                raise ValueError(f'{product} #{draw.draw_id}: nhật ký mâu thuẫn seed')
            draws.setdefault(draw.draw_id, draw)
    last = PROTOCOL['frozen_last_id'][product]
    kept = [draws[i] for i in sorted(draws) if i <= last]
    if [d.draw_id for d in kept] != list(range(1, last + 1)):
        raise ValueError(f'{product}: thiếu kỳ trước #{last}')
    series = matrix_series(DrawHistory.from_draws(kept, spec))
    dates = np.asarray(series.dates).astype('datetime64[D]')
    if (np.diff(dates).astype(int) <= 0).any():
        raise ValueError(f'{product}: ngày quay không tăng ngặt')
    provenance = {'seed_sha256': _sha256(seed_dir / ('power645.jsonl' if product == 'mega645' else 'power655.jsonl')),
                  'journal_sha256': _sha256(journal), 'history_sha256': _prefix_digest(series, len(series)),
                  'first_id': 1, 'last_id': last, 'first_date': str(dates[0]), 'last_date': str(dates[-1])}
    return series, provenance


@dataclass(frozen=True)
class Split:
    """Chỉ số kỳ (0-based) — [warmup, dev_end) dev, [dev_end, val_end) validation, [val_end, end) test."""

    warmup: int
    dev_end: int
    val_end: int
    end: int

    def segments(self) -> dict[str, tuple[int, int]]:
        return {'dev': (self.warmup, self.dev_end), 'validation': (self.dev_end, self.val_end), 'test': (self.val_end, self.end)}


def make_split(total: int) -> Split:
    warmup = PROTOCOL['warmup']
    scored = total - warmup
    if scored < 30:
        raise ValueError('Quá ít kỳ để chia dev/validation/test')
    dev_end = warmup + int(round(scored * PROTOCOL['split']['dev']))
    val_end = dev_end + int(round(scored * PROTOCOL['split']['validation']))
    return Split(warmup, dev_end, val_end, total)


# ============================================================================ chấm từng kỳ
def _ticket_from_marginals(pi: np.ndarray, k: int) -> list[int]:
    return sorted(int(i) + 1 for i in np.argsort(-pi, kind='stable')[:k])


def _record(draw_id: int, day: str, row: np.ndarray, bonus: int, main_ll: float, bonus_ll: float,
            pi: np.ndarray, ticket: list[int], spec: SetSpec, portfolio: list[list[int]] | None = None) -> dict:
    fair_main, fair_bonus = ch.fair_log_likelihood(spec.n, spec.k, spec.bonus_same_drum)
    drawn = set((np.flatnonzero(row) + 1).tolist())
    out = {'id': draw_id, 'date': day, 'main_gain': main_ll - fair_main,
           'bonus_gain': (bonus_ll - fair_bonus) if spec.bonus_same_drum else 0.,
           'brier': float(np.mean((pi - row) ** 2)), 'ticket': ticket, 'hits': len(drawn & set(ticket)),
           'pi': pi.tolist()}
    if portfolio is not None:
        out['portfolio'] = portfolio
    return out


def _law_records(laws: list[Law], series: Series, start: int, tau: float = 1.0,
                 top_nodes: int | None = None) -> list[dict]:
    """Chấm các luật hỗn hợp đã lưu (một luật mỗi kỳ, đã dựng TRƯỚC kỳ đó) — nhiệt độ τ trên trọng số.

    Vé: 6 số π cao nhất (quy tắc legacy) hoặc, khi có ``top_nodes``, bộ xác suất đồng thời cao nhất
    ``Law.top`` của CHÍNH luật đã hiệu chuẩn (quy tắc họ ML) — luôn là vé mà luật ấy sẽ phát.
    """
    spec = laws[0].spec
    out = []
    for offset, law in enumerate(laws):
        t = start + offset
        row = series.obs['main']['X'][t].astype(float)
        bonus = int(series.obs['main']['bonus'][t]) if spec.bonus_same_drum else 0
        tempered = law if tau == 1.0 else Law(spec, law.values ** tau, law.mixture)
        main_ll = _mixture_main_log_likelihood(tempered, row)
        # Số đặc biệt Power chấm riêng: log P(b | bộ chính) = log P(bộ chính, b) − log P(bộ chính).
        bonus_ll = tempered.log_likelihood(row, bonus) - main_ll if spec.bonus_same_drum else 0.
        pi = tempered.marginals()
        if top_nodes is None:
            ticket = _ticket_from_marginals(pi, spec.k)
        else:
            ticket = sorted(int(v) for v in tempered.top(1, max_nodes=top_nodes)[0][0]['numbers'])
        out.append(_record(int(series.draw_ids[t]), str(series.dates[t])[:10], row, bonus, main_ll, bonus_ll,
                           pi, ticket, spec))
    return out


def ml_arm_records(laws: list[Law], portfolios: list[list[list[int]]], series: Series, start: int,
                   tau: float, search_nodes: int) -> tuple[list[dict], list[dict]]:
    """Nhánh ML và ML + τ; cả hai chấm vé mà CHÍNH luật của nhánh sẽ phát (``Law.top``), không phải top biên.

    Nhánh ML dùng đúng danh mục đã xếp hạng lúc chạy (vé đầu là vé công bố); nhánh τ xếp hạng lại
    trên luật đã hiệu chuẩn, vì τ có thể đổi bộ xác suất cao nhất.
    """
    plain = _law_records(laws, series, start)
    for record, tickets in zip(plain, portfolios):
        record['ticket'] = sorted(tickets[0])
        record['hits'] = len(set(record['ticket']) & set(_drawn(series, record['id'])))
        record['portfolio'] = tickets
    return plain, _law_records(laws, series, start, tau, top_nodes=search_nodes)


def _mixture_main_log_likelihood(law: Law, row: np.ndarray) -> float:
    """log P(bộ chính) của hỗn hợp, đã lấy tổng trên số đặc biệt."""
    expert = law.log_values @ row - law.log_den
    return float(np.logaddexp.reduce(law.log_mix + expert))


def run_legacy(series: Series, start: int, end: int) -> tuple[list[Law], list[float]]:
    """Mô hình legacy đang chạy: luật hỗn hợp trước mỗi kỳ start..end − 1, và phần tăng e-value của engine.

    Phần tăng log W của engine ở mỗi kỳ phải bằng log-likelihood của luật dựng lại trừ luật công bằng
    (kiểm tra nhất quán: benchmark chấm đúng mô hình mà engine chấm)."""
    f = Forecaster(series.product)
    f.update(series.head(start))
    comp = f.components['main']
    laws, increments = [], []
    for t in range(start, end):
        st = f.state['components']['main']
        laws.append(Law(comp.spec, comp.predictions(st), st['v']))
        before = f.state['log_wealth']
        f.update(series.head(t + 1))
        increments.append(f.state['log_wealth'] - before)
    return laws, increments


def run_ml(series: Series, start: int, end: int, config: MLConfig, tickets: int) -> tuple[list[Law], list[list[list[int]]]]:
    """Bộ ML đang chạy: luật trước mỗi kỳ và danh mục ``tickets`` bộ theo đúng luật xếp hạng đã phát (``Law.top``)."""
    model = MLForecaster(series.product, config)
    model.update(series.head(start))
    comp = model.components['main']
    laws, portfolios = [], []
    for t in range(start, end):
        law = comp.law(str(series.dates[t])[:10], next_id=int(series.draw_ids[t]))
        top, _ = law.top(tickets, max_nodes=config.search_nodes)
        laws.append(law)
        portfolios.append([row['numbers'] for row in top])
        model.update(series.head(t + 1))
    return laws, portfolios


def _eta_records(eta: np.ndarray, series: Series, start: int) -> list[dict]:
    spec = CONFIGS[series.product].components['main']
    x = series.obs['main']['X'][start:start + len(eta)]
    bonus = series.obs['main']['bonus'][start:start + len(eta)] if spec.bonus_same_drum else None
    main, extra = ch.cb_log_likelihood(eta, x, bonus)
    pi = ch.cb_marginals(eta, spec.k)
    return [_record(int(series.draw_ids[start + i]), str(series.dates[start + i])[:10], x[i].astype(float),
                    int(bonus[i]) if bonus is not None else 0, float(main[i]), float(extra[i]), pi[i],
                    _ticket_from_marginals(pi[i], spec.k), spec) for i in range(len(eta))]


# ============================================================================ challenger: chọn, bỏ nhóm, hiệu chuẩn
def _weekdays(series: Series) -> np.ndarray:
    days = [date.fromisoformat(str(d)[:10]).weekday() for d in series.dates]
    return np.asarray(days + [days[-1]])


def select_challengers(series: Series, split: Split) -> dict:
    """Mọi quyết định của challenger, CHỈ trên dev và validation; trả cấu hình đã chốt kèm nhật ký chọn."""
    x = series.obs['main']['X']
    spec = CONFIGS[series.product].components['main']
    bonus = series.obs['main']['bonus'] if spec.bonus_same_drum else None
    w, d_end, v_end = split.warmup, split.dev_end, split.val_end
    dev_x, val_x = x[w:d_end], x[d_end:v_end]
    dev_b = bonus[w:d_end] if bonus is not None else None
    val_b = bonus[d_end:v_end] if bonus is not None else None

    def mean_ll(eta: np.ndarray, rows: np.ndarray, extra: np.ndarray | None) -> float:
        main, b = ch.cb_log_likelihood(eta, rows, extra)
        return float((main + b).mean())

    # shrink: lưới (nửa đời, độ co), τ tối ưu trên dev
    shrink_log = []
    for half_life in PROTOCOL['shrink_half_lives']:
        for prior in PROTOCOL['shrink_priors']:
            score = ch.shrink_scores(x, half_life, prior)
            tau = ch.fit_temperature(score[w:d_end], dev_x, dev_b, bounds=(-3.0, 3.0))
            shrink_log.append({'half_life': half_life, 'prior': prior, 'tau_dev': tau,
                               'dev_mean_ll': mean_ll(tau * score[w:d_end], dev_x, dev_b)})
    best = max(shrink_log, key=lambda r: r['dev_mean_ll'])
    shrink_score = ch.shrink_scores(x, best['half_life'], best['prior'])
    shrink_val = best['tau_dev'] * shrink_score[d_end:v_end]
    shrink_tau = ch.fit_temperature(shrink_val, val_x, val_b, PROTOCOL['temperature_bounds'])

    # causal: λ trên dev với mọi nhóm
    phi = ch.causal_features(x, _weekdays(series))
    every = PROTOCOL['refit_every']
    all_columns = list(range(len(ch.FEATURES)))
    l2_log = []
    for l2 in PROTOCOL['l2_grid']:
        eta = ch.causal_walk_forward(phi, x, all_columns, l2, w, d_end, every)
        l2_log.append({'l2': l2, 'dev_mean_ll': mean_ll(eta, dev_x, dev_b)})
    l2 = max(l2_log, key=lambda r: r['dev_mean_ll'])['l2']

    # ablation: bỏ từng nhóm, Δ trên từng fold liền của dev + validation
    folds = np.array_split(np.arange(w, v_end), PROTOCOL['ablation_folds'])
    full = ch.causal_walk_forward(phi, x, all_columns, l2, w, v_end, every)
    rows, extra = x[w:v_end], bonus[w:v_end] if bonus is not None else None
    full_main, full_b = ch.cb_log_likelihood(full, rows, extra)
    ablation = []
    for group, names in ch.GROUPS.items():
        kept_columns = [i for i, name in enumerate(ch.FEATURES) if name not in names]
        reduced = ch.causal_walk_forward(phi, x, kept_columns, l2, w, v_end, every)
        red_main, red_b = ch.cb_log_likelihood(reduced, rows, extra)
        delta = (full_main + full_b) - (red_main + red_b)   # > 0: nhóm có ích
        per_fold = [float(delta[f - w].mean()) for f in folds]
        keep = float(np.mean(per_fold)) > 0 and sum(v > 0 for v in per_fold) >= PROTOCOL['ablation_min_positive_folds']
        ablation.append({'group': group, 'delta_per_fold': per_fold, 'mean_delta': float(np.mean(per_fold)), 'keep': keep})
    groups = [a['group'] for a in ablation if a['keep']]
    columns = [i for i, name in enumerate(ch.FEATURES) if any(name in ch.GROUPS[g] for g in groups)]
    if columns:
        # Cùng chuỗi η (bắt đầu ở warmup, học lại cùng nhịp) mà challenger_eta sẽ chấm: học lại từ
        # dev_end thì lịch học lại lệch (Power lệch 8 kỳ) và τ được chỉnh trên một chuỗi khác.
        aligned = ch.causal_walk_forward(phi, x, columns, l2, w, v_end, every)
        causal_tau = ch.fit_temperature(aligned[d_end - w:], val_x, val_b, PROTOCOL['temperature_bounds'])
    else:
        causal_tau = 0.0  # không nhóm nào ổn định: challenger chính là luật công bằng
    return {'shrink': {**best, 'tau_validation': shrink_tau, 'grid': shrink_log},
            'causal': {'l2': l2, 'l2_grid': l2_log, 'ablation': ablation, 'groups': groups,
                       'tau_validation': causal_tau},
            '_phi': phi, '_shrink_score': shrink_score}


def challenger_eta(series: Series, chosen: dict, start: int, end: int) -> dict[str, np.ndarray]:
    """η đã chốt của hai challenger cho các kỳ start..end − 1 (walk-forward tiếp tục học lại)."""
    x = series.obs['main']['X']
    s = chosen['shrink']
    shrink = s['tau_validation'] * s['tau_dev'] * chosen['_shrink_score'][start:end]
    c = chosen['causal']
    columns = [i for i, name in enumerate(ch.FEATURES) if any(name in ch.GROUPS[g] for g in c['groups'])]
    if columns and c['tau_validation'] > 0:
        causal = c['tau_validation'] * ch.causal_walk_forward(chosen['_phi'], x, columns, c['l2'], start, end, PROTOCOL['refit_every'])
    else:
        causal = np.zeros((end - start, x.shape[1]))
    return {'shrink': shrink, 'causal': causal}


# ============================================================================ thước đo
def reliability(records: list[dict], k: int, n: int) -> dict:
    """Bin theo hệ số π/(k/n); ECE = Σ (số quan sát bin / tổng) · |dự báo trung bình − tần suất thật|."""
    edges = (0.0, 0.9, 0.97, 1.03, 1.1, np.inf)
    p0 = k / n
    pi = np.concatenate([r['pi'] for r in records])
    hit = np.concatenate([[1.0 if i + 1 in r['drawn'] else 0.0 for i in range(n)] for r in records])
    bins, ece = [], 0.0
    for lo, hi in zip(edges, edges[1:]):
        mask = (pi / p0 >= lo) & (pi / p0 < hi)
        if mask.any():
            predicted, observed = float(pi[mask].mean()), float(hit[mask].mean())
            ece += mask.mean() * abs(predicted - observed)
            bins.append({'lift_range': [lo, None if hi == np.inf else hi], 'count': int(mask.sum()),
                         'predicted': predicted, 'observed': observed})
    return {'ece': float(ece), 'bins': bins}


def segment_metrics(records: list[dict], spec: SetSpec) -> dict:
    gain = np.array([r['main_gain'] + r['bonus_gain'] for r in records])
    return {'draws': len(records), 'first_id': records[0]['id'], 'last_id': records[-1]['id'],
            'first_date': records[0]['date'], 'last_date': records[-1]['date'],
            'mean_log_gain_nats': float(gain.mean()),
            'mean_main_gain_nats': float(np.mean([r['main_gain'] for r in records])),
            'mean_bonus_gain_nats': float(np.mean([r['bonus_gain'] for r in records])),
            'brier': float(np.mean([r['brier'] for r in records])),
            'brier_fair': float((spec.k / spec.n) * (1 - spec.k / spec.n)),
            'reliability': reliability(records, spec.k, spec.n),
            'hits': summarize_hits([r['hits'] for r in records], spec.n, spec.k)}


def paired_test(candidate: list[dict], baseline: list[dict] | None) -> dict:
    """DM HAC một phía trên Δ log-score từng kỳ (baseline None = luật công bằng, điểm 0)."""
    a = np.array([r['main_gain'] + r['bonus_gain'] for r in candidate])
    if baseline is not None:
        if [r['id'] for r in baseline] != [r['id'] for r in candidate]:
            raise ValueError('So sánh phải trên cùng các kỳ')
        a = a - np.array([r['main_gain'] + r['bonus_gain'] for r in baseline])
    thirds = [float(part.mean()) for part in np.array_split(a, 3)]
    if np.allclose(a, 0.0, rtol=0.0, atol=1e-12):
        # Hai luật trùng nhau (ví dụ challenger đã co hẳn về công bằng): chênh lệch chỉ là sai số
        # làm tròn, không có gì để kiểm.
        return {'mean_difference_nats': 0.0, 'hac_se': 0.0, 'p_value_greater': 1.0, 'thirds': [0.0] * len(thirds),
                'identical': True}
    dm = diebold_mariano(a)
    return {'mean_difference_nats': dm.mean_differential, 'hac_se': dm.hac_standard_error,
            'p_value_greater': dm.p_value_greater, 'thirds': thirds}


def promotion_decision(results: dict) -> dict:
    """Áp luật đề bạt đã đăng ký lên kết quả test của mọi ứng viên × sản phẩm.

    Họ Holm CỐ ĐỊNH là mọi ứng viên × mọi sản phẩm đã đăng ký; giả thuyết vắng mặt (chạy một sản
    phẩm, hay không có ML) được tính p = 1 nên không làm họ hiệu chỉnh nhỏ lại. Lượt chạy thiếu thì
    không xét đề bạt (``incomplete_run``).
    """
    alpha = PROTOCOL['alpha']
    family = [(p, c) for p in PROTOCOL['products'] for c in CANDIDATES]
    present = {(p, c) for p, c in family if p in results and c in results[p]['tests']['test']}
    p_fair = [results[p]['tests']['test'][c]['vs_fair']['p_value_greater'] if (p, c) in present else 1.0 for p, c in family]
    adjusted = dict(zip(family, holm(p_fair)))
    complete = len(present) == len(family)
    keys = [key for key in family if key in present]
    out = {}
    for product, candidate in keys:
        tests = results[product]['tests']
        test = tests['test'][candidate]
        metrics = results[product]['segments']['test'][candidate]
        checks = {
            'beats_fair_holm': test['vs_fair']['mean_difference_nats'] > 0 and adjusted[(product, candidate)] < alpha,
            # Thiếu một mô hình đang chạy (chạy không có ML) thì không thể đạt điều kiện này.
            'beats_incumbents': all(f'vs_{inc}' in test and test[f'vs_{inc}']['mean_difference_nats'] > 0
                                    and test[f'vs_{inc}']['p_value_greater'] < alpha for inc in INCUMBENTS),
            'validation_positive': results[product]['segments']['validation'][candidate]['mean_log_gain_nats'] > 0,
            'stable_thirds': sum(v > 0 for v in test['vs_fair']['thirds']) >= 2,
            'brier_not_worse': metrics['brier'] <= metrics['brier_fair'] + 1e-12,  # dung sai làm tròn
        }
        checks = {name: bool(value) for name, value in checks.items()}
        out[f'{product}:{candidate}'] = {'checks': checks, 'holm_p_vs_fair': float(adjusted[(product, candidate)]),
                                         'eligible_for_prospective_trial': all(checks.values())}
    if not complete:
        for value in out.values():
            value['eligible_for_prospective_trial'] = False
        out['verdict'] = 'incomplete_run'
    else:
        out['verdict'] = ('challenger_eligible' if any(v['eligible_for_prospective_trial'] for v in out.values() if isinstance(v, dict))
                          else 'keep_production')
    return out


# ============================================================================ chạy
def _versions() -> dict:
    out = {'python': platform.python_version(), 'legacy_engine': LEGACY_VERSION, 'ml_checkpoint': ML_VERSION}
    for name in ('numpy', 'scipy', 'scikit-learn', 'pydantic'):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


SOURCES = ('vlm/forecast/hit_benchmark.py', 'vlm/forecast/hits.py', 'vlm/forecast/challengers.py',
           'vlm/forecast/distribution.py', 'vlm/forecast/features.py', 'vlm/forecast/models.py',
           'vlm/forecast/pipeline.py', 'vietlott_engine/forecast/engine.py', 'vietlott_engine/forecast/experts.py')


def source_manifest() -> dict:
    """sha256 của từng tệp mã quyết định kết quả — artifact chỉ tái lập được với đúng các tệp này."""
    base = Path(__file__).resolve().parents[2]
    return {name: _sha256(base / name) for name in SOURCES}


def _git_state(root: Path) -> dict:
    status = _git(root, 'status', '--porcelain', '--', '.')
    return {'git_commit': _git(root, 'rev-parse', 'HEAD') or None,
            'git_dirty': None if status is None else bool(status)}


def benchmark_product(product: str, root: Path, *, ml_config: MLConfig | None = None, include_ml: bool = True) -> dict:
    """Toàn bộ giao thức cho một sản phẩm; trả artifact JSON-hoá được (không gồm trạng thái mô hình)."""
    started = time.perf_counter()
    series, provenance = load_frozen_series(product, root)
    spec = CONFIGS[series.product].components['main']
    split = make_split(len(series))
    segments = split.segments()
    w, d_end, v_end, end = split.warmup, split.dev_end, split.val_end, split.end
    timings = {}

    t0 = time.perf_counter()
    legacy_laws, increments = run_legacy(series, w, end)
    timings['legacy_seconds'] = time.perf_counter() - t0
    arms: dict[str, list[dict]] = {'legacy': _law_records(legacy_laws, series, w)}
    consistency = float(np.max(np.abs(np.array([r['main_gain'] + r['bonus_gain'] for r in arms['legacy']]) - np.array(increments))))
    if consistency > 1e-6:
        raise ValueError(f'Luật legacy dựng lại lệch e-value của engine {consistency:.3g} nats')
    legacy_tau = ch_fit_law_temperature(legacy_laws[d_end - w:v_end - w], series, d_end)
    arms['legacy_tempered'] = _law_records(legacy_laws, series, w, legacy_tau)

    config = ml_config or MLConfig()
    portfolios: list[list[list[int]]] = []
    ml_tau = None
    if include_ml:
        t0 = time.perf_counter()
        ml_laws, portfolios = run_ml(series, w, end, config, PROTOCOL['portfolio_tickets'])
        timings['ml_seconds'] = time.perf_counter() - t0
        ml_tau = ch_fit_law_temperature(ml_laws[d_end - w:v_end - w], series, d_end)
        arms['ml'], arms['ml_tempered'] = ml_arm_records(ml_laws, portfolios, series, w, ml_tau, config.search_nodes)

    t0 = time.perf_counter()
    chosen = select_challengers(series, split)
    timings['challenger_selection_seconds'] = time.perf_counter() - t0
    etas = challenger_eta(series, chosen, w, end)
    for name, eta in etas.items():
        arms[name] = _eta_records(eta, series, w)
    fair_eta = np.zeros((end - w, spec.n))
    arms['fair'] = _eta_records(fair_eta, series, w)
    rng = np.random.default_rng(PROTOCOL['seed'])
    for record in arms['fair']:  # vé ngẫu nhiên chốt trước kỳ: kiểm tra độc lập của mốc siêu bội
        record['ticket'] = sorted((rng.choice(spec.n, spec.k, replace=False) + 1).tolist())
        record['hits'] = len(set(record['ticket']) & set(_drawn(series, record['id'])))
    for records in arms.values():
        for record in records:
            record['drawn'] = _drawn(series, record['id'])

    by_segment = {seg: {name: [r for r in records if segments_of(r, series, segments) == seg] for name, records in arms.items()}
                  for seg in segments}
    metrics = {seg: {name: segment_metrics(rows, spec) for name, rows in group.items()} for seg, group in by_segment.items()}
    tests = {}
    for seg in ('validation', 'test'):
        tests[seg] = {}
        for name in arms:
            if name == 'fair':
                continue
            entry = {'vs_fair': paired_test(by_segment[seg][name], None)}
            for incumbent in INCUMBENTS:
                if incumbent in arms and incumbent != name:
                    entry[f'vs_{incumbent}'] = paired_test(by_segment[seg][name], by_segment[seg][incumbent])
            tests[seg][name] = entry
    hit_power = {}
    pmf = fair_hit_pmf(spec.n, spec.k)
    for level in (3, 4):
        p0 = float(pmf[level:].sum())
        hit_power[f'ge{level}'] = {
            'fair_rate': p0,
            'test': detectable_lift(p0, split.end - split.val_end),
            'all_scored': detectable_lift(p0, split.end - split.warmup),
            'draws_needed_for_lift_2': draws_needed(p0, 2.0),
            'draws_needed_for_lift_1_2': draws_needed(p0, 1.2),
        }
    portfolio = None
    if include_ml and portfolios:
        portfolio = {seg: portfolio_summary([r['portfolio'] for r in by_segment[seg]['ml']],
                                            [r['drawn'] for r in by_segment[seg]['ml']], spec.n, spec.k,
                                            PROTOCOL['monte_carlo'], PROTOCOL['seed'])
                     for seg in ('test',)}
        portfolio['all_scored'] = portfolio_summary([r['portfolio'] for r in arms['ml']], [r['drawn'] for r in arms['ml']],
                                                    spec.n, spec.k, PROTOCOL['monte_carlo'], PROTOCOL['seed'])
    incumbent_hits_all = {name: summarize_hits([r['hits'] for r in arms[name]], spec.n, spec.k)
                          for name in ('legacy', 'ml', 'fair') if name in arms}
    timings['total_seconds'] = time.perf_counter() - started
    return {
        'product': product, 'protocol_registered_at': PROTOCOL['registered_at'],
        'provenance': {**provenance, **_git_state(root), 'source_sha256': source_manifest(), 'versions': _versions(),
                       'ml_config': config.model_dump(mode='json'), 'seed': PROTOCOL['seed'],
                       'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds')},
        'split': {seg: {'first_id': int(series.draw_ids[a]), 'last_id': int(series.draw_ids[b - 1]),
                        'first_date': str(series.dates[a])[:10], 'last_date': str(series.dates[b - 1])[:10], 'draws': b - a}
                  for seg, (a, b) in segments.items()} | {'warmup_draws': w},
        'selection': {'shrink': chosen['shrink'], 'causal': chosen['causal'],
                      'legacy_tau_validation': legacy_tau, 'ml_tau_validation': ml_tau},
        'legacy_consistency_max_abs_nats': consistency,
        'segments': metrics, 'tests': tests, 'hit_power': hit_power, 'portfolio_ml': portfolio,
        'hits_all_scored_descriptive': incumbent_hits_all,
        'tickets': {name: {'tickets_per_draw': PROTOCOL['portfolio_tickets'] if name == 'ml' else 1,
                           'budget_vnd_per_draw': TICKET_PRICE_VND * (PROTOCOL['portfolio_tickets'] if name == 'ml' else 1)}
                    for name in arms},
        'draws': draw_table(arms),
        'timings': timings,
    }


def draw_table(arms: dict[str, list[dict]]) -> dict:
    """Từng kỳ của mọi nhánh, dạng cột: dự báo (π từng số, vé), điểm (log, Brier) và số khớp."""
    first = next(iter(arms.values()))
    table = {'id': [r['id'] for r in first], 'date': [r['date'] for r in first], 'drawn': [r['drawn'] for r in first], 'arms': {}}
    for name, records in arms.items():
        if [r['id'] for r in records] != table['id']:
            raise ValueError('Các nhánh phải chấm cùng các kỳ')
        column = {'main_gain': [round(r['main_gain'], 10) for r in records],
                  'bonus_gain': [round(r['bonus_gain'], 10) for r in records],
                  'brier': [round(r['brier'], 10) for r in records],
                  'hits': [r['hits'] for r in records], 'ticket': [r['ticket'] for r in records],
                  'pi': [[round(v, 7) for v in r['pi']] for r in records]}
        if 'portfolio' in records[0]:
            column['portfolio'] = [r['portfolio'] for r in records]
        table['arms'][name] = column
    return table


def _drawn(series: Series, draw_id: int) -> list[int]:
    t = int(np.flatnonzero(series.draw_ids == draw_id)[0])
    return (np.flatnonzero(series.obs['main']['X'][t]) + 1).tolist()


def segments_of(record: dict, series: Series, segments: dict[str, tuple[int, int]]) -> str:
    t = int(np.flatnonzero(series.draw_ids == record['id'])[0])
    for name, (a, b) in segments.items():
        if a <= t < b:
            return name
    raise ValueError('Kỳ nằm ngoài các đoạn đã đăng ký')


def ch_fit_law_temperature(laws: list[Law], series: Series, start: int) -> float:
    """τ trên trọng số của từng chuyên gia (values ** τ) cực đại log-likelihood validation; giữ luật hợp lệ."""
    from scipy.optimize import minimize_scalar

    spec = laws[0].spec
    rows = [series.obs['main']['X'][start + i].astype(float) for i in range(len(laws))]
    bonus = [int(series.obs['main']['bonus'][start + i]) if spec.bonus_same_drum else 0 for i in range(len(laws))]

    def loss(tau: float) -> float:
        total = 0.0
        for law, row, b in zip(laws, rows, bonus):
            tempered = Law(spec, law.values ** tau, law.mixture)
            total += tempered.log_likelihood(row, b)
        return -total / len(laws)

    lo, hi = PROTOCOL['temperature_bounds']
    return float(minimize_scalar(loss, bounds=(lo, hi), method='bounded', options={'xatol': 1e-3}).x)


# ============================================================================ báo cáo
ARM_LABELS = {
    'fair': 'Công bằng (vé ngẫu nhiên chốt trước)', 'legacy': 'Legacy đang chạy', 'legacy_tempered': 'Legacy + hiệu chuẩn τ',
    'ml': 'ML đang chạy', 'ml_tempered': 'ML + hiệu chuẩn τ', 'shrink': 'Challenger co về công bằng',
    'causal': 'Challenger đặc trưng nhân quả',
}
PRODUCT_LABELS = {'mega645': 'Mega 6/45', 'power655': 'Power 6/55'}


def _vn(x: float | None, digits: int = 4) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return '—'
    if abs(x) < 0.5 * 10 ** -digits:
        x = 0.0  # không in "-0,00"
    return f'{x:,.{digits}f}'.replace(',', '\0').replace('.', ',').replace('\0', '.')


def _p(x: float) -> str:
    return '< 0,0001' if x < 1e-4 else _vn(x, 4)


def render_report(results: dict[str, dict], decision: dict) -> str:
    """Báo cáo Markdown tiếng Việt in TỪ artifact; không câu kết luận nào viết sẵn."""
    lines = ['# Vietlott: kiểm chứng xác suất và số khớp H — Mega 6/45, Power 6/55', '',
             f'Giao thức đăng ký ngày {PROTOCOL["registered_at"]} (`vlm.forecast.hit_benchmark.PROTOCOL`). '
             'Walk-forward theo kỳ: mỗi kỳ được dự báo trước khi mô hình thấy kết quả; cấu hình challenger chọn '
             'trên dev, bỏ nhóm đặc trưng không ổn định qua các fold dev + validation, hiệu chuẩn trên validation, '
             'rồi chốt trước khi chấm test một lần. Δ log-score là log P(mô hình) − log P(công bằng) mỗi kỳ, '
             'gồm bộ chính và (Power) số đặc biệt chấm riêng; dương là tốt hơn công bằng.', '']
    verdict = decision['verdict']
    eligible = [key for key, value in decision.items() if isinstance(value, dict) and value['eligible_for_prospective_trial']]
    lines += ['## Kết luận', '']
    if verdict == 'incomplete_run':
        lines.append('**Lượt chạy thiếu sản phẩm hoặc nhánh đã đăng ký: không xét đề bạt.** Chạy đủ '
                     '`python scripts/hit_benchmark.py` (cả hai sản phẩm, có bộ ML) để có kết luận.')
    elif verdict == 'keep_production':
        lines.append('**Challenger chưa chứng minh lợi thế.** Không ứng viên nào đạt đủ năm điều kiện đề bạt đã đăng ký; '
                     'giữ production: xác suất triển khai vẫn là luật công bằng (cổng live của bộ ML chưa mở), '
                     'vé công bố giữ nguyên quy tắc hiện có.')
    else:
        lines.append(f'**Đủ điều kiện chạy thử tiến cứu:** {", ".join(eligible)}. Xác suất triển khai chỉ đổi khi '
                     'ứng viên qua cổng live hiện có trên các kỳ SAU ngày đăng ký.')
    lines.append('')
    for product, r in results.items():
        name = PRODUCT_LABELS.get(product, product)
        prov, split = r['provenance'], r['split']
        lines += [f'## {name}', '',
                  f'Dữ liệu #{prov["first_id"]}–#{prov["last_id"]} ({prov["first_date"]} → {prov["last_date"]}), '
                  f'`history_sha256` `{prov["history_sha256"][:16]}…`, commit `{(prov["git_commit"] or "—")[:12]}`. '
                  f'Bỏ {split["warmup_draws"]} kỳ đầu; dev #{split["dev"]["first_id"]}–#{split["dev"]["last_id"]} '
                  f'({split["dev"]["draws"]} kỳ), validation #{split["validation"]["first_id"]}–#{split["validation"]["last_id"]} '
                  f'({split["validation"]["draws"]}), test #{split["test"]["first_id"]}–#{split["test"]["last_id"]} '
                  f'({split["test"]["first_date"]} → {split["test"]["last_date"]}, {split["test"]["draws"]} kỳ).', '']
        lines += ['### Test (nhìn một lần)', '',
                  '| Nhánh | Δ log-score (nats/kỳ) | p tốt hơn công bằng | Brier − công bằng (×10⁶) | ECE (×10⁴) | H trung bình | H ≥ 3 | H ≥ 4 | H ≥ 5 | H = 6 |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        seg, tests = r['segments']['test'], r['tests']['test']
        for arm in ('fair', 'legacy', 'legacy_tempered', 'ml', 'ml_tempered', 'shrink', 'causal'):
            if arm not in seg:
                continue
            m = seg[arm]
            lv = m['hits']['levels']
            p = '—' if arm == 'fair' else _p(tests[arm]['vs_fair']['p_value_greater'])
            lines.append(f'| {ARM_LABELS[arm]} | {_vn(m["mean_log_gain_nats"], 6)} | {p} | '
                         f'{_vn((m["brier"] - m["brier_fair"]) * 1e6, 2)} | {_vn(m["reliability"]["ece"] * 1e4, 2)} | '
                         f'{_vn(m["hits"]["mean_hits"], 3)} | {lv["ge3"]["reached"]} | {lv["ge4"]["reached"]} | '
                         f'{lv["ge5"]["reached"]} | {lv["ge6"]["reached"]} |')
        fair_levels = seg['fair']['hits']['levels']
        lines.append(f'| *Kỳ vọng siêu bội* | 0 | — | 0 | — | {_vn(seg["fair"]["hits"]["fair_mean"], 3)} | '
                     f'{_vn(fair_levels["ge3"]["expected"], 2)} | {_vn(fair_levels["ge4"]["expected"], 2)} | '
                     f'{_vn(fair_levels["ge5"]["expected"], 3)} | {_vn(fair_levels["ge6"]["expected"], 4)} |')
        lines.append('')
        comparisons = [(arm, inc) for arm in CANDIDATES if arm in tests for inc in INCUMBENTS if f'vs_{inc}' in tests[arm]]
        if comparisons:
            lines += ['| Ứng viên | So với | Δ (nats/kỳ) | p một phía (DM HAC) |', '|---|---|---:|---:|']
            for arm, inc in comparisons:
                t = tests[arm][f'vs_{inc}']
                lines.append(f'| {ARM_LABELS[arm]} | {ARM_LABELS[inc]} | {_vn(t["mean_difference_nats"], 6)} | {_p(t["p_value_greater"])} |')
            lines.append('')
        sel = r['selection']
        abl = ', '.join(f'{a["group"]} {_vn(a["mean_delta"] * 1e4, 2)}·10⁻⁴ ({"giữ" if a["keep"] else "bỏ"})' for a in sel['causal']['ablation'])
        lines += ['### Chọn cấu hình (chỉ dev/validation)', '',
                  f'- Co về công bằng: nửa đời {sel["shrink"]["half_life"] or "∞"}, độ co {_vn(sel["shrink"]["prior"], 0)}, '
                  f'τ dev {_vn(sel["shrink"]["tau_dev"], 3)}, τ validation {_vn(sel["shrink"]["tau_validation"], 3)}.',
                  f'- Đặc trưng nhân quả: λ = {sel["causal"]["l2"]}; ablation Δ trung bình theo nhóm: {abl}. '
                  f'Nhóm giữ lại: {", ".join(sel["causal"]["groups"]) or "không nhóm nào — challenger trùng luật công bằng"}; '
                  f'τ validation {_vn(sel["causal"]["tau_validation"], 3)}.',
                  f'- Hiệu chuẩn nhiệt độ trên validation: legacy τ = {_vn(sel["legacy_tau_validation"], 4)}'
                  + (f', ML τ = {_vn(sel["ml_tau_validation"], 4)}' if sel['ml_tau_validation'] is not None else '')
                  + ' (τ = 1: giữ nguyên; τ → 0: dữ liệu đòi co hẳn về công bằng).', '']
        power = r['hit_power']
        lines += ['### Công suất thống kê của H', '',
                  '| Mức | Tỷ lệ ngẫu nhiên | Hệ số tối thiểu phát hiện được (test, 80%, α = 5%) | Trên mọi kỳ đã chấm | Số kỳ cần để phát hiện ×2 | ×1,2 |',
                  '|---|---:|---:|---:|---:|---:|']
        for level, row in power.items():
            lines.append(f'| H ≥ {level[2:]} | {_vn(row["fair_rate"] * 100, 4)}% | ×{_vn(row["test"]["lift"], 2)} '
                         f'| ×{_vn(row["all_scored"]["lift"], 2)} | {row["draws_needed_for_lift_2"] or "—"} | {row["draws_needed_for_lift_1_2"] or "—"} |')
        lines.append('')
        descriptive = r['hits_all_scored_descriptive']
        lines += ['### H trên mọi kỳ đã chấm (mô tả; chỉ mô hình KHÔNG được chỉnh ở đây)', '',
                  '| Nhánh | Kỳ | H trung bình | H ≥ 3 (kỳ vọng) | H ≥ 4 (kỳ vọng) | p H ≥ 3 tốt hơn ngẫu nhiên |', '|---|---:|---:|---:|---:|---:|']
        for arm, summary in descriptive.items():
            lv = summary['levels']
            lines.append(f'| {ARM_LABELS[arm]} | {summary["draws"]} | {_vn(summary["mean_hits"], 3)} | '
                         f'{lv["ge3"]["reached"]} ({_vn(lv["ge3"]["expected"], 1)}) | {lv["ge4"]["reached"]} ({_vn(lv["ge4"]["expected"], 2)}) | '
                         f'{_p(lv["ge3"]["p_value_greater"])} |')
        lines.append('')
        if r.get('portfolio_ml'):
            lines += ['### Danh mục 5 vé của ML (ngân sách cố định 50.000 đ/kỳ)', '',
                      '| Đoạn | Kỳ | Trùng trung bình giữa hai vé | Độ phủ | Ít nhất một vé H ≥ 3 (ngẫu nhiên) | H ≥ 4 (ngẫu nhiên) | p H ≥ 3 |',
                      '|---|---:|---:|---:|---:|---:|---:|']
            for seg_name, pf in r['portfolio_ml'].items():
                a3, a4 = pf['any_ticket']['ge3'], pf['any_ticket']['ge4']
                lines.append(f'| {seg_name} | {pf["draws"]} | {_vn(pf["mean_pairwise_overlap"], 2)} số | {_vn(pf["mean_coverage"] * 100, 1)}% | '
                             f'{a3["reached"]} ({_vn(a3["expected"], 1)}) | {a4["reached"]} ({_vn(a4["expected"], 2)}) | {_p(a3["p_value_greater"])} |')
            lines += ['', 'Năm vé tốn năm lần tiền vé; xác suất "ít nhất một vé" cao hơn một vé là do mua nhiều vé, không phải dự báo tốt hơn.', '']
    lines += ['## Điều kiện đề bạt (đã đăng ký)', '']
    lines += [f'- {key}: {text}' for key, text in PROTOCOL['promotion'].items()]
    lines += ['', '| Ứng viên | Thắng công bằng (Holm) | Thắng legacy và ML | Validation dương | Ổn định 2/3 đoạn | Brier không kém | Đủ điều kiện |',
              '|---|---|---|---|---|---|---|']
    for key, value in decision.items():
        if not isinstance(value, dict):
            continue
        c = value['checks']
        mark = {True: 'đạt', False: 'không'}
        product, arm = key.split(':')
        lines.append(f'| {PRODUCT_LABELS.get(product, product)} · {ARM_LABELS[arm]} | {mark[c["beats_fair_holm"]]} (p Holm {_p(value["holm_p_vs_fair"])}) | '
                     f'{mark[c["beats_incumbents"]]} | {mark[c["validation_positive"]]} | {mark[c["stable_thirds"]]} | '
                     f'{mark[c["brier_not_worse"]]} | **{mark[value["eligible_for_prospective_trial"]]}** |')
    lines.append('')
    return '\n'.join(lines) + '\n'
