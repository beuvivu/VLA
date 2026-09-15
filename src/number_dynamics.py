from __future__ import annotations

"""Leakage-safe higher-order numerical dynamics for the 00..99 universe.

The module estimates descriptive/forecast-support signals using only observations
available through the anchor draw:
- hierarchical Bayesian first-order cross-number transition matrices;
- second-order per-number Markov state posteriors;
- empirical-Bayes renewal/hazard probabilities by current gap;
- multi-lag conditional kernels (1, 2, 3, 7, 14, 28 calendar days);
- recent-vs-long regime drift with Jensen-Shannon diagnostics;
- same-draw co-occurrence phi matrices for structural inspection.

All day/lag semantics require a strictly increasing, daily-contiguous calendar.
The estimates are aggressively shrunk toward historical baselines. They are
probabilistic ranking evidence, not deterministic lottery rules.
"""

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

import numpy as np
import pandas as pd

from calendar_alignment import require_daily_contiguous
from hierarchical_pooling import (
    MAX_PRIOR_STRENGTH,
    fit_pooling,
    fit_shrinkage_to_prior,
    fit_shrinkage_to_prior_rows,
    pooled_posterior,
)
from ensemble_utils import normalize_distribution
from opinion_pool import SIGNIFICANCE_SIGMAS
from lottery import Lottery

Mode = Literal["loto", "de"]
LAGS = (1, 2, 3, 7, 14, 28)


@dataclass(frozen=True)
class DynamicsArtifacts:
    current: pd.DataFrame
    transition_prob: pd.DataFrame
    transition_lift: pd.DataFrame
    cooccurrence_phi: pd.DataFrame
    lag_dependency: pd.DataFrame
    diagnostics: dict


def _clip_prob(p: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), 1e-6, 1.0 - 1e-6)


def _js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    p = normalize_distribution(np.clip(np.asarray(p, dtype=float), 1e-12, None))
    q = normalize_distribution(np.clip(np.asarray(q, dtype=float), 1e-12, None))
    m = 0.5 * (p + q)
    return float(
        0.5 * np.sum(p * np.log(p / m))
        + 0.5 * np.sum(q * np.log(q / m))
    )


#: ``None`` nghĩa là HỌC độ co ngót của đường nền từ dữ liệu.
#:
#: Giá trị cũ là ``max(20, κ·0,5)`` — tức 22,5 cho LOTO — và nó được đặt tay.
#: Đo walk-forward 400 kỳ trên dữ liệu thật, thống kê t cặp đôi so với bản
#: đang dùng:
#:
#:     κ = 22,5 (đang dùng)   Brier 0,18143488       —
#:     κ = 90                 Brier 0,18142966   t = -5,16
#:     κ = 1000               Brier 0,18138711   t = -4,57
#:     HỌC κ                  Brier 0,18132998   t = -3,09
#:
#: Cả ba đều vượt xa ngưỡng 2 SE, và bản học được có hiệu ứng lớn gấp hai mươi
#: lần bản κ=90. Trung vị κ học được là 1 000 000 — tức dữ liệu đòi co ngót
#: mạnh hơn 22,5 khoảng bốn mươi nghìn lần.
#:
#: Khác với việc chọn phép hợp hay chọn chu kỳ bán rã, đây KHÔNG phải chọn
#: kiến trúc mà là ƯỚC LƯỢNG THAM SỐ, nên không cần cổng 2 SE ở lúc chạy:
#: chính ``fit_pooling`` đã là phương pháp thích ứng.
LEARN_BASELINE_PRIOR: float | None = None

#: ``None`` nghĩa là HỌC độ co ngót của năm ước lượng có điều kiện.
#:
#: Giá trị cũ đặt tay theo chế độ: chuyển trạng thái 45/160, Markov bậc hai
#: 35/100, hiểm suất 60/180, độ trễ 45/120, chế độ 35/100. Mười con số ấy
#: không có căn cứ đo lường nào — chúng chỉ là "đủ lớn để an toàn".
#:
#: Khác với đường nền, tâm co ngót ở đây KHÔNG phải một tỉ lệ chung mà là
#: đường nền riêng của từng con, nên phải dùng ``fit_shrinkage_to_prior``
#: chứ không phải ``fit_pooling``. Câu hỏi cũng khác: không phải "các con số
#: có khác nhau không" mà "điều kiện hoá có dịch chuyển được con số khỏi
#: đường nền của chính nó không".
#:
#: Đo walk-forward qua chính ``build_dynamics_signal``, thống kê t cặp đôi
#: (âm là tốt hơn):
#:
#:     LOTO,  n = 500    đặt tay 0,18149960   học 0,18145090   t = -2,90
#:     LOTO,  n = 1000   đặt tay 0,18139358   học 0,18134064   t = -4,05
#:     đề,     n = 500    đặt tay 0,00990056   học 0,00990003   t = -1,22
#:     đề,     n = 1000   đặt tay 0,00990057   học 0,00990005   t = -1,64
#:
#: Nói thẳng phần không đạt: ở chế độ ĐỀ, phép học KHÔNG vượt ngưỡng 2 SE.
#: Hiệu ứng ổn định về dấu và độ lớn (-5,2e-7 ở cả hai cỡ mẫu) nên nó khó
#: đảo chiều, nhưng với dữ liệu hiện có thì đó vẫn là hoà chứ không phải
#: thắng. Lý do vẫn dùng phép học cho cả hai chế độ: thay đổi này BỚT mười
#: hằng số đặt tay chứ không thêm tham số nào, nên quy tắc "thêm phức tạp
#: mà không tăng biên tách thì dừng" không áp vào đây; và ở chế độ LOTO nó
#: thắng dứt khoát.
#:
#: Điều đáng chú ý nhất không nằm ở Brier mà ở chỗ κ học được bằng bao nhiêu.
#: Trên dữ liệu ngẫu nhiên thuần, ba trong năm ước lượng có điều kiện co ngót
#: HOÀN TOÀN, còn hằng số đặt tay thì tin chúng rất nhiều (lệch tuyệt đối khỏi
#: đường nền, trung vị / lớn nhất):
#:
#:     chuyển trạng thái   học 0,00000 / 0,00000   đặt tay 0,00499 / 0,01990
#:     Markov bậc hai      học 0,00000 / 0,00002   đặt tay 0,01400 / 0,06184
#:     nhân độ trễ         học 0,00018 / 0,01344   đặt tay 0,00914 / 0,03315
#:
#: Đó chính là chỗ phần Brier thắng được sinh ra, và nó là một kết luận về
#: DỮ LIỆU chứ không phải về mã.
#:
#: Vì sao κ phải học theo TỪNG HÀNG chứ không phải một mối chung: phiên bản
#: đầu gộp cả 10 000 ô của ma trận chuyển trạng thái vào một κ, và một quan hệ
#: TẤT ĐỊNH 12 → 34 bị xoá sạch — hệ số nâng tụt về 1,0005. Phép kiểm tiêm tín
#: hiệu bắt được ngay. Tách theo hàng nguồn thì quan hệ ấy sống, mà Brier
#: không đổi (t = -2,90 ở cả hai bản, n = 500). Giữ được tín hiệu thật mà không
#: mất gì là lý do chọn bản theo hàng.
LEARN_COMPONENT_PRIOR: float | None = None


def _baseline(hit: np.ndarray, prior_strength: float | None) -> np.ndarray:
    """Đường nền theo từng con, co ngót về tỉ lệ chung.

    ``prior_strength = None`` thì độ co ngót được học bằng Bayes thực nghiệm;
    truyền một số để ép, phục vụ tái lập kết quả cũ.
    """
    n = max(len(hit), 1)
    global_rate = float(np.mean(hit)) if hit.size else 0.01
    global_rate = float(np.clip(global_rate, 1e-5, 1 - 1e-5))
    hits = hit.sum(axis=0, dtype=np.float64)
    if prior_strength is None:
        if hits.size < 3 or n < 2:
            return np.full(hits.shape, global_rate, dtype=float)
        fit = fit_pooling(hits, float(n))
        return pooled_posterior(hits, float(n), fit)
    return (hits + prior_strength * global_rate) / (n + prior_strength)


def transition_posterior(
    hit: np.ndarray, *, prior_strength: float | None,
    baseline_prior: float | None = LEARN_BASELINE_PRIOR,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """P(target[next observation]=1 | source[current]=1), with shrinkage.

    This low-level numerical primitive operates on adjacent observations. Public
    day-based orchestration must validate calendar continuity before calling it.
    """
    h = np.asarray(hit, dtype=np.int8)
    if h.ndim != 2 or h.shape[1] != 100:
        raise ValueError("hit must have shape (n_observations, 100)")
    base = _baseline(h, prior_strength=baseline_prior)
    if len(h) < 2:
        post = np.tile(base, (100, 1))
        return (
            post,
            np.ones_like(post),
            np.zeros(100),
            base,
            np.full(100, MAX_PRIOR_STRENGTH),
        )

    src = h[:-1].astype(np.float64)
    dst = h[1:].astype(np.float64)
    trials = src.sum(axis=0)
    pair = src.T @ dst
    if prior_strength is None:
        row_prior = fit_shrinkage_to_prior_rows(pair, trials, base)[:, None]
    else:
        row_prior = np.full((100, 1), float(prior_strength))
    post = (pair + row_prior * base[None, :]) / (trials[:, None] + row_prior)
    lift = post / np.maximum(base[None, :], 1e-9)
    return post, lift, trials, base, row_prior.reshape(-1)


def _markov2_current(
    hit: np.ndarray, *, prior_strength: float | None,
    baseline_prior: float | None = LEARN_BASELINE_PRIOR,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-number P(hit_next | two previous states) with hierarchical shrinkage."""
    h = np.asarray(hit, dtype=np.int8)
    base = _baseline(h, prior_strength=baseline_prior)
    if len(h) < 3:
        return (
            base.copy(),
            np.zeros(100, dtype=np.int8),
            np.zeros(100),
            np.full(4, MAX_PRIOR_STRENGTH),
        )

    success = np.zeros((4, 100), dtype=np.float64)
    trials = np.zeros((4, 100), dtype=np.float64)
    cols = np.arange(100)
    for t in range(1, len(h) - 1):
        state = 2 * h[t - 1] + h[t]
        outcome = h[t + 1]
        trials[state, cols] += 1.0
        success[state, cols] += outcome

    if prior_strength is None:
        state_prior = fit_shrinkage_to_prior_rows(success, trials, base)
    else:
        state_prior = np.full(4, float(prior_strength))

    state_now = (2 * h[-2] + h[-1]).astype(np.int8)
    s = success[state_now, cols]
    n = trials[state_now, cols]
    k = state_prior[state_now]
    prob = (s + k * base) / (n + k)
    reliability = n / (n + k)
    return prob, state_now, reliability, state_prior


def _gap_hazard_current(
    hit: np.ndarray, *, max_gap: int, prior_strength: float | None,
    baseline_prior: float | None = LEARN_BASELINE_PRIOR,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame, float]:
    """Empirical-Bayes hazard by daily gap, shared across numbers."""
    h = np.asarray(hit, dtype=np.int8)
    n_days, n_numbers = h.shape
    base = _baseline(h, prior_strength=baseline_prior)
    denom = np.zeros(max_gap + 1, dtype=np.float64)
    numer = np.zeros(max_gap + 1, dtype=np.float64)

    last_seen = np.full(n_numbers, -1, dtype=np.int32)
    for t in range(n_days):
        seen = last_seen >= 0
        gaps = np.where(seen, t - last_seen, max_gap)
        gaps = np.clip(gaps, 1, max_gap)
        np.add.at(denom, gaps, 1.0)
        hit_idx = np.where(h[t] > 0)[0]
        if hit_idx.size:
            np.add.at(numer, gaps[hit_idx], 1.0)
            last_seen[hit_idx] = t

    global_rate = float(np.clip(np.mean(h), 1e-6, 1 - 1e-6))
    if prior_strength is None:
        prior_strength = fit_shrinkage_to_prior(numer, denom, global_rate)
    hazard = (numer + prior_strength * global_rate) / (denom + prior_strength)

    current_gap = np.empty(n_numbers, dtype=np.int32)
    for j in range(n_numbers):
        idx = np.where(h[:, j] > 0)[0]
        current_gap[j] = (
            0
            if idx.size and idx[-1] == n_days - 1
            else (n_days - 1 - idx[-1] if idx.size else max_gap - 1)
        )
    next_gap = np.clip(current_gap + 1, 1, max_gap)
    raw = hazard[next_gap]

    evidence = denom[next_gap]
    reliability = evidence / (evidence + 4.0 * prior_strength)
    prob = base + reliability * (raw - global_rate)

    table = pd.DataFrame(
        {
            "gap": np.arange(max_gap + 1, dtype=int),
            "trials": denom,
            "hits": numer,
            "posterior_hazard": hazard,
        }
    )
    return _clip_prob(prob), next_gap, reliability, table, float(prior_strength)


def _lag_kernel_current(
    hit: np.ndarray, *, lags: tuple[int, ...], prior_strength: float | None,
    baseline_prior: float | None = LEARN_BASELINE_PRIOR,
) -> tuple[np.ndarray, pd.DataFrame, list[float]]:
    """Same-number multi-lag kernels on a calendar-validated daily series."""
    h = np.asarray(hit, dtype=np.int8)
    base = _baseline(h, prior_strength=baseline_prior)
    weighted = np.zeros(100, dtype=np.float64)
    weight_sum = np.zeros(100, dtype=np.float64)
    learned_priors: list[float] = []
    rows: list[dict[str, float | int]] = []

    for lag in lags:
        if len(h) <= lag:
            continue
        src = h[:-lag]
        dst = h[lag:]
        for state in (0, 1):
            mask = src == state
            trials = mask.sum(axis=0, dtype=np.float64)
            hits = (mask & (dst > 0)).sum(axis=0, dtype=np.float64)
            cell_prior = (
                fit_shrinkage_to_prior(hits, trials, base)
                if prior_strength is None
                else float(prior_strength)
            )
            learned_priors.append(cell_prior)
            post = (hits + cell_prior * base) / (trials + cell_prior)
            current_state = h[-lag]
            active = current_state == state
            rel = trials / (trials + cell_prior)
            lag_weight = (1.0 / np.sqrt(float(lag))) * rel
            weighted[active] += post[active] * lag_weight[active]
            weight_sum[active] += lag_weight[active]

            for j in range(100):
                rows.append(
                    {
                        "number": j,
                        "lag": lag,
                        "state": state,
                        "trials": float(trials[j]),
                        "hits": float(hits[j]),
                        "posterior_prob": float(post[j]),
                        "lift_vs_baseline": float(post[j] / max(base[j], 1e-9)),
                    }
                )

    prob = np.where(
        weight_sum > 0,
        weighted / np.maximum(weight_sum, 1e-12),
        base,
    )
    return _clip_prob(prob), pd.DataFrame(rows), learned_priors


def _regime_current(
    hit: np.ndarray, *, recent: int, long: int, prior_strength: float | None,
    baseline_prior: float | None = LEARN_BASELINE_PRIOR,
) -> tuple[np.ndarray, np.ndarray, float, float, float, float, float]:
    h = np.asarray(hit, dtype=np.int8)
    base = _baseline(h, prior_strength=baseline_prior)
    r = h[-min(recent, len(h)) :]
    l = h[-min(long, len(h)) :]
    r_hits = r.sum(axis=0, dtype=np.float64)
    l_hits = l.sum(axis=0, dtype=np.float64)
    if prior_strength is None:
        recent_prior = fit_shrinkage_to_prior(r_hits, float(len(r)), base)
        long_prior = fit_shrinkage_to_prior(l_hits, float(len(l)), base)
    else:
        recent_prior = long_prior = float(prior_strength)
    recent_prob = (r_hits + recent_prior * base) / (len(r) + recent_prior)
    long_prob = (l_hits + long_prior * base) / (len(l) + long_prior)
    recent_dist = normalize_distribution(np.clip(r_hits + 0.5, 1e-12, None))
    long_dist = normalize_distribution(np.clip(l_hits + 0.5, 1e-12, None))
    js = _js_divergence(recent_dist, long_dist)
    entropy_recent = float(-np.sum(recent_dist * np.log(recent_dist)))
    entropy_long = float(-np.sum(long_dist * np.log(long_dist)))
    stability = float(np.exp(-8.0 * js))
    regime_prob = base + stability * (recent_prob - base)
    regime_log_ratio = np.log(
        np.maximum(recent_prob, 1e-9) / np.maximum(long_prob, 1e-9)
    )
    return (
        _clip_prob(regime_prob),
        regime_log_ratio,
        js,
        entropy_recent,
        entropy_long,
        float(recent_prior),
        float(long_prior),
    )


def _cooccurrence_phi(hit: np.ndarray, shrink_strength: float = 60.0) -> np.ndarray:
    h = np.asarray(hit, dtype=np.float64)
    if len(h) < 2:
        return np.zeros((100, 100), dtype=np.float64)
    p = h.mean(axis=0)
    joint = (h.T @ h) / float(len(h))
    cov = joint - p[:, None] * p[None, :]
    var = np.maximum(p * (1.0 - p), 1e-12)
    denom = np.sqrt(var[:, None] * var[None, :])
    phi = cov / np.maximum(denom, 1e-12)
    phi *= len(h) / (len(h) + shrink_strength)
    np.fill_diagonal(phi, 1.0)
    return np.clip(phi, -1.0, 1.0)



#: Chọn phép hợp các hàng nguồn trên một lát giữ riêng cắt theo thời gian.
POOL_HOLDOUT: Final[float] = 0.25
MIN_POOL_SELECTION_DAYS: Final[int] = 400
POOL_KINDS: Final[tuple[str, ...]] = ("arithmetic", "logodds")


def _pool_active_rows(
    kind: str, trans: np.ndarray, base: np.ndarray, active: np.ndarray
) -> np.ndarray:
    """Hợp các hàng nguồn đang hoạt động thành một véc-tơ theo từng con.

    Hai phép hợp, và khác biệt giữa chúng là khác biệt VỀ CẤU TRÚC chứ không
    phải về tham số:

    * ``arithmetic`` — trung bình các hậu nghiệm. Kết quả luôn nằm giữa giá
      trị nhỏ nhất và lớn nhất của đầu vào, nên nó KHÔNG THỂ sắc hơn bất kỳ
      hàng nào. Với 24 hàng đang hoạt động mà chỉ một hàng mang tin, tin ấy bị
      pha loãng 24 lần.
    * ``logodds`` — cộng độ lệch log-odds quanh đường nền. Sắc được, và đó vừa
      là ưu điểm vừa là rủi ro: nó cũng khuếch đại 23 hàng chỉ mang nhiễu.

    Không có phép nào đúng sẵn, nên phép chọn là việc của ``select_transition_pool``.
    """
    if not active.size:
        return base.copy()
    if kind == "arithmetic":
        return trans[active].mean(axis=0)
    base_logit = np.log(
        np.clip(base, 1e-9, 1 - 1e-9) / (1.0 - np.clip(base, 1e-9, 1 - 1e-9))
    )
    rows = np.clip(trans[active], 1e-9, 1 - 1e-9)
    deviation = (np.log(rows / (1.0 - rows)) - base_logit[None, :]).sum(axis=0)
    return 1.0 / (1.0 + np.exp(-(base_logit + deviation)))


def select_transition_pool(
    hit: np.ndarray, *, holdout_fraction: float = POOL_HOLDOUT
) -> tuple[str, dict]:
    """Giữ phép trung bình số học trừ khi log-odds thắng được 2 SE.

    Cắt theo thời gian: ước lượng ma trận chuyển trạng thái trên phần đầu, chấm
    điểm cả hai phép hợp trên phần đuôi mà phép ước lượng chưa từng thấy.

    Đo trên dữ liệu thật có tiêm quan hệ 12 → 34, cùng một định nghĩa tiêm
    (P(34 về | 12 về hôm trước) = tần suất nền × (1 + X), nền = 0,2378):

        tiêm     chọn        t       p(34) của bên thắng    34 về thật
          0 %    số học    +5,84            0,2372             0,254
         25 %    số học    +5,80            0,2374             0,297
         50 %    số học    +5,37            0,2383             0,348
        100 %    số học    +4,11            0,2426             0,464
        200 %    log-odds  -4,81            0,6053             0,768

    Trên dữ liệu hôm nay nó giữ trung bình số học, và giữ với biên rất rộng.
    Nhưng nó KHÔNG phải hằng số đặt tay nữa: khi tín hiệu đủ mạnh để việc làm
    sắc bù được nhiễu nó khuếch đại, phép chọn tự đổi.
    """
    h = np.asarray(hit, dtype=np.int8)
    n = len(h)
    empty = {"kind": "arithmetic", "t_statistic": None, "holdout_days": 0}
    if n < MIN_POOL_SELECTION_DAYS:
        return "arithmetic", empty
    cut = int(n * (1.0 - holdout_fraction))
    if cut < 2 or n - cut < 2:
        return "arithmetic", empty
    trans, _, _, base, _ = transition_posterior(h[:cut], prior_strength=None)

    errors = {kind: [] for kind in POOL_KINDS}
    for t in range(cut, n):
        active = np.where(h[t - 1] > 0)[0]
        y = h[t].astype(np.float64)
        for kind in POOL_KINDS:
            p = _clip_prob(_pool_active_rows(kind, trans, base, active))
            errors[kind].append(float(np.mean((p - y) ** 2)))

    incumbent = np.asarray(errors["arithmetic"])
    challenger = np.asarray(errors["logodds"])
    delta = challenger - incumbent
    standard_error = float(np.std(delta, ddof=1) / np.sqrt(delta.size))
    t_statistic = float(delta.mean() / standard_error) if standard_error else 0.0
    diagnostics = {
        "kind": "arithmetic",
        "t_statistic": t_statistic,
        "holdout_days": int(delta.size),
        "brier_arithmetic": float(incumbent.mean()),
        "brier_logodds": float(challenger.mean()),
    }
    if delta.mean() < -SIGNIFICANCE_SIGMAS * standard_error:
        diagnostics["kind"] = "logodds"
        return "logodds", diagnostics
    return "arithmetic", diagnostics


def build_dynamics_signal(
    hit: np.ndarray,
    *,
    dates: Sequence[object] | pd.Series | pd.Index,
    mode: Mode,
    transition_prior: float | None = LEARN_COMPONENT_PRIOR,
    markov_prior: float | None = LEARN_COMPONENT_PRIOR,
    hazard_prior: float | None = LEARN_COMPONENT_PRIOR,
    lag_prior: float | None = LEARN_COMPONENT_PRIOR,
    regime_prior: float | None = LEARN_COMPONENT_PRIOR,
) -> DynamicsArtifacts:
    """Build dynamics only when row offsets are provably calendar-day offsets.

    Năm ``*_prior`` để ``None`` thì độ co ngót được học; truyền số để ép, phục
    vụ đo đối chứng với các hằng số đặt tay cũ qua CHÍNH hàm này chứ không
    phải một bản dựng lại có thể lệch đi.
    """
    learned_flags = {
        "transition": transition_prior is None,
        "markov2": markov_prior is None,
        "hazard": hazard_prior is None,
        "lag": lag_prior is None,
        "regime": regime_prior is None,
    }
    h = np.asarray(hit, dtype=np.int8)
    if h.ndim != 2 or h.shape[1] != 100 or len(h) == 0:
        raise ValueError("hit must be a non-empty (n_days, 100) matrix")

    calendar = require_daily_contiguous(
        dates, context=f"{mode} number dynamics"
    )
    if len(calendar) != len(h):
        raise ValueError(
            f"date/hit length mismatch: dates={len(calendar)} hit_rows={len(h)}"
        )

    max_gap = 60 if mode == "loto" else 200

    trans, lift, trials, base, transition_priors = transition_posterior(
        h, prior_strength=transition_prior
    )
    active = np.where(h[-1] > 0)[0]
    # KHÔNG co ngót thêm một lần nữa ở đây. ``trans`` đã là hậu nghiệm co ngót
    # theo κ RIÊNG của từng hàng nguồn; nhân thêm một cổng dựng từ κ trung vị
    # là co ngót hai lần bằng một đại lượng không có nghĩa thống kê nào — và
    # nó đã đo được là xoá sạch tín hiệu: với quan hệ tiêm 12 → 34 mà bộ ước
    # lượng tìm ra đúng (0,8729 so với nền 0,3539), cổng ấy đóng lại ở mức
    # 0,0006 và trả xác suất về ĐÚNG BẰNG đường nền.
    pool_kind, pool_diagnostics = select_transition_pool(h)
    trans_current = _pool_active_rows(pool_kind, trans, base, active)

    markov2, markov_state, markov_rel, markov_priors = _markov2_current(
        h, prior_strength=markov_prior
    )
    hazard, next_gap, hazard_rel, hazard_table, hazard_prior = _gap_hazard_current(
        h, max_gap=max_gap, prior_strength=hazard_prior
    )
    lag_prob, lag_table, lag_priors = _lag_kernel_current(
        h, lags=LAGS, prior_strength=lag_prior
    )
    (
        regime,
        regime_log_ratio,
        js,
        ent_recent,
        ent_long,
        regime_recent_prior,
        regime_long_prior,
    ) = _regime_current(h, recent=30, long=180, prior_strength=regime_prior)

    components = [base, markov2, hazard, trans_current, lag_prob, regime]
    if mode == "de":
        components = [
            normalize_distribution(np.clip(x, 1e-12, None)) for x in components
        ]
    base_c, markov2_c, hazard_c, trans_c, lag_c, regime_c = components

    raw = (
        0.20 * base_c
        + 0.20 * markov2_c
        + 0.17 * hazard_c
        + 0.20 * trans_c
        + 0.13 * lag_c
        + 0.10 * regime_c
    )

    evidence_rel = min(1.0, len(h) / 365.0)
    stability = float(np.exp(-6.0 * js))
    global_rel = float(
        np.clip(0.15 + 0.65 * evidence_rel * stability, 0.15, 0.80)
    )
    signal = base_c + global_rel * (raw - base_c)
    if mode == "de":
        signal = normalize_distribution(np.clip(signal, 1e-12, None))
    else:
        signal = _clip_prob(signal)

    current = pd.DataFrame(
        {
            "number": np.arange(100, dtype=int),
            "number_str": [f"{x:02d}" for x in range(100)],
            "prob": signal,
            "baseline_prob": base_c,
            "markov2_prob": markov2_c,
            "markov2_state": markov_state,
            "markov2_reliability": markov_rel,
            "hazard_prob": hazard_c,
            "next_gap": next_gap,
            "hazard_reliability": hazard_rel,
            "transition_prob": trans_c,
            "lag_kernel_prob": lag_c,
            "regime_prob": regime_c,
            "regime_log_ratio": regime_log_ratio,
            "dynamics_reliability": global_rel,
        }
    ).sort_values("prob", ascending=False, ignore_index=True)

    columns = [f"{x:02d}" for x in range(100)]
    trans_df = pd.DataFrame(trans, columns=columns)
    trans_df.insert(0, "source", columns)
    lift_df = pd.DataFrame(lift, columns=columns)
    lift_df.insert(0, "source", columns)
    phi_df = pd.DataFrame(_cooccurrence_phi(h), columns=columns)
    phi_df.insert(0, "source", columns)

    diagnostics = {
        "schema_version": 2,
        "mode": mode,
        "history_days": int(len(h)),
        "calendar_contiguous": True,
        "calendar_start": calendar[0].date().isoformat(),
        "calendar_end": calendar[-1].date().isoformat(),
        "active_numbers_last_draw": int(active.size),
        "transition_prior_strength": float(np.median(transition_priors)),
        "component_prior_strengths": {
            "transition_median": float(np.median(transition_priors)),
            "markov2_by_state": [float(x) for x in markov_priors],
            "hazard": float(hazard_prior),
            "lag_median": float(np.median(lag_priors)) if lag_priors else None,
            "regime_recent": float(regime_recent_prior),
            "regime_long": float(regime_long_prior),
        },
        "component_priors_learned": learned_flags,
        "transition_pool": pool_diagnostics,
        "transition_active_mean_trials": float(
            np.mean(trials[active]) if active.size else 0.0
        ),
        "regime_js_divergence_30_vs_180": js,
        "entropy_recent": ent_recent,
        "entropy_long": ent_long,
        "global_dynamics_reliability": global_rel,
        "hazard_nonzero_bins": int((hazard_table["trials"] > 0).sum()),
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "interpretation": (
            "Higher-order Bayesian dynamics are shrinkage-regularized statistical "
            "evidence computed only on a verified daily-contiguous calendar. They "
            "do not imply deterministic numerical laws."
        ),
    }

    return DynamicsArtifacts(
        current=current,
        transition_prob=trans_df,
        transition_lift=lift_df,
        cooccurrence_phi=phi_df,
        lag_dependency=lag_table,
        diagnostics=diagnostics,
    )


def build_hit_matrix_from_lottery(mode: Mode) -> tuple[pd.DatetimeIndex, np.ndarray]:
    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data().copy()
    sparse = lot.get_sparse_data().copy()
    if two.empty or sparse.empty:
        raise RuntimeError("No lottery data loaded")
    two["date"] = pd.to_datetime(two["date"])
    sparse["date"] = pd.to_datetime(sparse["date"])
    if mode == "loto":
        hit = (sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0).astype(
            np.int8
        )
        return pd.DatetimeIndex(sparse["date"]), hit

    de = (two["special"].astype(int).to_numpy() % 100).astype(int)
    onehot = np.zeros((len(de), 100), dtype=np.int8)
    onehot[np.arange(len(de)), de] = 1
    return pd.DatetimeIndex(two["date"]), onehot


def export_dynamics(mode: Mode, out_dir: Path) -> DynamicsArtifacts:
    dates, hit = build_hit_matrix_from_lottery(mode)
    artifacts = build_dynamics_signal(hit, dates=dates, mode=mode)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts.current.to_csv(out_dir / f"current_dynamics_{mode}.csv", index=False)
    artifacts.transition_prob.to_csv(
        out_dir / f"transition_prob_lag1_{mode}.csv", index=False
    )
    artifacts.transition_lift.to_csv(
        out_dir / f"transition_lift_lag1_{mode}.csv", index=False
    )
    artifacts.cooccurrence_phi.to_csv(
        out_dir / f"cooccurrence_phi_{mode}.csv", index=False
    )
    artifacts.lag_dependency.to_csv(
        out_dir / f"lag_dependency_{mode}.csv", index=False
    )
    diag = dict(artifacts.diagnostics)
    diag["anchor_date"] = str(dates.max().date())
    (out_dir / f"diagnostics_{mode}.json").write_text(
        json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return artifacts


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build higher-order Bayesian number-dynamics matrices."
    )
    ap.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    ap.add_argument("--out-dir", default="data/number_dynamics")
    args = ap.parse_args()
    modes = ["loto", "de"] if args.mode == "both" else [args.mode]
    for mode in modes:
        artifacts = export_dynamics(mode, Path(args.out_dir))
        print(
            f"[OK] number dynamics {mode}: "
            f"reliability={artifacts.diagnostics['global_dynamics_reliability']:.3f}"
        )


if __name__ == "__main__":
    main()
