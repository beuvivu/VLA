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
import re
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pandas as pd


def atomic_write_bytes(
    path: Path, content: bytes, *, before_replace: Callable[[], None] | None = None,
) -> None:
    """Thay đích nguyên tử; chốt tùy chọn sau fsync có thể hủy mà giữ tệp cũ."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if before_replace is not None:
            before_replace()
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


def _without_stamps(text: str, stamps: tuple[re.Pattern[str], ...]) -> str:
    for stamp in stamps:
        text = stamp.sub("\0", text)
    return text


def write_text_unless_only_stamps(
    path: Path, text: str, stamps: Iterable[re.Pattern[str]], encoding: str = "utf-8",
) -> bool:
    """Ghi nguyên tử, TRỪ khi tệp hiện có chỉ khác ``text`` ở các dấu giờ dựng: khi ấy giữ tệp cũ.

    Pipeline chạy lại trong ngày (ví dụ lượt chạy theo push khi gộp một PR) dựng lại mọi trang trên
    CÙNG dữ liệu. Ngày 05-11-2026 lượt chạy lại ghi lại 15 trang chỉ để đổi «Dựng lúc …» và commit
    chúng; dấu giờ cũ vẫn đúng, vì nội dung trang là bản dựng lúc ấy. Trả về ``True`` khi đã ghi.
    """
    path = Path(path)
    patterns = tuple(stamps)
    if path.is_file():
        try:
            current = path.read_text(encoding=encoding)
        except (OSError, UnicodeDecodeError):
            current = None
        if current is not None and (
            current == text or _without_stamps(current, patterns) == _without_stamps(text, patterns)
        ):
            return False
    atomic_write_text(path, text, encoding)
    return True


#: Phần của tệp xlsx mà openpyxl ghi giờ lưu vào (``dcterms:modified``), dù dữ liệu không đổi.
XLSX_VOLATILE_PARTS = frozenset({"docProps/core.xml"})


def xlsx_payload_equal(first: Path, second: Path) -> bool:
    """Hai tệp xlsx chứa đúng cùng các phần và cùng nội dung, bỏ qua giờ lưu trong ``docProps/core.xml``."""
    try:
        with zipfile.ZipFile(first) as a, zipfile.ZipFile(second) as b:
            names = set(a.namelist()) - XLSX_VOLATILE_PARTS
            if names != set(b.namelist()) - XLSX_VOLATILE_PARTS:
                return False
            return all(a.read(name) == b.read(name) for name in names)
    except (OSError, zipfile.BadZipFile):
        return False


def save_xlsx(workbook: Any, path: Path) -> bool:
    """Lưu workbook nguyên tử; dữ liệu không đổi (chỉ khác giờ lưu) thì giữ nguyên tệp cũ.

    openpyxl đặt ``modified`` bằng giờ hiện tại mỗi lần lưu, nên trước 06-11-2026 ba tệp xlsx của
    kho được commit lại sau mỗi lượt pipeline chạy lại mà không một ô nào đổi. Trả về ``True`` khi đã ghi.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".xlsx", dir=path.parent)
    os.close(fd)
    try:
        workbook.save(temporary)
        if path.is_file() and xlsx_payload_equal(path, Path(temporary)):
            return False
        os.replace(temporary, path)
        return True
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

