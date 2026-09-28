# Vì sao cả 10 con LOTO kỳ 28-09-2026 đều đuôi 4 — và giả thuyết "đuôi nóng"

Ngày: 28-09-2026. Mọi con số dưới đây đo trên dữ liệu và artifact thật của kho.

## 1. Hiện tượng

Top 10 LOTO công bố cho kỳ 28-09-2026: **84 94 24 14 34 04 54 64 44 74** — cả 10 con
đuôi 4. Kỳ 29-09 còn 5/10 con đuôi 4. Các kỳ 21 → 27-09 nhiều nhất 2–5 con cùng đuôi.

## 2. Nguyên nhân — đã kiểm bằng thí nghiệm, không suy đoán

Lấy đúng các tệp thành phần trong commit đã sinh dự báo (`b6da3080`), đo từng thành phần
của tổ hợp:

| Thành phần | Đuôi 4 trong top 10 | z của đuôi 4 | Độ lệch chuẩn xác suất |
|---|---:|---:|---:|
| ml | 1 | −0,4 | 0,00031 |
| **cau** (mô hình cầu kèo) | **9** | **+7,9** | **0,00130** |
| stat | 2 | +1,4 | 0,00023 |
| active | 0 | −0,8 | 0,00120 |
| stable | 1 | −0,2 | 0,00084 |
| tổ hợp cuối | 10 | +6,9 | 0,00043 |

Thành phần cầu kèo mang trọng số lớn nhất (w_cau = 0,30) và phân tán gấp 4–5 lần các
thành phần khác, nên nó quyết định top 10.

Trong mô hình cầu kèo, ba đặc trưng có giá trị GIỐNG NHAU cho cả 10 con cùng đuôi:
`ones`, `share_tail_prev_special`, `tail_freq_7d`. Chạy lại đúng mô hình đã lưu của
kỳ ấy trên đặc trưng neo 27-09 cho lại đúng top 10 của thành phần (9/10 đuôi 4). Rồi san
phẳng từng đặc trưng (gán giá trị trung bình cho mọi con):

| San phẳng | Đuôi 4 trong top 10 |
|---|---:|
| không gì (gốc) | 9 |
| `ones` | 9 |
| `share_tail_prev_special` | 9 |
| **`tail_freq_7d`** | **2** |

`tail_freq_7d` = tổng số kỳ-về của 10 con cùng đuôi trong 7 kỳ gần nhất. Tới 27-09, đuôi 4
đứng hạng 1/10 (22). Mô hình học được "đuôi về nhiều gần đây → về tiếp", và vì cả 10 con
cùng đuôi nhận cùng giá trị, chúng lên top cùng nhau.

## 3. Đặc trưng ấy có sức dự báo không? — phản biện

So đuôi nóng với **trung bình các đuôi trong cùng kỳ** (không so với 1 − 0,99²⁷: kho thật
có trung bình 23,83 con khác nhau/kỳ, nhỉnh hơn kỳ vọng 23,77, nên mọi đuôi đều trên nền
một chút). p lấy bằng Monte Carlo trên 2 000 lịch sử công bằng cùng cỡ.

| Thống kê (đến 28-09-2026, 4 212 kỳ) | Chênh lệch | z | p hai phía |
|---|---:|---:|---:|
| Đuôi nóng 7 kỳ (hoà thì trung bình các đuôi hoà) | +0,456 điểm % | 2,43 | 0,011 |
| Đầu nóng 7 kỳ — **đối chứng** | +0,135 điểm % | 0,73 | 0,475 |

Theo từng tháng, phân bố chữ số cuối của 27 giải lệch khỏi đều nhiều hơn ngẫu nhiên (tổng
χ² 1 431 / 1 269 bậc tự do, p = 0,0009); chữ số đầu ít hơn (p = 0,036).

Hợp với giả thuyết chữ số cuối lệch nhẹ và trôi dần (bi/lồng mòn không đều) — nhưng **chưa
phải bằng chứng**:

- giả thuyết được đặt SAU khi thấy mô hình dồn vào nó;
- đã thử bốn cửa sổ (3, 7, 14, 30 kỳ; z = 1,79 / 2,10 / 3,56 / 0,77 với cách lấy một đuôi);
- hiệu ứng nhỏ: khoảng 2 % tương đối trên nền ~23,8 %.

## 4. Hai việc đã làm

**Giới hạn đuôi trong top LOTO** (`src/pick_diversity.py`): tối đa 3 con cùng đuôi, giữ
nguyên xác suất và thứ tự của mô hình. Áp dụng cho tệp top-4/8/10 (`predict_nextday_2d`)
và danh sách trang chủ (`run_daily_prediction`). Mười con cùng đuôi gần như là MỘT lần đặt:
kỳ nào đuôi ấy trượt thì cả nhóm trượt. Trên chính vector 28-09: cũ 84 94 24 14 34 04 54 64
44 74 → mới 84 94 24 25 67 68 61 46 97 31. Tệp `*_all` (nguồn chấm kỹ năng) không đổi; tệp
top đã công bố cho 29-09 giữ nguyên như đã công bố.

**Kiểm tiến cứu** (`src/hot_tail_test.py`), đăng ký ngày 28-09-2026 — tham số chốt trước
kỳ đầu tiên được chấm, có phép kiểm ghim để không thể sửa lặng lẽ:

| Tham số | Giá trị |
|---|---|
| Kỳ đầu được chấm | 29-09-2026 |
| Cửa sổ | 7 kỳ |
| Thống kê mỗi kỳ | tỉ lệ về của đuôi nóng − trung bình 10 đuôi, cùng kỳ |
| Kết luận sau | 180 kỳ |
| Kiểm định | z một phía ≥ 2,326 (α = 0,01) → xác nhận; còn lại → bác bỏ |

Sổ cái `data/hypotheses/hot_tail.csv` ghi mỗi kỳ một lần, lần ghi đầu giữ nguyên. Trạng thái
hiện trên trang Độ tin cậy dự báo. Muốn đổi tham số thì đăng ký một giả thuyết MỚI với ngày
bắt đầu mới — sửa giả thuyết này sau khi thấy kết quả là phá chính phép kiểm.
