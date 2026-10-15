"""Lô rơi nhiều nháy: con VỪA VỀ có tỉ lệ về ≥ 2 nháy ở kỳ SAU cao nhất, ước lượng từ lịch sử.

Vì sao có luật này (15-10-2026)
-------------------------------
Chủ dự án: bảng năm con của trang «Lô VIP nhiều nháy» "toàn lựa chọn những con số khan và không có
khả năng về", trong khi cần "những con số tỉ lệ về ngày hôm sau trên 2 nháy cao". Đúng như vậy: bộ
lọc VIP (``multi_hit_vip``) chấm thành phần "dị thường Poisson" bằng phương sai/trung bình của số
nháy, và chỉ số ấy CAO NHẤT ở con về thưa nhưng dồn cục. Con 32 đứng đầu mười kỳ liền (06 → 15-10-2026)
khi đang gan 10 → 19 kỳ, chỉ vì hai lần về 2 nháy hơn hai mươi kỳ trước. Thêm vào đó, mỗi ngày bộ lọc
chọn lại trọng số trong 286 vector trên đúng 30 kỳ, nên trọng số đổi theo nhiễu.

Luật này trả lời thẳng câu hỏi "con nào hay về ≥ 2 nháy ở kỳ sau", bằng tỉ lệ ĐẾM ĐƯỢC:

1. Ứng viên là các con đã về ở kỳ mới nhất ("lô rơi"). Con không về thì không được chọn.
2. Nhóm của một con là số nháy của nó ở kỳ mới nhất: 0, 1 hay ≥ 2. Với mỗi nhóm, đếm trên MỌI cặp
   (kỳ τ, kỳ τ + 1) đã quay: bao nhiêu lần một con ở nhóm ấy về ≥ 2 nháy ở kỳ sau. Đo đến 15-10-2026:
   nhóm ≥ 2 nháy cho 3,11% (384/12 353), nhóm 1 nháy 2,90%, nhóm 0 nháy 2,92%.
3. Xu hướng riêng của từng con: tỉ lệ kỳ về ≥ 2 nháy của nó trên toàn lịch sử, CO về mức chung theo
   Bayes thực nghiệm. Độ co ước lượng bằng phương pháp mômen: phương sai giữa 100 con trừ phần
   phương sai mà riêng dao động nhị thức đã sinh ra. Khi chênh lệch giữa các con chỉ cỡ dao động
   ngẫu nhiên (lịch sử thật: tỉ số ≈ 0,98), mọi con co hẳn về mức chung, tức không con nào được
   coi là "hay về" chỉ vì may.
4. Xác suất kỳ sau = xu hướng riêng × hệ số nhóm, trong đó hệ số nhóm = số lần về ≥ 2 nháy QUAN SÁT
   ở nhóm / số lần KỲ VỌNG theo xu hướng riêng của chính các con trong nhóm. Nhân thẳng tỉ lệ thô
   của nhóm với xu hướng riêng là đếm hai lần: con có xu hướng cao cũng hay rơi vào nhóm ≥ 2 nháy
   (lịch sử cài tín hiệu: dự báo 19,0% so với 10,7% thực tế; cách chia kỳ vọng cho 10,8%).
5. Xếp ứng viên theo xác suất ấy; hoà thì theo một hoán vị cố định của kỳ (``tie_keys``), không
   thiên về con số nhỏ.

Mọi đại lượng ở kỳ t chỉ đọc các kỳ < t, nên chấm luật trên mọi kỳ đã quay là walk-forward thật;
xác suất in ra cạnh mỗi con và tỉ lệ trúng của chính luật được so trên cùng các kỳ ấy.

Đây vẫn là KHUNG THÁCH ĐẤU, không vào tổ hợp xác suất của pipeline: walk-forward 4 206 kỳ cho 3,04%
so với 2,92% của chọn bừa cùng kỳ (z = +1,09), không có ý nghĩa thống kê. Luật được thiết kế sau khi
đã xem lịch sử đến ``FROZEN_AT``; mức tin chỉ tính trên các kỳ quay sau ngày ấy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from multi_hit_vip import N_NUMBERS, base_rate, tie_keys

#: Tên luật ghi vào tệp đo; đổi định nghĩa thì đổi tên và đăng ký ngày chốt mới.
RULE = "lo-roi-ti-le-hom-sau-v1"
#: Luật được thiết kế SAU khi đã xem lịch sử đến ngày này. Đừng dời ngày; đổi luật thì đăng ký ngày mới.
FROZEN_AT = "2026-10-15"
TOP_K = 5
#: Số kỳ đầu không chấm: trước đó tỉ lệ nhóm còn quá ít cặp kỳ để đọc.
WARMUP = 30
#: Tiên nghiệm của hệ số nhóm, tính bằng số LẦN về ≥ 2 nháy giả định đúng như kỳ vọng (hệ số 1).
STATE_PRIOR = 10.0
#: Nhóm theo số nháy ở kỳ mới nhất: 0, 1, ≥ 2.
STATES = (0, 1, 2)
STATE_LABELS = {0: "không về", 1: "về 1 nháy", 2: "về ≥ 2 nháy"}


@dataclass(frozen=True)
class Estimates:
    """Ước lượng cho mọi kỳ t = 0..T (hàng T là kỳ chưa quay); hàng t chỉ đọc các kỳ < t."""

    prob: np.ndarray        # (T+1, 100) P(con i về ≥ 2 nháy ở kỳ t)
    state: np.ndarray       # (T+1, 100) nhóm của con i theo kỳ t − 1 (hàng 0: −1)
    propensity: np.ndarray  # (T+1, 100) xu hướng riêng đã co, chia cho mức chung (1 = như mọi con)
    own_multi: np.ndarray   # (T+1, 100) số kỳ < t con i về ≥ 2 nháy
    pooled: np.ndarray      # (T+1,) mức chung: tỉ lệ (con, kỳ) về ≥ 2 nháy trên các kỳ < t
    shrink: np.ndarray      # (T+1,) trọng số của xu hướng riêng (0 = co hẳn về mức chung)
    seen: np.ndarray        # (T+1, 3) số cặp (con, kỳ τ) ở từng nhóm, với τ + 1 < t
    observed: np.ndarray    # (T+1, 3) trong số ấy, số lần về ≥ 2 nháy ở kỳ τ + 1
    expected: np.ndarray    # (T+1, 3) số lần kỳ vọng theo xu hướng riêng ước lượng tại kỳ τ + 1
    factor: np.ndarray      # (T+1, 3) hệ số nhóm (observed + tiên nghiệm) / (expected + tiên nghiệm)


def estimate(counts: np.ndarray, prior: float = STATE_PRIOR) -> Estimates:
    """Ước lượng walk-forward từ ma trận số nháy ``counts`` (kỳ × 100)."""
    counts = np.asarray(counts)
    n_draws = len(counts)
    p0 = base_rate()
    state_of = np.minimum(counts, 2)
    multi = (counts >= 2).astype(float)
    rows = n_draws + 1
    prob = np.full((rows, N_NUMBERS), p0)
    state = np.full((rows, N_NUMBERS), -1, dtype=int)
    propensity = np.ones((rows, N_NUMBERS))
    own_multi = np.zeros((rows, N_NUMBERS))
    pooled = np.full(rows, p0)
    shrink = np.zeros(rows)
    seen = np.zeros((rows, len(STATES)))
    observed = np.zeros((rows, len(STATES)))
    expected = np.zeros((rows, len(STATES)))
    factor = np.ones((rows, len(STATES)))
    own_prob = np.full((rows, N_NUMBERS), p0)   # xu hướng riêng ước lượng TẠI kỳ t (chưa nhân nhóm)
    s_seen = np.zeros(len(STATES))
    s_obs = np.zeros(len(STATES))
    s_exp = np.zeros(len(STATES))
    m = np.zeros(N_NUMBERS)
    for t in range(1, rows):
        if t >= 2:
            # Cặp (t − 2, t − 1) vừa đủ điều kiện: nhóm ở kỳ t − 2, kết quả ở kỳ t − 1, và kỳ vọng là
            # xu hướng riêng đã ước lượng cho kỳ t − 1 (chỉ từ các kỳ < t − 1).
            for s in STATES:
                mask = state_of[t - 2] == s
                s_seen[s] += mask.sum()
                s_obs[s] += multi[t - 1][mask].sum()
                s_exp[s] += own_prob[t - 1][mask].sum()
        m += multi[t - 1]
        mean = m.sum() / (N_NUMBERS * t)
        if mean > 0:
            noise = mean * (1 - mean) / t
            between = max(float((m / t).var()) - noise, 0.0)
            w = between / (between + noise)
            own_prob[t] = w * m / t + (1 - w) * mean
            propensity[t] = own_prob[t] / mean
            pooled[t], shrink[t] = mean, w
        f = (s_obs + prior) / (s_exp + prior)
        state[t] = state_of[t - 1]
        prob[t] = np.clip(own_prob[t] * f[state[t]], 0.0, 1.0)
        own_multi[t] = m
        seen[t], observed[t], expected[t], factor[t] = s_seen, s_obs, s_exp, f
    return Estimates(prob, state, propensity, own_multi, pooled, shrink, seen, observed, expected, factor)


def order(counts: np.ndarray, est: Estimates, t: int) -> np.ndarray:
    """Thứ hạng 100 con cho kỳ t: con đã về ở kỳ t − 1 trước, rồi xác suất giảm dần, hoà theo ``tie_keys``."""
    came = np.asarray(counts)[t - 1] >= 1
    return np.lexsort((tie_keys(t), -est.prob[t], ~came))


@dataclass(frozen=True)
class WalkForward:
    rows: np.ndarray        # các kỳ được chấm
    picks: np.ndarray       # (n, k) các con đã chọn TRƯỚC kỳ quay
    hits: np.ndarray        # (n,) số con trong top-k về ≥ 2 nháy
    predicted: np.ndarray   # (n, k) xác suất đã in cho các con ấy


def walk_forward(counts: np.ndarray, est: Estimates, k: int = TOP_K, warmup: int = WARMUP) -> WalkForward:
    """Chấm luật trên mọi kỳ từ ``warmup`` tới kỳ cuối đã quay."""
    counts = np.asarray(counts)
    rows = np.arange(min(warmup, len(counts)), len(counts))
    picks = np.array([order(counts, est, t)[:k] for t in rows], dtype=int).reshape(len(rows), k)
    hits = (np.take_along_axis(counts[rows], picks, axis=1) >= 2).sum(axis=1) if len(rows) else np.zeros(0)
    predicted = np.take_along_axis(est.prob[rows], picks, axis=1) if len(rows) else np.zeros((0, k))
    return WalkForward(rows, picks, np.asarray(hits, dtype=int), predicted)
