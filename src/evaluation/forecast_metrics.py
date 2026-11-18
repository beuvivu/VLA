"""Thước đo dự báo dùng chung cho mọi sản phẩm: xếp hạng (Top-K, MRR), hiệu chỉnh (ECE), bất định theo KỲ.

Trước module này mỗi nơi chấm tự đếm Top-K theo cách riêng (`research.vla.backtest.top_k` xếp hoà
"số nhỏ trước"), và không nơi nào của `src/` tính ECE hay hạng nghịch đảo. Ba luật giữ cho các
thước dưới đây không tự sinh ra "kỹ năng":

1. **Hoà điểm chia đều.** Tổ hợp XSMB gần như phẳng (thành phần ML có trust = 0 thì mọi con bằng
   nền), nên hoà điểm là trường hợp THƯỜNG GẶP chứ không phải biên. Xếp hoà theo số nhỏ trước
   biến thứ tự 00…99 thành một "mô hình". Ở đây một vector phẳng ra ĐÚNG mức ngẫu nhiên ở mọi
   thước: mỗi thước là kỳ vọng dưới phép xếp ngẫu nhiên đều các phần tử hoà, tính bằng công thức.
2. **Đơn vị độc lập là KỲ QUAY.** 100 con số của một kỳ dùng chung các giải của kỳ ấy nên không
   độc lập; khoảng tin cậy và phép hoán vị lấy mẫu theo kỳ (hoặc theo cụm kỳ được khai).
3. **Mức ngẫu nhiên là công thức chính xác** của kỳ quay công bằng, không ước lượng từ dữ liệu.

Mọi phép lấy mẫu có hạt giống: cùng đầu vào thì cùng đầu ra trên mọi máy.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

#: Số chữ số thập phân khi so hoà. Xác suất công bố cỡ 0,01–0,24; lệch dưới 10⁻¹² là nhiễu dấu
#: phẩy động giữa các CPU, không phải thứ hạng.
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
    """Kỳ vọng tổng ``weights`` của ``k`` phần tử điểm cao nhất mỗi hàng, hoà chia đều.

    ``weights`` là chỉ báo trúng (0/1) thì kết quả là số lần trúng kỳ vọng trong Top-K; là số nháy
    thì là số nháy kỳ vọng. Khối hoà vắt qua ranh giới K đóng góp theo tỉ lệ số chỗ còn lại.
    """
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
    """Hạng kỳ vọng và hạng nghịch đảo kỳ vọng của phần tử đúng (một phần tử đúng mỗi hàng).

    Với ``a`` phần tử điểm cao hơn hẳn và khối hoà ``t`` phần tử (kể cả phần tử đúng): hạng đều
    trên ``a+1 … a+t``, nên hạng kỳ vọng là ``a + (t+1)/2`` và hạng nghịch đảo kỳ vọng là
    ``(H[a+t] − H[a]) / t`` với ``H`` là số điều hoà.
    """
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
    """AUC từng kỳ: xác suất một con ĐÃ VỀ được xếp trên một con KHÔNG về; hoà tính nửa.

    Thước xếp hạng của TOÀN vector (không chỉ Top-K): 0,5 là mức ngẫu nhiên chính xác, kể cả với
    vector phẳng. Tính bằng hạng trung bình (thống kê U của Mann–Whitney). Kỳ không có con nào về,
    hoặc mọi con đều về, không xác định và trả ``NaN``.
    """
    s = _matrix(scores)
    y = np.asarray(hits).astype(bool)
    if y.shape != s.shape:
        raise ValueError("hits phải cùng hình dạng với scores")
    order = np.argsort(s, axis=1, kind="stable")
    ordered = np.take_along_axis(s, order, axis=1)
    ranks = np.empty_like(s)
    for row in range(len(s)):
        # Hạng trung bình của từng khối hoà: (vị trí đầu + vị trí cuối) / 2, đếm từ 1.
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
    """p hai phía khi XÁO NHÃN trong từng kỳ (giữ nguyên số con về của kỳ ấy).

    Null: "điểm số không liên quan tới con nào về". Xáo trong từng kỳ giữ đúng cấu trúc của kỳ (số
    con khác nhau đã về), nên đây là phép kiểm chính xác có điều kiện, không cần giả định phân phối.
    ``statistic(scores, hits)`` trả một số; tâm của phân phối null lấy từ chính các lần xáo.
    """
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
    """Hạng nghịch đảo kỳ vọng khi xếp ngẫu nhiên ``size`` phần tử: ``H_size / size``."""
    if size < 1:
        raise ValueError("size phải ≥ 1")
    return float(_harmonic(size)[-1] / size)


def chance_presence(slots: int, size: int = 100, picks: int = 1) -> float:
    """P(ít nhất một trong ``picks`` số CHỈ ĐỊNH TRƯỚC có mặt) khi rút ``slots`` giải đều, có hoàn lại.

    ``picks = 1`` là tỉ lệ nền của một con (XSMB 27 giải: 1 − 0,99²⁷; đài miền Trung/Nam 18 giải:
    1 − 0,99¹⁸). ``picks = k`` là mức "Top-K có ít nhất một con về": ``1 − (1 − k/size)^slots``.
    """
    if slots < 0 or size < 1 or not 0 <= picks <= size:
        raise ValueError("slots ≥ 0, size ≥ 1 và 0 ≤ picks ≤ size")
    return float(1.0 - (1.0 - picks / size) ** slots)


def calibration_error(rows: Sequence[dict]) -> dict:
    """ECE và MCE từ bảng hiệu chỉnh đã chia nhóm (mỗi dòng: ``count``, ``predicted``, ``observed``).

    ``ECE = Σ_b (n_b / N)·|p̄_b − ȳ_b|``, ``MCE = max_b |p̄_b − ȳ_b|``. Nhận CHÍNH các nhóm của biểu
    đồ hiệu chỉnh (`model_quality.calibration`) để hai phần của một báo cáo nói về cùng một cách
    chia. ECE luôn ≥ 0 kể cả khi dự báo hiệu chỉnh hoàn hảo (dao động mẫu của từng nhóm), nên phải
    đọc cạnh ECE của dự báo hằng số trên cùng dữ liệu, không đọc riêng.
    """
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
    """Khoảng tin cậy phân vị của ``statistic`` khi lấy mẫu lại theo KỲ (hoặc theo cụm).

    ``values`` có một hàng mỗi kỳ (vector hay ma trận). ``statistic`` nhận các hàng đã lấy mẫu lại
    và trả một số; mặc định là trung bình. Thống kê dạng tỉ số (kỹ năng ``1 − LL/LL_mốc``) phải
    truyền cả hai cột và tính tỉ số BÊN TRONG ``statistic``, không lấy trung bình của tỉ số từng kỳ.
    """
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
        # Trung bình: chỉ cần tổng và số phần tử của từng cụm, không phải dựng lại từng mẫu.
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
    """p hai phía của phép hoán vị đổi dấu cho hiệu từng kỳ (mô hình − mốc).

    Dưới giả thuyết "mô hình không khác mốc", hiệu của một kỳ đối xứng quanh 0, nên đổi dấu ngẫu
    nhiên từng kỳ (cả cụm cùng đổi) cho phân phối null của trung bình. ``+1`` ở tử và mẫu: p không
    bao giờ bằng 0 — một p bằng 0 khẳng định mạnh hơn số lần hoán vị cho phép.
    """
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
    # Theo lô để bộ nhớ không phụ thuộc số lần hoán vị.
    for start in range(0, n_perm, 1000):
        size = min(1000, n_perm - start)
        signs = rng.integers(0, 2, size=(size, groups)) * 2 - 1
        extreme += int((np.abs(signs @ sums) >= observed * (1.0 - 1e-12)).sum())
    return float((extreme + 1) / (n_perm + 1))


def by_period(dates: Sequence[str], values: np.ndarray, *, period: str = "month") -> list[dict]:
    """Trung bình theo tháng (``YYYY-MM``) hoặc tuần ISO (``YYYY-Www``) của một chuỗi theo kỳ.

    Mỗi dòng kèm số kỳ và sai số chuẩn: một tháng "tốt" 30 kỳ phải đọc cạnh độ rộng nhiễu của nó.
    Thứ tự dòng theo thời gian.
    """
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
