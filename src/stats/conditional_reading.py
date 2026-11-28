from __future__ import annotations

import pandas as pd

DISPLAY_COLUMNS = ("count", "base_count", "conditional_rate", "baseline_rate", "posterior_rate", "q_value_fdr")

FDR_LEVEL = 0.05


def reading_note(table: pd.DataFrame) -> str:
    if table is None or table.empty or "q_value_fdr" not in table.columns:
        return "Chưa có số đo mức nền cho bảng này."
    q = pd.to_numeric(table["q_value_fdr"], errors="coerce")
    passed = int((q < FDR_LEVEL).sum())
    order = "Xếp theo p tăng dần: ô lệch khỏi mức nền mạnh nhất lên đầu."
    level = f"{FDR_LEVEL:.2f}".replace(".", ",")
    if passed == 0:
        q_min = f"{q.min():.2f}".replace(".", ",")
        return (f"{order} Không ô nào lệch khỏi mức nền có ý nghĩa sau hiệu chỉnh đa kiểm trên 100 × 100 ô "
                f"(q nhỏ nhất {q_min}): tỉ lệ thô ở đầu bảng là ô may mắn nhất trong cả bảng, ước lượng sau co "
                "≈ mức nền.")
    count = f"ít nhất {passed}" if passed >= len(q) else str(passed)
    return (f"{order} {count} ô lệch khỏi mức nền có ý nghĩa sau hiệu chỉnh đa kiểm (q < {level}); "
            "các ô còn lại chưa có bằng chứng lệch.")
