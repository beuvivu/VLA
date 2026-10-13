"""Challenger cho Mega 6/45 và Power 6/55: luật k-trong-n học từ đặc trưng NHÂN QUẢ.

Mọi challenger ở đây cho ra log-trọng số η (T, n) của luật conditional Bernoulli

    P(S) = Π_{i∈S} wᵢ / e_k(w),  wᵢ = exp ηᵢ,

nên mọi ràng buộc của trò chơi đúng theo cấu trúc: xác suất biên các số chính thuộc [0, 1] và
cộng lại bằng k (không bằng 1), phân phối trên mọi bộ k số chuẩn hoá đúng, và số đặc biệt Power —
rút từ n − k số còn lại của cùng lồng cầu — có P(b | S) = w_b / Σ_{i∉S} wᵢ, chấm RIÊNG.
η = 0 chính là luật công bằng; hiệu chuẩn nhiệt độ (η ← τ·η, τ ≥ 0) giữ nguyên mọi ràng buộc ấy.

Hai challenger:

* ``shrink`` — tần suất có trọng số mũ, co Beta về k/n, rồi nhân nhiệt độ τ (τ < 0 là "số lạnh").
* ``causal`` — conditional logit trên bốn nhóm đặc trưng (tần suất, gap/lag, lịch, đồng xuất hiện
  trễ), phạt L2, học lại định kỳ trên cửa sổ mở rộng. Đặc trưng của kỳ t chỉ đọc các kỳ trước t
  và thứ trong tuần của kỳ t (biết trước theo lịch quay).
"""

from __future__ import annotations

from math import lgamma, log

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from vietlott_engine.forecast.engine import inclusion_probabilities
from vietlott_engine.game_theory.popularity import elementary_symmetric

GROUPS: dict[str, tuple[str, ...]] = {
    'frequency': ('freq_all', 'freq_ewma10', 'freq_ewma100'),
    'gap_lag': ('gap_z', 'lag1', 'lag2'),
    'calendar': ('weekday_freq',),
    'cooccurrence': ('lag_link',),
}
FEATURES: tuple[str, ...] = tuple(name for names in GROUPS.values() for name in names)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p) - np.log1p(-p)


def _check_draws(x: np.ndarray, k: int | None = None) -> tuple[np.ndarray, int]:
    x = np.asarray(x)
    if x.ndim != 2 or x.shape[0] == 0 or x.dtype != bool:
        raise ValueError('Cần ma trận kỳ × số kiểu bool')
    sums = x.sum(axis=1)
    k = int(sums[0]) if k is None else k
    if not (sums == k).all() or not 0 < k < x.shape[1]:
        raise ValueError('Mỗi kỳ phải có đúng k số chính')
    return x, k


# ============================================================================ đặc trưng nhân quả
def causal_features(x: np.ndarray, weekdays: np.ndarray) -> np.ndarray:
    """(T + 1, n, F) đặc trưng theo thứ tự ``FEATURES``; hàng t chỉ đọc kỳ 0..t − 1.

    Args:
        x: (T, n) kỳ đã quay, đúng k số mỗi kỳ.
        weekdays: (T + 1,) thứ trong tuần 0..6 của từng kỳ, phần tử cuối là kỳ KẾ TIẾP.

    Returns:
        Hàng cuối là đặc trưng cho kỳ kế tiếp chưa quay.
    """
    x, k = _check_draws(x)
    weekdays = np.asarray(weekdays)
    t_len, n = x.shape
    if weekdays.shape != (t_len + 1,) or ((weekdays < 0) | (weekdays > 6)).any():
        raise ValueError('Cần thứ trong tuần cho mọi kỳ và kỳ kế tiếp')
    p0 = k / n
    base = _logit(np.array(p0))
    lam = {10: 0.5 ** (1 / 10), 100: 0.5 ** (1 / 100)}
    count = np.zeros(n)
    ew = {h: np.zeros(n) for h in lam}
    mass = {h: 0.0 for h in lam}
    last = np.full(n, -1)
    prev = np.zeros(n)
    prev2 = np.zeros(n)
    wd_count = np.zeros((7, n))
    wd_seen = np.zeros(7)
    lag_pairs = np.zeros((n, n))   # lag_pairs[j, i]: j về ở kỳ s − 1 và i về ở kỳ s
    lag_base = np.zeros(n)        # số lần j về ở một kỳ có kỳ kế tiếp
    out = np.empty((t_len + 1, n, len(FEATURES)))
    gap_mu, gap_sd = 1 / p0, np.sqrt(1 - p0) / p0
    for t in range(t_len + 1):
        seen = t
        overall = (count + 50 * p0) / (seen + 50)
        logit_all = _logit(overall)
        d = int(weekdays[t])
        weekday = (wd_count[d] + 20 * overall) / (wd_seen[d] + 20)
        gap = np.where(last >= 0, t - last, t + 1)
        support = np.flatnonzero(prev > 0)
        if len(support):
            rates = (lag_pairs[support] + 20 * p0) / (lag_base[support][:, None] + 20)
            lift = _logit(rates) - base                       # (m, n): j kỳ trước → i kỳ này
            total = lift.sum(axis=0)
            total[support] -= lift[np.arange(len(support)), support]   # bỏ "j = i": đó là lag1
            partners = np.full(n, len(support))
            partners[support] -= 1
            link = np.where(partners > 0, total / np.maximum(partners, 1), 0.)
        else:
            link = np.zeros(n)
        out[t] = np.column_stack([
            logit_all - base,
            _logit((ew[10] + 20 * p0) / (mass[10] + 20)) - base,
            _logit((ew[100] + 20 * p0) / (mass[100] + 20)) - base,
            np.clip((gap - gap_mu) / gap_sd, -3, 5), prev, prev2,
            _logit(weekday) - logit_all,
            link,
        ])
        if t == t_len:
            break
        row = x[t].astype(float)
        lag_pairs += np.outer(prev, row)
        lag_base += prev
        count += row
        for h, decay in lam.items():
            ew[h] = decay * ew[h] + row
            mass[h] = decay * mass[h] + 1
        last[x[t]] = t
        prev2, prev = prev, row
        wd_count[int(weekdays[t])] += row
        wd_seen[int(weekdays[t])] += 1
    return out


# ============================================================================ luật conditional Bernoulli
def cb_log_likelihood(eta: np.ndarray, x: np.ndarray, bonus: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """log P(bộ số chính) và log P(số đặc biệt | bộ chính) mỗi kỳ dưới log-trọng số ``eta``.

    Returns:
        (main, bonus) — vectơ (T,); bonus bằng 0 khi không có số đặc biệt.
    """
    x, k = _check_draws(x)
    eta = np.asarray(eta, dtype=float)
    if eta.shape != x.shape or not np.isfinite(eta).all():
        raise ValueError('Log-trọng số phải hữu hạn và cùng hình với kỳ quay')
    shift = eta.max(axis=1, keepdims=True)
    w = np.exp(eta - shift)
    log_ek = np.log(elementary_symmetric(w, k)[:, k]) + k * shift[:, 0]
    main = (eta * x).sum(axis=1) - log_ek
    extra = np.zeros(len(x))
    if bonus is not None:
        b = np.asarray(bonus, dtype=np.int64) - 1
        rows = np.arange(len(x))
        if b.shape != (len(x),) or (b < 0).any() or (b >= x.shape[1]).any() or x[rows, b].any():
            raise ValueError('Số đặc biệt phải nằm ngoài bộ số chính')
        extra = eta[rows, b] - (np.log((w * ~x).sum(axis=1)) + shift[:, 0])
    return main, extra


def fair_log_likelihood(n: int, k: int, bonus: bool) -> tuple[float, float]:
    """Log-xác suất của MỘT kỳ dưới máy quay công bằng: (bộ chính, số đặc biệt)."""
    return -(lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)), (-log(n - k) if bonus else 0.)


def cb_marginals(eta: np.ndarray, k: int) -> np.ndarray:
    """Xác suất biên πᵢ của từng số chính; mỗi hàng cộng lại đúng bằng k."""
    eta = np.asarray(eta, dtype=float)
    w = np.exp(eta - eta.max(axis=-1, keepdims=True))
    return inclusion_probabilities(np.atleast_2d(w), k).reshape(eta.shape)


def fit_conditional_logit(phi: np.ndarray, x: np.ndarray, l2: float, beta0: np.ndarray | None = None) -> np.ndarray:
    """β cực đại log-likelihood conditional Bernoulli có phạt L2 (đặc trưng đã chuẩn hoá).

    Gradient đúng của −(1/T)Σₜ[Σ_{i∈Sₜ} φₜᵢ·β − log e_k(e^{φₜβ})] là −(1/T)Σₜ[Σ_{i∈Sₜ}φₜᵢ − Σᵢ πₜᵢ φₜᵢ].
    """
    x, k = _check_draws(x)
    phi = np.asarray(phi, dtype=float)
    if phi.ndim != 3 or phi.shape[:2] != x.shape or not np.isfinite(phi).all() or l2 < 0:
        raise ValueError('Đặc trưng/phạt không hợp lệ')
    t_len = len(x)
    observed = np.einsum('tnf,tn->f', phi, x.astype(float)) / t_len

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        eta = phi @ beta
        main, _ = cb_log_likelihood(eta, x)
        pi = cb_marginals(eta, k)
        grad = -(observed - np.einsum('tnf,tn->f', phi, pi) / t_len) + l2 * beta
        return float(-main.mean() + 0.5 * l2 * beta @ beta), grad

    start = np.zeros(phi.shape[2]) if beta0 is None else np.asarray(beta0, dtype=float)
    result = minimize(objective, start, jac=True, method='L-BFGS-B', options={'maxiter': 200})
    if not np.isfinite(result.x).all():
        raise FloatingPointError('Hệ số conditional logit không hữu hạn')
    return result.x


def standardize(phi: np.ndarray, rows: slice) -> tuple[np.ndarray, np.ndarray]:
    """Độ lệch chuẩn từng đặc trưng tính CHỈ trên các hàng huấn luyện ``rows`` (gộp mọi số)."""
    scale = phi[rows].reshape(-1, phi.shape[2]).std(axis=0)
    return np.where(scale > 1e-12, scale, 1.0), np.asarray(scale > 1e-12)


def causal_walk_forward(phi: np.ndarray, x: np.ndarray, columns: list[int], l2: float,
                        start: int, end: int, refit_every: int, fit_from: int = 0) -> np.ndarray:
    """η cho các kỳ start..end − 1; hệ số học lại mỗi ``refit_every`` kỳ trên mọi kỳ TRƯỚC điểm học lại.

    Đặc trưng hàng t đã nhân quả; học lại ở kỳ r chỉ dùng kỳ fit_from..r − 1, nên nhãn của một kỳ
    chỉ ảnh hưởng các kỳ sau nó.
    """
    if not 0 <= fit_from < start < end <= len(x) or refit_every < 1 or not columns:
        raise ValueError('Ranh giới walk-forward không hợp lệ')
    eta = np.zeros((end - start, x.shape[1]))
    beta = None
    sub = phi[:, :, columns]
    for t in range(start, end):
        if (t - start) % refit_every == 0:
            scale, _ = standardize(sub, slice(fit_from, t))
            scaled = sub / scale
            beta = fit_conditional_logit(scaled[fit_from:t], x[fit_from:t], l2, beta)
        eta[t - start] = scaled[t] @ beta
    return eta


# ============================================================================ challenger co về công bằng
def shrink_scores(x: np.ndarray, half_life: float | None, prior: float) -> np.ndarray:
    """(T + 1, n): logit tần suất (mũ hoá theo nửa đời, None = toàn lịch sử) co Beta về k/n, trước kỳ t."""
    x, k = _check_draws(x)
    p0 = k / x.shape[1]
    xf = x.astype(float)
    if half_life is None:
        s = np.vstack([np.zeros(x.shape[1]), np.cumsum(xf, axis=0)])
        m = np.arange(len(x) + 1, dtype=float)
    else:
        decay = 0.5 ** (1 / half_life)
        s = np.zeros((len(x) + 1, x.shape[1]))
        m = np.zeros(len(x) + 1)
        for t in range(len(x)):
            s[t + 1] = decay * s[t] + xf[t]
            m[t + 1] = decay * m[t] + 1
    score = _logit((s + prior * p0) / (m[:, None] + prior))
    return score - score.mean(axis=1, keepdims=True)


def fit_temperature(eta: np.ndarray, x: np.ndarray, bonus: np.ndarray | None = None,
                    bounds: tuple[float, float] = (0.0, 2.0)) -> float:
    """τ cực đại log-likelihood của luật η·τ trên các kỳ ĐÃ CHO (hiệu chuẩn, giữ ràng buộc trò chơi)."""
    def loss(tau: float) -> float:
        main, extra = cb_log_likelihood(tau * eta, x, bonus)
        return float(-(main + extra).mean())
    result = minimize_scalar(loss, bounds=bounds, method='bounded', options={'xatol': 1e-4})
    return float(result.x)
