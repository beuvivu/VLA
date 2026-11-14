"""Ghi pack model nguyên tử mà không thêm phụ thuộc ML cho sổ cái/trang."""

from __future__ import annotations

import io
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


def dump_pack_unless_equivalent(pack: dict[str, Any], path: Path, *, stamp_keys: frozenset[str]) -> bool:
    """Ghi pack, TRỪ khi pack đang có trên đĩa trùng nó ở mọi khoá ngoài ``stamp_keys``: khi ấy giữ tệp cũ.

    Lượt pipeline chạy lại trên cùng dữ liệu học lại mô hình xếp chồng y hệt (``random_state`` cố định)
    nhưng vẫn ghi lại ``models/meta_<mode>.joblib``: khác giờ học, và pickle khác cả cách chia sẻ chuỗi
    giữa các đối tượng dù mọi tham số, mọi mảng và mọi dự báo trùng từng bit (đo 11-11-2026).

    So bằng ``joblib.hash``, phép băm theo GIÁ TRỊ (nó cố ý không ghi nhớ chuỗi). Nó lại tính bước nhảy
    bộ nhớ của mảng, mà numpy đặt tuỳ ý cho chiều dài 1 (``coef_`` hình (1, 3) vừa học có bước nhảy 0,
    đọc từ tệp thì 24). Nên pack mới được tuần tự hoá rồi đọc lại TRƯỚC khi băm: hai bên cùng là đối
    tượng đọc từ pickle. Pack xếp chồng nhỏ (≤ 30 KB), giữ bản tuần tự trong bộ nhớ là rẻ. Đọc pack cũ
    hỏng thì ghi pack mới. Trả về ``True`` khi đã ghi.
    """
    from core.atomic_io import atomic_write_bytes

    path = Path(path)
    buffer = io.BytesIO()
    joblib.dump(pack, buffer)
    content = buffer.getvalue()
    if path.is_file():
        try:
            current = joblib.load(path)
        except MODEL_LOAD_ERRORS:
            current = None
        if isinstance(current, dict):
            def digest(value: dict[str, Any]) -> str:
                return joblib.hash({key: item for key, item in value.items() if key not in stamp_keys})

            if digest(current) == digest(joblib.load(io.BytesIO(content))):
                return False
    atomic_write_bytes(path, content)
    return True
