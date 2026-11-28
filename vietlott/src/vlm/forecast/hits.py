from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations
from math import comb, exp, log, sqrt

import numpy as np
from scipy import stats
from scipy.special import logsumexp

LEVELS = (3, 4, 5, 6)
PREDICTABLE_LIFTS = (1.25, 1.5, 2.0, 3.0, 5.0, 10.0)


def fair_hit_pmf(n: int, k: int = 6, ticket: int = 6) -> np.ndarray:
    for value in (n, k, ticket):
        if type(value) is not int:
            raise ValueError('Tham số siêu bội phải là số nguyên')
    if not 1 <= k <= n or not 1 <= ticket <= n:
        raise ValueError('Cần 1 ≤ k ≤ n và 1 ≤ số trên vé ≤ n')
    total = comb(n, k)
    return np.array([comb(ticket, h) * comb(n - ticket, k - h) / total if 0 <= k - h <= n - ticket else 0.0
                     for h in range(ticket + 1)])


def hit_count(ticket: Sequence[int], drawn: Sequence[int], n: int) -> int:
    for name, values in (('vé', ticket), ('kết quả', drawn)):
        if any(type(v) not in (int, np.int64, np.int32) for v in values):
            raise ValueError(f'{name} phải gồm số nguyên')
        if len(set(values)) != len(values) or any(not 1 <= v <= n for v in values):
            raise ValueError(f'{name} có số trùng hoặc ngoài 1..{n}')
    return len(set(int(v) for v in ticket) & set(int(v) for v in drawn))


def clopper_pearson(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    if trials < 1 or not 0 <= successes <= trials:
        raise ValueError('Số lần đạt phải trong 0..số kỳ')
    alpha = 1 - confidence
    low = 0.0 if successes == 0 else float(stats.beta.ppf(alpha / 2, successes, trials - successes + 1))
    high = 1.0 if successes == trials else float(stats.beta.ppf(1 - alpha / 2, successes + 1, trials - successes))
    return low, high


def summarize_hits(hits: Sequence[int], n: int, k: int = 6, ticket: int = 6) -> dict:
    h = np.asarray(hits, dtype=np.int64)
    if h.ndim != 1 or h.size == 0 or (h < 0).any() or (h > ticket).any():
        raise ValueError('Số khớp phải là vectơ khác rỗng trong 0..số trên vé')
    draws = int(h.size)
    pmf = fair_hit_pmf(n, k, ticket)
    counts = np.bincount(h, minlength=ticket + 1)
    fair_mean = ticket * k / n
    fair_var = ticket * (k / n) * (1 - k / n) * (n - ticket) / (n - 1)
    mean = float(h.mean())
    sd = float(h.std(ddof=1)) if draws > 1 else 0.0
    half = float(stats.t.ppf(0.975, draws - 1)) * sd / sqrt(draws) if draws > 1 else float('nan')
    levels = {}
    for level in LEVELS:
        if level > ticket:
            continue
        reached = int((h >= level).sum())
        p0 = float(pmf[level:].sum())
        low, high = clopper_pearson(reached, draws)
        levels[f'ge{level}'] = {
            'reached': reached, 'rate': reached / draws, 'ci95': [low, high],
            'fair_rate': p0, 'expected': draws * p0,
            'lift': (reached / draws) / p0 if p0 > 0 else None,
            'p_value_greater': float(stats.binom.sf(reached - 1, draws, p0)),
        }
    return {
        'draws': draws, 'counts': counts.tolist(), 'expected_counts': (draws * pmf).tolist(),
        'mean_hits': mean, 'mean_ci95': [mean - half, mean + half], 'fair_mean': fair_mean,
        'z_mean': (float(h.sum()) - draws * fair_mean) / sqrt(draws * fair_var),
        'levels': levels,
    }


def _critical_count(p0: float, draws: int, alpha: float) -> int:
    c = int(stats.binom.isf(alpha, draws, p0))
    while stats.binom.sf(c - 1, draws, p0) > alpha:
        c += 1
    while c > 0 and stats.binom.sf(c - 2, draws, p0) <= alpha:
        c -= 1
    return c


def detectable_lift(p0: float, draws: int, alpha: float = 0.05, power: float = 0.8) -> dict:
    if not 0 < p0 < 1 or draws < 1 or not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError('Tham số công suất không hợp lệ')
    c = _critical_count(p0, draws, alpha)
    if c > draws:
        return {'draws': draws, 'alpha': alpha, 'power': power, 'critical_reached': c,
                'attainable': False, 'rate': None, 'lift': None}
    low, high = p0, 1.0
    for _ in range(200):
        mid = (low + high) / 2
        if stats.binom.sf(c - 1, draws, mid) >= power:
            high = mid
        else:
            low = mid
    return {'draws': draws, 'alpha': alpha, 'power': power, 'critical_reached': c,
            'attainable': True, 'rate': high, 'lift': high / p0}


def _critical_counts(p0: float, draws: np.ndarray, alpha: float) -> np.ndarray:
    c = stats.binom.isf(alpha, draws, p0).astype(np.int64)
    while (high := stats.binom.sf(c - 1, draws, p0) > alpha).any():
        c += high
    while (low := (c > 0) & (stats.binom.sf(c - 2, draws, p0) <= alpha)).any():
        c -= low
    return c


def draws_needed(p0: float, lift: float, alpha: float = 0.05, power: float = 0.8, limit: int = 10_000_000) -> int | None:
    if lift <= 1 or lift * p0 >= 1:
        raise ValueError('Cần 1 < lift và lift·p₀ < 1')
    if limit < 1:
        raise ValueError('limit phải ≥ 1')

    def powers(draws: np.ndarray) -> np.ndarray:
        return stats.binom.sf(_critical_counts(p0, draws, alpha) - 1, draws, lift * p0)

    high = 1
    while high < limit and powers(np.array([high]))[0] < power:
        high = min(high * 2, limit)
    for start in range(1, high + 1, 200_000):
        block = np.arange(start, min(high, start + 199_999) + 1)
        hit = np.flatnonzero(powers(block) >= power)
        if hit.size:
            return int(block[hit[0]])
    return None


def poisson_binomial_sf(reached: int, probabilities: Sequence[float]) -> float:
    dist = np.zeros(len(probabilities) + 1)
    dist[0] = 1.0
    for count, p in enumerate(probabilities, start=1):
        dist[1:count + 1] = dist[1:count + 1] * (1 - p) + dist[:count] * p
        dist[0] *= 1 - p
    return float(dist[max(reached, 0):].sum())


def predictable_p_value(reached: Sequence[bool], probabilities: Sequence[float],
                        lifts: Sequence[float] = PREDICTABLE_LIFTS) -> float:
    r = np.asarray(lifts, dtype=float)
    if r.size == 0 or (r <= 1).any():
        raise ValueError('Cần lưới hệ số tăng r > 1')
    log_wealth = np.zeros(r.size)
    best = 0.0
    for x, p in zip(reached, probabilities, strict=True):
        p = float(p)
        if not 0 <= p <= 1:
            raise ValueError('Xác suất ngoài [0, 1]')
        if p == 0:
            if x:
                return 0.0
            continue
        if p == 1:
            continue
        q = np.minimum(r * p, 1.0)
        with np.errstate(divide='ignore'):
            log_wealth += np.log(q / p) if x else np.log1p(-q) - np.log1p(-p)
        best = max(best, float(logsumexp(log_wealth)) - log(r.size))
    return min(1.0, exp(-best))


def any_ticket_tail(tickets: Sequence[Sequence[int]], n: int, k: int = 6, limit: int = 200_000) -> np.ndarray | None:
    sets = [set(t) for t in tickets]
    regions: dict[tuple[bool, ...], int] = {}
    for v in set().union(*sets):
        key = tuple(v in s for s in sets)
        regions[key] = regions.get(key, 0) + 1
    keys = list(regions)
    if comb(k + len(keys), k) > limit:
        return None
    sizes = [regions[key] for key in keys]
    owned = [[a for a, key in enumerate(keys) if key[t]] for t in range(len(sets))]
    outside = n - sum(sizes)
    weights = [0] * (k + 1)
    counts = [0] * len(keys)

    def walk(region: int, left: int, weight: int) -> None:
        if region == len(keys):
            w = weight * comb(outside, left)
            if w:
                weights[max(sum(counts[a] for a in regions_of) for regions_of in owned)] += w
            return
        for c in range(min(sizes[region], left) + 1):
            counts[region] = c
            walk(region + 1, left - c, weight * comb(sizes[region], c))
        counts[region] = 0

    walk(0, k, 1)
    total = comb(n, k)
    tail = np.zeros(k + 1)
    acc = 0
    for level in range(k, -1, -1):
        acc += weights[level]
        tail[level] = acc / total
    return tail


def union_bounds(tickets: Sequence[Sequence[int]], n: int, k: int = 6) -> tuple[np.ndarray, np.ndarray]:
    single = np.array([any_ticket_tail([t], n, k, limit=10**9) for t in tickets])
    total = single.sum(axis=0)
    joint = np.zeros(k + 1)
    for i, j in combinations(range(len(tickets)), 2):
        joint += single[i] + single[j] - any_ticket_tail([tickets[i], tickets[j]], n, k, limit=10**9)
    return np.maximum(single.max(axis=0), total - joint), np.minimum(total, 1.0)


def portfolio_summary(portfolios: Sequence[Sequence[Sequence[int]]], drawn: Sequence[Sequence[int]], n: int,
                      k: int = 6, simulations: int = 20_000, seed: int = 20261013, exact_limit: int = 200_000) -> dict:
    if len(portfolios) != len(drawn) or not portfolios:
        raise ValueError('Mỗi kỳ cần đúng một danh mục vé')
    size = len(portfolios[0])
    if size < 1 or any(len(p) != size for p in portfolios):
        raise ValueError('Số vé mỗi kỳ phải cố định khi so sánh')
    incidence = None
    monte_carlo_draws = 0
    per_ticket = []
    best = []
    fair_any = {level: [] for level in LEVELS}
    null_for_test = {level: [] for level in LEVELS}
    aggregate = {level: np.zeros(simulations) for level in LEVELS}
    overlap, coverage = [], []
    for tickets, result in zip(portfolios, drawn):
        hits = [hit_count(list(t), list(result), n) for t in tickets]
        per_ticket.extend(hits)
        best.append(max(hits))
        tail = any_ticket_tail(tickets, n, k, exact_limit)
        if tail is not None:
            for level in LEVELS:
                fair_any[level].append(float(tail[level]))
                null_for_test[level].append(float(tail[level]))
        else:
            if incidence is None:
                rng = np.random.default_rng(seed)
                sample = np.argsort(rng.random((simulations, n)), axis=1)[:, :k]
                incidence = np.zeros((simulations, n), dtype=bool)
                np.put_along_axis(incidence, sample, True, axis=1)
            monte_carlo_draws += 1
            index = np.asarray([[v - 1 for v in t] for t in tickets])
            simulated = incidence[:, index].sum(axis=2).max(axis=1)
            lower, upper = union_bounds(tickets, n, k)
            for level in LEVELS:
                reached = simulated >= level
                fair_any[level].append(float(np.clip(reached.mean(), lower[level], upper[level])))
                null_for_test[level].append(float(upper[level]))
                aggregate[level] += reached
        pairs = [len(set(a) & set(b)) for a, b in combinations(tickets, 2)]
        overlap.append(float(np.mean(pairs)) if pairs else 0.0)
        coverage.append(len({v for t in tickets for v in t}) / (size * len(tickets[0])))
    best_arr = np.asarray(best)
    any_level = {}
    for level in LEVELS:
        reached = int((best_arr >= level).sum())
        probabilities = fair_any[level]
        expected = float(np.sum(probabilities))
        any_level[f'ge{level}'] = {
            'reached': reached, 'rate': reached / len(best), 'expected': expected,
            'fair_rate': expected / len(best),
            'monte_carlo_se': float(aggregate[level].std(ddof=1) / np.sqrt(simulations)),
            'p_value_greater': predictable_p_value(best_arr >= level, null_for_test[level]),
            'p_value_fixed_portfolios': poisson_binomial_sf(reached, null_for_test[level]),
        }
    return {'draws': len(portfolios), 'tickets_per_draw': size, 'simulations': simulations, 'seed': seed,
            'exact_draws': len(portfolios) - monte_carlo_draws, 'monte_carlo_draws': monte_carlo_draws,
            'per_ticket': summarize_hits(per_ticket, n, k, len(portfolios[0][0])),
            'per_ticket_note': 'Vé trong cùng kỳ chấm trên cùng một kết quả nên không độc lập; p theo từng vé chỉ mô tả.',
            'any_ticket_note': ('p_value_greater luôn hợp lệ kể cả khi danh mục học lại sau mỗi kỳ (e-process, Ville); '
                                'p_value_fixed_portfolios chỉ đúng khi mọi danh mục chốt trước cả cửa sổ. Kỳ tính bằng '
                                'Monte Carlo kiểm bằng cận trên chính xác, không bằng ước lượng điểm.'),
            'any_ticket': any_level, 'mean_pairwise_overlap': float(np.mean(overlap)),
            'mean_coverage': float(np.mean(coverage))}
