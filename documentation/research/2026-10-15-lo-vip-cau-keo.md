# Lô VIP: dự báo kỳ sau từ kinh nghiệm cầu kèo và cầu hai nháy (15-10-2026)

## Yêu cầu

Chủ dự án, về `docs/lo-vip-nhieu-nhay.html` sau khi trang chuyển sang luật lô rơi:

> Hiện tại trang chỉ thể hiện các con số về nhiều nháy trong ngày, không hề có phỏng đoán cho ngày
> hôm sau. Hãy dựa trên các dữ liệu và cả kinh nghiệm cầu kèo đưa ra dự báo tỉ lệ cao cho số ngày
> hôm tiếp theo về nhiều nháy thì mới gọi là lô VIP, chứ thống kê hôm nay thì ai chả xem được.

Lời phàn nàn đúng: luật lô rơi (`2026-10-15-lo-roi-ti-le-ky-sau.md`) chỉ liệt kê con vừa về và số
nháy hôm nay. Nó là một phép chọn, nhưng nhìn như thống kê.

## Kinh nghiệm cầu đo được trên toàn lịch sử

Mỗi con ở mỗi kỳ được ghi số cầu đang chạy báo nó; kỳ sau nó có về ≥ 2 nháy không. Dữ liệu là 4 175
kỳ neo × 100 con (từ 06-03-2015).

**Cầu hai nháy** (`bridge_rules`, kiểu `hai-nhay`, chạy ≥ 2 kỳ):

| Số cầu đang chạy báo con ấy | Lần | Kỳ sau ≥ 2 nháy |
|---|---|---|
| 0 | 325 633 | 2,94% |
| 1 | 67 803 | 2,81% |
| 2 | 18 030 | 2,83% |
| 3–4 | 5 553 | 2,90% |
| 5–9 | 479 | 3,97% (z = +1,36) |

**Cầu LOTO** (≥ 3 kỳ, báo cả số lộn): mọi nhóm từ 0 tới trên 11 cầu đều nằm trong 2,88–2,94%. Cầu dài
nhất cũng vậy: từ 3 kỳ tới trên 10 kỳ đều 2,87–2,93%.

**Kết luận:** không nhóm nào khác mức chung (2,92%) một cách có ý nghĩa thống kê. Nhóm 5–9 cầu hai
nháy chỉ có 479 lần, nên 3,97% vẫn nằm trong dao động ngẫu nhiên.

## Mô hình Lô VIP — `src/forecast/multi_hit_forecast.py`

### Đặc trưng

Có 42 đặc trưng, mọi đặc trưng của kỳ t chỉ đọc các kỳ ≤ t.

- **Kinh nghiệm cầu kèo:** mọi đặc trưng của `cau_keo_ml`, trừ 6 đặc trưng định danh và lịch.
  - Tần suất 3 → 365 kỳ, gan, lô rơi.
  - Quan hệ với Đặc Biệt: trùng, lộn, bóng, cùng đầu/đuôi/tổng, chạm.
  - Đường chữ số.
  - Xác suất chuyển sau Đặc Biệt và sau lô hôm nay.
  - Đầu/đuôi nóng 7 kỳ.
- **Cầu vị trí:** số cầu hai nháy (≥ 2 kỳ) và cầu LOTO (≥ 3 kỳ) đang chạy báo con ấy, cùng cầu dài
  nhất. Số cầu hai nháy khớp từng con với trang soi cầu hai nháy (phép kiểm so với `bridge_rules.find`).
- **Nhiều nháy:** số nháy hôm nay, có về ≥ 2 nháy hôm nay không, tỉ lệ kỳ ≥ 2 nháy, số kỳ ≥ 2 nháy
  trong 30 và 100 kỳ.

### Cách học và cách in

- **Mô hình:** hồi quy logistic, nhãn là "kỳ sau về ≥ 2 nháy".
- **Độ điều chuẩn:** chọn trên lưới 0,0001 / 0,001 / 0,01 / 0,1 bằng log-loss của 20% kỳ cuối trong
  phần huấn luyện.
- **Walk-forward:** học lại mỗi 250 kỳ trên mọi kỳ trước đó, khởi động 365 kỳ.
- **Xác suất in ra:** hiệu chỉnh Platt chỉ trên các lượt chọn ngoài mẫu của những khối TRƯỚC, nên
  "xác suất đã in" so được với tỉ lệ trúng thật.
- **Lý do mỗi con:** các tín hiệu có đóng góp dương lớn nhất, tức hệ số × giá trị đã chuẩn hoá.
- **Năm con công bố:** do chính mô hình và hiệu chỉnh của khối walk-forward đang chạy chọn, không phải
  một mô hình học lại trên mọi kỳ. Nhờ vậy khi kỳ ấy có kết quả, phần kiểm chứng (và e-process tiến
  cứu) chấm đúng năm con người đọc đã thấy (theo review Codex trên PR #171).
- **Kỳ được dự báo:** kỳ quay kế tiếp, bỏ qua ngày nghỉ đã khai trong `data/non_draw_days.json`. Đặc
  trưng cùng thứ / từ đầu tháng / từ đầu năm của kỳ ấy tính theo đúng ngày quay đó.
- **Đặc trưng cầu kèo:** `cau_keo_ml.build_cau_keo_feature_frame` nay nhận `raw`/`two` truyền vào,
  để phép kiểm chạy được trên lịch sử giả định. Bỏ trống thì vẫn đọc sổ thật như cũ.

## Kết quả (dữ liệu đến 15-10-2026)

| | Lô VIP | Chọn bừa cùng kỳ |
|---|---|---|
| Walk-forward 3 810 kỳ (khởi động 365 kỳ) | 569/19 050 = **2,99%** | 2,92% |
| z | +0,58 | — |
| Xác suất đã in, trung bình | 2,86% | — |

Thẩm định trong chọn C = 0,0001 (điều chuẩn mạnh nhất) ở 13/16 khối. Trên lát thẩm định, log-loss
hơn hằng số chỉ vài phần triệu, có khối còn kém hơn.

Dự báo cho kỳ 16-10-2026:

| Con | Xác suất | Lý do |
|---|---|---|
| 11 | 3,43% | bóng của Đặc Biệt 66, cùng tổng |
| 66 | 3,19% | về ≥ 2 nháy kỳ mới nhất, cùng tổng |
| 48 | 3,07% | cùng tổng, về 28/90 kỳ |
| 62 | 3,06% | đầu 6 nóng, cùng đầu với Đặc Biệt |
| 61 | 3,05% | đầu 6 nóng, cùng đầu với Đặc Biệt |

**Kết luận trung thực:** trang nay là phỏng đoán cho kỳ sau, dựng từ đúng dữ liệu và kinh nghiệm cầu
kèo chủ dự án muốn. Nhưng cả kinh nghiệm cầu lẫn mô hình gộp đều không đưa tỉ lệ về ≥ 2 nháy lên rõ
rệt trên mức chọn bừa. Vì thế:

- trang in xác suất đã hiệu chỉnh (khoảng 3%), không in "tỉ lệ cao";
- kết luận "hơn / không hơn chọn bừa" vẫn rút từ phép đo, và mức tin chỉ tính trên các kỳ quay sau
  ngày chốt (`FROZEN_AT`).

Luật lô rơi nghỉ cùng ngày; module `multi_hit_next_day.py` đã gỡ.

## Đã kiểm

- **`tests/test_multi_hit_forecast.py`** ghim:
  - cầu hai nháy và cầu LOTO đếm khớp `bridge_rules.find`;
  - không nhìn trước;
  - nhãn đúng kỳ sau;
  - mỗi khối chấm bằng mô hình chưa thấy nó;
  - hiệu chỉnh chỉ bằng các khối trước;
  - lịch sử cài tín hiệu bị bắt và xác suất in khớp thực tế;
  - thẩm định trong chọn đúng theo log-loss;
  - lý do là đóng góp dương lớn nhất;
  - kinh nghiệm cầu đếm đủ mọi kỳ;
  - số đo đã xuất bản là dự báo cho kỳ sau kỳ mới nhất.
- **`tests/test_multi_hit_page.py`:** chuyển sang mô hình mới. Thêm phép kiểm tiêu đề ghi kỳ dự báo,
  lý do từng con và dòng kinh nghiệm cầu.
- **17 đột biến** (15 trong mã, 2 trên chính `vip.json`) đều đỏ đúng chỗ.
