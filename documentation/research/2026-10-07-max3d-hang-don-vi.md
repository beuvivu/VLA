# Max 3D / Max 3D Pro: số 6 ở hàng đơn vị — 07-10-2026

Engine Vietlott (`vietlott/`, chép từ VLM) báo e-value vượt ngưỡng 20 cho Max 3D
(10^2,57) và Max 3D Pro (10^2,84). Kỳ quay được coi là ngẫu nhiên, nên một kết quả "tốt
hơn ngẫu nhiên" phải được kiểm lại trước khi tin. Kết luận: **độ lệch là thật**. Nó
không do lỗi dữ liệu, cũng không do cách tính. Dù vậy mọi cửa Max 3D / Pro mà mô hình tính vẫn có kỳ vọng âm.

## Dữ liệu

`vietlott/data/seed/max3d.jsonl` (1 139 kỳ, 2019-04-22 → 2026-09-30) và
`max3d_pro.jsonl` (786 kỳ, 2021-09-14 → 2026-10-01), mỗi kỳ 20 số ba chữ số. Hai tệp:

- không có mã kỳ trùng, không thiếu mã kỳ nào;
- không có số sai định dạng (mọi số đủ 3 chữ số, kể cả số 0 đứng đầu);
- không có kỳ nào có kết quả trùng hệt một kỳ khác;
- tỉ lệ kỳ có số lặp trong cùng kỳ là 0,192 và 0,177, khớp với kỳ vọng 0,174.

## Tần suất chữ số theo vị trí (χ², 9 bậc tự do)

| Sản phẩm | Trăm | Chục | Đơn vị | Số trội ở đơn vị |
| --- | --- | --- | --- | --- |
| Max 3D | p = 0,34 | p = 0,037 | **p = 9·10⁻⁷** | 6: 10,89% |
| Max 3D Pro | p = 0,053 | p = 0,016 | p = 0,012 | 6: 11,06% |

Với số 6 ở hàng đơn vị, z ≈ 4,5 (Max 3D, n = 22 780) và z ≈ 4,4 (Pro, n = 15 720). Hai
sản phẩm có dữ liệu độc lập nhưng cùng lệch về một chữ số, ở cùng một vị trí, nên đây là
một lần lặp lại, không phải phát hiện chọn lọc sau khi nhìn dữ liệu. Chia mỗi chuỗi làm
sáu giai đoạn đều nhau thì tỉ lệ số 6 ở hàng đơn vị vượt 10,5% ở 5/6 giai đoạn của Max 3D
và ở 6/6 giai đoạn của Pro. Độ lệch không gói trong một giai đoạn thu dữ liệu nào. Tách
theo hạng giải (Đặc biệt, Nhất, Nhì, Ba) thì không hạng nào lệch rõ. Hàng chục và hàng
đơn vị độc lập với nhau (bảng 10×10, p = 0,36 và 0,30).

## Cách engine tính

`vietlott_engine.forecast.engine.Component.process` nhân tỉ số hợp lý của một hỗn hợp
chuyên gia (có chuyên gia "máy công bằng") với giả thuyết không "mọi chữ số đều, độc lập".
Đó là một e-process. Ngưỡng 20 áp lên đỉnh của đường wealth là hợp lệ ở mọi thời điểm
theo bất đẳng thức Ville. Max 3D chỉ có một thành phần, nên không có phép lấy max qua
nhiều phép thử.

## Hệ quả cho trang

RTP cao nhất theo mô hình là 0,59 (Max 3D) và 0,63 (Max 3D Pro), đều dưới 1. Câu viết
cứng "Kỳ quay đã kiểm là ngẫu nhiên; dự báo không làm tăng xác suất trúng" ở trang tổng
quan vì thế sai với Max 3D. Câu ấy nay được in TỪ SỐ ĐO
(`build_vietlott_results.randomness_summary`). Câu về kỳ vọng âm chỉ nói về các sản phẩm mà mô hình tính được RTP. Mega, Power và Lotto không có RTP trong phân tích, mà jackpot dồn hay chia giải có thể đẩy RTP của chúng vượt 1 (`vietlott/reports/vietlott_v3.md`).
