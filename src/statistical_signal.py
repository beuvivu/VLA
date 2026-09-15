from __future__ import annotations

"""Conservative empirical-Bayes statistical signal for the 00..99 universe.

This component combines:
- recency-weighted Bayesian frequency;
- target-weekday posterior;
- 30/90/365-calendar-day shrinkage;
- stability/credible intervals;
- higher-order number dynamics (Markov-2, renewal hazard, lag kernels,
  cross-number lag-1 transition matrices, and regime drift).

Every day/lag/window interpretation is evaluated only on a verified daily-
contiguous canonical calendar. All dynamic evidence is strongly shrunk toward
historical baselines. The output is a calibrated ranking component for the wider
ML/path ensemble, not a claim of deterministic numerical predictability.
"""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist

from calendar_alignment import require_daily_contiguous
from ensemble_utils import normalize_distribution
from hierarchical_pooling import PoolingFit, fit_pooling
from opinion_pool import (
    SIGNIFICANCE_SIGMAS,
    PoolAudit,
    PoolParams,
    apply_pool,
    fit_pool,
)
from lottery import Lottery
from number_dynamics import build_dynamics_signal, export_dynamics


def _exp_weights(n: int, half_life: float) -> np.ndarray:
    age = np.arange(n - 1, -1, -1, dtype=float)
    return np.power(0.5, age / max(float(half_life), 1.0))


def _effective_n(weights: np.ndarray) -> float:
    s = float(weights.sum())
    q = float(np.square(weights).sum())
    return 0.0 if q <= 0 else s * s / q


def _logit(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def _js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    p = normalize_distribution(np.clip(p.astype(float), 1e-12, None))
    q = normalize_distribution(np.clip(q.astype(float), 1e-12, None))
    m = 0.5 * (p + q)
    return float(
        0.5 * np.sum(p * np.log(p / m))
        + 0.5 * np.sum(q * np.log(q / m))
    )


def _eb_posterior(
    counts: np.ndarray, trials: float, prior_strength: float | None
) -> np.ndarray:
    """Hậu nghiệm Beta-Binomial, HỌC độ co ngót riêng cho từng phép đo.

    Mỗi hậu nghiệm trả lời một câu hỏi gộp KHÁC NHAU, nên phải có κ riêng:

    * ``ewm`` hỏi "các con có khác nhau về tần suất chung không?"
    * ``weekday`` hỏi "các con có khác nhau về tần suất RIÊNG thứ ấy không?"
    * mỗi cửa sổ hỏi câu tương tự trên đúng cửa sổ của nó.

    Dùng chung một κ học từ tần suất chung là sai, và cái sai ấy có hướng rõ
    ràng: tần suất chung đồng nhất kéo κ lên rất lớn, rồi κ ấy nghiền nát một
    nhịp theo thứ có thật. Phép kiểm nhịp thứ Hai bắt được đúng điều này.
    """
    if trials <= 0.0:
        return np.full(counts.shape, 1.0 / max(counts.size, 1), dtype=float)
    if prior_strength is None:
        fit = fit_pooling(counts, float(trials))
        kappa, mean = fit.prior_strength, fit.pooled_rate
    else:
        kappa = float(prior_strength)
        mean = float(counts.sum() / (trials * counts.size))
    a0 = max(1e-6, mean * kappa)
    b0 = max(1e-6, (1.0 - mean) * kappa)
    return (a0 + counts) / (a0 + b0 + trials)


#: Trọng số của ba thành phần tầng 2, giữ nguyên từ bản cũ.
#:
#: Tệp này đổi CÁCH HỢP, không đổi HỢP CÁI GÌ. Tách hai câu hỏi ra là cố ý:
#: gộp chúng vào một phép tối ưu sẽ cho một mặt mục tiêu mà không ai đọc được
#: kết quả, và khi nó tệ đi thì không biết tại phần nào.
SIGNAL_COMPONENT_WEIGHTS: tuple[float, float, float] = (0.55, 0.25, 0.20)
#: Số kỳ cuối dùng để chọn phép hợp. Đủ dài để phép so cặp đôi có ý nghĩa,
#: đủ ngắn để không kéo dài thời gian dựng tín hiệu hằng ngày.
POOL_SELECTION_DAYS = 300


def select_signal_pool(
    hit: np.ndarray,
    dates: pd.Series,
    *,
    mode: str,
    half_life: int,
    eval_days: int = POOL_SELECTION_DAYS,
) -> tuple[PoolParams | None, PoolAudit | None]:
    """Chọn phép hợp ba thành phần tầng 2 bằng Brier trên lát giữ riêng.

    Trả về ``(None, None)`` khi lịch sử quá ngắn — khi ấy giữ trộn số học, đúng
    hành vi cũ, và nói rõ là không chọn.

    Vì sao đáng làm, bằng số đo: trộn số học luôn nằm trong ``[min, max]`` của
    đầu vào nên không bao giờ sắc hơn thành phần sắc nhất. Đo với tín hiệu tiêm
    +25 %: trộn số học thu hồi 6,8 %, log-odds ở độ sắc 2 thu hồi 13,4 %, ở độ
    sắc 3 thu hồi 20,3 %. Kiến trúc cũ vứt bỏ 93 % của một tín hiệu có thật.
    """
    days = int(hit.shape[0])
    start = max(200, days - eval_days)
    if days - start < 60:
        return None, None

    cube, labels = [], []
    for t in range(start, days):
        past = hit[:t]
        w = _exp_weights(t, half_life)
        ewm = _eb_posterior((past * w[:, None]).sum(axis=0), float(w.sum()), None)

        target_weekday = int(pd.Timestamp(dates.iloc[t]).weekday())
        mask = np.array(
            [pd.Timestamp(d).weekday() == target_weekday for d in dates.iloc[:t]]
        )
        weekday_rows = past[mask]
        weekday = _eb_posterior(
            weekday_rows.sum(axis=0) if len(weekday_rows) else np.zeros(100),
            float(len(weekday_rows)),
            None,
        )
        window = past[-min(90, t):]
        p90 = _eb_posterior(window.sum(axis=0), float(len(window)), None)

        cube.append(np.vstack([ewm, weekday, p90]))
        labels.append(hit[t])

    return fit_pool(
        mode,  # type: ignore[arg-type]
        np.stack(cube),
        np.stack(labels),
        np.asarray(SIGNAL_COMPONENT_WEIGHTS),
    )


def _loto_signal(
    hit: np.ndarray,
    dates: pd.Series,
    target_weekday: int,
    *,
    half_life: int,
    prior_strength: float | None,
    pool: PoolParams | None = None,
) -> pd.DataFrame:
    n = hit.shape[0]
    baseline = float(hit.mean())

    w = _exp_weights(n, half_life)
    weighted_hits = (hit * w[:, None]).sum(axis=0)
    weighted_trials = float(w.sum())
    ewm = _eb_posterior(weighted_hits, weighted_trials, prior_strength)

    weekday_mask = dates.dt.weekday.to_numpy() == int(target_weekday)
    weekday_hit = hit[weekday_mask]
    wk_hits = weekday_hit.sum(axis=0) if len(weekday_hit) else np.zeros(100)
    wk_n = int(len(weekday_hit))
    weekday = _eb_posterior(wk_hits, float(wk_n), prior_strength)

    window_probs: dict[int, np.ndarray] = {}
    for window in (30, 90, 365):
        h = hit[-min(window, n) :]
        window_probs[window] = _eb_posterior(
            h.sum(axis=0), float(len(h)), prior_strength
        )

    stack = np.vstack([_logit(window_probs[w]) for w in (30, 90, 365)])
    instability = np.std(stack, axis=0)
    stability = np.exp(-0.55 * instability)

    components = np.vstack([ewm, weekday, window_probs[90]])
    if pool is None:
        # Hành vi cũ: trộn số học với trọng số đặt tay.
        raw = np.tensordot(np.asarray(SIGNAL_COMPONENT_WEIGHTS), components, axes=(0, 0))
    else:
        raw = apply_pool("loto", components, pool)
    prob = baseline + stability * (raw - baseline)
    prob = np.clip(prob, 1e-5, 1 - 1e-5)

    ess = _effective_n(w)
    weighted_rate = weighted_hits / max(weighted_trials, 1e-12)
    # Khoảng khả tín phải dùng ĐÚNG tiên nghiệm của phép đo `ewm`, không phải
    # một tiên nghiệm khác — nếu không, khoảng và ước lượng điểm nói hai
    # chuyện khác nhau về cùng một con số.
    ewm_kappa = (
        fit_pooling(weighted_hits, weighted_trials).prior_strength
        if prior_strength is None
        else float(prior_strength)
    )
    a0 = max(1e-6, baseline * ewm_kappa)
    b0 = max(1e-6, (1 - baseline) * ewm_kappa)
    alpha = a0 + weighted_rate * ess
    beta = b0 + (1 - weighted_rate) * ess
    ci_low = beta_dist.ppf(0.025, alpha, beta)
    ci_high = beta_dist.ppf(0.975, alpha, beta)

    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=int),
            "prob": prob,
            "baseline_prob": baseline,
            "ewm_prob": ewm,
            "weekday_prob": weekday,
            "p30": window_probs[30],
            "p90": window_probs[90],
            "p365": window_probs[365],
            "stability": stability,
            "credible_low": ci_low,
            "credible_high": ci_high,
            "effective_sample_size": ess,
            "weekday_trials": wk_n,
        }
    )


def _de_posterior(
    onehot: np.ndarray, weights: np.ndarray, prior_strength: float | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hậu nghiệm Dirichlet-Multinomial cho đề, độ tập trung HỌC được nếu None.

    Đề là bài toán một-trong-một-trăm nên tiên nghiệm là Dirichlet đối xứng với
    tổng độ tập trung ``κ``. Câu hỏi gộp vẫn y hệt chế độ LOTO — "các con có
    khác nhau thật hay chỉ dao động?" — nên dùng cùng bộ ước lượng, chỉ khác ở
    chỗ chia đều κ cho 100 loại.
    """
    counts = (onehot * weights[:, None]).sum(axis=0)
    total_weight = float(weights.sum())
    if prior_strength is None:
        kappa = (
            fit_pooling(counts, total_weight).prior_strength
            if total_weight > 0.0 and counts.size >= 3
            else 100.0
        )
    else:
        kappa = float(prior_strength)
    prior = np.full(100, kappa / 100.0, dtype=float)
    alpha = prior + counts
    total = float(alpha.sum())
    p = alpha / total
    low = beta_dist.ppf(0.025, alpha, np.maximum(total - alpha, 1e-9))
    high = beta_dist.ppf(0.975, alpha, np.maximum(total - alpha, 1e-9))
    return p, low, high


def _de_signal(
    onehot: np.ndarray,
    dates: pd.Series,
    target_weekday: int,
    *,
    half_life: int,
    prior_strength: float | None,
) -> pd.DataFrame:
    n = onehot.shape[0]
    uniform = np.full(100, 0.01, dtype=float)
    w = _exp_weights(n, half_life)
    ewm, ci_low, ci_high = _de_posterior(onehot, w, prior_strength)

    weekday_mask = dates.dt.weekday.to_numpy() == int(target_weekday)
    weekday_rows = onehot[weekday_mask]
    weekday = (
        _de_posterior(
            weekday_rows, np.ones(len(weekday_rows)), prior_strength
        )[0]
        if len(weekday_rows)
        else uniform
    )

    window_probs: dict[int, np.ndarray] = {}
    for window in (30, 90, 365):
        h = onehot[-min(window, n) :]
        window_probs[window] = _de_posterior(
            h, np.ones(len(h)), prior_strength
        )[0]

    drift = np.array(
        [
            _js_divergence(window_probs[30], window_probs[90]),
            _js_divergence(window_probs[90], window_probs[365]),
            _js_divergence(window_probs[30], window_probs[365]),
        ]
    )
    global_stability = float(np.exp(-10.0 * drift.mean()))
    raw = normalize_distribution(
        0.55 * ewm + 0.25 * weekday + 0.20 * window_probs[90]
    )
    prob = normalize_distribution(
        uniform + global_stability * (raw - uniform)
    )

    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=int),
            "prob": prob,
            "baseline_prob": 0.01,
            "ewm_prob": ewm,
            "weekday_prob": weekday,
            "p30": window_probs[30],
            "p90": window_probs[90],
            "p365": window_probs[365],
            "stability": global_stability,
            "credible_low": ci_low,
            "credible_high": ci_high,
            "effective_sample_size": _effective_n(w),
            "weekday_trials": int(len(weekday_rows)),
        }
    )


def _blend_dynamics(
    df: pd.DataFrame,
    hit: np.ndarray,
    dates: pd.Series,
    *,
    mode: str,
) -> tuple[pd.DataFrame, dict]:
    dynamics = build_dynamics_signal(hit, dates=dates, mode=mode)  # type: ignore[arg-type]
    dyn = dynamics.current.rename(
        columns={
            "prob": "dynamics_prob",
            "baseline_prob": "dynamics_baseline_prob",
            "transition_prob": "cross_transition_prob",
        }
    )
    keep = [
        "number",
        "dynamics_prob",
        "dynamics_baseline_prob",
        "markov2_prob",
        "markov2_state",
        "markov2_reliability",
        "hazard_prob",
        "next_gap",
        "hazard_reliability",
        "cross_transition_prob",
        "lag_kernel_prob",
        "regime_prob",
        "regime_log_ratio",
        "dynamics_reliability",
    ]
    merged = df.merge(dyn[keep], on="number", how="left")
    merged["base_stat_prob"] = merged["prob"].astype(float)

    dyn_weight = 0.30 if mode == "loto" else 0.20
    combined = (
        (1.0 - dyn_weight) * merged["base_stat_prob"].to_numpy(dtype=float)
        + dyn_weight * merged["dynamics_prob"].to_numpy(dtype=float)
    )
    if mode == "de":
        combined = normalize_distribution(np.clip(combined, 1e-12, None))
    else:
        combined = np.clip(combined, 1e-5, 1 - 1e-5)
    merged["prob"] = combined

    dyn_diag = {
        "dynamics_weight_in_stat_signal": dyn_weight,
        "global_dynamics_reliability": float(
            dynamics.diagnostics["global_dynamics_reliability"]
        ),
        "regime_js_divergence_30_vs_180": float(
            dynamics.diagnostics["regime_js_divergence_30_vs_180"]
        ),
        "transition_active_mean_trials": float(
            dynamics.diagnostics["transition_active_mean_trials"]
        ),
        "calendar_contiguous": bool(dynamics.diagnostics["calendar_contiguous"]),
    }
    return merged, dyn_diag


#: ``None`` nghĩa là HỌC độ co ngót từ dữ liệu thay vì đặt tay.
#:
#: Giá trị cũ là 80, và nó được chọn bằng cảm tính. Đo walk-forward trên 938 kỳ
#: của chính kho này: κ học được có trung vị 1 000 000 (chạm trần) và nhỏ nhất
#: 23 626 — tức dữ liệu đòi co ngót mạnh hơn 80 từ ba trăm tới hơn mười nghìn
#: lần. Brier: gộp hoàn toàn 0,18138190; học κ 0,18138272; đặt tay 80
#: 0,18149968; không gộp 0,18150858.
#:
#: Vẫn nhận một số cụ thể để ép, phục vụ tái lập kết quả cũ.
LEARN_PRIOR_STRENGTH: float | None = None

#: Lưới chu kỳ bán rã để chọn, tính bằng KỲ QUAY.
#:
#: Giá trị cũ là 45, cũng đặt tay. Đo walk-forward 300 kỳ cuối trên dữ liệu
#: thật, kèm phép tiêm tín hiệu +100 % vào một con:
#:
#:   bán rã   ESS    Brier         ngụy tín hiệu   thu hồi tín hiệu
#:       45   130    0,18134089    0,00001          0,0 %
#:      180   519    0,18133923    0,00002         36,0 %
#:      365  1031    0,18133891    0,00003         63,9 %
#:        ∞  2398    0,18133866    0,00009         90,4 %
#:
#: Brier tốt lên ĐƠN ĐIỆU theo chu kỳ dài hơn, còn ngụy tín hiệu tăng chín lần
#: nhưng vẫn ở mức 0,009 điểm phần trăm trên nền 23,77 %. Ở mức 45, thành phần
#: `ewm` — vốn mang trọng số lớn nhất của tầng này — thu hồi ĐÚNG 0 % của một
#: tín hiệu gấp đôi tần suất nền. Nó đang mù hoàn toàn.
#:
#: ``None`` nghĩa là chọn từ lưới này bằng Brier trên lát giữ riêng.
HALF_LIFE_GRID: tuple[int, ...] = (45, 90, 180, 365, 730, 1460)
LEARN_HALF_LIFE: int | None = None
#: Dưới ngưỡng này thì cắt lát giữ riêng làm hỏng chính phép khớp.
MIN_HALF_LIFE_SELECTION_DAYS = 200
HALF_LIFE_HOLDOUT = 0.25
#: Sàn tuyệt đối cho phép so cặp đôi: dưới mức này là nhiễu cộng dấu chấm
#: động chứ không phải chênh lệch. Chỉ dùng khi sai số chuẩn bằng 0 (mọi kỳ
#: cho chênh lệch giống hệt nhau).
_FLOAT_NOISE = 1e-12


def select_half_life(
    hit: np.ndarray,
    *,
    grid: tuple[int, ...] = HALF_LIFE_GRID,
    holdout_fraction: float = HALF_LIFE_HOLDOUT,
) -> tuple[int, dict[str, float] | None]:
    """Chọn chu kỳ bán rã bằng Brier trên lát giữ riêng cắt theo THỜI GIAN.

    Trả về ``(chu kỳ, điểm từng ứng viên)``; phần thứ hai là ``None`` khi lịch
    sử quá ngắn để chọn — khi ấy giữ giá trị đầu lưới và nói rõ là không chọn,
    thay vì chọn bừa trên vài chục kỳ.
    """
    days = int(hit.shape[0])
    split = int(round(days * (1.0 - holdout_fraction)))
    if days < MIN_HALF_LIFE_SELECTION_DAYS or split <= 1 or days - split <= 1:
        return int(grid[0]), None

    per_day: dict[int, np.ndarray] = {}
    for half_life in grid:
        errors = []
        for t in range(split, days):
            past = hit[:t]
            w = _exp_weights(t, half_life)
            p = _eb_posterior((past * w[:, None]).sum(axis=0), float(w.sum()), None)
            errors.append(float(np.mean((p - hit[t]) ** 2)))
        per_day[half_life] = np.asarray(errors, dtype=float)
    scores = {str(hl): float(errors.mean()) for hl, errors in per_day.items()}

    # So CẶP ĐÔI có sai số chuẩn, không so với một dung sai đặt tay.
    #
    # Câu hỏi đúng không phải "chênh bao nhiêu" mà "chênh ấy có ĐO ĐƯỢC không".
    # Hai lý do buộc phải hỏi như vậy:
    #
    # * Dung sai tương đối sụp đổ khi Brier gần 0 — với dữ liệu mà mọi con đều
    #   trúng, ``|best| * 1e-6`` bằng 0 nên không gì hoà, và bộ chọn quay lại
    #   quyết định theo chữ số cuối.
    # * Đo thật ở chế độ đề: cả sáu ứng viên cho 0,00990000 giống hệt tới tám
    #   chữ số. Chọn giữa chúng là chọn theo nhiễu dấu chấm động.
    #
    # Phép so cặp đôi tận dụng việc mọi ứng viên được chấm trên CÙNG các kỳ:
    # phương sai của chênh lệch nhỏ hơn hẳn phương sai của từng bản, nên phép
    # kiểm nhạy hơn nhiều so với việc so hai trung bình độc lập.
    best_hl = min(grid, key=lambda hl: (scores[str(hl)], hl))
    best_errors = per_day[best_hl]
    n_days = max(best_errors.size, 1)

    tied = []
    for half_life in grid:
        delta = per_day[half_life] - best_errors
        standard_error = float(np.std(delta, ddof=1) / np.sqrt(n_days)) if n_days > 1 else 0.0
        if float(delta.mean()) <= SIGNIFICANCE_SIGMAS * standard_error + _FLOAT_NOISE:
            tied.append(half_life)

    # Hoà thì chu kỳ NGẮN hơn thắng: nó phản ứng nhanh hơn với trôi khái niệm,
    # nên khi không đo được khác biệt thì chọn bản linh hoạt hơn.
    return int(min(tied)), scores


def _resolve_prior_strength(
    observations: np.ndarray, prior_strength: float | None
) -> tuple[float, PoolingFit | None]:
    """Trả về độ co ngót sẽ dùng, kèm bằng chứng nếu nó được HỌC."""
    if prior_strength is not None:
        return float(prior_strength), None
    fit = fit_pooling(observations.sum(axis=0), float(observations.shape[0]))
    return fit.prior_strength, fit


def build_statistical_signal(
    mode: str,
    *,
    half_life: int | None = LEARN_HALF_LIFE,
    prior_strength: float | None = LEARN_PRIOR_STRENGTH,
) -> tuple[pd.DataFrame, dict]:
    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data().copy()
    sparse = lot.get_sparse_data().copy()
    if two.empty or sparse.empty:
        raise RuntimeError("No lottery data loaded")
    two["date"] = pd.to_datetime(two["date"])
    sparse["date"] = pd.to_datetime(sparse["date"])

    two_calendar = require_daily_contiguous(
        two["date"], context="statistical signal two-digit history"
    )
    sparse_calendar = require_daily_contiguous(
        sparse["date"], context="statistical signal sparse history"
    )
    if not two_calendar.equals(sparse_calendar):
        raise ValueError("two-digit and sparse statistical histories are not date-aligned")

    anchor = two_calendar[-1].date()
    target = anchor + timedelta(days=1)

    if mode == "de":
        de = (two["special"].astype(int).to_numpy() % 100).astype(int)
        hit = np.zeros((len(de), 100), dtype=np.int8)
        hit[np.arange(len(de)), de] = 1
        dates = two["date"]
        _strength, pooling = _resolve_prior_strength(hit, prior_strength)
        chosen_half_life, half_life_scores = (
            (half_life, None) if half_life is not None else select_half_life(hit)
        )
        # Chế độ đề chưa nối phép hợp học được: nó chuẩn hoá về phân phối tổng
        # bằng 1 nên phép hợp phải giữ ràng buộc ấy, và cần đo riêng trước khi
        # đổi. Giữ trộn số học cho tới khi có số liệu.
        pool, pool_audit = None, None
        df = _de_signal(
            hit,
            dates,
            target.weekday(),
            half_life=chosen_half_life,
            prior_strength=prior_strength,
        )
    elif mode == "loto":
        hit = (
            sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
        ).astype(np.int8)
        dates = sparse["date"]
        # `_resolve_prior_strength` ở đây chỉ để BÁO CÁO độ co ngót tổng thể;
        # từng phép đo bên trong tự học κ của riêng nó.
        _strength, pooling = _resolve_prior_strength(hit, prior_strength)
        chosen_half_life, half_life_scores = (
            (half_life, None) if half_life is not None else select_half_life(hit)
        )
        pool, pool_audit = select_signal_pool(
            hit, dates, mode="loto", half_life=chosen_half_life
        )
        df = _loto_signal(
            hit,
            dates,
            target.weekday(),
            half_life=chosen_half_life,
            prior_strength=prior_strength,
            pool=pool,
        )
    else:
        raise ValueError(mode)

    df, dynamics_diag = _blend_dynamics(df, hit, dates, mode=mode)
    df["number_str"] = df["number"].map(lambda x: f"{int(x):02d}")
    df["anchor_date"] = anchor.isoformat()
    df["target_date"] = target.isoformat()
    df.sort_values("prob", ascending=False, inplace=True, ignore_index=True)

    diagnostics = {
        "schema_version": 3,
        "mode": mode,
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "anchor_date": anchor.isoformat(),
        "target_date": target.isoformat(),
        "history_days": int(len(two)),
        # Tên trường giữ nguyên để không phá bản tóm tắt cũ, nhưng đơn vị là
        # KỲ QUAY chứ không phải ngày lịch — xem ghi chú ở HALF_LIFE_GRID.
        "half_life_days": chosen_half_life,
        "half_life_learned": half_life_scores is not None,
        "half_life_brier_by_candidate": half_life_scores,
        "pool": None if pool_audit is None else {
            "kind": pool_audit.chosen,
            "sharpness": pool_audit.sharpness,
            "selected": pool_audit.selected,
            "brier_by_candidate": pool_audit.brier_by_candidate,
            "holdout_days": pool_audit.holdout_days,
            "verdict": pool_audit.describe(),
        },
        "prior_strength": _strength,
        "prior_strength_learned": pooling is not None,
        # Số tham số HIỆU DỤNG là con số nối thẳng tới công suất thống kê: báo
        # cáo ngẫu nhiên đo được ngưỡng phát hiện +15,8 % tương đối với 100 giả
        # thuyết, nhưng chỉ +10,3 % với một. Co ngót kéo 100 xuống gần 1, tức
        # hạ ngưỡng ấy khoảng một phần ba — đó mới là phần thắng thật, không
        # phải vài phần trăm nghìn Brier.
        "pooling": None if pooling is None else {
            "pooled_rate": pooling.pooled_rate,
            "shrinkage": pooling.shrinkage,
            "effective_parameters": pooling.effective_parameters,
            "fully_pooled": pooling.fully_pooled,
            "between_variance": pooling.between_variance,
            "within_variance": pooling.within_variance,
            "verdict": pooling.describe(),
        },
        "mean_stability": float(df["stability"].mean()),
        "min_stability": float(df["stability"].min()),
        "max_stability": float(df["stability"].max()),
        **dynamics_diag,
        "interpretation": (
            "Empirical-Bayes + higher-order dynamics component. Markov, "
            "transition, hazard, lag and regime evidence is shrinkage-regularized, "
            "calendar-validated, and used only as probabilistic ranking support."
        ),
    }
    return df, diagnostics


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Build conservative empirical-Bayes + higher-order dynamics "
            "statistical prediction component."
        )
    )
    ap.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    # Mặc định là CHỌN từ lưới; truyền số để ép.
    ap.add_argument("--half-life", type=int, default=None)
    # Mặc định là HỌC (không truyền cờ). Truyền một số để ép, phục vụ tái lập
    # kết quả của các bản chạy cũ.
    ap.add_argument("--prior-strength", type=float, default=None)
    ap.add_argument("--out-dir", default="data/statistical_signal")
    ap.add_argument("--dynamics-out-dir", default="data/number_dynamics")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    modes = ["loto", "de"] if args.mode == "both" else [args.mode]
    for mode in modes:
        df, diag = build_statistical_signal(
            mode,
            half_life=args.half_life,
            prior_strength=args.prior_strength,
        )
        df.to_csv(out / f"predict_next_{mode}_stat_all.csv", index=False)
        (out / f"diagnostics_{mode}.json").write_text(
            json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        export_dynamics(mode, Path(args.dynamics_out_dir))
        print(
            f"[OK] statistical signal {mode}: "
            f"target={diag['target_date']} -> {out}"
        )


if __name__ == "__main__":
    main()
