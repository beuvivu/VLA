"""Phần TRANG cần của bảng có điều kiện: cột in ra, ngưỡng FDR và câu đọc bảng.

Tách khỏi ``conditional_matrices`` vì trình dựng trang chỉ đọc CSV đã ghi: import mô-đun dựng
bảng sẽ kéo theo ``ingest.lottery`` (bs4, requests, openpyxl…) và scipy, nên workflow chỉ dựng
trang (``dashboard-refresh.yml``) phải cài cả bộ ấy. Ở đây chỉ cần pandas.
"""

from __future__ import annotations

import pandas as pd

#: Cột trang in: tỉ lệ thô LUÔN đứng cạnh mức nền, ước lượng sau co và q — tỉ lệ thô ở đầu một
#: bảng 100 × 100 ô là ô may mắn nhất, không phải xác suất kỳ sau.
DISPLAY_COLUMNS = ("count", "base_count", "conditional_rate", "baseline_rate", "posterior_rate", "q_value_fdr")

#: Ngưỡng FDR mà câu đọc bảng dùng để nói một ô "khác mức nền".
FDR_LEVEL = 0.05


def reading_note(table: pd.DataFrame) -> str:
    """Câu đọc bảng cho trang, suy TỪ q của chính bảng — không viết cứng kết luận.

    q của BH không giảm theo p và bảng xếp theo p tăng dần, nên mọi ô đạt ngưỡng đều nằm
    trong ``top`` dòng đã ghi (khi số ô đạt ngưỡng không vượt ``top``).
    """
    if table is None or table.empty or "q_value_fdr" not in table.columns:
        return "Chưa có số đo mức nền cho bảng này."
    q = pd.to_numeric(table["q_value_fdr"], errors="coerce")
    passed = int((q < FDR_LEVEL).sum())
    order = "Xếp theo p tăng dần: ô lệch khỏi mức nền mạnh nhất lên đầu."
    if passed == 0:
        q_min = f"{q.min():.2f}".replace(".", ",")
        return (f"{order} Không ô nào khác mức nền sau hiệu chỉnh đa kiểm trên 100 × 100 ô (q nhỏ nhất "
                f"{q_min}): tỉ lệ thô ở đầu bảng là ô may mắn nhất trong cả bảng, ước lượng sau co ≈ mức nền.")
    level = f"{FDR_LEVEL:.2f}".replace(".", ",")
    return f"{order} {passed} ô khác mức nền sau hiệu chỉnh đa kiểm (q < {level}); các ô còn lại ngang mức nền."
