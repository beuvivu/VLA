"""Thư mục của kho, tính MỘT lần từ vị trí gói ``core``.

Module nằm trong gói con, nên ``Path(__file__).parent`` không còn là ``src/`` và
``parents[1]`` không còn là gốc kho. Đếm tầng tại chỗ thì mỗi lần chuyển gói lại sai
một nơi — có nơi lặng lẽ: ``calendar_alignment`` đọc lịch ngày nghỉ bằng đường dẫn ấy,
và thiếu tệp thì lịch rỗng chứ không báo lỗi. Mọi đường dẫn tới gốc kho,
``src/web/templates`` và ``src/web/assets`` đi qua đây.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
#: Tài nguyên của tầng trang: mẫu HTML/CSS/JS và tệp tĩnh chép sang ``docs/assets``.
TEMPLATES = SRC / "web" / "templates"
ASSETS = SRC / "web" / "assets"

#: Thư mục dẫn xuất của ``data/`` gom theo gói sinh ra chúng (24-10-2026): tên cũ → chỗ mới,
#: tương đối với ``data/``. Gốc ``data/`` chỉ còn sổ chuẩn, tệp đọc từ bên ngoài kho (Worker
#: và trang live đọc ``xsmb.json``, ``ai_ml/daily`` bằng địa chỉ thô) và thư mục đã mang tên
#: gói (``ensemble``, ``ml``, ``research``). Commit trước ngày ấy giữ tệp ở chỗ cũ, nên ai đọc
#: LỊCH SỬ git phải hỏi cả hai chỗ qua ``legacy_data_path``.
DATA_MOVES = {
    name: f"{group}/{name}"
    for group, names in {
        "stats": "advanced conditional cycle descriptive_ext hazard markov number_dynamics pairs "
                 "reference significance statistical_signal",
        "soi_cau": "path_ui position_bridges bridge_pages",
        "forecast": "predict online knowledge multi_hit agents feature_attribution",
        "evaluation": "history model_quality prob_eval confidence fun_draw prediction_board",
        "research": "hypotheses",
    }.items()
    for name in names.split()
}


def legacy_data_path(rel: str) -> str | None:
    """Chỗ của ``rel`` (tương đối với ``data/``) trước đợt gom 24-10-2026; None nếu nó không đổi chỗ."""
    group, _, rest = rel.partition("/")
    name, sep, tail = rest.partition("/")
    if DATA_MOVES.get(name) != f"{group}/{name}":
        return None
    return name + sep + tail
