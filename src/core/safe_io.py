from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

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
    path = Path(path)
    if not _present(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, **kwargs)
    except CSV_DATA_ERRORS as error:
        logger.warning("bỏ qua %s vì không đọc được: %s", path, error)
        return pd.DataFrame()


def read_json_or_empty(path: Path) -> Any:
    path = Path(path)
    if not _present(path):
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except JSON_DATA_ERRORS as error:
        logger.warning("bỏ qua %s vì không đọc được: %s", path, error)
        return {}
