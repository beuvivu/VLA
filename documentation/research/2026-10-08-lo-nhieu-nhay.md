# Lô nhiều nháy (≥ 2 nháy một kỳ) — bộ lọc VIP và phép đo trên 4 228 kỳ

Ngày 08-10-2026. Mã: `src/multi_hit_vip.py`. Phép kiểm: `tests/test_multi_hit_vip.py`.

## Kết luận

Trên 4 228 kỳ XSMB thật, chọn top-5 của bộ lọc (bốn lớp đặc trưng, trọng số tự tối ưu) trúng
"nhiều nháy" **2,89%** số lượt chọn, KTC95 2,67–3,13%. Chọn bừa trúng **2,97%**. Top-3: 2,91%.
Bộ lọc không hơn chọn bừa (p = 0,76). Phép đo đủ nhạy để thấy một lợi thế chỉ ×1,13, nên mức
15–25% (gấp 4–6 lần nền) mà đặc tả ban đầu đặt ra bị bác chắc chắn.

Bộ lọc không mù: trên lịch sử giả định có cài tín hiệu, nó đưa đúng ba con được cài lên top-3
và trúng 19,5% (×6,6, p ≈ 10⁻²⁰). Vì vậy kết luận "không có tín hiệu" là của dữ liệu, không phải
của công cụ đo.

Bộ lọc không vào pipeline và không có trang trên site. Theo luật đề bạt của kho, một mô hình chỉ
được đưa vào khi thắng cả dự báo hằng số, và bộ lọc này không thắng.

## Mức nền

Một kỳ có 27 lô, gần như đều trên 00–99. Số nháy của một con định trước là X ~ Binomial(27, 1/100):

    P(X ≥ 2) = 1 − 0,99²⁷ − 27 · 0,01 · 0,99²⁶ = 2,975 %

| Khẳng định trong đặc tả | Đo trên 4 228 kỳ |
|---|---|
| P(một con ≥ 2 nháy) ≈ 3,8–4,5% | 2,916% (lý thuyết 2,975%) |
| Mỗi kỳ có 21–23 số khác nhau | 23,83 (lý thuyết 100 · (1 − 0,99²⁷) = 23,77) |
| Lô gan > 10 kỳ thì nổ ≥ 2 nháy < 1,2% | 2,94%, KTC95 2,75–3,15% (n = 27 856) |
| Vừa ra 2 nháy trong 5 kỳ thì nên cộng điểm | 2,99%, KTC95 2,85–3,13% (n = 57 619) |

Gan và "vừa nổ" đều cho đúng mức nền. Không lớp nào trong bộ lọc được đặt luật cứng dựa trên hai
khẳng định ấy.

## Bộ lọc

Đặc trưng của kỳ t chỉ đọc các kỳ 0..t−1. Có phép kiểm canh luật này (xem mục Kiểm thử).

1. **Tần suất & điểm rơi.** Gồm tần suất trong 30 kỳ, đà về (EWMA 5 kỳ − EWMA 30 kỳ), độ dài
   chuỗi trúng và độ gan.
2. **Dị thường Poisson.** Lấy số kỳ ≥ 2 nháy trong cửa sổ, đổi ra điểm z so với kỳ vọng nhị
   thức. Kèm chỉ số phân tán var/mean − 1, bằng 0 với Poisson.
3. **Đồng xuất hiện.** Ước lượng P(i ≥ 2 nháy ở t | j về ở t−1), làm trơn Beta về mức nền, rồi
   lấy log-lift trung bình theo số nháy của các con đã về kỳ trước.
4. **Cầu nhịp.** Con số đã về 3–5 lần liên tiếp cùng khoảng cách, và kỳ t đúng là kỳ tiếp theo
   của nhịp ấy.

Cách chấm và chọn:

- **VIP Score.** VIP_Score = Σ wₖ · thành phầnₖ. Mỗi thành phần được chuẩn hoá chéo 100 số
  (z-score, hoặc min-max qua tùy chọn).
- **Chọn trọng số.** Trọng số chọn trên lưới đơn hình bước 0,1 (286 vector), bằng 30 kỳ ngay
  trước kỳ dự báo: ưu tiên số lần trúng top-k, hoà thì xét AUC.
- **Đánh giá.** Walk-forward lồng nhau: kỳ t được chấm bằng trọng số chọn trên [t − 30, t). Vì
  vậy tỉ lệ trúng báo ra không mang thiên lệch của phép chọn.
- **Xác suất hiển thị.** Hiệu chỉnh Platt trên các cặp (điểm, kết quả) ngoài mẫu. Không có tín
  hiệu thì xác suất về mức nền; kỳ tới (sau 07-10-2026), top-5 nhận 2,88–2,90%.
- **Confidence (High/Medium/Low).** Suy từ kiểm định nhị thức một phía của tỉ lệ trúng ngoài mẫu
  (High: p < 0,01; Medium: p < 0,05; cả hai đều đòi lift > 1). Một con chỉ tin được tới mức bộ
  lọc đã chứng minh.

## Kết quả

Walk-forward ngoài mẫu qua 4 168 kỳ (kỳ thứ 61 tới kỳ cuối):

| | Lượt chọn | Trúng | Tỉ lệ | Chọn bừa | Lift | p một phía |
|---|---|---|---|---|---|---|
| Top-5, trọng số tự tối ưu | 20 840 | 603 | 2,89% | 2,97% | ×0,97 | 0,76 |
| Top-3, trọng số tự tối ưu | 12 504 | 364 | 2,91% | 2,97% | ×0,98 | 0,67 |
| Top-5, trọng số cố định gần đặc tả (0,3/0,3/0,2/0,2) | 20 840 | 589 | 2,83% | 2,97% | ×0,95 | — |
| Top-5, trọng số tốt nhất **nhìn lại** | 20 840 | 682 | 3,27% | 2,97% | ×1,10 | — |

Dòng cuối chọn vector trọng số tốt nhất trên chính 4 168 kỳ kiểm, tức cố tình rò rỉ. Ngay cả gian
lận ấy cũng chỉ được 3,27%. Mức này là thiên lệch do chọn cái tốt nhất trong 286 vector, không
phải kỹ năng: chọn trên 30 kỳ trước rồi kiểm ngoài mẫu thì nó về 2,89%.

Độ nhạy: với 20 840 lượt chọn, α = 0,01 một phía và lực 80%, phép đo phát hiện được tỉ lệ thật
≥ 3,35% (lift ×1,13).

## Tái lập

    python3 src/multi_hit_vip.py --mock                          # 100 kỳ giả định, quay công bằng
    python3 src/multi_hit_vip.py --mock --plant                  # cài tín hiệu cho 07, 38, 68
    python3 src/multi_hit_vip.py --csv data/xsmb-2-digits.csv    # 4 228 kỳ thật, khoảng 20 giây
    python3 src/multi_hit_vip.py --csv data/xsmb-2-digits.csv --top-k 3 --json /tmp/vip.json

## Kiểm thử

`tests/test_multi_hit_vip.py` gồm 13 phép kiểm. Đã thử tám đột biến và cả tám đều đỏ:

- cửa sổ đặc trưng gồm cả kỳ đang dự báo (nhìn trước);
- cửa sổ chọn trọng số gồm cả kỳ t;
- cầu nhịp lệch một kỳ;
- đồng xuất hiện ghép cùng kỳ thay vì kỳ trước → kỳ sau;
- hiệu chỉnh bỏ qua điểm;
- Confidence không đòi lift > 1;
- hằng số bị chuẩn hoá thành khác 0;
- lưới trọng số thiếu đỉnh.

## Nếu muốn có trang "VIP"

Không in một con số như "Xác suất 2+ nháy: 28,5%". Nếu có trang, nó phải in từ phép đo, giống
`verdict` của trang soi cầu vị trí:

- tỉ lệ trúng ngoài mẫu;
- mức nền;
- khoảng tin cậy;
- Confidence suy từ kiểm định.

Trên dữ liệu hiện tại, mọi con đều nhận Confidence Low và xác suất sát 2,97%.
