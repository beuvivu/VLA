"""Bảng chẩn đoán lớn: bảng đầy đủ ra khỏi git, git giữ một bản cắt (07 → 11-11-2026).

Các bảng dưới đây đổi gần như mọi số mỗi kỳ, nên git không lấy được delta. Chúng là nguồn tăng lớn nhất
của kho sau đợt dọn 04-11-2026 (`documentation/plans/2026-11-05-dung-luong-kho.md`). Mỗi lượt pipeline vẫn
tính bảng đầy đủ và ghi ra đĩa; `update-data.yml` tải nó lên artifact `research-full-tables-*`. Git chỉ theo
dõi bản cắt.

`FULL_TABLE_CUTS` là nguồn DUY NHẤT của danh sách ấy. Ba nơi phải khớp với nó, và
`tests/research/test_research_table_cuts.py` buộc cả ba:
- `.gitignore` bỏ qua bảng đầy đủ, không bỏ qua bản cắt;
- bước lưu artifact của `update-data.yml` tải đủ mọi bảng đầy đủ;
- mỗi trình ghi ghi đúng cặp tệp đã khai.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: Bảng đầy đủ (không vào git) → bản cắt (git theo dõi). Đường dẫn tính từ `data/`.
FULL_TABLE_CUTS: dict[str, str] = {
    "research/crosslag_positional/crosslag_rules.csv":
        "research/crosslag_positional/crosslag_rules_top.csv",
    "stats/conditional/loto_nextday_given_special_long.csv":
        "stats/conditional/current_special_next_loto.csv",
    "research/research_firewall_loto.csv": "research/research_firewall_loto_top.csv",
    "research/research_firewall_de.csv": "research/research_firewall_de_top.csv",
    "research/path_timelines/path_timeline_loto.csv":
        "research/path_timelines/path_timeline_loto_top.csv",
    "research/path_timelines/path_timeline_de.csv":
        "research/path_timelines/path_timeline_de_top.csv",
    "research/legacy_extensions/pair_recency_loto.csv":
        "research/legacy_extensions/pair_recency_loto_top.csv",
}


def cut_ranked(
    table: pd.DataFrame,
    *,
    rows: int,
    keep: str | None = None,
    smallest: str | None = None,
) -> pd.DataFrame:
    """Bản cắt của một bảng ĐÃ xếp theo thứ tự đọc; giữ nguyên thứ tự ấy.

    Bản cắt gồm:
    - `rows` dòng đầu của bảng;
    - mọi dòng có cột `keep` đúng (ví dụ quy tắc qua cổng), dù nhiều tới đâu;
    - `rows` dòng có cột `smallest` nhỏ nhất (ví dụ p huấn luyện), dù chúng nằm sâu trong bảng.

    Hàm không tự xếp lại bảng: thứ tự đọc là của trình ghi, và bản cắt phải là một phần của đúng bảng ấy.
    """
    if table.empty:
        return table.copy()
    ordered = table.reset_index(drop=True)
    mask = np.zeros(len(ordered), dtype=bool)
    mask[:rows] = True
    if keep is not None:
        mask |= ordered[keep].astype(bool).to_numpy()
    if smallest is not None:
        values = pd.to_numeric(ordered[smallest], errors="coerce")
        mask[values.sort_values(kind="stable").index[:rows]] = True
    return ordered[mask].reset_index(drop=True)
