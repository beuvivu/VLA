"""Định dạng mã xổ số tại biên hiển thị và xuất CSV, không đổi phép tính."""

from __future__ import annotations

import argparse
import csv
import io
import math
from numbers import Integral, Real
from pathlib import Path

import numpy as np
import pandas as pd

from core.excel_export import FIELD_WIDTHS


def lottery_code(value: object, width: int = 2) -> str:
    """Giữ ô thiếu là rỗng, nhận số nguyên hợp lệ và trả mã đủ độ rộng."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return ""
        if not value.isascii() or not value.isdigit() or len(value) > width:
            raise ValueError(f"Mã không hợp lệ cho {width} chữ số: {value!r}")
        number = int(value)
    elif isinstance(value, bool):
        raise ValueError("Giá trị đúng/sai không phải mã xổ số")
    elif isinstance(value, Integral):
        number = int(value)
    elif isinstance(value, Real) and math.isfinite(value) and float(value).is_integer():
        number = int(value)
    else:
        raise ValueError(f"Mã xổ số phải là số nguyên: {value!r}")
    if not 0 <= number < 10 ** width:
        raise ValueError(f"Mã nằm ngoài miền {width} chữ số: {value!r}")
    return f"{number:0{width}d}"


def csv_code_widths(path: Path, headers: list[str]) -> dict[str, int]:
    """Chỉ chọn cột mã đã biết; đầu/đuôi, số đếm, hạng và xác suất là số đo."""
    names = {
        "number", "number_str", "value_str", "a_str", "b_str",
        "prev_loto", "next_loto", "prev_special_2d", "next_special_2d",
        "reverse", "bong_duong", "bong_am", "cap_loto_50_partner",
        "bo_seed_label", "bo_family_id", "canonical_family_id", "seed_label",
    }
    widths = {name: 2 for name in headers if name in names}
    if "value_str" in headers:
        widths["value"] = 2
    if any(name in headers for name in ("pair", "pair_id", "a_str", "b_str")):
        widths.update({name: 2 for name in ("a", "b", "x", "y") if name in headers})
    if path.name in ("xsmb.csv", "xsmb-2-digits.csv"):
        widths.update({name: 2 if path.name == "xsmb-2-digits.csv" else width
                       for name, width in FIELD_WIDTHS.items() if name in headers})
    if path.parent.name == "conditional" and "special" in headers:
        widths["special"] = 2
    if path.parent.name == "number_dynamics" and "source" in headers:
        widths["source"] = 2
    return widths


def write_code_csv(frame: pd.DataFrame, path_or_buf=None, **kwargs):
    """Ghi bản sao có mã dạng text; giữ nguyên kiểu và giá trị khung tính toán.

    Giữ giao diện xuất CSV của pandas, kể cả chuỗi trả về cho bộ ghi nguyên tử.
    """
    path = Path(path_or_buf) if isinstance(path_or_buf, (str, Path)) else Path(
        getattr(path_or_buf, "name", "export.csv")
    )
    widths = csv_code_widths(path, list(frame.columns))
    output = frame.copy()
    for name, width in widths.items():
        if name in output:
            output[name] = code_column(output[name], width)
    return output.to_csv(path_or_buf, **kwargs)


def code_column(series: pd.Series, width: int) -> pd.Series:
    """Đúng bằng ``series.map(lambda v: lottery_code(v, width))``, nhưng mỗi giá trị khác nhau chỉ định dạng MỘT lần.

    Bảng thống kê có hàng triệu ô mà chỉ vài trăm mã khác nhau; gọi
    ``lottery_code`` từng ô từng chiếm 12,5 trong 41 giây của
    ``statistical_matrices``. Cột số (nguyên/thực) đi qua ``pd.factorize``:
    mọi phần tử cùng một kiểu nên hai giá trị bằng nhau cho cùng một mã. Cột
    ``object`` có thể trộn ``True`` với ``1`` — bằng nhau theo ``==`` nhưng
    ``lottery_code`` nhận cái sau và từ chối cái trước — nên khoá bộ nhớ đệm
    gồm cả KIỂU của giá trị.
    """
    if pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype):
        codes, uniques = pd.factorize(series, use_na_sentinel=True)
        table = np.array([lottery_code(value, width) for value in uniques] + [""], dtype=object)
        # Mã -1 (ô thiếu) trỏ vào phần tử cuối: chuỗi rỗng, như lottery_code(NaN).
        return pd.Series(table[codes], index=series.index, name=series.name, dtype=object)
    cache: dict[tuple[type, object], str] = {}
    out = np.empty(len(series), dtype=object)
    for i, value in enumerate(series.to_numpy(dtype=object)):
        try:
            key = (type(value), value)
            out[i] = cache[key]
        except KeyError:
            out[i] = cache[key] = lottery_code(value, width)
        except TypeError:  # giá trị không băm được: để lottery_code tự từ chối
            out[i] = lottery_code(value, width)
    return pd.Series(out, index=series.index, name=series.name, dtype=object)


def normalize_csv(path: Path) -> bool:
    """Sửa riêng mã số bằng bộ đọc chuỗi; giữ nguyên mọi chữ số của số đo.

    Không đi qua suy kiểu pandas nên không làm tròn xác suất hoặc đổi ô rỗng.
    Kiểm toàn bộ trước khi thay tệp và không ghi lại tệp đã đúng định dạng.
    """
    text = path.read_text(encoding="utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return False
    headers = rows[0]
    widths = csv_code_widths(path, headers)
    indices = [(headers.index(name), width) for name, width in widths.items() if name in headers]
    changed = False
    for line, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        for index, width in indices:
            if index >= len(row):
                raise ValueError(f"{path}: dòng {line} thiếu cột {headers[index]}")
            try:
                code = lottery_code(row[index], width)
            except ValueError as exc:
                raise ValueError(f"{path}: dòng {line}, cột {headers[index]}: {exc}") from exc
            changed |= row[index] != code
            row[index] = code
    if changed:
        target = path.with_suffix(path.suffix + ".tmp")
        with target.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, lineterminator="\n").writerows(rows)
        target.replace(path)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Giữ số 0 đầu các mã trong CSV xuất bản")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    changed = sum(normalize_csv(path) for path in sorted(args.data_dir.rglob("*.csv")))
    print(f"Đã chuẩn hóa mã số trong {changed} tệp CSV")


if __name__ == "__main__":
    main()
