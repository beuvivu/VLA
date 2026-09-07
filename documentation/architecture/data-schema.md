# Data Schema — lịch sử KQXS Miền Bắc

Tài liệu này mô tả schema ĐANG DÙNG trong kho, đo trực tiếp từ dữ liệu chứ
không phải schema đề xuất. Ngày kiểm: 2026-09-07.

## 1. Bảng gốc — `data/xsmb.csv`

Nguồn sự thật duy nhất. Mọi bảng khác đều dẫn xuất từ đây.

| Thuộc tính | Giá trị |
|---|---|
| Số kỳ | **393** (2025-08-11 → 2026-09-07) |
| Số cột | 28 (`date` + 27 ô giải) |
| Tổng ô giải | 10 611 |
| Khoá chính | `date` (ISO `YYYY-MM-DD`, giờ Việt Nam) |

### 1.1 Cột và độ rộng chữ số

Cấu trúc XSMB: **27 ô giải, 107 chữ số**.

| Cột | Số ô | Độ rộng | Ghi chú |
|---|---|---|---|
| `special` | 1 | 5 | Giải đặc biệt |
| `prize1` | 1 | 5 | |
| `prize2_1..2` | 2 | 5 | |
| `prize3_1..6` | 6 | 5 | |
| `prize4_1..4` | 4 | 4 | |
| `prize5_1..6` | 6 | 4 | |
| `prize6_1..3` | 3 | 3 | |
| `prize7_1..4` | 4 | 2 | |

`1 + 1 + 2 + 6 = 10` ô × 5 chữ số, `4 + 6 = 10` ô × 4, `3` ô × 3, `4` ô × 2
→ `50 + 40 + 9 + 8 = 107` chữ số. **27 ô** là bất biến của bài toán.

### 1.2 CẢNH BÁO: cột lưu kiểu số nguyên, mất số 0 ở đầu

Đây là cái bẫy dễ gây lỗi nhất trong toàn bộ schema.

```
prize2_1 = 5225      # đọc từ CSV
                     # giá trị THẬT là "05225" — Giải nhì luôn 5 chữ số
```

Đo trên dữ liệu hiện tại: **1 096 / 10 611 ô (10,3%)** ngắn hơn độ rộng đúng.

Mọi nơi tiêu thụ dữ liệu **bắt buộc** đệm 0 theo độ rộng của giải trước khi
cắt chữ số:

```python
digits = df[col].astype(str).str.strip().str.zfill(WIDTH[base_prize])
two_digit = digits.str[-2:]        # chỉ đúng SAU khi đã zfill
```

Không zfill thì `05225` thành `5225`, và hai chữ số cuối vẫn ra `25` — đúng
tình cờ. Nhưng `00123` thành `123`, hai số cuối vẫn `23` — cũng đúng. Chỗ vỡ
là khi lấy chữ số theo **vị trí từ trái**, hoặc khi dựng tensor 107 chiều:
mọi vị trí sau đó lệch một ô.

Tham chiếu bản đã làm đúng: `src/ml_engine/schema.py`.

## 2. Bảng dẫn xuất

| Tệp | Nội dung | Sinh bởi |
|---|---|---|
| `data/xsmb-2-digits.csv` | 27 cột hai chữ số cuối mỗi kỳ | `src/lottery.py` |
| `data/xsmb-sparse.csv` | Ma trận nhị phân `(n_kỳ × 100)`, 1 = số về | `src/lottery.py` |
| `data/predictions_today.json` | Dự đoán kỳ kế tiếp | `src/pipeline.py` |
| `data/health.json` | Tình trạng dữ liệu và quy trình | `src/monitor_health.py` |
| `data/source_audit.json` | Đối soát giữa các nguồn | `src/live_sync.py` |

`data/` hiện chứa **857 tệp** artifact dẫn xuất.

### 2.1 Ma trận thưa — dạng chuẩn cho mọi mô hình

`xsmb-sparse` là dạng đầu vào của hầu hết thuật toán:

```
shape  : (n_kỳ, 100)
dtype  : int8
[t, k] = 1 nếu số k về ở kỳ t (kể cả về nhiều nháy), 0 nếu không
```

Tỉ lệ nền: một số bất kỳ về trong một kỳ với xác suất

```
P = 1 − (1 − 1/100)^27 ≈ 0.2377
```

Con số **0,2377** là mốc so sánh bắt buộc cho mọi mô hình lô tô. Mô hình nào
báo "độ chính xác 24%" mà không nói tới mốc này thì đang mô tả sự ngẫu nhiên.

## 3. Bất biến dữ liệu

Các ràng buộc được kiểm tự động; vi phạm là lỗi phát hành, không phải cảnh báo.

1. `date` duy nhất, tăng dần, không thiếu ngày trong khoảng đã công bố.
2. Đúng 27 ô giải mỗi kỳ, không thiếu ô nào.
3. Mỗi ô khớp `^\d{w}$` sau khi zfill theo độ rộng của giải.
4. Kỳ mới chỉ được ghi khi ≥ 2 nhóm nguồn **độc lập** khớp nhau
   (`src/sources.py::source_consensus_partial`).

## 4. Vì sao không dùng cơ sở dữ liệu server

Kho này phát hành dưới dạng **site tĩnh trên GitHub Pages**
(`.github/workflows/pages.yml`). Không có tiến trình server nào chạy: không
FastAPI, không Redis, không DuckDB thường trú.

Hệ quả cho bất kỳ đề xuất kiến trúc nào:

* Một backend FastAPI **không chạy được** trên GitHub Pages. Muốn có nó phải
  chọn nơi lưu trữ khác (Fly.io, Render, VPS) — đó là quyết định vận hành và
  chi phí, không phải quyết định kỹ thuật thuần tuý.
* Với 393 kỳ × 28 cột (56 KB), toàn bộ dữ liệu lịch sử **nhỏ hơn một ảnh
  chụp màn hình**. Nó nằm gọn trong bộ nhớ ở bất kỳ đâu, kể cả trong trình
  duyệt. Tầng cache Redis + DuckDB + memmap được thiết kế cho tập dữ liệu lớn
  hơn nhiều bậc; ở quy mô này nó thêm ba thành phần phải vận hành mà không
  giải quyết vấn đề nào đang có.
* Chi phí thật hiện nay không nằm ở truy vấn mà ở **thời điểm dữ liệu về**
  (xem `documentation/operations/on-time-trigger.md`).
