from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
#: Thư mục ``tests/``: helper dùng chung giữa các nhóm (``*_helpers.py``) nằm ở đây, còn phép kiểm
#: nằm trong ``tests/<nhóm>/``. Đặt tường minh thay vì dựa vào việc pytest tự chèn thư mục conftest.
TESTS = Path(__file__).resolve().parent
for path in (SRC, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
