from __future__ import annotations

"""Dựng TOÀN BỘ site VLA — một lệnh, một thứ tự, một nguồn sự thật.

Thay cho mười một trình dựng rời của giao diện cũ, vốn mỗi cái tự khai điều
hướng và tự khai CSS. Hệ quả đo được ở bản cũ: bốn trang soi-path nằm lệch
khỏi phần còn lại vì không trình dựng nào chạy lại chúng.

Ở đây mọi trang đi qua cùng một khung, và một phép kiểm đối chiếu danh sách
trang dựng được với mô hình điều hướng — thiếu một trang là bộ kiểm đỏ, không
phải là một liên kết chết mà không ai thấy.
"""

import argparse
from pathlib import Path

from vla_design.assets import write_assets
from functools import partial

from vla_pages import loto, models, overview, results, special

#: Mọi trình dựng trang. Thêm trang mới là thêm vào đây.
BUILDERS = (
    overview.build_index,
    overview.build_dashboard,
    overview.build_statistics,
    overview.build_summary,
    results.build_live,
    results.build_traditional,
    loto.build_frequency,
    loto.build_pair_frequency,
    loto.build_big_pairs,
    loto.build_head_tail,
    loto.build_overdue,
    special.build_board,
    special.build_month_board,
    special.build_year_frequency,
    special.build_bridge,
    special.build_group_bridge,
    special.build_cycle,
    special.build_by_total,
    special.build_tomorrow,
    partial(models.build_ml_top10, mode="loto"),
    partial(models.build_ml_top10, mode="de"),
    models.build_model_quality,
    partial(models.build_path, mode="loto", kind="stable"),
    partial(models.build_path, mode="loto", kind="active"),
    partial(models.build_path, mode="de", kind="stable"),
    partial(models.build_path, mode="de", kind="active"),
    models.build_research,
    partial(models.build_landing, desktop=False),
    partial(models.build_landing, desktop=True),
)


def build_all(docs_dir: Path, data_dir: Path) -> list[Path]:
    """Ghi tài sản rồi dựng mọi trang; trả về danh sách tệp đã ghi."""
    write_assets(docs_dir)
    return [builder(docs_dir, data_dir) for builder in BUILDERS]


def main() -> None:
    ap = argparse.ArgumentParser(description="Dựng toàn bộ site VLA.")
    ap.add_argument("--docs-dir", default="docs")
    ap.add_argument("--data-dir", default="data")
    args = ap.parse_args()
    written = build_all(Path(args.docs_dir), Path(args.data_dir))
    for path in written:
        print(f"[OK] {path}")
    print(f"[OK] đã dựng {len(written)} trang")


if __name__ == "__main__":
    main()
