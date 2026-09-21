from __future__ import annotations

"""Đọc hiện vật trong ``data/`` — FAIL-CLOSED, không bao giờ bịa.

Mục VIII của spec cấm thẳng: "Do not mask an actual data-loading bug with a
fabricated placeholder. Where no data genuinely exists, render a meaningful
Vietnamese empty state. Where data loading fails, expose a recoverable error
state."

Nên mọi hàm ở đây trả về :class:`Dataset` — một trong ba trạng thái, và trạng
thái là DỮ LIỆU chứ không phải ngoại lệ, để trang dựng được cả ba mà không cần
``try`` ở từng chỗ gọi:

* ``ok`` — có dữ liệu.
* ``empty`` — tệp tồn tại, đọc được, nhưng rỗng. Đây là sự thật về dữ liệu.
* ``error`` — tệp thiếu, hỏng, hoặc sai kiểu. Đây là sự thật về HỆ THỐNG, và
  nó phải hiện ra chứ không được lặng lẽ thành "chưa có dữ liệu".

Phân biệt ``empty`` với ``error`` là điểm chính của tệp này. Gộp hai thứ lại
thì một đường ống hỏng trông y như một ngày chưa có số liệu, và không ai đi
sửa.
"""

import csv
import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

State = Literal["ok", "empty", "error"]


@dataclass(frozen=True)
class Dataset:
    """Kết quả đọc một hiện vật dữ liệu.

    Attributes:
        state: ``ok``, ``empty`` hoặc ``error``.
        rows: Các bản ghi khi ``ok``; rỗng ở hai trạng thái kia.
        source: Đường dẫn tương đối, để ghi vào trang cho người đọc truy vết.
        reason: Lý do khi ``error`` — nói rõ thiếu gì, hỏng ở đâu.
    """

    state: State
    rows: tuple[dict[str, Any], ...] = ()
    source: str = ""
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.state == "ok"

    def __len__(self) -> int:
        return len(self.rows)


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return path.name


def read_json_rows(path: Path) -> Dataset:
    """Đọc một tệp JSON là DANH SÁCH bản ghi.

    Một tệp JSON hợp lệ nhưng là ``dict`` hoặc số thì KHÔNG phải rỗng — nó là
    sai kiểu, tức lỗi hệ thống, nên trả ``error``. Trả ``empty`` ở đó sẽ biến
    một hiện vật hỏng thành "hôm nay chưa có gì".
    """
    path = Path(path)
    if not path.exists():
        return Dataset("error", source=_relative(path), reason="không tìm thấy tệp")
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Dataset("error", source=_relative(path), reason=f"không đọc được: {exc}")
    if not isinstance(blob, list):
        return Dataset(
            "error",
            source=_relative(path),
            reason=f"cần danh sách bản ghi, nhận {type(blob).__name__}",
        )
    if not blob:
        return Dataset("empty", source=_relative(path))
    if not all(isinstance(row, dict) for row in blob):
        return Dataset("error", source=_relative(path), reason="có phần tử không phải bản ghi")
    return Dataset("ok", tuple(blob), source=_relative(path))


def read_json_object(path: Path) -> Dataset:
    """Đọc một tệp JSON là MỘT đối tượng; trả về nó như một bản ghi duy nhất."""
    path = Path(path)
    if not path.exists():
        return Dataset("error", source=_relative(path), reason="không tìm thấy tệp")
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Dataset("error", source=_relative(path), reason=f"không đọc được: {exc}")
    if not isinstance(blob, dict):
        return Dataset(
            "error",
            source=_relative(path),
            reason=f"cần đối tượng, nhận {type(blob).__name__}",
        )
    if not blob:
        return Dataset("empty", source=_relative(path))
    return Dataset("ok", (blob,), source=_relative(path))


def read_csv_rows(path: Path, *, limit: int | None = None) -> Dataset:
    """Đọc CSV thành bản ghi. ``limit`` cắt sau khi đọc, không cắt lúc đọc."""
    path = Path(path)
    if not path.exists():
        return Dataset("error", source=_relative(path), reason="không tìm thấy tệp")
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return Dataset("error", source=_relative(path), reason=f"không đọc được: {exc}")
    if not rows:
        return Dataset("empty", source=_relative(path))
    return Dataset("ok", tuple(rows[:limit] if limit else rows), source=_relative(path))


def first(dataset: Dataset) -> dict[str, Any]:
    """Bản ghi đầu tiên, hoặc ``{}`` nếu không có.

    Chỉ dùng cho hiện vật một-đối-tượng đã qua :func:`read_json_object`, nơi
    người gọi đã kiểm ``state`` trước.
    """
    return dict(dataset.rows[0]) if dataset.rows else {}


def number_text(value: Any, *, digits: int = 2) -> str:
    """Định dạng một con số 00-99 thành chuỗi hai chữ số.

    Trả ``"—"`` cho giá trị không phải số. Dấu gạch dài là quy ước "không có
    số liệu" của cả sản phẩm; trả ``"0"`` ở đây sẽ là bịa một con số.
    """
    try:
        return f"{int(value):0{digits}d}"
    except (TypeError, ValueError):
        return "—"


def decimal_text(value: Any, *, places: int = 2) -> str:
    """Số thập phân theo quy ước Việt Nam (dấu phẩy), hoặc ``"—"``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:  # NaN
        return "—"
    return f"{number:,.{places}f}".replace(",", " ").replace(".", ",")


def percent_text(value: Any, *, places: int = 2) -> str:
    """Phần trăm từ một tỉ lệ trong [0, 1], hoặc ``"—"``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:
        return "—"
    return f"{number * 100:.{places}f}".replace(".", ",") + "%"


def integer_text(value: Any) -> str:
    """Số nguyên có dấu phân nhóm nghìn kiểu Việt Nam, hoặc ``"—"``."""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def epoch_ms_text(value: Any) -> str:
    """Ngày từ epoch MILI-giây, hoặc ``"—"``.

    Một số hiện vật (``special_total_overdue``, ``special_cham_overdue``) ghi
    ``last_seen`` là epoch mili-giây chứ không phải chuỗi ISO như phần lớn tệp
    khác. In thô ra trang sẽ là ``1788480000000`` — một con số vô nghĩa mà
    người đọc không có cách nào hiểu.

    Chia 1000 rồi đọc theo UTC. Không đổi múi giờ: ngày xổ số là ngày theo
    lịch, và ép nó qua múi giờ địa phương sẽ lệch một ngày ở các mốc nửa đêm.
    """
    try:
        seconds = float(value) / 1000.0
    except (TypeError, ValueError):
        return "—"
    try:
        return datetime.datetime.fromtimestamp(seconds, tz=datetime.UTC).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return "—"
