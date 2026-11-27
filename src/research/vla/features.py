from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import networkx as nx
import numpy as np
import pandas as pd
from scipy.signal import lfilter

from core.xsmb_domain import FIELD_WIDTHS, PRIZE_FIELDS
from soi_cau.bridge_rules import BO_ID, step_matrix
from soi_cau.position_bridges import load_draws, pair_index, run_lengths

Mode = Literal["loto", "de"]
NUMBERS = np.arange(100)


@dataclass(frozen=True)
class History:

    dates: tuple[str, ...]
    digits: np.ndarray
    values: np.ndarray

    def __len__(self) -> int:
        return len(self.dates)

    @property
    def counts(self) -> np.ndarray:
        two = (self.values % 100).astype(np.int64)
        out = np.zeros((len(self), 100), dtype=np.int16)
        np.add.at(out, (np.arange(len(self))[:, None], two), 1)
        return out

    @property
    def special(self) -> np.ndarray:
        return (self.values[:, 0] % 100).astype(np.int64)

    def hits(self, mode: Mode) -> np.ndarray:
        if mode == "loto":
            return self.counts > 0
        out = np.zeros((len(self), 100), dtype=bool)
        out[np.arange(len(self)), self.special] = True
        return out

    def head(self, n: int) -> History:
        return History(self.dates[:n], self.digits[:n], self.values[:n])


def history_from_frame(raw: pd.DataFrame) -> History:
    dates, digits, values = load_draws(raw)
    return History(tuple(dates), digits, values)


def load_history(data_dir: Path) -> History:
    return history_from_frame(pd.read_csv(Path(data_dir) / "xsmb.csv"))


def targets(history: History, mode: Mode) -> np.ndarray:
    hit = history.hits(mode).astype(np.float32)
    out = np.full(hit.shape, np.nan, dtype=np.float32)
    out[:-1] = hit[1:]
    return out


@dataclass(frozen=True)
class FeatureParams:
    half_lives: tuple[int, ...] = (7, 30, 90, 180)
    bridge_min_streak: dict[str, int] = field(default_factory=lambda: {"loto": 3, "de": 1})
    community_every: int = 250
    gap_prior_cycles: float = 3.0
    seed: int = 7


@dataclass(frozen=True)
class FeatureTensor:
    names: tuple[str, ...]
    X: np.ndarray

    def column(self, name: str) -> np.ndarray:
        return self.X[:, :, self.names.index(name)]


def decayed_sum(x: np.ndarray, half_life: float) -> np.ndarray:
    if not np.isfinite(half_life):
        return np.cumsum(x, axis=0, dtype=np.float64)
    decay = float(2.0 ** (-1.0 / max(float(half_life), 1e-9)))
    return lfilter([1.0], [1.0, -decay], np.asarray(x, dtype=np.float64), axis=0)


def expanding_rate(hit: np.ndarray) -> np.ndarray:
    per_day = hit.mean(axis=1, dtype=np.float64)
    return np.cumsum(per_day) / np.arange(1, len(hit) + 1)


def gap_matrix(hit: np.ndarray) -> np.ndarray:
    n = len(hit)
    index = np.arange(n, dtype=np.int64)[:, None]
    last = np.maximum.accumulate(np.where(hit, index, -1), axis=0)
    return np.where(last >= 0, index - last, index + 1).astype(np.float64)


def gap_zscore(hit: np.ndarray, base_rate: np.ndarray, prior_cycles: float) -> np.ndarray:
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
    T = len(history)
    count = np.zeros((T, 100))
    longest = np.zeros((T, 100))
    if T < 2:
        return count, longest
    kind = "loto" if mode == "loto" else "dac-biet"
    steps = step_matrix(kind, history.digits, history.values, both=(mode == "de"))
    runs = run_lengths(steps)
    pa, pb = pair_index(True)
    for t in range(1, T):
        r = runs[t - 1].astype(np.float64)
        x = history.digits[t, pa].astype(np.int64)
        y = history.digits[t, pb].astype(np.int64)
        n1, n2 = 10 * x + y, 10 * y + x
        alive = r >= min_streak
        for nums, use in ((n1, np.ones(len(r), dtype=bool)), (n2, n1 != n2)):
            count[t] += np.bincount(nums[use & alive], minlength=100)
            np.maximum.at(longest[t], nums[use], r[use])
    return count, longest


PMI_PSEUDOCOUNT = 5.0


def _pmi(joint: np.ndarray, left: np.ndarray, right: np.ndarray, total: float,
         pseudo: float = PMI_PSEUDOCOUNT) -> np.ndarray:
    expected = np.outer(left, right) / max(float(total), 1.0)
    return np.log((joint + pseudo) / (expected + pseudo))


def cooccurrence_features(
    present: np.ndarray, target_hit: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
    T = len(present)
    out = np.ones((T, 100))
    labels = np.zeros(100, dtype=np.int64)
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
            prob = (row + share * k) / (row.sum() + k)
            feat[t] = prob[group] / share[group]
        out[f"markov_{name}"] = feat
    return out


def weekday_features(dates: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    day = pd.to_datetime(pd.Series(dates))
    nxt = day.shift(-1)
    nxt.iloc[-1] = day.iloc[-1] + pd.Timedelta(days=1)
    target = nxt.dt.day_of_week.to_numpy(dtype=np.float64)
    angle = 2.0 * np.pi * target / 7.0
    return np.sin(angle), np.cos(angle)


def build_features(history: History, mode: Mode, params: FeatureParams | None = None) -> FeatureTensor:
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


def synthetic_history(n: int, seed: int, *, loto_signal: float = 0.5, de_signal: float = 0.15) -> History:
    rng = np.random.default_rng(seed)
    values = np.column_stack([rng.integers(0, 10**w, size=n) for _, w in FIELD_WIDTHS])
    seven = PRIZE_FIELDS.index("prize7_1")
    for t in range(1, n):
        if 37 in set((values[t - 1] % 100).tolist()) and rng.random() < loto_signal:
            values[t, seven] = 73
        if rng.random() < de_signal:
            values[t, 0] = values[t, 0] // 100 * 100 + (values[t - 1, 0] % 100 + 1) % 100
    raw = pd.DataFrame(values, columns=list(PRIZE_FIELDS))
    raw.insert(0, "date", pd.date_range("2010-01-01", periods=n, freq="D").strftime("%Y-%m-%d"))
    return history_from_frame(raw)


TUNING_SEED = 11
POWER_SEED = 31
POWER_SIGNALS = {"loto": {"loto_signal": 0.5, "de_signal": 0.0}, "de": {"loto_signal": 0.0, "de_signal": 0.15}}


def power_history(mode: str, n: int, seed: int) -> History:
    return synthetic_history(n, seed, **POWER_SIGNALS[mode])
