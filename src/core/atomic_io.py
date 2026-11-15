"""Ghi tệp của kho: nguyên tử, và không ghi lại khi nội dung không đổi.

Ba phần, cùng một mục đích là commit của pipeline chỉ mang thay đổi THẬT:

1. Ghi nguyên tử: viết ra tệp tạm cạnh đích, fsync, rồi ``os.replace``. Mở tệp bằng ``"w"`` cắt nó
   về rỗng TRƯỚC khi ghi. Tiến trình chết giữa chừng (đĩa đầy, runner bị huỷ, lỗi giữa vòng ghi) để
   lại một tệp cụt. Với các sổ cái "đọc lại rồi ghi lại toàn bộ" của kho (bảng mô phỏng, giả thuyết
   tiến cứu, kỹ năng đã công bố), lần chạy sau sẽ gộp một sổ cụt và mất luôn các dòng cũ, mà đó lại
   là bản ghi duy nhất dài hơn hạn giữ artifact. ``os.replace`` trên cùng một thư mục là nguyên tử
   với POSIX: người đọc thấy hoặc bản cũ trọn vẹn, hoặc bản mới trọn vẹn, không bao giờ thấy bản dở.
2. Nhiễu dấu phẩy động: hai bản của một bảng hay một cây JSON chỉ khác nhau ở bit cuối do CPU runner.
3. Giữ bản đã commit: tệp chỉ đổi dấu giờ ghi hay nhiễu số thực thì trả về đúng bản HEAD.

Chỉ dùng thư viện chuẩn: `web.page_output` nạp mô-đun này trong job Chromium, nơi không cài pandas.
Gộp từ ``core.float_noise`` và ``core.stamp_only_json`` ngày 15-11-2026.
"""

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

if TYPE_CHECKING:  # pandas chỉ cần cho atomic_to_csv: job Chromium của CI không cài pandas, mà
    import pandas as pd  # web.page_output (qua write_text_unless_only_stamps) lại nằm trong chuỗi import của nó.


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


# --- Nhiễu dấu phẩy động (14-11-2026) ----------------------------------------------------------------
#
# Lượt pipeline chạy lại trên runner có CPU khác ghi lại những bảng mà mọi số chỉ lệch ở bit cuối:
# `np.corrcoef`, `np.dot` và hàm đặc biệt của scipy chọn lệnh SIMD theo CPU. Lượt chạy lại sau PR #223
# ghi lại `strategy_diversity_<mode>.csv` (phi lệch ≤ 4·10⁻¹⁵, hai cặp gần hoà đổi chỗ nên cả 378 dòng
# đổi) và `loto_acf_bartlett.csv` (một giá trị p lệch 2,8·10⁻¹⁷); lượt 09-11 ghi lại 21 bảng và 10 JSON
# kiểu ấy. Sửa tận gốc từng bảng là đổi phép tính thống kê, mà mỗi bảng dùng một hàm khác.
#
# Luật so, cùng ngưỡng với tệp tóm tắt Vietlott (`vlm.forecast.service._same_up_to_float_noise`):
# - CHỈ số thực được nới: lệch ≤ 10⁻⁹ tương đối (hoặc ≤ 10⁻¹² tuyệt đối gần 0). NaN bằng NaN.
# - Số nguyên, chuỗi, ngày, mã có số 0 đầu, giá trị đúng/sai, khoá, độ dài danh sách, số dòng và tiêu đề
#   cột phải trùng tuyệt đối.
# - Bảng CSV không tính thứ tự dòng: dòng được xếp theo các cột KHÔNG phải số thực trước khi so, vì nhiễu
#   đổi được thứ tự của hai dòng gần hoà ở cột số thực mà bảng xếp theo.

#: Ngưỡng nhiễu: tương đối, và tuyệt đối cho số gần 0. Thay đổi thật của một xác suất hay một thống kê
#: đã công bố lớn hơn nhiều bậc.
FLOAT_NOISE_RELATIVE = 1e-9
FLOAT_NOISE_ABSOLUTE = 1e-12

#: Ô viết như số thực: có dấu chấm, số mũ hay nan/inf. Số nguyên trần («47», «05») so tuyệt đối.
_FLOAT_SPELLING = re.compile(r"[.eEnN]")


def floats_close(x: float, y: float) -> bool:
    """Hai số thực chỉ khác nhau ở nhiễu."""
    if math.isnan(x) or math.isnan(y):
        return math.isnan(x) and math.isnan(y)
    if math.isinf(x) or math.isinf(y):
        return x == y
    return abs(x - y) <= max(FLOAT_NOISE_ABSOLUTE, FLOAT_NOISE_RELATIVE * max(abs(x), abs(y)))


def same_tree_up_to_float_noise(old: object, new: object) -> bool:
    """Hai cây JSON trùng nhau, trừ nhiễu ở số thực. Thứ tự khoá không tính; độ dài danh sách thì có."""
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
    """Hai bản CSV trùng nhau, trừ nhiễu ở cột số thực và thứ tự dòng. Đọc hỏng thì coi là khác."""
    if old.count(b"\n") != new.count(b"\n"):   # lối tắt: khác số dòng thì khỏi đọc
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


# --- Giữ bản đã commit khi chỉ đổi dấu giờ hay nhiễu (11 → 14-11-2026) -------------------------------
#
# Pipeline chạy lại trên cùng dữ liệu (ví dụ lượt chạy theo push khi gộp một PR) ghi lại mọi manifest và
# báo cáo. Ngày 11-11-2026 lượt chạy lại không có kỳ quay mới vẫn commit 57 tệp; 31 tệp trong đó là JSON
# chỉ khác đúng MỘT khoá dấu giờ (`generated_at_utc`, `learned_at_utc`…). Dấu giờ ấy còn lan sang bước
# sau: mã thí nghiệm `EXP-…-<ngày>` lấy ngày từ `generated_at` của cổng Cầu Kèo, trang bảng điều khiển
# nhúng `learned_at_utc` của trọng số.
#
# Sửa ở MỘT chỗ thay vì ở từng trình ghi: sau mỗi bước, `pipeline._run` gọi
# `keep_committed_when_only_stamps_changed`. Tệp JSON git đang theo dõi mà chỉ khác bản HEAD ở các khoá
# dấu giờ thì được ghi lại đúng từng byte của bản HEAD, TRƯỚC khi bước sau kịp đọc dấu giờ mới. Dấu giờ cũ
# vẫn đúng: nội dung này có từ lúc ấy.
#
# Chỉ khoá dấu giờ GHI được bỏ qua. Mọi khoá khác, kể cả ngày neo và ngày đích, phải trùng tuyệt đối;
# số thực được nới đúng mức nhiễu dấu phẩy động giữa các CPU runner (phần trên, ≤ 10⁻⁹ tương đối).
# Bảng CSV trong `data/` theo cùng luật nhiễu (`keep_committed_tables_when_only_noise_changed`): lượt chạy
# lại sau PR #223 ghi lại ba bảng chỉ vì bit cuối, lượt 09-11 hai mươi mốt bảng.

#: Khoá ghi «tệp này được ghi lúc nào». Thêm khoá mới thì thêm phép kiểm ghim nó vào một tệp thật.
WRITE_STAMP_KEYS = frozenset({
    "generated_at", "generated_at_utc", "learned_at_utc", "trained_at_utc", "evaluated_at_utc",
    "checked_at",
})

#: Tệp đã so và thấy đổi THẬT, theo (đường dẫn, mtime_ns, cỡ) lúc so. Pipeline gọi phép so sau mỗi bước
#: (~110 lần), và tệp đã đổi thật vẫn hiện trong `git status` tới cuối lượt: không nhớ thì mỗi lần gọi đọc
#: lại mọi tệp ấy (đo 14-11-2026: 0,55 s cho 70 tệp, 5,2 MB). Tệp bị ghi lại thì mtime đổi và được so lại.
_REAL_CHANGES: set[tuple[str, int, int]] = set()


def json_without_stamps(node: object, stamp_keys: frozenset[str] = WRITE_STAMP_KEYS) -> object:
    """Bản sao của một cây JSON, bỏ mọi khoá dấu giờ ở mọi tầng."""
    if isinstance(node, dict):
        return {key: json_without_stamps(value, stamp_keys) for key, value in node.items()
                if key not in stamp_keys}
    if isinstance(node, list):
        return [json_without_stamps(value, stamp_keys) for value in node]
    return node


def same_but_for_stamps_and_noise(old: object, new: object,
                                  stamp_keys: frozenset[str] = WRITE_STAMP_KEYS) -> bool:
    """Hai cây JSON chỉ khác nhau ở khoá dấu giờ và nhiễu số thực (thứ tự khoá không tính)."""
    return same_tree_up_to_float_noise(json_without_stamps(old, stamp_keys), json_without_stamps(new, stamp_keys))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)  # noqa: S603, S607


def _same_json_but_for_stamps(committed: bytes, current: bytes) -> bool:
    return same_but_for_stamps_and_noise(json.loads(committed), json.loads(current))


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
    """Trả mọi tệp JSON chỉ khác bản HEAD ở dấu giờ ghi và nhiễu số thực về đúng bản HEAD."""
    return keep_committed_when(repo, scope=scope, suffix=".json", same=_same_json_but_for_stamps)


def keep_committed_tables_when_only_noise_changed(repo: Path, scope: Iterable[str] = ("data", "models")) -> list[str]:
    """Trả mọi bảng CSV chỉ khác bản HEAD ở nhiễu số thực (kể cả thứ tự dòng gần hoà) về đúng bản HEAD.

    Gồm `models/train_report_<mode>.csv`: bước học ML ghi lại nó cùng lúc với pack mô hình.
    """
    return keep_committed_when(repo, scope=scope, suffix=".csv", same=same_table_up_to_float_noise)
