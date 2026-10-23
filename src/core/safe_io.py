"""Đọc tệp dữ liệu cho trình dựng trang: thiếu thì rỗng, HỎNG thì báo, lỗi mã thì nổ.

Trước đây mỗi trình dựng tự viết ``_read_csv``/``_read_json`` với ``except
Exception`` trùm hết. Hệ quả có hai: tệp có mặt nhưng hỏng (ghi dở, sai mã hoá,
JSON cụt) làm trang lặng lẽ in "chưa có dữ liệu" mà không dòng log nào nói vì
sao; và lỗi LẬP TRÌNH — truyền sai tham số, gọi sai tên — cũng bị nuốt như thể
tệp trống.

Luật ở đây tách ba trường hợp:

* tệp không có hoặc rỗng  -> trả rỗng, im lặng (trạng thái bình thường khi
  pipeline chưa sinh tệp);
* tệp có nhưng không đọc được (``OSError``, lỗi phân tích CSV, lỗi giải mã JSON,
  lỗi giải mã chữ) -> trả rỗng VÀ ghi cảnh báo nêu đường dẫn cùng lỗi;
* mọi lỗi khác (``TypeError``, ``NameError``, và cả ``ValueError`` chung — mà
  ``pd.read_csv`` ném cho tham số sai như ``engine`` lạ) -> để nổ: đó là lỗi của
  mã.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

#: Lỗi của DỮ LIỆU, không phải của mã. Cố ý KHÔNG bắt ``ValueError`` chung:
#: cả ba lớp dưới đây là lớp con của nó, nhưng ``ValueError`` trần từ
#: ``pd.read_csv`` thường là tham số sai.
CSV_DATA_ERRORS: tuple[type[BaseException], ...] = (
    OSError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError,
)
JSON_DATA_ERRORS: tuple[type[BaseException], ...] = (
    OSError, UnicodeDecodeError, json.JSONDecodeError,
)


def _present(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError as error:
        logger.warning("không xem được %s: %s", path, error)
        return False


def read_csv_or_empty(path: Path, **kwargs: Any) -> pd.DataFrame:
    """``pd.read_csv(path, **kwargs)``; thiếu/rỗng/hỏng thì ``DataFrame`` rỗng."""
    path = Path(path)
    if not _present(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, **kwargs)
    except CSV_DATA_ERRORS as error:
        logger.warning("bỏ qua %s vì không đọc được: %s", path, error)
        return pd.DataFrame()


def read_json_or_empty(path: Path) -> Any:
    """Nội dung JSON của ``path``; thiếu/rỗng/hỏng thì ``{}``."""
    path = Path(path)
    if not _present(path):
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except JSON_DATA_ERRORS as error:
        logger.warning("bỏ qua %s vì không đọc được: %s", path, error)
        return {}
