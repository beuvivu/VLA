"""Ghi pack model nguyên tử mà không thêm phụ thuộc ML cho sổ cái/trang."""

from __future__ import annotations

import os
import lzma
import pickle
import tempfile
import zlib
from pathlib import Path
from typing import Any

import joblib

# Joblib hỗ trợ cả pickle thuần và các codec nén. Chỉ bắt lỗi đọc pack;
# lỗi huấn luyện/lập trình bên ngoài thao tác load vẫn phải nổi lên.
MODEL_LOAD_ERRORS = (AttributeError, EOFError, ImportError, IndexError, KeyError,
                     OSError, TypeError, ValueError, pickle.UnpicklingError,
                     zlib.error, lzma.LZMAError)


def atomic_joblib_dump(value: Any, path: Path) -> None:
    """Ghi một pack joblib cạnh đích; dump/ghi/thay lỗi vẫn giữ pack cũ.

    Ghi qua stream để joblib không tạo tệp phụ, rồi fsync trước khi thay đích.
    Không dựng thêm bản sao toàn bộ pack trong bộ nhớ.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            joblib.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
