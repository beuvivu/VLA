"""Lưu 10 số đứng đầu bảng Cầu Kèo theo ĐÚNG ngày quay mà chúng nhắm tới.

Trang chủ in khối "Đặc Biệt ngày mai" / "LOTO ngày mai" từ
``data/ai_ml/cau_keo_<mode>_top20.csv``, xếp theo ``cau_score`` giảm dần. Tệp ấy
bị ghi đè sau mỗi kỳ quay, nên tới lúc trang trực tiếp cần nó (trong phiên quay
của ngày D) hoặc sau đó, bảng đã chuyển sang ngày D + 1. Module này chụp 10 số
ấy vào ``data/ai_ml/daily/cau_keo_<mode>_top10_<ngày>.csv`` — khoá theo cột
``predict_for_date`` của chính bảng — để trang trực tiếp đọc đúng ngày.

Thứ hạng đi qua :func:`top_by_cau_score`, hàm trang chủ cũng dùng, nên hai nơi
không thể lệch nhau. Điểm cầu-kèo là thứ hạng 0–100 trong một kỳ, KHÔNG phải
xác suất đã hiệu chuẩn.

Chạy lại trước giờ quay thì bản của ngày ấy được ghi đè bằng bảng mới nhất —
đúng thứ trang chủ đang hiện. Sau kỳ quay bảng đã nhắm sang ngày sau, nên bản
của ngày đã quay không bị chạm tới nữa.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

from safe_io import read_csv_or_empty

MODES = ("de", "loto")
TOP = 10
DAILY_DIR = Path("ai_ml") / "daily"
FIELDS = ["predict_for_date", "rank", "number", "cau_score", "prob"]


def top_by_cau_score(df: pd.DataFrame, limit: int = TOP) -> pd.DataFrame:
    """``limit`` dòng có ``cau_score`` cao nhất; hoà thì giữ thứ tự trong tệp.

    Sắp xếp ỔN ĐỊNH (mergesort): ``quicksort`` mặc định của pandas không hứa giữ
    thứ tự các dòng hoà điểm, nên hai lần xếp cùng một bảng có thể ra hai top-10.
    """
    if df.empty or "cau_score" not in df.columns:
        return pd.DataFrame()
    score = pd.to_numeric(df["cau_score"], errors="coerce").fillna(0.0)
    order = score.sort_values(ascending=False, kind="mergesort").index
    return df.loc[order].head(limit)


def daily_path(data_dir: Path, mode: str, day: str) -> Path:
    return data_dir / DAILY_DIR / f"cau_keo_{mode}_top{TOP}_{day}.csv"


def write_daily_top(data_dir: Path, mode: str) -> Path | None:
    """Chụp top 10 hiện tại của ``mode``; trả đường dẫn đã ghi, hoặc ``None``."""
    table = read_csv_or_empty(
        data_dir / "ai_ml" / f"cau_keo_{mode}_top20.csv",
        dtype={"number_str": str, "predict_for_date": str},
    )
    if table.empty or "predict_for_date" not in table.columns:
        return None
    days = {str(v)[:10] for v in table["predict_for_date"].dropna()}
    if len(days) != 1:
        # Một bảng phải nhắm đúng một ngày; nhiều ngày lẫn nhau là tệp hỏng.
        raise ValueError(f"cau_keo_{mode}_top20.csv nhắm nhiều ngày: {sorted(days)}")
    (day,) = days
    top = top_by_cau_score(table)
    path = daily_path(data_dir, mode, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for rank, row in enumerate(top.to_dict("records"), 1):
            writer.writerow({
                "predict_for_date": day,
                "rank": rank,
                "number": f"{int(row['number_str']):02d}",
                "cau_score": row["cau_score"],
                "prob": row.get("prob", ""),
            })
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "data"))
    args = parser.parse_args()
    for mode in MODES:
        path = write_daily_top(Path(args.data_dir), mode)
        print(f"{mode}: {path if path else 'chưa có bảng cầu-kèo'}")


if __name__ == "__main__":
    main()
