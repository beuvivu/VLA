"""Tệp JSON chỉ đổi DẤU GIỜ GHI thì trả về bản đã commit (11-11-2026).

Pipeline chạy lại trên cùng dữ liệu (ví dụ lượt chạy theo push khi gộp một PR) ghi lại mọi manifest và
báo cáo. Ngày 11-11-2026 lượt chạy lại không có kỳ quay mới vẫn commit 57 tệp; 31 tệp trong đó là JSON
chỉ khác đúng MỘT khoá dấu giờ (`generated_at_utc`, `learned_at_utc`…). Dấu giờ ấy còn lan sang bước
sau: mã thí nghiệm `EXP-…-<ngày>` lấy ngày từ `generated_at` của cổng Cầu Kèo, trang bảng điều khiển
nhúng `learned_at_utc` của trọng số.

Sửa ở MỘT chỗ thay vì ở từng trình ghi: sau mỗi bước, `pipeline._run` gọi
`keep_committed_when_only_stamps_changed`. Tệp JSON git đang theo dõi mà chỉ khác bản HEAD ở các khoá
dấu giờ thì được ghi lại đúng từng byte của bản HEAD, TRƯỚC khi bước sau kịp đọc dấu giờ mới. Dấu giờ cũ
vẫn đúng: nội dung này có từ lúc ấy.

Chỉ khoá dấu giờ GHI được bỏ qua. Mọi khoá khác, kể cả ngày neo, ngày đích và mọi con số, phải trùng
tuyệt đối; số thực so từng bit (nhiễu dấu phẩy động là thay đổi, không phải dấu giờ).
"""
from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

from core.atomic_io import atomic_write_bytes

#: Khoá ghi «tệp này được ghi lúc nào». Thêm khoá mới thì thêm phép kiểm ghim nó vào một tệp thật.
WRITE_STAMP_KEYS = frozenset({
    "generated_at", "generated_at_utc", "learned_at_utc", "trained_at_utc", "evaluated_at_utc",
    "checked_at",
})

_NAN = ("<NaN>",)   # NaN khác chính nó; hai tệp cùng mang NaN ở cùng chỗ vẫn là cùng nội dung

#: Tệp đã so và thấy đổi THẬT, theo (đường dẫn, mtime_ns, cỡ) lúc so. Pipeline gọi phép so sau mỗi bước
#: (~110 lần), và tệp đã đổi thật vẫn hiện trong `git status` tới cuối lượt: không nhớ thì mỗi lần gọi đọc
#: lại mọi tệp ấy (đo 14-11-2026: 0,55 s cho 70 tệp, 5,2 MB). Tệp bị ghi lại thì mtime đổi và được so lại.
_REAL_CHANGES: set[tuple[str, int, int]] = set()


def without_stamps(node: object, stamp_keys: frozenset[str] = WRITE_STAMP_KEYS) -> object:
    """Bản sao của một cây JSON, bỏ mọi khoá dấu giờ ở mọi tầng."""
    if isinstance(node, dict):
        return {key: without_stamps(value, stamp_keys) for key, value in node.items()
                if key not in stamp_keys}
    if isinstance(node, list):
        return [without_stamps(value, stamp_keys) for value in node]
    if isinstance(node, float) and math.isnan(node):
        return _NAN
    return node


def same_but_for_stamps(old: object, new: object,
                        stamp_keys: frozenset[str] = WRITE_STAMP_KEYS) -> bool:
    """Hai cây JSON chỉ khác nhau ở khoá dấu giờ (hoặc không khác gì ngoài thứ tự khoá)."""
    return without_stamps(old, stamp_keys) == without_stamps(new, stamp_keys)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)  # noqa: S603, S607


def _same_json_but_for_stamps(committed: bytes, current: bytes) -> bool:
    return same_but_for_stamps(json.loads(committed), json.loads(current))


def keep_committed_when(
    repo: Path, *, scope: Iterable[str], suffix: str, same: Callable[[bytes, bytes], bool],
) -> list[str]:
    """Trả mọi tệp `*<suffix>` đã theo dõi trong `scope` mà ``same(bản HEAD, bản hiện tại)`` về đúng bản HEAD.

    Trả danh sách tệp đã trả về. ``same`` ném ``ValueError`` (tệp không đọc được) thì coi như khác. Không
    phải kho git, không có HEAD, hay git không chạy được thì không làm gì: đây là việc giữ sạch commit,
    không được làm hỏng lượt chạy.
    """
    repo = Path(repo)
    # `status` chứ không phải `diff`: nó làm mới chỉ mục, nên lần gọi sau không băm lại các tệp mà bước
    # vừa rồi ghi lại y nguyên.
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
    """Trả mọi tệp JSON chỉ khác bản HEAD ở dấu giờ ghi về đúng bản HEAD; trả danh sách tệp đã trả về."""
    return keep_committed_when(repo, scope=scope, suffix=".json", same=_same_json_but_for_stamps)
