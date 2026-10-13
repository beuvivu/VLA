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
ngẫu nhiên của "ít nhất một vé" phụ thuộc độ trùng giữa các vé nên được tính CHÍNH XÁC trên chính bộ
vé ấy (liệt kê theo vùng giao của các vé); Monte Carlo chỉ là dự phòng khi danh mục quá lớn. Nhiều
vé hơn KHÔNG phải dự báo tốt hơn.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations
from math import comb, exp, log, sqrt

import numpy as np
from scipy import stats
from scipy.special import logsumexp

LEVELS = (3, 4, 5, 6)
#: Lưới hệ số tăng r của e-process cho xác suất dự đoán được (chốt 13-10-2026; đổi lưới là đổi phép kiểm).
PREDICTABLE_LIFTS = (1.25, 1.5, 2.0, 3.0, 5.0, 10.0)


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
        Khi số kỳ tới hạn vượt số kỳ (``attainable`` = False) không kết quả nào bác bỏ được H₀:
        công suất bằng 0 ở MỌI tỷ lệ, nên ``rate`` và ``lift`` là None, không phải ×(1/p₀).
    """
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
    """``_critical_count`` cho cả một mảng số kỳ (vectơ hoá)."""
    c = stats.binom.isf(alpha, draws, p0).astype(np.int64)
    while (high := stats.binom.sf(c - 1, draws, p0) > alpha).any():
        c += high
    while (low := (c > 0) & (stats.binom.sf(c - 2, draws, p0) <= alpha)).any():
        c -= low
    return c


def draws_needed(p0: float, lift: float, alpha: float = 0.05, power: float = 0.8, limit: int = 10_000_000) -> int | None:
    """Số kỳ NHỎ NHẤT mà phép kiểm nhị thức chính xác đạt công suất cho trước với tỷ lệ lift·p₀.

    Công suất của phép kiểm rời rạc không đơn điệu theo số kỳ (răng cưa: mỗi khi số kỳ đạt tới hạn
    tăng một bậc, công suất tụt xuống), nên không tìm nhị phân được: tìm một mốc đủ bằng cách nhân
    đôi (mốc cuối chặn ở ``limit``) rồi quét MỌI số kỳ tới mốc ấy. None nếu không số kỳ nào
    ≤ ``limit`` đạt — kết luận ấy chỉ đưa ra sau khi đã quét hết 1..``limit``: công suất ở chính
    ``limit`` thấp không loại được một số kỳ nhỏ hơn nằm trên đỉnh răng cưa.
    """
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
    """P(X ≥ reached) với X là tổng các Bernoulli độc lập xác suất khác nhau (quy hoạch động)."""
    dist = np.zeros(len(probabilities) + 1)
    dist[0] = 1.0
    for count, p in enumerate(probabilities, start=1):
        dist[1:count + 1] = dist[1:count + 1] * (1 - p) + dist[:count] * p
        dist[0] *= 1 - p
    return float(dist[max(reached, 0):].sum())


def predictable_p_value(reached: Sequence[bool], probabilities: Sequence[float],
                        lifts: Sequence[float] = PREDICTABLE_LIFTS) -> float:
    """p một phía LUÔN hợp lệ khi xác suất mốc p_t của mỗi kỳ chỉ phụ thuộc các kỳ TRƯỚC (dự đoán được).

    Danh mục học lại sau mỗi kỳ nên p_t phụ thuộc các kết quả trước; khi ấy tổng các chỉ báo KHÔNG theo
    Poisson–nhị thức của dãy p đã thực hiện (ba kỳ đủ để Poisson–nhị thức bác bỏ 5,84% ở α = 5%). Dưới
    H₀, P(X_t = 1 | quá khứ) = p_t, nên tỉ số hợp lý của Bernoulli(min(r·p_t, 1)) so với Bernoulli(p_t)
    nhân dồn là martingale không âm kỳ vọng 1, và trung bình đều trên lưới r cũng vậy. Theo bất đẳng thức
    Ville, p = min(1, 1 / max_t E_t) hợp lệ ở mọi thời điểm, kể cả khi dừng theo dữ liệu.

    Args:
        reached: Chỉ báo đạt mức của từng kỳ, theo THỨ TỰ THỜI GIAN.
        probabilities: p_t dưới H₀, tính trước kỳ t.
    """
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
                return 0.0  # đạt một mức bất khả dưới H₀
            continue
        if p == 1:
            continue
        q = np.minimum(r * p, 1.0)
        with np.errstate(divide='ignore'):
            log_wealth += np.log(q / p) if x else np.log1p(-q) - np.log1p(-p)
        best = max(best, float(logsumexp(log_wealth)) - log(r.size))
    return min(1.0, exp(-best))


def any_ticket_tail(tickets: Sequence[Sequence[int]], n: int, k: int = 6, limit: int = 200_000) -> np.ndarray | None:
    """P(số khớp TỐT NHẤT trong danh mục ≥ L), L = 0..k, CHÍNH XÁC khi kết quả là k số rút đều từ n số.

    Hợp các vé được chia thành vùng theo tập vé chứa số ấy (vùng Venn). Kết quả rút đều nên số con rơi
    vào từng vùng theo siêu bội nhiều chiều, P(c) = Π C(cỡ vùng, c_vùng) · C(n − |hợp|, k − Σc) / C(n, k),
    và số khớp của mỗi vé là tổng c trên các vùng của nó. Liệt kê mọi c (số nguyên, không làm tròn) cho
    phân phối của số khớp tốt nhất — kể cả mức hiếm mà một mẫu mô phỏng hữu hạn không bao giờ gặp.

    Returns:
        Mảng k + 1 phần tử; None khi cận số tổ hợp C(k + số vùng, k) vượt ``limit`` (dùng Monte Carlo).
    """
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
    """Cận CHÍNH XÁC của P(ít nhất một vé ≥ L), L = 0..k, khi danh mục quá lớn để liệt kê.

    Trên: Σ P(Aᵢ). Dưới: Bonferroni bậc hai Σ P(Aᵢ) − Σ_{i<j} P(Aᵢ ∩ Aⱼ) (không nhỏ hơn vé tốt nhất),
    với P(Aᵢ ∩ Aⱼ) = P(Aᵢ) + P(Aⱼ) − P(Aᵢ ∪ Aⱼ) tính bằng ``any_ticket_tail`` trên hai vé. Ở mức hiếm
    hai cận gần trùng nhau (sáu vé khác nhau: H = 6 đúng 6/C(n, 6)), nên một sự kiện mà mẫu mô phỏng
    hữu hạn chưa gặp không kéo ước lượng xuống cận của MỘT vé.
    """
    single = np.array([any_ticket_tail([t], n, k, limit=10**9) for t in tickets])
    total = single.sum(axis=0)
    joint = np.zeros(k + 1)
    for i, j in combinations(range(len(tickets)), 2):
        joint += single[i] + single[j] - any_ticket_tail([tickets[i], tickets[j]], n, k, limit=10**9)
    return np.maximum(single.max(axis=0), total - joint), np.minimum(total, 1.0)


def portfolio_summary(portfolios: Sequence[Sequence[Sequence[int]]], drawn: Sequence[Sequence[int]], n: int,
                      k: int = 6, simulations: int = 20_000, seed: int = 20261013, exact_limit: int = 200_000) -> dict:
    """Nhiều vé mỗi kỳ, số vé CỐ ĐỊNH: tách chỉ số từng vé với "ít nhất một vé đạt mức".

    Mốc ngẫu nhiên của "ít nhất một vé ≥ L" phụ thuộc độ trùng giữa các vé, nên được tính chính xác
    trên chính bộ vé (``any_ticket_tail``). Danh mục quá lớn để liệt kê (cận vượt ``exact_limit``)
    mới dùng ``simulations`` kết quả rút đều (số ngẫu nhiên chung cho mọi kỳ, kèm sai số Monte Carlo);
    khi ấy ước lượng bị kẹp vào cận chính xác ``union_bounds`` (Bonferroni bậc hai, tổng các vé) — mức
    hiếm không gặp trong mẫu hữu hạn không thành xác suất 0, cũng không thành cận của một vé.

    ``p_value_greater`` là p luôn hợp lệ (``predictable_p_value``): danh mục của mô hình học lại sau
    mỗi kỳ nên xác suất mốc phụ thuộc kết quả trước. ``p_value_fixed_portfolios`` (Poisson–nhị thức)
    chỉ đúng khi MỌI danh mục được chốt trước cả cửa sổ. ``portfolios`` và ``drawn`` theo thứ tự thời gian.
    """
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
    # Mọi kỳ dùng CÙNG các mô phỏng, nên ước lượng của các kỳ tương quan: sai số của tổng kỳ vọng
    # phải tính từ tổng theo TỪNG mô phỏng, không cộng phương sai như thể độc lập.
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
        else:
            if incidence is None:
                rng = np.random.default_rng(seed)
                sample = np.argsort(rng.random((simulations, n)), axis=1)[:, :k]
                incidence = np.zeros((simulations, n), dtype=bool)
                np.put_along_axis(incidence, sample, True, axis=1)
            monte_carlo_draws += 1
            index = np.asarray([[v - 1 for v in t] for t in tickets])
            simulated = incidence[:, index].sum(axis=2).max(axis=1)  # (S,) số khớp tốt nhất trong danh mục
            lower, upper = union_bounds(tickets, n, k)
            for level in LEVELS:
                reached = simulated >= level
                fair_any[level].append(float(np.clip(reached.mean(), lower[level], upper[level])))
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
            'p_value_greater': predictable_p_value(best_arr >= level, probabilities),
            'p_value_fixed_portfolios': poisson_binomial_sf(reached, probabilities),
        }
    return {'draws': len(portfolios), 'tickets_per_draw': size, 'simulations': simulations, 'seed': seed,
            'exact_draws': len(portfolios) - monte_carlo_draws, 'monte_carlo_draws': monte_carlo_draws,
            'per_ticket': summarize_hits(per_ticket, n, k, len(portfolios[0][0])),
            'per_ticket_note': 'Vé trong cùng kỳ chấm trên cùng một kết quả nên không độc lập; p theo từng vé chỉ mô tả.',
            'any_ticket_note': ('p_value_greater luôn hợp lệ kể cả khi danh mục học lại sau mỗi kỳ (e-process, Ville); '
                                'p_value_fixed_portfolios chỉ đúng khi mọi danh mục chốt trước cả cửa sổ.'),
            'any_ticket': any_level, 'mean_pairwise_overlap': float(np.mean(overlap)),
            'mean_coverage': float(np.mean(coverage))}
