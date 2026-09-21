from __future__ import annotations

"""Phần dùng chung của mọi trang: đường dẫn, ngày, cảnh báo, ghi trang."""

from pathlib import Path

from vla_design.data_access import Dataset, first, read_csv_rows, read_json_object
from vla_design.shell import Page, render_page

#: Câu cảnh báo THƯỜNG TRỰC. Xuất hiện trên mọi trang mang tính dự đoán.
#:
#: Ba cổng đo trên dữ liệu thật của kho đều không tìm được bằng chứng nào cho
#: thấy có thể đánh bại ngẫu nhiên; câu này là kết luận ấy nói ra thành lời,
#: không phải lời rào đón lấy lệ.
PREDICTION_DISCLAIMER = (
    "Mọi số liệu ở đây là THỐNG KÊ MÔ TẢ trên dữ liệu lịch sử. "
    "Không phải dự đoán có giá trị kỳ vọng dương, và không bảo đảm kết quả tương lai."
)

SIMULATION_DISCLAIMER = (
    "Bảng này là MÔ PHỎNG GIẢI TRÍ, KHÔNG PHẢI KẾT QUẢ THẬT. "
    "Mô hình chỉ ước lượng xác suất hai số cuối; các chữ số tiền tố được sinh tất định."
)


def health(data_dir: Path) -> Dataset:
    return read_json_object(Path(data_dir) / "health.json")


def latest_date(data_dir: Path) -> str:
    """Kỳ mới nhất trong kho, hoặc ``"—"`` nếu không đọc được.

    Không đoán bằng ngày hôm nay: một trang ghi ngày hôm nay trong khi dữ liệu
    dừng ở tuần trước là trang nói dối mà không ai kiểm được.
    """
    blob = health(data_dir)
    return str(first(blob).get("latest_date") or "—") if blob.ok else "—"


def write(docs_dir: Path, filename: str, page: Page, content: str) -> Path:
    out = Path(docs_dir) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_page(page, content), encoding="utf-8")
    return out


def latest_prediction_csv(data_dir: Path, mode: str) -> Dataset:
    """Bảng xác suất từng số của kỳ MỚI NHẤT, cho ``mode``.

    Chọn tệp theo thứ tự tên — tên mang ngày ISO nên sắp chuỗi là sắp thời
    gian. Không đoán tên bằng ngày hôm nay: một ngày chưa có tệp sẽ thành lỗi
    "không tìm thấy" trong khi thật ra chỉ là chưa chạy, và người đọc sẽ thấy
    lỗi hệ thống ở chỗ đáng lẽ là trạng thái rỗng.
    """
    folder = Path(data_dir) / "predict"
    files = sorted(folder.glob(f"predict_next_{mode}_all_*.csv"))
    if not files:
        return Dataset(
            "empty",
            source=f"data/predict/predict_next_{mode}_all_*.csv",
            reason="chưa có bảng xác suất nào",
        )
    return read_csv_rows(files[-1])
