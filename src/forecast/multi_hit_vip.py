"""Lọc "lô nhiều nháy" — con số về ≥ 2 nháy trong một kỳ XSMB — bằng VIP Score có kiểm chứng.

Mức nền trước tiên. Một kỳ XSMB có 27 lô (hai số cuối của 27 giải), gần như đều trên 00–99.
Nếu các giải độc lập và đều, số nháy của một con số định trước là X ~ Binomial(27, 1/100), nên

    P(X ≥ 2) = 1 − 0,99²⁷ − 27 · 0,01 · 0,99²⁶ ≈ 2,975 %.

Đó là xác suất trúng "nhiều nháy" khi chọn BỪA một con. 4 228 kỳ thật của kho cho 2,916 %.
Một bộ lọc chỉ có giá trị khi tỉ lệ trúng NGOÀI MẪU của nó vượt mức nền một cách có ý nghĩa
thống kê. Module này ĐO điều đó trên chính dữ liệu được đưa vào, không giả định nó.

Bốn lớp đặc trưng; đặc trưng của kỳ t chỉ đọc các kỳ 0..t−1:

1. Tần suất & điểm rơi: tần suất trong cửa sổ, đà về (EWMA ngắn − EWMA dài), độ dài chuỗi
   trúng, độ gan (số kỳ kể từ lần về gần nhất).
2. Dị thường Poisson: số kỳ về ≥ 2 nháy trong cửa sổ so với kỳ vọng nhị thức (điểm z), và chỉ
   số phân tán var/mean của số nháy trừ 1 (Poisson cho 0, nhiều nháy dồn cục cho > 0).
3. Đồng xuất hiện: P(i về ≥ 2 nháy ở kỳ t | j về ở kỳ t − 1), làm trơn Beta về mức nền, lấy
   log-lift trung bình theo số nháy của các con đã về kỳ trước.
4. Cầu nhịp: con số đã về 3–5 lần liên tiếp theo cùng một khoảng cách d, và kỳ t đúng là kỳ
   tiếp theo của nhịp ấy. Độ mạnh là số lần trong nhịp.

VIP_Score(i) = Σ wₖ · thành phầnₖ(i). Mỗi thành phần được chuẩn hoá chéo 100 số trong cùng một
kỳ (z-score hoặc min-max), nên các trọng số so được với nhau. Trọng số chọn trên lưới đơn hình
(bước 0,1) bằng backtest ``weight_window`` kỳ NGAY TRƯỚC kỳ dự báo: tối đa số lần trúng top-k,
hoà thì lấy AUC. Đánh giá là walk-forward LỒNG NHAU: kỳ t được chấm bằng trọng số chọn trên
[t − weight_window, t), nên tỉ lệ trúng báo ra không mang thiên lệch của chính phép chọn.

Xác suất in ra là hiệu chỉnh Platt (hồi quy logistic có điều chuẩn) khớp trên các cặp (điểm,
kết quả) NGOÀI MẪU của walk-forward. Không có tín hiệu thì hệ số về 0 và xác suất về mức nền:
đó là câu trả lời đúng, không phải lỗi. Confidence Index suy từ phép so một phía của số lượt
trúng top-k ngoài mẫu với CHỌN BỪA trên chính các kỳ ấy (``random_pick_null``), không đặt tay.

Chạy thử:

    python3 src/forecast/multi_hit_vip.py --mock                 # 100 kỳ giả định, quay công bằng
    python3 src/forecast/multi_hit_vip.py --mock --plant         # cài sẵn tín hiệu: bộ lọc phải bắt được
    python3 src/forecast/multi_hit_vip.py --csv data/xsmb-2-digits.csv
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binom, norm, rankdata
from sklearn.linear_model import LogisticRegression

N_NUMBERS = 100
LOTO_PER_DRAW = 27

COMPONENTS = ("frequency", "poisson_anomaly", "co_occurrence", "pattern")
COMPONENT_LABELS = {
    "frequency": "Tần suất & điểm rơi",
    "poisson_anomaly": "Dị thường Poisson",
    "co_occurrence": "Đồng xuất hiện kỳ trước",
    "pattern": "Cầu nhịp",
}
RAW_FEATURES = (
    "freq", "momentum", "streak", "gap", "multi_window", "multi_excess_z",
    "dispersion", "poisson_p2", "co_lift", "pattern", "pattern_interval",
)
_F = {name: k for k, name in enumerate(RAW_FEATURES)}

DEFAULT_PLANTED = (7, 38, 68)
TIE_SEED = 20261008


def base_rate(per_draw: int = LOTO_PER_DRAW, p: float = 1 / N_NUMBERS) -> float:
    """P(X ≥ 2) với X ~ Binomial(per_draw, p): một con số định trước về ≥ 2 nháy khi quay công bằng."""
    return float(binom.sf(1, per_draw, p))


def any_multi_chance(k: int, per_draw: int = LOTO_PER_DRAW, n: int = N_NUMBERS) -> float:
    """P(ít nhất một trong ``k`` con định trước về ≥ 2 nháy) khi quay công bằng.

    Đây là tỉ lệ KỲ ĐẠT của MỌI cách chọn ``k`` con, kể cả cách chọn dựa trên lịch sử: kỳ quay công
    bằng không phụ thuộc kỳ trước. Không con nào trong ``k`` con về ≥ 2 nháy ⇔ đúng j lô rơi vào
    ``k`` con ấy, mỗi lô một con khác nhau, còn ``per_draw − j`` lô rơi ngoài:
    Σⱼ C(per_draw, j)·k·(k − 1)…(k − j + 1)·(n − k)^(per_draw − j) / n^per_draw (số nguyên, chính xác).
    ``k = 1`` cho lại ``base_rate``; ``k = n`` là bài toán ngày sinh.
    """
    if not 0 <= k <= n:
        raise ValueError("cần 0 ≤ k ≤ n")
    none = sum(math.comb(per_draw, j) * math.perm(k, j) * (n - k) ** (per_draw - j)
               for j in range(min(k, per_draw) + 1))
    return 1 - none / n ** per_draw


def random_any_hit(n_multi: np.ndarray, k: int) -> np.ndarray:
    """Từng kỳ: P(chọn BỪA ``k`` trong 100 con có ít nhất một con thuộc ``n_multi`` con về ≥ 2 nháy).

    Mốc của tỉ lệ kỳ đạt trên CHÍNH các kỳ đã chấm: 1 − C(100 − m, k) / C(100, k) với m con về
    ≥ 2 nháy ở kỳ ấy (siêu bội, như ``random_pick_null``).
    """
    total = math.comb(N_NUMBERS, k)
    return np.array([1 - math.comb(N_NUMBERS - int(m), k) / total for m in n_multi], dtype=float)


@dataclass(frozen=True)
class VIPConfig:
    """Tham số của bộ lọc. Mặc định khớp yêu cầu: cửa sổ 30 kỳ, chọn trọng số trên 30 kỳ."""

    window: int = 30              # cửa sổ tần suất và dị thường Poisson
    short_span: int = 5           # EWMA ngắn của đà về
    long_span: int = 30           # EWMA dài của đà về
    weight_window: int = 30       # số kỳ backtest ngay trước kỳ dự báo để chọn trọng số
    weight_step: float = 0.1      # bước lưới đơn hình của trọng số
    top_k: int = 5
    prior_strength: float = 50.0  # độ mạnh tiên nghiệm Beta khi làm trơn xác suất điều kiện
    pattern_min_len: int = 3      # cầu nhịp: tối thiểu 3 lần cùng khoảng cách
    pattern_max_len: int = 5
    normalisation: str = "zscore"  # "zscore" hoặc "minmax"
    calibration_c: float = 0.1    # điều chuẩn L2 của hiệu chỉnh Platt (nhỏ = co mạnh về mức nền)

    def __post_init__(self) -> None:
        if self.normalisation not in {"zscore", "minmax"}:
            raise ValueError("normalisation phải là 'zscore' hoặc 'minmax'")
        if not 1 <= self.top_k <= N_NUMBERS:
            raise ValueError("top_k phải trong 1..100")
        if self.window < 1 or self.weight_window < 1:
            raise ValueError("window và weight_window phải ≥ 1")
        if not 2 <= self.pattern_min_len <= self.pattern_max_len:
            raise ValueError("cần 2 ≤ pattern_min_len ≤ pattern_max_len")
        steps = 1 / self.weight_step
        if abs(steps - round(steps)) > 1e-9:
            raise ValueError("1 / weight_step phải là số nguyên")

    @property
    def warmup(self) -> int:
        """Kỳ đầu tiên được chấm: trước đó cửa sổ tần suất chưa đầy."""
        return self.window

    @property
    def first_evaluated(self) -> int:
        """Kỳ đầu tiên có đủ ``weight_window`` kỳ đã chấm phía trước để chọn trọng số."""
        return self.warmup + self.weight_window


# --------------------------------------------------------------------------- dữ liệu

def draws_from_frame(frame: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Ma trận (kỳ × 27) số nguyên 00–99 và nhãn kỳ (cột ``date`` nếu có)."""
    labels = (frame["date"].astype(str).tolist() if "date" in frame.columns
              else [str(k) for k in range(len(frame))])
    values = frame.drop(columns=["date"], errors="ignore").astype(int).to_numpy()
    return validate_draws(values), labels


def until(frame: pd.DataFrame, last_date: str) -> pd.DataFrame:
    """Các kỳ có ``date`` ≤ ``last_date``: CSV lịch sử dài thêm mỗi ngày, nên một phép đo đã
    công bố chỉ tái lập được khi chốt ngày cuối."""
    cutoff = pd.Timestamp(last_date)
    kept = frame[pd.to_datetime(frame["date"]) <= cutoff]
    if kept.empty:
        raise ValueError(f"không có kỳ nào tới ngày {last_date}")
    return kept


def validate_draws(draws: np.ndarray | list) -> np.ndarray:
    arr = np.asarray(draws, dtype=int)
    if arr.ndim != 2 or arr.shape[1] != LOTO_PER_DRAW:
        raise ValueError(f"mỗi kỳ phải có đúng {LOTO_PER_DRAW} lô, nhận được {arr.shape}")
    if arr.size and (arr.min() < 0 or arr.max() >= N_NUMBERS):
        raise ValueError("lô phải nằm trong 00–99")
    return arr


def counts_matrix(draws: np.ndarray) -> np.ndarray:
    """C[t, i] = số nháy của con i ở kỳ t (tổng mỗi hàng = 27)."""
    draws = validate_draws(draws)
    counts = np.zeros((len(draws), N_NUMBERS), dtype=int)
    rows = np.repeat(np.arange(len(draws)), LOTO_PER_DRAW)
    np.add.at(counts, (rows, draws.ravel()), 1)
    return counts


def mock_history(n_draws: int = 100, seed: int = 2026, planted: tuple[int, ...] = (),
                 plant_rate: float = 0.3) -> pd.DataFrame:
    """Lịch sử giả định cùng khuôn với ``data/xsmb-2-digits.csv``.

    Mặc định: 27 lô độc lập, đều trên 00–99, tức đúng mô hình quay công bằng; một bộ lọc trung
    thực KHÔNG được báo tin cậy cao trên dữ liệu này. ``planted`` CÀI tín hiệu: mỗi kỳ, mỗi con
    trong ``planted`` với xác suất ``plant_rate`` được ghi đè vào hai vị trí ngẫu nhiên (thành
    ≥ 2 nháy). Dùng để chứng minh bộ lọc không mù.
    """
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, N_NUMBERS, size=(n_draws, LOTO_PER_DRAW))
    for t in range(n_draws):
        for number in planted:
            if rng.random() < plant_rate:
                draws[t, rng.choice(LOTO_PER_DRAW, size=2, replace=False)] = number
    frame = pd.DataFrame(draws, columns=[f"loto_{k + 1}" for k in range(LOTO_PER_DRAW)])
    frame.insert(0, "date", pd.date_range("2026-01-01", periods=n_draws, freq="D").strftime("%Y-%m-%d"))
    return frame


# --------------------------------------------------------------------------- đặc trưng

def build_raw_features(counts: np.ndarray, cfg: VIPConfig) -> np.ndarray:
    """Đặc trưng thô ``F[t, i, f]`` cho t = 0..T; hàng T là kỳ KẾ TIẾP chưa quay.

    Mọi thống kê ở hàng t chỉ dùng các kỳ < t: trạng thái được cập nhật bằng kỳ t SAU khi hàng t
    đã ghi xong.
    """
    n_draws = counts.shape[0]
    p2 = base_rate()
    multi = (counts >= 2).astype(float)
    appear = counts >= 1
    zeros = np.zeros((1, N_NUMBERS))
    cum = np.vstack([zeros, np.cumsum(counts, axis=0)])
    cum_sq = np.vstack([zeros, np.cumsum(counts.astype(float) ** 2, axis=0)])
    cum_multi = np.vstack([zeros, np.cumsum(multi, axis=0)])

    alpha_s, alpha_l = 2 / (cfg.short_span + 1), 2 / (cfg.long_span + 1)
    ewma_s = np.zeros(N_NUMBERS)
    ewma_l = np.zeros(N_NUMBERS)
    streak = np.zeros(N_NUMBERS)
    last_seen = np.full(N_NUMBERS, -1)
    occurrences: list[list[int]] = [[] for _ in range(N_NUMBERS)]
    pair_multi = np.zeros((N_NUMBERS, N_NUMBERS))   # [i, j]: j về ở s−1 và i ≥ 2 nháy ở s
    pair_base = np.zeros(N_NUMBERS)                 # [j]: số kỳ s−1 có j về (với s đã quay)

    out = np.zeros((n_draws + 1, N_NUMBERS, len(RAW_FEATURES)))
    for t in range(n_draws + 1):
        lo = max(0, t - cfg.window)
        n = t - lo
        row = out[t]
        if n:
            freq = (cum[t] - cum[lo]) / n
            var = (cum_sq[t] - cum_sq[lo]) / n - freq**2
            row[:, _F["freq"]] = freq
            row[:, _F["dispersion"]] = np.where(freq > 0, var / np.where(freq > 0, freq, 1), 1.0) - 1.0
            m = cum_multi[t] - cum_multi[lo]
            row[:, _F["multi_window"]] = m
            row[:, _F["multi_excess_z"]] = (m - n * p2) / np.sqrt(n * p2 * (1 - p2))
            row[:, _F["poisson_p2"]] = 1 - np.exp(-freq) * (1 + freq)
        row[:, _F["momentum"]] = ewma_s - ewma_l
        row[:, _F["streak"]] = streak
        row[:, _F["gap"]] = np.where(last_seen >= 0, t - last_seen, t + 1)
        if t >= 1 and counts[t - 1].sum():
            a = cfg.prior_strength
            lift = np.log((pair_multi + a * p2) / (pair_base[None, :] + a) / p2)
            row[:, _F["co_lift"]] = lift @ counts[t - 1] / counts[t - 1].sum()
        for i in range(N_NUMBERS):
            strength, interval = _rhythm(occurrences[i], t, cfg)
            row[i, _F["pattern"]] = strength
            row[i, _F["pattern_interval"]] = interval
        if t == n_draws:
            break
        # Cập nhật trạng thái bằng kỳ t — chỉ ảnh hưởng hàng t + 1 trở đi.
        c = counts[t]
        ewma_s = alpha_s * c + (1 - alpha_s) * ewma_s
        ewma_l = alpha_l * c + (1 - alpha_l) * ewma_l
        streak = np.where(appear[t], streak + 1, 0)
        last_seen[appear[t]] = t
        for i in np.flatnonzero(appear[t]):
            occurrences[i].append(t)
            del occurrences[i][:-cfg.pattern_max_len]
        if t >= 1:
            pair_multi += np.outer(multi[t], appear[t - 1])
            pair_base += appear[t - 1]
    return out


def _rhythm(occ: list[int], t: int, cfg: VIPConfig) -> tuple[int, int]:
    """Cầu nhịp dài nhất (cfg.pattern_min_len..max_len lần) cùng khoảng cách và đúng nhịp ở kỳ t."""
    for length in range(min(cfg.pattern_max_len, len(occ)), cfg.pattern_min_len - 1, -1):
        seq = occ[-length:]
        gaps = np.diff(seq)
        if gaps[0] > 0 and np.all(gaps == gaps[0]) and t - seq[-1] == gaps[0]:
            return length, int(gaps[0])
    return 0, 0


def normalise(values: np.ndarray, method: str) -> np.ndarray:
    """Chuẩn hoá chéo 100 số trong từng kỳ (trục cuối). Hằng số thì thành 0 (không thông tin)."""
    if method == "zscore":
        mean = values.mean(axis=-1, keepdims=True)
        std = values.std(axis=-1, keepdims=True)
        return np.divide(values - mean, std, out=np.zeros_like(values, dtype=float), where=std > 0)
    low = values.min(axis=-1, keepdims=True)
    span = values.max(axis=-1, keepdims=True) - low
    return np.divide(values - low, span, out=np.zeros_like(values, dtype=float), where=span > 0)


def build_components(raw: np.ndarray, method: str) -> np.ndarray:
    """Bốn thành phần VIP ``[t, i, k]`` (thứ tự ``COMPONENTS``), mỗi thành phần đã chuẩn hoá."""
    def z(name: str, sign: float = 1.0) -> np.ndarray:
        return normalise(sign * raw[:, :, _F[name]], method)

    gap_term = normalise(-np.log1p(raw[:, :, _F["gap"]]), method)
    parts = {
        "frequency": (z("freq") + z("momentum") + z("streak") + gap_term) / 4,
        "poisson_anomaly": (z("multi_excess_z") + z("dispersion")) / 2,
        "co_occurrence": z("co_lift"),
        "pattern": z("pattern"),
    }
    return np.stack([normalise(parts[name], method) for name in COMPONENTS], axis=-1)


def weight_grid(step: float) -> np.ndarray:
    """Mọi vector trọng số không âm, tổng 1, là bội của ``step`` (bốn thành phần)."""
    units = round(1 / step)
    rows = [(a, b, c, units - a - b - c)
            for a in range(units + 1) for b in range(units + 1 - a) for c in range(units + 1 - a - b)]
    return np.array(rows, dtype=float) / units


# --------------------------------------------------------------------------- xếp hạng

def tie_keys(t: int, n: int = N_NUMBERS) -> np.ndarray:
    """Khoá phá hoà của kỳ t: một hoán vị 00–99 cố định theo kỳ, không thiên về con nào.

    Thành phần thưa (cầu nhịp: phần lớn 100 con cùng điểm) làm hoà rất thường. Phá hoà bằng thứ
    tự số thì hoà nào cũng chọn 00–04, và phép chọn trọng số sẽ thưởng cho một chiến lược "chọn
    00–04" không ai khai báo: đo trên 4 228 kỳ, ở các kỳ trọng số dồn hết vào cầu nhịp, 52% lượt
    chọn rơi vào 00–04.
    """
    return np.random.default_rng([TIE_SEED, t]).permutation(n)


def rank_order(scores: np.ndarray, t: int) -> np.ndarray:
    """Chỉ số theo điểm GIẢM dần dọc trục 0; hoà phá bằng ``tie_keys(t)``.

    ``scores`` là (100,) hoặc (100, G). Chọn trọng số, backtest và dự báo đều xếp qua hàm này,
    nên cả ba thấy cùng một thứ tự.
    """
    keys = tie_keys(t, scores.shape[0])
    if scores.ndim == 2:
        keys = np.broadcast_to(keys[:, None], scores.shape)
    return np.lexsort((keys, -scores), axis=0)


# --------------------------------------------------------------------------- backtest

def random_pick_null(n_multi: np.ndarray, k: int) -> tuple[float, float]:
    """Kỳ vọng và phương sai số lượt trúng khi chọn BỪA k trong 100 con ở từng kỳ, cộng qua các kỳ.

    ``n_multi[t]`` là số con về ≥ 2 nháy ở kỳ t. Chọn bừa k con trong 100 thì số lượt trúng của
    kỳ ấy theo phân phối siêu bội. So với mức nền LÝ THUYẾT (2,975%) thì sai: lịch sử thật có tỉ lệ
    riêng (4 168 kỳ chấm: 2,914%), và một lịch sử có tỉ lệ cao hơn lý thuyết sẽ làm cả chọn bừa
    trông như "hơn nền".
    """
    share = np.asarray(n_multi, dtype=float) / N_NUMBERS
    expected = float((k * share).sum())
    variance = float((k * share * (1 - share) * (N_NUMBERS - k) / (N_NUMBERS - 1)).sum())
    return expected, variance


@dataclass
class Backtest:
    """Kết quả walk-forward lồng nhau trên các kỳ đã quay.

    ``base`` là mức nền lý thuyết, chỉ để hiển thị. ``expected``, lift và p so với chọn bừa trên
    CHÍNH các kỳ đã chấm (``random_pick_null``).
    """

    top_k: int
    base: float
    draws: int
    picks: int
    hits: int
    expected: float
    z: float
    p_value: float
    per_draw: pd.DataFrame
    oos_scores: np.ndarray = field(repr=False)
    oos_labels: np.ndarray = field(repr=False)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.picks if self.picks else float("nan")

    @property
    def expected_hits(self) -> float:
        return self.expected

    @property
    def random_rate(self) -> float:
        """Tỉ lệ trúng kỳ vọng của chọn bừa trên chính các kỳ đã chấm."""
        return self.expected / self.picks if self.picks else float("nan")

    @property
    def lift(self) -> float:
        return self.hits / self.expected if self.expected else float("nan")


class VIPMultiHitModel:
    """Toàn bộ quy trình: đặc trưng → thành phần → chọn trọng số → walk-forward → dự báo."""

    def __init__(self, draws: np.ndarray, labels: list[str] | None = None,
                 config: VIPConfig | None = None) -> None:
        self.cfg = config or VIPConfig()
        self.draws = validate_draws(draws)
        self.labels = labels or [str(k) for k in range(len(self.draws))]
        if len(self.draws) <= self.cfg.first_evaluated:
            raise ValueError(f"cần nhiều hơn {self.cfg.first_evaluated} kỳ "
                             f"(window {self.cfg.window} + weight_window {self.cfg.weight_window})")
        self.base = base_rate()
        self.counts = counts_matrix(self.draws)
        self.labels_y = self.counts >= 2
        self.raw = build_raw_features(self.counts, self.cfg)
        self.components = build_components(self.raw, self.cfg.normalisation)
        self.grid = weight_grid(self.cfg.weight_step)
        self._hits, self._auc = self._score_all_weights()

    # -- chấm mọi vector trọng số trên mọi kỳ đã quay (một lần, dùng lại khi chọn)
    def _score_all_weights(self) -> tuple[np.ndarray, np.ndarray]:
        n_draws, k = len(self.draws), self.cfg.top_k
        hits = np.zeros((n_draws, len(self.grid)))
        auc = np.full((n_draws, len(self.grid)), np.nan)
        for t in range(self.cfg.warmup, n_draws):
            scores = self.components[t] @ self.grid.T            # (100, G)
            y = self.labels_y[t]
            top = rank_order(scores, t)[:k]
            hits[t] = y[top].sum(axis=0)
            n_pos = int(y.sum())
            if 0 < n_pos < N_NUMBERS:
                ranks = rankdata(scores, axis=0)
                auc[t] = (ranks[y].sum(axis=0) - n_pos * (n_pos + 1) / 2) / (n_pos * (N_NUMBERS - n_pos))
        return hits, auc

    def select_weights(self, t: int) -> int:
        """Chỉ số vector trọng số tốt nhất trên [t − weight_window, t): trúng top-k, hoà thì AUC."""
        lo = t - self.cfg.weight_window
        if lo < self.cfg.warmup:
            raise ValueError(f"kỳ {t} chưa đủ {self.cfg.weight_window} kỳ đã chấm phía trước")
        total = self._hits[lo:t].sum(axis=0)
        tied = np.flatnonzero(total == total.max())
        auc = self._auc[lo:t][:, tied]
        valid = ~np.isnan(auc)
        mean_auc = np.where(valid.any(axis=0),
                            np.nansum(auc, axis=0) / np.maximum(valid.sum(axis=0), 1), -np.inf)
        return int(tied[int(np.argmax(mean_auc))])

    def scores(self, t: int, weight_index: int) -> np.ndarray:
        return self.components[t] @ self.grid[weight_index]

    def backtest(self) -> Backtest:
        """Walk-forward lồng nhau trên mọi kỳ từ ``first_evaluated`` tới kỳ cuối đã quay."""
        k = self.cfg.top_k
        rows, oos_s, oos_y = [], [], []
        for t in range(self.cfg.first_evaluated, len(self.draws)):
            g = self.select_weights(t)
            s = self.scores(t, g)
            top = rank_order(s, t)[:k]
            hit = int(self.labels_y[t, top].sum())
            rows.append({"ky": self.labels[t], "chon": [f"{i:02d}" for i in top], "trung": hit,
                         **{f"w_{name}": self.grid[g][j] for j, name in enumerate(COMPONENTS)}})
            oos_s.append(s)
            oos_y.append(self.labels_y[t])
        draws = len(rows)
        hits = sum(r["trung"] for r in rows)
        picks = draws * k
        expected, variance = random_pick_null(
            self.labels_y[self.cfg.first_evaluated:].sum(axis=1), k)
        z = (hits - expected) / np.sqrt(variance) if variance > 0 else 0.0
        p_value = float(norm.sf(z)) if picks else 1.0
        return Backtest(k, self.base, draws, picks, hits, expected, float(z), p_value, pd.DataFrame(rows),
                        np.concatenate(oos_s) if oos_s else np.empty(0),
                        np.concatenate(oos_y) if oos_y else np.empty(0, dtype=bool))

    def calibrator(self, bt: Backtest):
        """Hiệu chỉnh Platt trên (điểm, kết quả) NGOÀI MẪU; quá ít ca dương thì trả mức nền."""
        if bt.oos_labels.sum() < 5 or bt.oos_labels.all():
            return lambda s: np.full(np.shape(s), self.base)
        model = LogisticRegression(C=self.cfg.calibration_c)
        model.fit(bt.oos_scores.reshape(-1, 1), bt.oos_labels)
        return lambda s: model.predict_proba(np.asarray(s, dtype=float).reshape(-1, 1))[:, 1]

    def predict_next(self) -> VIPReport:
        """Dự báo kỳ KẾ TIẾP (hàng T của đặc trưng) kèm bằng chứng walk-forward."""
        bt = self.backtest()
        t = len(self.draws)
        g = self.select_weights(t)
        s = self.scores(t, g)
        prob = self.calibrator(bt)(s)
        level = model_confidence(bt.p_value, bt.lift)
        top = rank_order(s, t)[: self.cfg.top_k]
        weights = dict(zip(COMPONENTS, self.grid[g], strict=True))
        picks = []
        for i in top:
            contrib = {name: weights[name] * self.components[t, i, j] for j, name in enumerate(COMPONENTS)}
            raw = {name: float(self.raw[t, i, _F[name]]) for name in RAW_FEATURES}
            picks.append(Pick(number=f"{i:02d}", vip_score=float(s[i]), probability=float(prob[i]),
                              lift=float(prob[i] / self.base),
                              confidence=number_confidence(level, float(prob[i]), self.base),
                              contributions=contrib, raw=raw, weights=weights))
        return VIPReport(after=self.labels[-1], draws_used=len(self.draws), base=self.base,
                         weights=weights, backtest=bt, model_level=level, picks=picks,
                         weight_window=self.cfg.weight_window)


# --------------------------------------------------------------------------- tin cậy

#: Ngưỡng p một phía của từng mức tin bộ lọc (kèm lift > 1); trang Lô VIP in đúng các ngưỡng này.
CONFIDENCE_P = {"High": 0.01, "Medium": 0.05}


def model_confidence(p_value: float, lift: float) -> str:
    """Mức tin của CẢ bộ lọc, từ phép so một phía của top-k ngoài mẫu với chọn bừa cùng kỳ."""
    for level in ("High", "Medium"):
        if lift > 1 and p_value < CONFIDENCE_P[level]:
            return level
    return "Low"


def number_confidence(model_level: str, probability: float, base: float) -> str:
    """Một con chỉ tin được tới mức bộ lọc đã chứng minh, và khi xác suất hiệu chỉnh vượt nền."""
    if model_level == "High" and probability >= 2 * base:
        return "High"
    if model_level in {"High", "Medium"} and probability >= 1.5 * base:
        return "Medium"
    return "Low"


# --------------------------------------------------------------------------- báo cáo

@dataclass
class Pick:
    number: str
    vip_score: float
    probability: float
    lift: float
    confidence: str
    contributions: dict[str, float]
    raw: dict[str, float]
    weights: dict[str, float]

    def reasons(self, n: int = 2) -> list[str]:
        """Các thành phần (trọng số > 0) đóng góp lớn nhất, kèm số đo thô giải thích nó."""
        active = {k: v for k, v in self.contributions.items() if self.weights[k] > 0}
        ranked = sorted(active.items(), key=lambda kv: kv[1], reverse=True)[:n]
        return [f"{COMPONENT_LABELS[name]} {value:+.2f} ({_explain(name, self.raw)})"
                for name, value in ranked]


def _explain(component: str, raw: dict[str, float]) -> str:
    if component == "frequency":
        return (f"{raw['freq']:.2f} nháy/kỳ, đà {raw['momentum']:+.2f}, "
                f"chuỗi {raw['streak']:.0f}, gan {raw['gap']:.0f}")
    if component == "poisson_anomaly":
        return (f"{raw['multi_window']:.0f} kỳ ≥2 nháy trong cửa sổ, z = {raw['multi_excess_z']:+.2f}, "
                f"phân tán {raw['dispersion']:+.2f}")
    if component == "co_occurrence":
        return f"lift điều kiện ×{np.exp(raw['co_lift']):.2f}"
    if raw["pattern"]:
        return f"nhịp {raw['pattern']:.0f} lần, cách {raw['pattern_interval']:.0f} kỳ"
    return "không có nhịp"


@dataclass
class VIPReport:
    after: str
    draws_used: int
    base: float
    weights: dict[str, float]
    backtest: Backtest
    model_level: str
    picks: list[Pick]
    weight_window: int

    def to_dict(self) -> dict:
        bt = self.backtest
        return {
            "sau_ky": self.after,
            "so_ky_dung": self.draws_used,
            "muc_nen_p_ge2": self.base,
            "trong_so": self.weights,
            "kiem_chung": {"so_ky": bt.draws, "luot_chon": bt.picks, "trung": bt.hits,
                           "ti_le_trung": bt.hit_rate, "ky_vong_chon_bua": bt.expected_hits,
                           "ti_le_chon_bua": bt.random_rate, "lift": bt.lift, "z": bt.z,
                           "p_value": bt.p_value, "confidence": self.model_level},
            "top": [{"so": p.number, "vip_score": p.vip_score, "xac_suat": p.probability,
                     "x_nen": p.lift, "confidence": p.confidence, "ly_do": p.reasons()}
                    for p in self.picks],
        }

    def render(self) -> str:
        bt = self.backtest
        pct = lambda x: f"{100 * x:.2f}%"  # noqa: E731
        lines = [
            f"BÁO CÁO LÔ NHIỀU NHÁY — kỳ kế tiếp sau {self.after} ({self.draws_used} kỳ dữ liệu)",
            f"Mức nền: chọn bừa một con trúng ≥ 2 nháy với xác suất {pct(self.base)}.",
            f"Trọng số (chọn trên {self.weight_window} kỳ ngay trước): "
            + ", ".join(f"{COMPONENT_LABELS[k]} {v:.1f}" for k, v in self.weights.items()),
            f"Kiểm chứng walk-forward ngoài mẫu: {bt.draws} kỳ × top-{bt.top_k} = {bt.picks} lượt chọn, "
            f"trúng {bt.hits} ({pct(bt.hit_rate)}); chọn bừa trên chính các kỳ ấy kỳ vọng "
            f"{bt.expected_hits:.1f} ({pct(bt.random_rate)}). Lift ×{bt.lift:.2f}, z = {bt.z:+.2f}, "
            f"p = {bt.p_value:.3g} → Confidence bộ lọc: {self.model_level}.",
        ]
        if self.model_level == "Low":
            lines.append("⚠ Không có bằng chứng thống kê rằng bộ lọc hơn chọn bừa trên dữ liệu này; "
                         "xác suất bên dưới vì thế nằm sát mức nền.")
        lines.append("")
        lines.append(f"{'#':>2}  {'Số':>3}  {'VIP Score':>9}  {'P(≥2) dự báo':>12}  {'×nền':>5}  {'Tin cậy':<7}")
        for rank, p in enumerate(self.picks, 1):
            lines.append(f"{rank:>2}  {p.number:>3}  {p.vip_score:>9.3f}  {pct(p.probability):>12}  "
                         f"{p.lift:>5.2f}  {p.confidence:<7}")
        lines.append("")
        lines.append("Giải trình (hai thành phần đóng góp lớn nhất = trọng số × điểm chuẩn hoá):")
        for p in self.picks:
            lines.append(f"  {p.number}: " + "; ".join(p.reasons()))
        return "\n".join(lines)


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--mock", action="store_true", help="dữ liệu giả định")
    source.add_argument("--csv", type=Path, help="CSV cùng khuôn data/xsmb-2-digits.csv")
    parser.add_argument("--draws", type=int, default=100, help="số kỳ giả định (mặc định 100)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--plant", action="store_true",
                        help=f"cài tín hiệu cho {', '.join(f'{n:02d}' for n in DEFAULT_PLANTED)} (kiểm độ nhạy)")
    parser.add_argument("--until", help="chỉ dùng các kỳ tới ngày này (YYYY-MM-DD) — để tái lập một phép đo")
    parser.add_argument("--last", type=int, default=0, help="chỉ dùng N kỳ gần nhất của CSV")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--normalisation", choices=["zscore", "minmax"], default="zscore")
    parser.add_argument("--json", type=Path, help="ghi báo cáo JSON ra tệp này")
    args = parser.parse_args(argv)

    if args.mock:
        frame = mock_history(args.draws, args.seed, DEFAULT_PLANTED if args.plant else ())
    else:
        frame = pd.read_csv(args.csv, dtype=str)
        if args.until:
            frame = until(frame, args.until)
        if args.last:
            frame = frame.tail(args.last)
    draws, labels = draws_from_frame(frame)
    cfg = VIPConfig(top_k=args.top_k, normalisation=args.normalisation)
    report = VIPMultiHitModel(draws, labels, cfg).predict_next()
    print(report.render())
    if args.json:
        args.json.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
