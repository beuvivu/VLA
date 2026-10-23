"""Chọn top LOTO có giới hạn số con cùng đuôi.

Vì sao cần
----------
Ngày 28-09-2026 cả 10 con LOTO công bố đều đuôi 4. Thí nghiệm đối chứng cho
thấy nguyên nhân là đặc trưng ``tail_freq_7d`` của mô hình cầu kèo: mười con
cùng đuôi nhận CÙNG một giá trị, nên chúng lên top cùng nhau
(``documentation/research/2026-09-28-duoi-4-va-gia-thuyet-duoi-nong.md``).

Mười con như thế gần như là MỘT lần đặt: kỳ nào đuôi ấy trượt thì cả nhóm
trượt. Hàm này giữ nguyên xác suất và thứ tự của mô hình, chỉ bỏ qua con thứ
``max_per_tail + 1`` trở đi của một đuôi khi chọn danh sách hiển thị. Không
phép tính xác suất nào đổi — chỉ đổi cách lấy k con từ vector đã có.
"""

from __future__ import annotations

import numpy as np

#: Số con tối đa cùng một đuôi trong một danh sách top LOTO.
MAX_PER_TAIL = 3


def diversified_order(
    probabilities: np.ndarray, k: int, *, max_per_tail: int = MAX_PER_TAIL
) -> list[int]:
    """Chỉ số của ``k`` con xác suất cao nhất, không quá ``max_per_tail`` con/đuôi.

    Duyệt theo xác suất giảm dần (hoà thì số nhỏ trước — cùng quy ước với
    ``build_picks``). Nếu giới hạn làm thiếu con (chỉ xảy ra khi
    ``k > 10 · max_per_tail``), phần còn thiếu lấy tiếp theo thứ tự xác suất.
    """
    probs = np.asarray(probabilities, dtype=float)
    if max_per_tail < 1:
        raise ValueError("max_per_tail phải ≥ 1")
    order = np.lexsort((np.arange(len(probs)), -probs))
    chosen: list[int] = []
    per_tail = [0] * 10
    for n in order:
        if len(chosen) == k:
            return chosen
        tail = int(n) % 10
        if per_tail[tail] < max_per_tail:
            chosen.append(int(n))
            per_tail[tail] += 1
    for n in order:
        if len(chosen) == k:
            break
        if int(n) not in chosen:
            chosen.append(int(n))
    return chosen
