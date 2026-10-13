"""Cặp xiên 2 — hai con cùng về trong một kỳ XSMB — chọn bằng một luật chốt trước, có kiểm chứng.

Mức nền trước tiên. Một kỳ có 27 lô gần như đều trên 00–99. Hai con định trước cùng về (mỗi con
≥ 1 nháy) với xác suất

    P = 1 − 2 · 0,99²⁷ + 0,98²⁷ ≈ 5,49 %.

Luật (chốt ngày 13-10-2026, TRƯỚC khi chạy kiểm chứng; đổi luật thì đăng ký ngày chốt mới):

1. Điểm của cặp (a, b) ở kỳ t = số kỳ trong ``WINDOW`` kỳ ngay trước t mà cả a lẫn b cùng về.
2. Hoà điểm thì cặp cùng về GẦN đây hơn đứng trước; còn hoà nữa thì phá bằng một hoán vị cố định
   theo kỳ (``tie_keys``), không thiên về cặp số nhỏ.
3. Lấy ``TOP_K`` cặp theo thứ tự ấy, mỗi con nằm trong tối đa ``MAX_PER_NUMBER`` cặp: năm cặp cùng
   chứa một con gần như là MỘT lần đặt.

Kiểm chứng walk-forward trên mọi kỳ: điểm của kỳ t chỉ đọc các kỳ trước t. Mốc so là chọn bừa
cùng số cặp trong CÙNG kỳ: kỳ t có dₜ con khác nhau về thì Mₜ = C(dₜ, 2) trong 4 950 cặp cùng về,
nên một cặp bất kỳ (chọn trước kỳ quay) trúng với xác suất Mₜ / 4 950. Các cặp chung một con thì
trúng/trượt cùng nhau, nên sai số lấy từ hiệu từng kỳ chứ không giả định các cặp độc lập.
"""

from __future__ import annotations

import numpy as np

N_NUMBERS = 100
N_PAIRS = N_NUMBERS * (N_NUMBERS - 1) // 2
WINDOW = 100
TOP_K = 5
MAX_PER_NUMBER = 2
TIE_SEED = 20261013
#: Luật được thiết kế với lịch sử đến ngày này; chỉ các kỳ SAU ngày này là tiến cứu.
FROZEN_AT = "2026-10-12"

#: Hai con của cặp thứ i: ``PAIR_A[i] < PAIR_B[i]``.
PAIR_A, PAIR_B = np.triu_indices(N_NUMBERS, k=1)


def base_rate(per_draw: int = 27) -> float:
    """P(hai con định trước cùng về) khi 27 lô đều và độc lập trên 00–99."""
    return float(1 - 2 * 0.99 ** per_draw + 0.98 ** per_draw)


def tie_keys(t: int) -> np.ndarray:
    """Hoán vị 4 950 cặp cố định theo kỳ t: phá hoà không thiên về cặp số nhỏ."""
    return np.random.default_rng([TIE_SEED, t]).permutation(N_PAIRS)


def pick_pairs(together: np.ndarray, last: np.ndarray, t: int, k: int = TOP_K,
               max_per_number: int = MAX_PER_NUMBER) -> list[int]:
    """Chỉ số ``k`` cặp theo luật: điểm giảm dần, rồi lần cùng về gần nhất, rồi khoá phá hoà."""
    order = np.lexsort((tie_keys(t), -last, -together))
    used = np.zeros(N_NUMBERS, dtype=int)
    chosen: list[int] = []
    for i in order:
        a, b = PAIR_A[i], PAIR_B[i]
        if used[a] >= max_per_number or used[b] >= max_per_number:
            continue
        chosen.append(int(i))
        used[a] += 1
        used[b] += 1
        if len(chosen) == k:
            break
    return chosen


def walk_forward(present: np.ndarray, window: int = WINDOW, k: int = TOP_K,
                 max_per_number: int = MAX_PER_NUMBER) -> dict:
    """Chạy luật trên mọi kỳ t ∈ [window, T] (t = T là kỳ kế tiếp, chưa quay).

    ``present`` là ma trận (T, 100) đúng/sai: con j về ít nhất một nháy ở kỳ t. Trả về:

    * ``rows``: các kỳ đã chấm (window … T − 1);
    * ``picks``: (len(rows) + 1, k) chỉ số cặp, hàng cuối là cho kỳ kế tiếp;
    * ``hits``: số cặp trúng của từng kỳ đã chấm;
    * ``expected``: kỳ vọng của chọn bừa k cặp trong CÙNG kỳ, k·C(dₜ, 2)/4 950;
    * ``together`` / ``last``: điểm và lần cùng về gần nhất (chỉ số kỳ, −1 nếu chưa) của các cặp
      đã chọn cho kỳ kế tiếp.
    """
    present = np.asarray(present, dtype=bool)
    total = len(present)
    if total < window:
        raise ValueError(f"cần ít nhất {window} kỳ, có {total}")
    as_int = present.astype(np.int32)
    co = np.zeros((N_NUMBERS, N_NUMBERS), dtype=np.int32)
    last = np.full((N_NUMBERS, N_NUMBERS), -1, dtype=np.int64)
    for s in range(window):
        both = np.outer(as_int[s], as_int[s])
        co += both
        last[both.astype(bool)] = s
    picks, hits, expected = [], [], []
    for t in range(window, total + 1):
        together, recency = co[PAIR_A, PAIR_B], last[PAIR_A, PAIR_B]
        chosen = pick_pairs(together, recency, t, k, max_per_number)
        picks.append(chosen)
        if t == total:
            break
        row = present[t]
        hits.append(int((row[PAIR_A[chosen]] & row[PAIR_B[chosen]]).sum()))
        d = int(row.sum())
        expected.append(k * d * (d - 1) / 2 / N_PAIRS)
        # Trượt cửa sổ: thêm kỳ t, bỏ kỳ t − window. Lần cùng về gần nhất thì không bỏ.
        both = np.outer(as_int[t], as_int[t])
        co += both
        last[both.astype(bool)] = t
        co -= np.outer(as_int[t - window], as_int[t - window])
    final = picks[-1]
    return {
        "rows": list(range(window, total)),
        "picks": np.asarray(picks, dtype=int),
        "hits": np.asarray(hits, dtype=int),
        "expected": np.asarray(expected, dtype=float),
        "together": [int(co[PAIR_A[i], PAIR_B[i]]) for i in final],
        "last": [int(last[PAIR_A[i], PAIR_B[i]]) for i in final],
    }


def pair_label(i: int) -> list[str]:
    return [f"{int(PAIR_A[i]):02d}", f"{int(PAIR_B[i]):02d}"]


def planted_present(n_draws: int, pair: tuple[int, int], rate: float, seed: int = 2026) -> np.ndarray:
    """Lịch sử giả định: 27 lô đều, và cặp ``pair`` được cài cùng về thêm với xác suất ``rate``.

    Dùng để kiểm luật có BẮT được một cặp thật sự hay đi cùng nhau hay không.
    """
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, N_NUMBERS, size=(n_draws, 27))
    present = np.zeros((n_draws, N_NUMBERS), dtype=bool)
    present[np.arange(n_draws)[:, None], draws] = True
    planted = rng.random(n_draws) < rate
    present[planted, pair[0]] = True
    present[planted, pair[1]] = True
    return present
