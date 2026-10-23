"""Thư mục của kho, tính MỘT lần từ vị trí gói ``core``.

Module nằm trong gói con, nên ``Path(__file__).parent`` không còn là ``src/`` và
``parents[1]`` không còn là gốc kho. Đếm tầng tại chỗ thì mỗi lần chuyển gói lại sai
một nơi — có nơi lặng lẽ: ``calendar_alignment`` đọc lịch ngày nghỉ bằng đường dẫn ấy,
và thiếu tệp thì lịch rỗng chứ không báo lỗi. Mọi đường dẫn tới gốc kho,
``src/templates`` và ``src/assets`` đi qua đây.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
TEMPLATES = SRC / "templates"
ASSETS = SRC / "assets"
