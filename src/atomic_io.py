"""Ghi tệp nguyên tử: viết ra tệp tạm cạnh đích, fsync, rồi ``os.replace``.

Mở tệp bằng ``"w"`` cắt nó về rỗng TRƯỚC khi ghi. Tiến trình chết giữa chừng
(đĩa đầy, runner bị huỷ, lỗi giữa vòng ghi) để lại một tệp cụt. Với các sổ cái
"đọc lại rồi ghi lại toàn bộ" của kho (bảng mô phỏng, giả thuyết tiến cứu, kỹ
năng đã công bố), lần chạy sau sẽ gộp một sổ cụt và mất luôn các dòng cũ, mà
đó lại là bản ghi duy nhất dài hơn hạn giữ artifact.

``os.replace`` trên cùng một thư mục là nguyên tử với POSIX: người đọc thấy
hoặc bản cũ trọn vẹn, hoặc bản mới trọn vẹn, không bao giờ thấy bản dở.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Thay ``path`` bằng ``content``; lỗi ở bất kỳ bước nào giữ nguyên tệp cũ."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Như :func:`atomic_write_bytes` cho văn bản."""
    atomic_write_bytes(path, text.encode(encoding))


def atomic_to_csv(frame: pd.DataFrame, path: Path, **kwargs) -> None:
    """``frame.to_csv(path, **kwargs)`` nhưng nguyên tử.

    Dựng trọn CSV trong bộ nhớ trước: lỗi khi định dạng không chạm tới tệp đích.
    """
    buffer = io.StringIO()
    frame.to_csv(buffer, **kwargs)
    atomic_write_text(path, buffer.getvalue())
