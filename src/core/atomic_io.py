from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


def atomic_write_bytes(
    path: Path, content: bytes, *, before_replace: Callable[[], None] | None = None,
) -> None:
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
    atomic_write_bytes(path, text.encode(encoding))


def atomic_to_csv(frame: pd.DataFrame, path: Path, **kwargs) -> None:
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


XLSX_VOLATILE_PARTS = frozenset({"docProps/core.xml"})


def xlsx_payload_equal(first: Path, second: Path) -> bool:
    try:
        with zipfile.ZipFile(first) as a, zipfile.ZipFile(second) as b:
            names = set(a.namelist()) - XLSX_VOLATILE_PARTS
            if names != set(b.namelist()) - XLSX_VOLATILE_PARTS:
                return False
            return all(a.read(name) == b.read(name) for name in names)
    except (OSError, zipfile.BadZipFile):
        return False


def save_xlsx(workbook: Any, path: Path) -> bool:
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


FLOAT_NOISE_RELATIVE = 1e-9
FLOAT_NOISE_ABSOLUTE = 1e-12

_FLOAT_SPELLING = re.compile(r"[.eEnN]")


def floats_close(x: float, y: float) -> bool:
    if math.isnan(x) or math.isnan(y):
        return math.isnan(x) and math.isnan(y)
    if math.isinf(x) or math.isinf(y):
        return x == y
    return abs(x - y) <= max(FLOAT_NOISE_ABSOLUTE, FLOAT_NOISE_RELATIVE * max(abs(x), abs(y)))


def same_tree_up_to_float_noise(old: object, new: object) -> bool:
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(same_tree_up_to_float_noise(old[k], new[k]) for k in old)
    if isinstance(old, list) and isinstance(new, list):
        return len(old) == len(new) and all(same_tree_up_to_float_noise(a, b) for a, b in zip(old, new, strict=True))
    if type(old) is float and type(new) is float:
        return floats_close(old, new)
    return type(old) is type(new) and old == new


def _as_float(cell: str) -> float | None:
    try:
        return float(cell)
    except ValueError:
        return None


def same_table_up_to_float_noise(old: bytes, new: bytes) -> bool:
    if old.count(b"\n") != new.count(b"\n"):
        return False
    try:
        rows_old = list(csv.reader(io.StringIO(old.decode("utf-8"))))
        rows_new = list(csv.reader(io.StringIO(new.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error):
        return False
    if not rows_old or not rows_new or rows_old[0] != rows_new[0]:
        return False
    header, body_old, body_new = rows_old[0], rows_old[1:], rows_new[1:]
    width = len(header)
    if len(body_old) != len(body_new) or any(len(row) != width for row in body_old + body_new):
        return False
    floating = [
        any(_FLOAT_SPELLING.search(row[i]) and _as_float(row[i]) is not None for row in body_old + body_new)
        for i in range(width)
    ]
    keys = [i for i in range(width) if not floating[i]]

    def order(row: list[str]) -> list[str]:
        return [row[i] for i in keys]

    for row_old, row_new in zip(sorted(body_old, key=order), sorted(body_new, key=order), strict=True):
        for i in range(width):
            if row_old[i] == row_new[i]:
                continue
            if not floating[i]:
                return False
            a, b = _as_float(row_old[i]), _as_float(row_new[i])
            if a is None or b is None or not floats_close(a, b):
                return False
    return True


WRITE_STAMP_KEYS = frozenset({
    "generated_at", "generated_at_utc", "learned_at_utc", "trained_at_utc", "evaluated_at_utc",
    "checked_at",
})

_REAL_CHANGES: set[tuple[str, int, int]] = set()


def json_without_stamps(node: object, stamp_keys: frozenset[str] = WRITE_STAMP_KEYS) -> object:
    if isinstance(node, dict):
        return {key: json_without_stamps(value, stamp_keys) for key, value in node.items()
                if key not in stamp_keys}
    if isinstance(node, list):
        return [json_without_stamps(value, stamp_keys) for value in node]
    return node


def same_but_for_stamps_and_noise(old: object, new: object,
                                  stamp_keys: frozenset[str] = WRITE_STAMP_KEYS) -> bool:
    return same_tree_up_to_float_noise(json_without_stamps(old, stamp_keys), json_without_stamps(new, stamp_keys))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)


def _same_json_but_for_stamps(committed: bytes, current: bytes) -> bool:
    return same_but_for_stamps_and_noise(json.loads(committed), json.loads(current))


def keep_committed_when(
    repo: Path, *, scope: Iterable[str], suffix: str, same: Callable[[bytes, bytes], bool],
) -> list[str]:
    repo = Path(repo)
    listed = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=no", "--", *scope)
    if listed.returncode != 0:
        return []
    restored: list[str] = []
    for entry in listed.stdout.decode("utf-8", "replace").split("\0"):
        state, path = entry[:2], entry[3:]
        if not path.endswith(suffix) or "M" not in state:
            continue
        target = repo / path
        try:
            info = target.stat()
        except OSError:
            continue
        seen = (str(target.resolve()), info.st_mtime_ns, info.st_size)
        if seen in _REAL_CHANGES:
            continue
        head = _git(repo, "show", f"HEAD:{path}")
        if head.returncode != 0:
            continue
        try:
            current = target.read_bytes()
            if current == head.stdout or not same(head.stdout, current):
                _REAL_CHANGES.add(seen)
                continue
        except (OSError, ValueError):
            continue
        atomic_write_bytes(target, head.stdout)
        restored.append(path)
    return restored


def keep_committed_when_only_stamps_changed(repo: Path, scope: Iterable[str] = ("data",)) -> list[str]:
    return keep_committed_when(repo, scope=scope, suffix=".json", same=_same_json_but_for_stamps)


def keep_committed_tables_when_only_noise_changed(repo: Path, scope: Iterable[str] = ("data", "models")) -> list[str]:
    return keep_committed_when(repo, scope=scope, suffix=".csv", same=same_table_up_to_float_noise)
