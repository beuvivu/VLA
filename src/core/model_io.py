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

from core.atomic_io import FLOAT_NOISE_ABSOLUTE, FLOAT_NOISE_RELATIVE, atomic_write_bytes, floats_close

MODEL_LOAD_ERRORS = (AttributeError, EOFError, ImportError, IndexError, KeyError,
                     OSError, TypeError, ValueError, pickle.UnpicklingError,
                     zlib.error, lzma.LZMAError)


Predict = Callable[[Any], Any]


def _close_arrays(old: np.ndarray, new: np.ndarray) -> bool:
    old, new = np.asarray(old, dtype=float), np.asarray(new, dtype=float)
    if old.shape != new.shape:
        return False
    with np.errstate(invalid="ignore"):
        bound = np.maximum(FLOAT_NOISE_ABSOLUTE, FLOAT_NOISE_RELATIVE * np.maximum(np.abs(old), np.abs(new)))
        near = np.abs(old - new) <= bound
    return bool(np.all(near | (old == new) | (np.isnan(old) & np.isnan(new))))


def _same_value(old: Any, new: Any) -> bool:
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(_same_value(old[key], new[key]) for key in old)
    if isinstance(old, (list, tuple)) and isinstance(new, (list, tuple)):
        return type(old) is type(new) and len(old) == len(new) and all(map(_same_value, old, new, strict=True))
    if isinstance(old, np.ndarray) and isinstance(new, np.ndarray):
        if old.shape != new.shape or old.dtype != new.dtype:
            return False
        return _close_arrays(old, new) if old.dtype.kind == "f" else bool(np.array_equal(old, new))
    if isinstance(old, (float, np.floating)) and isinstance(new, (float, np.floating)):
        return type(old) is type(new) and floats_close(float(old), float(new))
    if isinstance(old, (str, bytes, bool, int, np.integer, np.bool_)) or old is None:
        return type(old) is type(new) and old == new
    return joblib.hash(old) == joblib.hash(new)


def _equivalent(current: dict[str, Any], fresh: dict[str, Any], *, stamp_keys: frozenset[str],
                predictions: Mapping[str, Predict]) -> bool:
    keys = current.keys() - stamp_keys
    if keys != fresh.keys() - stamp_keys:
        return False
    models = [key for key in keys if key in predictions and current[key] is not None and fresh[key] is not None]
    if not all(_same_value(current[key], fresh[key]) for key in keys - set(models)):
        return False
    for key in models:
        old, new = current[key], fresh[key]
        try:
            same = type(old) is type(new) and _close_arrays(predictions[key](old), predictions[key](new))
        except Exception:
            return False
        if not same:
            return False
    return True


def dump_pack_unless_equivalent(pack: dict[str, Any], path: Path, *, stamp_keys: frozenset[str] = frozenset(),
                                predictions: Mapping[str, Predict] | None = None) -> bool:
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
