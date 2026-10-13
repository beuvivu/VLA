"""Số khớp H của vé sáu số chính đã phát TRƯỚC kỳ quay, so với mốc ngẫu nhiên đúng luật.

Với vé t số và kết quả k số chính rút từ n số, H = |vé ∩ kết quả|. Khi máy quay công bằng và vé
được chốt trước kỳ quay thì H theo phân phối siêu bội, BẤT KỂ vé được chọn thế nào:

    P(H = h) = C(t, h) · C(n − t, k − h) / C(n, k).

Đơn vị quan sát là KỲ QUAY: các số trong một kỳ không độc lập, nên mọi kiểm định ở đây đếm kỳ,
không đếm số. Số đặc biệt Power không bao giờ được cộng vào H — nó được chấm riêng ở nơi khác.

H ≥ 4 là sự kiện hiếm (Mega ≈ 0,139%, Power ≈ 0,062% mỗi vé), nên module có phân tích công suất:
với cỡ mẫu hiện có, chỉ một mức tăng rất lớn mới có thể được phát hiện; dưới ngưỡng ấy kết luận
đúng là "chưa đủ bằng chứng", không phải "không có".

Nhiều vé mỗi kỳ được tách bạch: chỉ số theo TỪNG vé khác với "ít nhất một vé đạt mức", và mốc
ngẫu nhiên của "ít nhất một vé" phụ thuộc độ trùng giữa các vé nên được ước lượng Monte Carlo trên
chính bộ vé ấy (kèm sai số Monte Carlo). Nhiều vé hơn KHÔNG phải dự báo tốt hơn.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations
from math import comb, sqrt

import numpy as np
from scipy import stats

LEVELS = (3, 4, 5, 6)


def fair_hit_pmf(n: int, k: int = 6, ticket: int = 6) -> np.ndarray:
    """P(H = h), h = 0..ticket, khi kết quả là k số rút đều từ n số (siêu bội).

    Args:
        n: Số số trong lồng cầu (45 Mega, 55 Power).
        k: Số số chính được quay.
        ticket: Số số trên vé.

    Returns:
        Mảng ticket + 1 xác suất, tổng bằng 1.

    Raises:
        ValueError: Tham số không hợp lệ.
    """
    for value in (n, k, ticket):
        if type(value) is not int:
            raise ValueError('Tham số siêu bội phải là số nguyên')
    if not 1 <= k <= n or not 1 <= ticket <= n:
        raise ValueError('Cần 1 ≤ k ≤ n và 1 ≤ số trên vé ≤ n')
    total = comb(n, k)
    # h > k hoặc k − h > n − ticket là bất khả: xác suất 0 (comb không nhận đối số âm).
    return np.array([comb(ticket, h) * comb(n - ticket, k - h) / total if 0 <= k - h <= n - ticket else 0.0
                     for h in range(ticket + 1)])


def hit_count(ticket: Sequence[int], drawn: Sequence[int], n: int) -> int:
    """|vé ∩ kết quả|, sau khi kiểm vé và kết quả đều là các số phân biệt trong 1..n."""
    for name, values in (('vé', ticket), ('kết quả', drawn)):
        if any(type(v) not in (int, np.int64, np.int32) for v in values):
            raise ValueError(f'{name} phải gồm số nguyên')
        if len(set(values)) != len(values) or any(not 1 <= v <= n for v in values):
            raise ValueError(f'{name} có số trùng hoặc ngoài 1..{n}')
    return len(set(int(v) for v in ticket) & set(int(v) for v in drawn))


def clopper_pearson(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    """Khoảng tin cậy chính xác cho tỷ lệ nhị thức (không dùng xấp xỉ chuẩn cho sự kiện hiếm)."""
    if trials < 1 or not 0 <= successes <= trials:
        raise ValueError('Số lần đạt phải trong 0..số kỳ')
    alpha = 1 - confidence
    low = 0.0 if successes == 0 else float(stats.beta.ppf(alpha / 2, successes, trials - successes + 1))
    high = 1.0 if successes == trials else float(stats.beta.ppf(1 - alpha / 2, successes + 1, trials - successes))
    return low, high


def summarize_hits(hits: Sequence[int], n: int, k: int = 6, ticket: int = 6) -> dict:
    """Phân bố H của MỘT vé mỗi kỳ, so với siêu bội.

    Returns:
        draws, phân bố đếm và kỳ vọng, số khớp trung bình (khoảng tin cậy 95%, z theo phương sai
        siêu bội chính xác), và cho mỗi mức L ∈ {3, 4, 5, 6}: số kỳ đạt, tỷ lệ, khoảng
        Clopper–Pearson, tỷ lệ ngẫu nhiên, hệ số so với ngẫu nhiên và p một phía (nhị thức chính
        xác, "tốt hơn ngẫu nhiên").
    """
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
    """Số kỳ đạt nhỏ nhất c để P₀(X ≥ c) ≤ α (kiểm định nhị thức một phía, chính xác)."""
    c = int(stats.binom.isf(alpha, draws, p0))
    while stats.binom.sf(c - 1, draws, p0) > alpha:
        c += 1
    while c > 0 and stats.binom.sf(c - 2, draws, p0) <= alpha:
        c -= 1
    return c


def detectable_lift(p0: float, draws: int, alpha: float = 0.05, power: float = 0.8) -> dict:
    """Hệ số tăng nhỏ nhất của tỷ lệ p₀ mà phép kiểm nhị thức một phía phát hiện với công suất cho trước.

    Returns:
        ``critical_reached`` (số kỳ phải đạt để bác bỏ), ``rate`` và ``lift`` = rate / p₀ cần có.
    """
    if not 0 < p0 < 1 or draws < 1 or not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError('Tham số công suất không hợp lệ')
    c = _critical_count(p0, draws, alpha)
    low, high = p0, 1.0
    for _ in range(200):
        mid = (low + high) / 2
        if stats.binom.sf(c - 1, draws, mid) >= power:
            high = mid
        else:
            low = mid
    return {'draws': draws, 'alpha': alpha, 'power': power, 'critical_reached': c,
            'rate': high, 'lift': high / p0}


def draws_needed(p0: float, lift: float, alpha: float = 0.05, power: float = 0.8, limit: int = 10_000_000) -> int | None:
    """Số kỳ tối thiểu để phát hiện tỷ lệ lift·p₀ với công suất cho trước; None nếu vượt ``limit``."""
    if lift <= 1 or lift * p0 >= 1:
        raise ValueError('Cần 1 < lift và lift·p₀ < 1')

    def enough(draws: int) -> bool:
        c = _critical_count(p0, draws, alpha)
        return bool(stats.binom.sf(c - 1, draws, lift * p0) >= power)

    high = 1
    while not enough(high):
        high *= 2
        if high > limit:
            return None
    low = high // 2
    while high - low > 1:
        mid = (low + high) // 2
        if enough(mid):
            high = mid
        else:
            low = mid
    return high


def poisson_binomial_sf(reached: int, probabilities: Sequence[float]) -> float:
    """P(X ≥ reached) với X là tổng các Bernoulli độc lập xác suất khác nhau (quy hoạch động)."""
    dist = np.zeros(len(probabilities) + 1)
    dist[0] = 1.0
    for count, p in enumerate(probabilities, start=1):
        dist[1:count + 1] = dist[1:count + 1] * (1 - p) + dist[:count] * p
        dist[0] *= 1 - p
    return float(dist[max(reached, 0):].sum())


def portfolio_summary(portfolios: Sequence[Sequence[Sequence[int]]], drawn: Sequence[Sequence[int]], n: int,
                      k: int = 6, simulations: int = 20_000, seed: int = 20261013) -> dict:
    """Nhiều vé mỗi kỳ, số vé CỐ ĐỊNH: tách chỉ số từng vé với "ít nhất một vé đạt mức".

    Mốc ngẫu nhiên của "ít nhất một vé ≥ L" phụ thuộc độ trùng giữa các vé, nên được ước lượng bằng
    cùng ``simulations`` kết quả rút đều (số ngẫu nhiên chung cho mọi kỳ), kèm sai số Monte Carlo.
    Số kỳ đạt được so với tổng các xác suất ấy bằng p Poisson–nhị thức một phía.
    """
    if len(portfolios) != len(drawn) or not portfolios:
        raise ValueError('Mỗi kỳ cần đúng một danh mục vé')
    size = len(portfolios[0])
    if size < 1 or any(len(p) != size for p in portfolios):
        raise ValueError('Số vé mỗi kỳ phải cố định khi so sánh')
    rng = np.random.default_rng(seed)
    sample = np.argsort(rng.random((simulations, n)), axis=1)[:, :k]
    incidence = np.zeros((simulations, n), dtype=bool)
    np.put_along_axis(incidence, sample, True, axis=1)
    per_ticket = []
    best = []
    fair_any = {level: [] for level in LEVELS}
    overlap, coverage = [], []
    for tickets, result in zip(portfolios, drawn):
        hits = [hit_count(list(t), list(result), n) for t in tickets]
        per_ticket.extend(hits)
        best.append(max(hits))
        index = np.asarray([[v - 1 for v in t] for t in tickets])
        simulated = incidence[:, index].sum(axis=2).max(axis=1)  # (S,) số khớp tốt nhất trong danh mục
        for level in LEVELS:
            fair_any[level].append(float((simulated >= level).mean()))
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
            'monte_carlo_se': float(np.sqrt(np.sum(np.asarray(probabilities) * (1 - np.asarray(probabilities)) / simulations))),
            'p_value_greater': poisson_binomial_sf(reached, probabilities),
        }
    return {'draws': len(portfolios), 'tickets_per_draw': size, 'simulations': simulations, 'seed': seed,
            'per_ticket': summarize_hits(per_ticket, n, k, len(portfolios[0][0])),
            'per_ticket_note': 'Vé trong cùng kỳ chấm trên cùng một kết quả nên không độc lập; p theo từng vé chỉ mô tả.',
            'any_ticket': any_level, 'mean_pairwise_overlap': float(np.mean(overlap)),
            'mean_coverage': float(np.mean(coverage))}
