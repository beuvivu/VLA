"""Ma trận đặc trưng cho bài toán "con số n có về ở kỳ t+1 không".

Quy ước DUY NHẤT của module: hàng ``t`` của mọi ma trận chỉ dùng các kỳ
``0..t`` (kỳ ``t`` đã quay xong), và dự báo kỳ ``t+1``. Nhãn của hàng ``t`` là
kết cục của kỳ ``t+1`` (``targets``); hàng cuối không có nhãn. Phép kiểm
``test_features_never_look_at_the_draw_they_predict`` đổi mọi kỳ sau ``t`` rồi
đòi hàng ``0..t`` giữ nguyên từng bit.

Các nhóm đặc trưng:

* Nhịp & gan: số kỳ chưa về, điểm z của gan so với chu kỳ đã hoàn tất của
  chính con số (co về lý thuyết hình học khi còn ít chu kỳ), chuỗi về liên tiếp.
* Tần suất suy giảm ``w = 2^{-(T-t)/h}`` với chu kỳ bán rã 7/30/90/180 kỳ,
  chia cho tỉ lệ nền tích luỹ (1 = đúng mức nền).
* Cầu vị trí: số cặp vị trí (a < b) đang chạy liên tiếp ≥ k kỳ và báo đúng
  con số, cùng độ dài cầu dài nhất (luật ``bridge_rules``).
* Đồ thị đồng xuất hiện: PMI cùng kỳ (mức "hợp nhau" với các con vừa về), PMI
  trễ 1 kỳ (con j về hôm nay thì con n về ngày mai nhiều hơn nền?), và nhiệt
  của cộng đồng Louvain chứa con số.
* Riêng Đặc Biệt: tần suất suy giảm của đầu, đuôi, tổng, bộ, lớn/nhỏ, chẵn/lẻ;
  xác suất chuyển Markov bậc 1 của tổng/đầu/đuôi từ kỳ t sang t+1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import networkx as nx
import numpy as np
import pandas as pd
from scipy.signal import lfilter

from bridge_rules import BO_ID, step_matrix
from position_bridges import load_draws, pair_index, run_lengths

Mode = Literal["loto", "de"]
NUMBERS = np.arange(100)


@dataclass(frozen=True)
class History:
    """Lịch sử theo thứ tự kỳ quay."""

    dates: tuple[str, ...]
    digits: np.ndarray  # (T, 107) chữ số theo thứ tự in
    values: np.ndarray  # (T, 27) giá trị đầy đủ của từng giải

    def __len__(self) -> int:
        return len(self.dates)

    @property
    def counts(self) -> np.ndarray:
        """(T, 100): số nháy của mỗi con trong 27 giải."""
        two = (self.values % 100).astype(np.int64)
        out = np.zeros((len(self), 100), dtype=np.int16)
        np.add.at(out, (np.arange(len(self))[:, None], two), 1)
        return out

    @property
    def special(self) -> np.ndarray:
        """(T,): hai số cuối giải Đặc Biệt."""
        return (self.values[:, 0] % 100).astype(np.int64)

    def hits(self, mode: Mode) -> np.ndarray:
        """(T, 100) bool: con số "về" theo nghĩa của ``mode``."""
        if mode == "loto":
            return self.counts > 0
        out = np.zeros((len(self), 100), dtype=bool)
        out[np.arange(len(self)), self.special] = True
        return out

    def head(self, n: int) -> "History":
        return History(self.dates[:n], self.digits[:n], self.values[:n])


def history_from_frame(raw: pd.DataFrame) -> History:
    dates, digits, values = load_draws(raw)
    return History(tuple(dates), digits, values)


def load_history(data_dir: Path) -> History:
    return history_from_frame(pd.read_csv(Path(data_dir) / "xsmb.csv"))


def targets(history: History, mode: Mode) -> np.ndarray:
    """(T, 100) float: nhãn của hàng t là kết cục kỳ t+1; hàng cuối là NaN."""
    hit = history.hits(mode).astype(np.float32)
    out = np.full(hit.shape, np.nan, dtype=np.float32)
    out[:-1] = hit[1:]
    return out


@dataclass(frozen=True)
class FeatureParams:
    half_lives: tuple[int, ...] = (7, 30, 90, 180)
    #: Cầu LOTO đếm khi đã chạy ≥ 3 kỳ (mặc định trang tham chiếu); cầu Đặc
    #: Biệt "cả hai chữ số" hiếm nên đếm từ 1 kỳ.
    bridge_min_streak: dict[str, int] = field(default_factory=lambda: {"loto": 3, "de": 1})
    #: Tính lại cộng đồng Louvain sau mỗi ngần này kỳ, CHỈ trên dữ liệu đến
    #: mốc ấy — cộng đồng dùng ở kỳ t là cộng đồng của mốc gần nhất ≤ t.
    community_every: int = 250
    #: Số chu kỳ ảo theo lý thuyết hình học dùng để co trung bình/phương sai gan.
    gap_prior_cycles: float = 3.0
    seed: int = 7


@dataclass(frozen=True)
class FeatureTensor:
    names: tuple[str, ...]
    X: np.ndarray  # (T, 100, F) float32

    def column(self, name: str) -> np.ndarray:
        return self.X[:, :, self.names.index(name)]


# --------------------------------------------------------------------------
# Khối tính toán dùng chung
# --------------------------------------------------------------------------


def decayed_sum(x: np.ndarray, half_life: float) -> np.ndarray:
    """``S_t = Σ_{s≤t} 2^{-(t-s)/h} x_s`` theo trục 0 (bộ lọc IIR bậc 1)."""
    if not np.isfinite(half_life):
        return np.cumsum(x, axis=0, dtype=np.float64)
    decay = float(2.0 ** (-1.0 / max(float(half_life), 1e-9)))
    return lfilter([1.0], [1.0, -decay], np.asarray(x, dtype=np.float64), axis=0)


def expanding_rate(hit: np.ndarray) -> np.ndarray:
    """(T,) tỉ lệ nền tích luỹ tới hết kỳ t (trung bình trên mọi con số)."""
    per_day = hit.mean(axis=1, dtype=np.float64)
    return np.cumsum(per_day) / np.arange(1, len(hit) + 1)


def gap_matrix(hit: np.ndarray) -> np.ndarray:
    """Số kỳ kể từ lần về gần nhất, tính tới hết kỳ t (0 = về đúng kỳ t)."""
    n = len(hit)
    index = np.arange(n, dtype=np.int64)[:, None]
    last = np.maximum.accumulate(np.where(hit, index, -1), axis=0)
    # Chưa về lần nào: đếm từ đầu chuỗi.
    return np.where(last >= 0, index - last, index + 1).astype(np.float64)


def gap_zscore(hit: np.ndarray, base_rate: np.ndarray, prior_cycles: float) -> np.ndarray:
    """z của gan hiện tại so với các chu kỳ ĐÃ HOÀN TẤT của chính con số.

    Chu kỳ = số kỳ giữa hai lần về liên tiếp (≥ 1). Trung bình và phương sai co
    về phân phối hình học với tỉ lệ nền ``p``: trung bình ``1/p``, phương sai
    ``(1-p)/p²``, nặng ``prior_cycles`` chu kỳ ảo.
    """
    n, m = hit.shape
    gaps = gap_matrix(hit)
    out = np.zeros((n, m), dtype=np.float64)
    last = np.full(m, -1, dtype=np.int64)
    count = np.zeros(m)
    total = np.zeros(m)
    total_sq = np.zeros(m)
    for t in range(n):
        h = hit[t]
        done = h & (last >= 0)
        cycle = (t - last)[done].astype(np.float64)
        count[done] += 1
        total[done] += cycle
        total_sq[done] += cycle * cycle
        last[h] = t
        p = min(max(float(base_rate[t]), 1e-6), 1 - 1e-6)
        mu0, var0 = 1.0 / p, (1.0 - p) / (p * p)
        k = prior_cycles
        mean = (total + k * mu0) / (count + k)
        second = (total_sq + k * (var0 + mu0 * mu0)) / (count + k)
        std = np.sqrt(np.maximum(second - mean * mean, 1e-9))
        out[t] = (gaps[t] - mean) / std
    return out


def hit_streak(hit: np.ndarray) -> np.ndarray:
    out = np.zeros(hit.shape, dtype=np.float64)
    state = np.zeros(hit.shape[1])
    for t in range(len(hit)):
        state = (state + 1.0) * hit[t]
        out[t] = state
    return out


def bridge_features(history: History, mode: Mode, min_streak: int) -> tuple[np.ndarray, np.ndarray]:
    """(số cầu đang chạy ≥ min_streak báo con n, cầu dài nhất báo con n) tại mỗi kỳ.

    Cầu (a, b) "báo" ở kỳ t số ``10·d[a]+d[b]`` (và số lộn của nó). Độ dài cầu
    là số bước kỳ-sang-kỳ liên tiếp gần nhất đã trúng tính tới kỳ t, theo luật
    LOTO (lô) hoặc Đặc Biệt "cả hai chữ số" của ``bridge_rules.step_matrix``.
    """
    T = len(history)
    count = np.zeros((T, 100))
    longest = np.zeros((T, 100))
    if T < 2:
        return count, longest
    kind = "loto" if mode == "loto" else "dac-biet"
    steps = step_matrix(kind, history.digits, history.values, both=(mode == "de"))
    runs = run_lengths(steps)  # runs[t-1] = độ dài cầu tính tới kỳ t
    pa, pb = pair_index(True)
    for t in range(1, T):
        r = runs[t - 1].astype(np.float64)
        x = history.digits[t, pa].astype(np.int64)
        y = history.digits[t, pb].astype(np.int64)
        n1, n2 = 10 * x + y, 10 * y + x
        alive = r >= min_streak
        # Số lộn chỉ tính khi khác số thuận: số kép là MỘT số.
        for nums, use in ((n1, np.ones(len(r), dtype=bool)), (n2, n1 != n2)):
            count[t] += np.bincount(nums[use & alive], minlength=100)
            np.maximum.at(longest[t], nums[use], r[use])
    return count, longest


#: Số đếm ảo cộng vào CẢ số quan sát lẫn số kỳ vọng của một cặp trước khi lấy log.
PMI_PSEUDOCOUNT = 5.0


def _pmi(joint: np.ndarray, left: np.ndarray, right: np.ndarray, total: float,
         pseudo: float = PMI_PSEUDOCOUNT) -> np.ndarray:
    """PMI co về 0: ``log[(c_ij + k) / (e_ij + k)]`` với ``e_ij = c_i·c_j / N``.

    ``e_ij`` là số lần cặp cùng xuất hiện nếu hai con độc lập. Cặp chưa có bằng
    chứng (``c_ij`` và ``e_ij`` đều ≈ 0) cho PMI ≈ 0, không phải "liên kết mạnh";
    cặp có nhiều dữ liệu tiến về ``log(c_ij / e_ij)``. Dạng cũ
    ``log[(c_ij+1)·N / ((c_i+1)(c_j+1))]`` cho hai con chưa từng về PMI = log N.
    """
    expected = np.outer(left, right) / max(float(total), 1.0)
    return np.log((joint + pseudo) / (expected + pseudo))


def cooccurrence_features(
    present: np.ndarray, target_hit: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PMI cùng kỳ, PMI trễ 1 kỳ trung bình, và PMI trễ 1 kỳ LỚN NHẤT.

    ``present`` là tập LOTO của từng kỳ; ``target_hit`` là biến cố được dự báo
    (LOTO hoặc Đặc Biệt). Ma trận đếm chỉ gồm các kỳ ≤ t. Bản trung bình pha
    loãng một cặp mạnh trong ~23 con vừa về; bản lớn nhất giữ được nó.
    """
    T = len(present)
    same = np.zeros((T, 100))
    lagged = np.zeros((T, 100))
    lagged_max = np.zeros((T, 100))
    joint = np.zeros((100, 100))
    lag_joint = np.zeros((100, 100))
    marg = np.zeros(100)
    lag_left = np.zeros(100)
    lag_right = np.zeros(100)
    prev = None
    for t in range(T):
        h = present[t].astype(np.float64)
        joint += np.outer(h, h)
        marg += h
        if prev is not None:
            g = target_hit[t].astype(np.float64)
            lag_joint += np.outer(prev, g)
            lag_left += prev
            lag_right += g
        k = max(h.sum(), 1.0)
        pmi = _pmi(joint, marg, marg, t + 1)
        np.fill_diagonal(pmi, 0.0)
        same[t] = pmi @ h / k
        if t >= 1:
            lag = _pmi(lag_joint, lag_left, lag_right, t)
            lagged[t] = h @ lag / k
            if h.any():
                lagged_max[t] = lag[h > 0].max(axis=0)
        prev = h
    return same, lagged, lagged_max


def community_heat(present: np.ndarray, rate_ratio: np.ndarray, every: int, seed: int) -> np.ndarray:
    """Nhiệt của cộng đồng Louvain chứa con số: trung bình ``rate_ratio`` của cả cụm.

    Đồ thị: 100 đỉnh, cạnh nặng = PMI dương cùng kỳ. Cộng đồng được tính lại tại
    các mốc ``every, 2·every, …`` chỉ từ các kỳ ≤ mốc.
    """
    T = len(present)
    out = np.ones((T, 100))
    labels = np.zeros(100, dtype=np.int64)  # trước mốc đầu: một cụm duy nhất
    for start in range(0, T, every):
        if start > 0:
            seen = present[:start].astype(np.float64)
            joint = seen.T @ seen
            marg = seen.sum(axis=0)
            pmi = _pmi(joint, marg, marg, float(start))
            graph = nx.Graph()
            graph.add_nodes_from(range(100))
            i, j = np.triu_indices(100, 1)
            keep = pmi[i, j] > 0
            graph.add_weighted_edges_from(zip(i[keep].tolist(), j[keep].tolist(), pmi[i, j][keep].tolist(), strict=True))
            groups = nx.community.louvain_communities(graph, weight="weight", seed=seed)
            for label, members in enumerate(groups):
                labels[list(members)] = label
        stop = min(start + every, T)
        block = rate_ratio[start:stop]
        heat = np.zeros_like(block)
        for label in np.unique(labels):
            members = labels == label
            heat[:, members] = block[:, members].mean(axis=1, keepdims=True)
        out[start:stop] = heat
    return out


#: Thuộc tính của con số Đặc Biệt: (tên, mã nhóm của mỗi con 00..99).
SPECIAL_GROUPS: dict[str, np.ndarray] = {
    "dau": NUMBERS // 10,
    "duoi": NUMBERS % 10,
    "tong": (NUMBERS // 10 + NUMBERS % 10) % 10,
    "bo": BO_ID[NUMBERS].astype(np.int64),
    "lon_nho": (NUMBERS >= 50).astype(np.int64),
    "chan_le": (NUMBERS % 2).astype(np.int64),
}
MARKOV_GROUPS = ("tong", "dau", "duoi")


def special_group_features(special: np.ndarray, half_life: float = 30.0) -> dict[str, np.ndarray]:
    """Tần suất suy giảm của nhóm chứa con n, chia cho tỉ phần của nhóm ấy."""
    T = len(special)
    out = {}
    for name, group in SPECIAL_GROUPS.items():
        k = int(group.max()) + 1
        share = np.bincount(group, minlength=k) / 100.0
        onehot = np.zeros((T, k))
        onehot[np.arange(T), group[special]] = 1.0
        weight = decayed_sum(np.ones(T), half_life)[:, None]
        rate = decayed_sum(onehot, half_life) / weight
        out[f"db_{name}_ratio"] = rate[:, group] / share[group]
    return out


def markov_features(special: np.ndarray) -> dict[str, np.ndarray]:
    """P(nhóm kỳ t+1 = nhóm của n | nhóm kỳ t) / tỉ phần nhóm, đếm trên các cặp ≤ t."""
    T = len(special)
    out = {}
    for name in MARKOV_GROUPS:
        group = SPECIAL_GROUPS[name]
        k = int(group.max()) + 1
        share = np.bincount(group, minlength=k) / 100.0
        counts = np.zeros((k, k))
        feat = np.ones((T, 100))
        for t in range(T):
            if t >= 1:
                counts[group[special[t - 1]], group[special[t]]] += 1.0
            row = counts[group[special[t]]]
            prob = (row + share * k) / (row.sum() + k)  # làm trơn về tỉ phần, nặng k
            feat[t] = prob[group] / share[group]
        out[f"markov_{name}"] = feat
    return out


def weekday_features(dates: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    """sin/cos thứ của kỳ đích t+1 (lịch quay biết trước, không phải kết cục).

    Hàng lịch sử lấy đúng ngày của kỳ quay KẾ TIẾP trong chuỗi — qua quãng nghỉ
    (Tết, 2020) đó không phải ngày lịch kế tiếp. Chỉ hàng cuối, khi kỳ đích chưa
    có trong dữ liệu, mới giả định quay vào ngày hôm sau.
    """
    day = pd.to_datetime(pd.Series(dates))
    nxt = day.shift(-1)
    nxt.iloc[-1] = day.iloc[-1] + pd.Timedelta(days=1)
    target = nxt.dt.weekday.to_numpy(dtype=np.float64)
    angle = 2.0 * np.pi * target / 7.0
    return np.sin(angle), np.cos(angle)


def build_features(history: History, mode: Mode, params: FeatureParams | None = None) -> FeatureTensor:
    """Dựng tensor đặc trưng (T, 100, F) cho ``mode``."""
    params = params or FeatureParams()
    T = len(history)
    hit = history.hits(mode)
    present = history.hits("loto")
    base = expanding_rate(hit)
    cols: dict[str, np.ndarray] = {}

    gaps = gap_matrix(hit)
    cols["log_gap"] = np.log1p(gaps)
    cols["gap_z"] = gap_zscore(hit, base, params.gap_prior_cycles)
    cols["streak"] = hit_streak(hit)
    cols["hit_today"] = hit.astype(np.float64)
    reverse = 10 * (NUMBERS % 10) + NUMBERS // 10
    ratio30 = None
    for h in params.half_lives:
        rate = decayed_sum(hit, h) / decayed_sum(np.ones(T), h)[:, None]
        ratio = rate / np.maximum(base, 1e-9)[:, None]
        cols[f"ewm{h}_ratio"] = ratio
        if h == 30:
            ratio30 = ratio
    if ratio30 is None:
        ratio30 = cols[f"ewm{params.half_lives[0]}_ratio"]
    cols["reverse_ewm30_ratio"] = ratio30[:, reverse]
    cols["reverse_hit_today"] = hit[:, reverse].astype(np.float64)

    if mode == "de":
        # Đặc Biệt còn đọc được tập LOTO của kỳ vừa quay.
        loto_rate = decayed_sum(present, 30) / decayed_sum(np.ones(T), 30)[:, None]
        cols["loto_ewm30_ratio"] = loto_rate / np.maximum(expanding_rate(present), 1e-9)[:, None]
        cols["loto_present_today"] = present.astype(np.float64)

    count, longest = bridge_features(history, mode, params.bridge_min_streak[mode])
    cols["bridge_count"] = count
    cols["bridge_longest"] = longest

    same, lagged, lagged_max = cooccurrence_features(present, hit)
    cols["pmi_same_day"] = same
    cols["pmi_lag1"] = lagged
    cols["pmi_lag1_max"] = lagged_max
    cols["community_heat"] = community_heat(present, ratio30, params.community_every, params.seed)

    if mode == "de":
        cols.update(special_group_features(history.special))
        cols.update(markov_features(history.special))

    sin, cos = weekday_features(history.dates)
    cols["target_weekday_sin"] = np.repeat(sin[:, None], 100, axis=1)
    cols["target_weekday_cos"] = np.repeat(cos[:, None], 100, axis=1)
    cols["is_double"] = np.repeat((NUMBERS // 10 == NUMBERS % 10)[None, :].astype(np.float64), T, axis=0)

    names = tuple(cols)
    X = np.stack([cols[n] for n in names], axis=2).astype(np.float32)
    return FeatureTensor(names, X)
