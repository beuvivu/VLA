"""Đọc và ghi pack mô hình: ghi nguyên tử, và giữ tệp cũ khi pack học lại tương đương."""

from __future__ import annotations

import io
import lzma
import pickle
import zlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from core.atomic_io import atomic_write_bytes
from core.float_noise import FLOAT_NOISE_ABSOLUTE, FLOAT_NOISE_RELATIVE, close

# Joblib hỗ trợ cả pickle thuần và các codec nén. Chỉ bắt lỗi đọc pack;
# lỗi huấn luyện/lập trình bên ngoài thao tác load vẫn phải nổi lên.
MODEL_LOAD_ERRORS = (AttributeError, EOFError, ImportError, IndexError, KeyError,
                     OSError, TypeError, ValueError, pickle.UnpicklingError,
                     zlib.error, lzma.LZMAError)


Predict = Callable[[Any], Any]


def _close_arrays(old: np.ndarray, new: np.ndarray) -> bool:
    """Mọi phần tử của hai mảng số thực chỉ khác nhau ở nhiễu (cùng luật `core.float_noise.close`)."""
    old, new = np.asarray(old, dtype=float), np.asarray(new, dtype=float)
    if old.shape != new.shape:
        return False
    with np.errstate(invalid="ignore"):
        bound = np.maximum(FLOAT_NOISE_ABSOLUTE, FLOAT_NOISE_RELATIVE * np.maximum(np.abs(old), np.abs(new)))
        near = np.abs(old - new) <= bound
    return bool(np.all(near | (old == new) | (np.isnan(old) & np.isnan(new))))


def _same_value(old: Any, new: Any) -> bool:
    """Hai giá trị trong pack trùng nhau, trừ nhiễu ở số thực; đối tượng khác (mô hình…) so bằng ``joblib.hash``."""
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(_same_value(old[key], new[key]) for key in old)
    if isinstance(old, (list, tuple)) and isinstance(new, (list, tuple)):
        return type(old) is type(new) and len(old) == len(new) and all(map(_same_value, old, new, strict=True))
    if isinstance(old, np.ndarray) and isinstance(new, np.ndarray):
        if old.shape != new.shape or old.dtype != new.dtype:
            return False
        return _close_arrays(old, new) if old.dtype.kind == "f" else bool(np.array_equal(old, new))
    if isinstance(old, (float, np.floating)) and isinstance(new, (float, np.floating)):
        return type(old) is type(new) and close(float(old), float(new))
    if isinstance(old, (str, bytes, bool, int, np.integer, np.bool_)) or old is None:
        return type(old) is type(new) and old == new
    return joblib.hash(old) == joblib.hash(new)


def _equivalent(current: dict[str, Any], fresh: dict[str, Any], *, stamp_keys: frozenset[str],
                predictions: Mapping[str, Predict]) -> bool:
    keys = current.keys() - stamp_keys
    if keys != fresh.keys() - stamp_keys:
        return False
    models = [key for key in keys if key in predictions and current[key] is not None and fresh[key] is not None]
    # Khoá thường trước: đặc trưng đổi thì mô hình cũ không dự báo được trên dữ liệu mới.
    if not all(_same_value(current[key], fresh[key]) for key in keys - set(models)):
        return False
    for key in models:
        old, new = current[key], fresh[key]
        try:
            same = type(old) is type(new) and _close_arrays(predictions[key](old), predictions[key](new))
        except Exception:  # noqa: BLE001 - mô hình cũ không dự báo được trên dữ liệu này thì đã khác
            return False
        if not same:
            return False
    return True


def dump_pack_unless_equivalent(pack: dict[str, Any], path: Path, *, stamp_keys: frozenset[str] = frozenset(),
                                predictions: Mapping[str, Predict] | None = None) -> bool:
    """Ghi pack, TRỪ khi pack đang có trên đĩa tương đương nó: khi ấy giữ tệp cũ. Trả về ``True`` khi đã ghi.

    Tương đương nghĩa là cùng khoá, và mọi khoá ngoài ``stamp_keys`` trùng nhau: số thực tới mức nhiễu
    dấu phẩy động (``core.float_noise``, ≤ 10⁻⁹ tương đối), mảng số thực từng phần tử như thế, còn lại
    tuyệt đối. Mô hình ở khoá có trong ``predictions`` ({khoá: hàm(mô hình) → mảng dự báo}) trùng khi hai
    bản cho cùng dự báo tới mức nhiễu trên đúng dữ liệu hàm ấy dùng; mô hình không có hàm dự báo thì so
    ``joblib.hash``.

    Hai lý do pack học lại trên CÙNG dữ liệu vẫn khác bản cũ (11 → 15-11-2026):

    - Pickle khác cách chia sẻ chuỗi giữa các đối tượng, dù mọi tham số trùng từng bit. ``joblib.hash``
      băm theo GIÁ TRỊ (cố ý không ghi nhớ chuỗi), nhưng tính bước nhảy bộ nhớ của mảng, mà numpy đặt tuỳ
      ý cho chiều dài 1 (``coef_`` hình (1, 3) vừa học có bước nhảy 0, đọc từ tệp thì 24). Nên pack mới
      được tuần tự hoá rồi đọc lại TRƯỚC khi so: hai bên cùng là đối tượng đọc từ pickle.
    - Runner khác CPU: đặc trưng float32 (`log1p` của khoảng cách) lệch một ULP float32, nên ngưỡng chia
      bin của cây lệch tới 9·10⁻⁸ tương đối, hệ số Platt lệch 10⁻¹⁴. Tham số không so được bằng một
      ngưỡng chung; dự báo thì so được: dữ liệu và ngưỡng cùng lệch nên mọi mẫu rơi đúng bin cũ. Lượt
      chạy lại 09-11 và 06-11-2026 ghi lại cả hai ``ml_<mode>.joblib`` chỉ vì thế.

    Đọc pack cũ hỏng thì ghi pack mới.
    """
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
            fresh = joblib.load(io.BytesIO(content))

            def digest(value: dict[str, Any]) -> str:
                return joblib.hash({key: item for key, item in value.items() if key not in stamp_keys})

            if digest(current) == digest(fresh) or _equivalent(
                    current, fresh, stamp_keys=stamp_keys, predictions=predictions or {}):
                return False
    atomic_write_bytes(path, content)
    return True
