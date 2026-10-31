# Kiểm toán Lô VIP nhiều nháy — tính toán, thuật toán, xác suất, tính khả thi (31-10-2026)

## Yêu cầu

Chủ dự án: "Kiểm tra tính toán, thuật toán, xác suất và logic tính khả thi của phần lô VIP về nhiều
nháy, hiện hiệu quả thấp, rất thấp, hầu như không đạt yêu cầu hôm nào."

## Kết luận ngắn

1. **Không có lỗi tính toán.** Các phần sau đều đúng:
   - mức nền;
   - mốc chọn bừa;
   - phép chấm;
   - p luôn hợp lệ.

   Năm con đã công bố đúng là năm con được chấm. Đếm lại độc lập từ sổ kết quả cũng khớp.
2. **Thuật toán đúng quy trình, nhưng không có gì để học.**
   - Hồi quy logistic 42 đặc trưng gần như luôn chọn mức điều chuẩn mạnh nhất.
   - Nó không hơn dự báo hằng số trên lát thẩm định.
   - Kết quả: ngang chọn bừa cả theo lượt chọn lẫn theo kỳ.
3. **"Hầu như hôm nào cũng trượt" là bản chất xác suất, không phải lỗi.** Khi quay công bằng, MỌI
   cách chọn 5 con chỉ có 14,11% số kỳ có ít nhất một con về ≥ 2 nháy, tức khoảng 1 kỳ trong 7. Có
   2,1% số kỳ không con nào về ≥ 2 nháy, nên chọn cả 100 con cũng không "đạt" được mọi kỳ.
4. **Trang nay in thêm thước theo kỳ.** Ba số in cạnh nhau, đều đọc từ phép đo:
   - số kỳ đạt của mô hình;
   - số kỳ đạt của chọn bừa trên cùng các kỳ;
   - mức mọi cách chọn đạt được khi quay công bằng.

Tái lập: `python3 scripts/research/audit_multi_hit_vip.py` (dữ liệu đến 30-10-2026, 4 251 kỳ).

## 1. Tính toán

| Hạng mục | Kiểm | Kết quả |
|---|---|---|
| Mức nền một con | `base_rate` = P(X ≥ 2), X ~ Nhị thức(27; 1/100) | 2,9746%, đúng |
| Mốc chọn bừa theo lượt | siêu bội k·m/100 trên chính kỳ có m con ≥ 2 nháy | đúng |
| Năm con công bố = năm con được chấm | so sổ phỏng đoán `data/evaluation/prediction_board/` với `recent` của `vip.json` | 11/11 kỳ (21 → 31/10) khớp |
| Đếm lại độc lập | bộ đếm tự viết trên `xsmb-2-digits.csv`, không dùng mã của kho | 10 kỳ có sổ → 1 lượt trúng (con 69 kỳ 27/10), khớp |
| Không nhìn trước | mỗi khối 250 kỳ chỉ học trên các kỳ trước; hiệu chỉnh chỉ trên lượt chọn của khối trước | phép kiểm sẵn có xanh |
| p luôn hợp lệ | e-process với hệ số cược ≤ 0,8 | vốn không bao giờ âm vì kỳ vọng ≤ 0,65 |

## 2. Thuật toán

**Mô hình gần như hằng số.** Mô hình là hồi quy logistic trên 42 đặc trưng: kinh nghiệm cầu kèo,
cầu hai nháy, cầu LOTO và dữ liệu nhiều nháy. Độ điều chuẩn được chọn bằng log-loss trên 20% kỳ cuối
của phần huấn luyện. Qua 16 khối walk-forward:

- 12/16 khối chọn C = 0,0001, mức co mạnh nhất của lưới.
- Lợi log-loss so với hằng số nằm trong khoảng −4,7·10⁻⁵ đến +3,1·10⁻⁵ nats.
- 10/16 khối âm, tức thua hằng số.

Vì vậy thứ hạng 100 con gần như do nhiễu.

**Xác suất in ra không mang thông tin.** Xác suất in nằm trong 2,29–3,70%, quanh mức nền. Chia các
lượt chọn thành năm nhóm theo xác suất đã in, tỉ lệ trúng thật là 3,45 / 2,67 / 2,82 / 2,90 / 3,09%.
Dãy này không tăng đều theo xác suất in.

**Walk-forward 3 825 kỳ (10/03/2016 → 30/10/2026):**

| Thước | Mô hình | Chọn bừa cùng kỳ | z |
|---|---|---|---|
| Theo lượt (con về ≥ 2 nháy) | 571/19 125 = 2,99% | 2,91% | +0,60 |
| Theo kỳ (≥ 1 trong 5 con) | 546/3 825 = 14,27% | 13,84% | +0,79 |
| Tiến cứu sau 15/10 (15 kỳ) | 2 kỳ đạt | 1,59 kỳ | — |

**Năm 2026 là hồi cứu, không phải bằng chứng.** Riêng năm 2026 cho 19,7% so với 14,2%. Nhưng mô hình
được thiết kế ngày 15-10-2026 sau khi đã xem chính lịch sử ấy (`FROZEN_AT`). Mười năm còn lại dao
động 12,2–17,2% quanh mức chọn bừa.

**Cặp xiên 2 cũng vậy.** Hồi cứu 4 151 kỳ: 5,48% so với 5,52%. Tiến cứu: 3 lượt trúng so với 5,2
của chọn bừa.

## 3. Xác suất và trần khả thi

"Đạt" hiểu là kỳ có ít nhất một trong k con về ≥ 2 nháy.

Khi quay công bằng, xác suất ấy như nhau cho MỌI cách chọn k con, kể cả cách chọn dựa vào lịch sử.
Công thức đóng: không con nào trong k con về ≥ 2 nháy ⇔ đúng j lô rơi vào k con, mỗi lô một con
khác nhau. Ta có

P = 1 − Σⱼ C(27, j)·k·(k−1)…(k−j+1)·(100−k)^(27−j) / 100²⁷

(`multi_hit_vip.any_multi_chance`; trùng phép đếm thẳng trên xổ số tí hon).

| k con | Quay công bằng | Chọn bừa trên lịch sử thật | Số con trúng TB/kỳ |
|---|---|---|---|
| 1 | 2,97% | 2,91% | 0,030 |
| 3 | 8,69% | 8,52% | 0,089 |
| **5** | **14,11%** | **13,84%** | 0,149 |
| 10 | 26,46% | 25,98% | 0,297 |
| 20 | 46,60% | 45,84% | 0,595 |
| 50 | 81,31% | 80,47% | 1,487 |
| 100 | 97,91% | 97,62% | 2,975 |

Hệ quả:

- **Với 5 con, trung bình 6 trên 7 kỳ trượt.** Khoảng cách trung bình giữa hai kỳ đạt của mô hình
  là 7,0 kỳ. Chuỗi trượt dài nhất trong walk-forward là 60 kỳ. Với xác suất trượt 0,86 mỗi kỳ, chuỗi
  dài như vậy đủ hợp lý trên 3 825 kỳ.
- **Kỳ đạt chỉ tăng khi tăng số con.** Muốn đạt nửa số kỳ phải chọn khoảng 20 con. Xác suất của TỪNG
  con không đổi.
- **Không cách chọn nào đạt mọi kỳ.** 2,09% số kỳ (thực tế 2,38%) không con nào về ≥ 2 nháy.

## 4. Có cấu trúc nào để khai thác không

**Mức lặp thấp hơn lý thuyết, tức ngược hướng cần.** Mỗi kỳ có 2,914 con về ≥ 2 nháy, so với 2,975
theo lý thuyết (z = −2,91, sai số theo cụm kỳ). Chín trên mười hai năm thấp hơn lý thuyết.

**Chênh lệch giữa các con nhỏ.** Độ tản giữa 100 con bằng 1,18 lần nhị thức. Tương quan nửa đầu –
nửa sau là +0,19.

Giả sử phần chênh ấy là thật. Chọn 5 con có tỉ lệ lịch sử cao nhất, sau khi co theo độ tin cậy
0,18/1,18, thì mỗi con được thêm khoảng +0,1 điểm %. Kỳ đạt khi ấy lên khoảng 14,2%, so với 13,8%.

Lượt thử thứ hai đã kiểm đúng ý này («Nhiều kỳ ≥ 2 nháy nhất · toàn lịch sử»). Ở giai đoạn kiểm,
nó cho 3,26% (z = +1,31) và không đạt ngưỡng.

**Phụ thuộc giữa các kỳ ngang mức nền.** Tỉ lệ một con về ≥ 2 nháy ở kỳ sau:

| Kỳ này | Độ trễ | Tỉ lệ kỳ sau | z |
|---|---|---|---|
| Về ≥ 2 nháy | 1 | 3,10% | +1,23 |
| Về 1 nháy | 1 | 2,90% | −0,33 |
| Không về | 1 | 2,91% | −0,07 |
| Về ≥ 2 nháy | 2 | 2,79% | −0,80 |
| Về ≥ 2 nháy | 3 | 2,96% | +0,33 |
| Về ≥ 2 nháy | 7 | 2,91% | −0,03 |

**22 chiến lược của lượt hai đều không đạt.** Tương quan hạng giữa hai giai đoạn là −0,02.

## 5. Đề xuất — chủ dự án quyết

- **Mục tiêu "kỳ nào cũng có con về ≥ 2 nháy" không đạt được với 5 con, dù bằng mô hình nào.** Mức
  cao nhất là 14% số kỳ. Mô hình đang chạy đã ở đúng mức ấy. Thêm đặc trưng hay đổi sang mô hình phức
  tạp hơn sẽ chỉ khớp quá vào quá khứ, vì 22 chiến lược và logistic 42 đặc trưng đều ngang chọn bừa.
- **Muốn đạt nhiều kỳ hơn thì phải chọn nhiều con hơn.** 10 con cho 26% số kỳ, 20 con cho 47%. Hoặc
  đổi mục tiêu sang "về ≥ 1 nháy": top-5 đạt khoảng 74% số kỳ. Cả hai chỉ đổi cách đặt mục tiêu,
  không tăng xác suất của từng con.
- **Trang giữ nguyên mô hình** và in thước theo kỳ cạnh thước theo lượt, để người đọc thấy mức mà
  mọi cách chọn đều chỉ đạt được.

## Thay đổi đi kèm

- `multi_hit_vip.any_multi_chance` (trần theo kỳ, chính xác) và `random_any_hit` (mốc chọn bừa
  theo kỳ, siêu bội).
- `vip.json` lên phiên bản 10. Phần `backtest` có thêm `days_hit`, `day_rate`, `day_random_rate`,
  `day_z`, `day_fair`; phần `prospective` có thêm `days_hit`, `days_expected`.
- Trang `docs/lo-vip-nhieu-nhay.html` có thêm dòng «Kỳ có ít nhất một trong 5 con về ≥ 2 nháy».
- Phép kiểm:
  - `test_the_any_multi_chance_counts_every_fair_draw_exactly`: đếm thẳng mọi kỳ của xổ số tí hon.
  - `test_random_any_hit_is_the_hypergeometric_zero_complement`.
  - `test_the_day_measure_counts_draws_where_any_pick_came_twice`.
  - `test_the_page_prints_the_day_measure_from_the_measurement`.
- Đột biến: 6/6 làm phép kiểm tương ứng đỏ.
  - `perm` → `comb`;
  - siêu bội sai;
  - kỳ đạt cần 2 lượt;
  - trần giả định các con độc lập: 1 − (1 − p)⁵ = 14,03% thay cho 14,11%;
  - in sai mốc;
  - in số lượt thay cho số kỳ.
