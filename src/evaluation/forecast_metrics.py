from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

TIE_DECIMALS = 12
DEFAULT_BOOTSTRAP = 2000
DEFAULT_PERMUTATIONS = 10000
DEFAULT_SEED = 20261116


def _matrix(scores: np.ndarray) -> np.ndarray:
    out = np.asarray(scores, dtype=float)
    if out.ndim != 2 or out.shape[1] == 0:
        raise ValueError("scores phải là ma trận (kỳ, số) không rỗng")
    if not np.isfinite(out).all():
        raise ValueError("scores phải hữu hạn")
    return np.round(out, TIE_DECIMALS)


def top_k_mass(scores: np.ndarray, weights: np.ndarray, k: int) -> np.ndarray:
    s = _matrix(scores)
    w = np.asarray(weights, dtype=float)
    if w.shape != s.shape:
        raise ValueError("weights phải cùng hình dạng với scores")
    if not 1 <= k <= s.shape[1]:
        raise ValueError("k phải nằm trong 1..số phần tử")
    threshold = np.sort(s, axis=1)[:, ::-1][:, k - 1 : k]
    above = s > threshold
    tied = s == threshold
    room = k - above.sum(axis=1)
    return (w * above).sum(axis=1) + room / tied.sum(axis=1) * (w * tied).sum(axis=1)


def _harmonic(n: int) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(1.0 / np.arange(1, n + 1))])


def rank_of_truth(scores: np.ndarray, truth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    s = _matrix(scores)
    index = np.asarray(truth, dtype=np.int64)
    if index.shape != (len(s),) or (index < 0).any() or (index >= s.shape[1]).any():
        raise ValueError("truth phải là một chỉ số hợp lệ cho mỗi hàng")
    own = s[np.arange(len(s)), index][:, None]
    above = (s > own).sum(axis=1)
    tied = (s == own).sum(axis=1)
    harmonic = _harmonic(s.shape[1])
    return above + (tied + 1) / 2.0, (harmonic[above + tied] - harmonic[above]) / tied


def auc_by_draw(scores: np.ndarray, hits: np.ndarray) -> np.ndarray:
    s = _matrix(scores)
    y = np.asarray(hits).astype(bool)
    if y.shape != s.shape:
        raise ValueError("hits phải cùng hình dạng với scores")
    order = np.argsort(s, axis=1, kind="stable")
    ordered = np.take_along_axis(s, order, axis=1)
    ranks = np.empty_like(s)
    for row in range(len(s)):
        _, first, counts = np.unique(ordered[row], return_index=True, return_counts=True)
        ranks[row, order[row]] = np.repeat(first + (counts + 1) / 2.0, counts)
    positives = y.sum(axis=1)
    negatives = y.shape[1] - positives
    u = (ranks * y).sum(axis=1) - positives * (positives + 1) / 2.0
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((positives > 0) & (negatives > 0), u / (positives * negatives), np.nan)


def within_draw_permutation_p(
    scores: np.ndarray,
    hits: np.ndarray,
    statistic: Callable[[np.ndarray, np.ndarray], float],
    *,
    n_perm: int = 2000,
    seed: int = DEFAULT_SEED,
) -> float:
    s = _matrix(scores)
    y = np.asarray(hits).astype(bool)
    if y.shape != s.shape:
        raise ValueError("hits phải cùng hình dạng với scores")
    observed = float(statistic(s, y))
    rng = np.random.default_rng(seed)
    null = np.array([float(statistic(s, rng.permuted(y, axis=1))) for _ in range(n_perm)])
    centre = float(null.mean())
    extreme = int((np.abs(null - centre) >= abs(observed - centre) * (1.0 - 1e-12)).sum())
    return float((extreme + 1) / (n_perm + 1))


def chance_reciprocal_rank(size: int) -> float:
    if size < 1:
        raise ValueError("size phải ≥ 1")
    return float(_harmonic(size)[-1] / size)


def chance_presence(slots: int, size: int = 100, picks: int = 1) -> float:
    if slots < 0 or size < 1 or not 0 <= picks <= size:
        raise ValueError("slots ≥ 0, size ≥ 1 và 0 ≤ picks ≤ size")
    return float(1.0 - (1.0 - picks / size) ** slots)


def calibration_error(rows: Sequence[dict]) -> dict:
    total = sum(int(row["count"]) for row in rows)
    if total <= 0:
        return {"ece": float("nan"), "mce": float("nan"), "bins": 0, "observations": 0}
    gaps = [abs(float(row["predicted"]) - float(row["observed"])) for row in rows]
    ece = sum(int(row["count"]) * gap for row, gap in zip(rows, gaps, strict=True)) / total
    return {"ece": float(ece), "mce": float(max(gaps)), "bins": len(rows), "observations": int(total)}


def _cluster_index(n: int, clusters: Sequence | np.ndarray | None) -> tuple[np.ndarray, int]:
    if clusters is None:
        return np.arange(n), n
    labels = np.asarray(clusters)
    if labels.shape != (n,):
        raise ValueError("clusters phải có một nhãn cho mỗi kỳ")
    _, inverse = np.unique(labels, return_inverse=True)
    return inverse, int(inverse.max()) + 1 if n else 0


def cluster_bootstrap_ci(
    values: np.ndarray,
    *,
    statistic: Callable[[np.ndarray], float] | None = None,
    clusters: Sequence | np.ndarray | None = None,
    n_boot: int = DEFAULT_BOOTSTRAP,
    level: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float]:
    data = np.asarray(values, dtype=float)
    n = len(data)
    if n < 2:
        return float("nan"), float("nan")
    if not 0.0 < level < 1.0:
        raise ValueError("level phải nằm trong (0, 1)")
    membership, groups = _cluster_index(n, clusters)
    if groups < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    if statistic is None and data.ndim == 1:
        sums = np.bincount(membership, weights=data, minlength=groups)
        sizes = np.bincount(membership, minlength=groups).astype(float)
        chosen = rng.integers(0, groups, size=(n_boot, groups))
        draws = sums[chosen].sum(axis=1) / sizes[chosen].sum(axis=1)
    else:
        compute = statistic or (lambda rows: float(np.mean(rows)))
        members = [np.flatnonzero(membership == g) for g in range(groups)]
        draws = np.empty(n_boot)
        for b in range(n_boot):
            chosen = rng.integers(0, groups, size=groups)
            draws[b] = compute(data[np.concatenate([members[g] for g in chosen])])
    tail = (1.0 - level) / 2.0
    low, high = np.quantile(draws, [tail, 1.0 - tail])
    return float(low), float(high)


def paired_sign_flip_p(
    differences: np.ndarray,
    *,
    clusters: Sequence | np.ndarray | None = None,
    n_perm: int = DEFAULT_PERMUTATIONS,
    seed: int = DEFAULT_SEED,
) -> float:
    d = np.asarray(differences, dtype=float).reshape(-1)
    n = len(d)
    if n < 2:
        return float("nan")
    membership, groups = _cluster_index(n, clusters)
    sums = np.bincount(membership, weights=d, minlength=groups)
    observed = abs(sums.sum())
    if observed == 0.0:
        return 1.0
    rng = np.random.default_rng(seed)
    extreme = 0
    for start in range(0, n_perm, 1000):
        size = min(1000, n_perm - start)
        signs = rng.integers(0, 2, size=(size, groups)) * 2 - 1
        extreme += int((np.abs(signs @ sums) >= observed * (1.0 - 1e-12)).sum())
    return float((extreme + 1) / (n_perm + 1))


def by_period(dates: Sequence[str], values: np.ndarray, *, period: str = "month") -> list[dict]:
    series = np.asarray(values, dtype=float).reshape(-1)
    if len(series) != len(dates):
        raise ValueError("dates và values phải cùng độ dài")
    if period not in {"month", "week"}:
        raise ValueError("period phải là 'month' hoặc 'week'")
    keys: list[str] = []
    for text in dates:
        day = np.datetime64(str(text), "D").astype(object)
        if period == "month":
            keys.append(f"{day.year:04d}-{day.month:02d}")
        else:
            iso = day.isocalendar()
            keys.append(f"{iso.year:04d}-W{iso.week:02d}")
    out = []
    for key in sorted(set(keys)):
        chosen = series[[k == key for k in keys]]
        spread = float(chosen.std(ddof=1) / np.sqrt(len(chosen))) if len(chosen) > 1 else float("nan")
        out.append({"period": key, "draws": int(len(chosen)), "mean": float(chosen.mean()), "stderr": spread})
    return out
