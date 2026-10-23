# Lô rơi nhiều nháy — chọn theo tỉ lệ về ≥ 2 nháy ở kỳ sau (15-10-2026)

> Cập nhật cùng ngày: luật lô rơi đã nghỉ khỏi trang. Nó chỉ liệt kê con vừa về nên trông như thống kê
> hôm nay, không phải phỏng đoán. Trang nay in dự báo kỳ sau của mô hình Lô VIP (kinh nghiệm cầu kèo,
> cầu hai nháy, dữ liệu nhiều nháy), xem `2026-10-15-lo-vip-cau-keo.md`. Module `multi_hit_next_day.py`
> đã gỡ; các số đo dưới đây vẫn đúng và được giữ làm lịch sử.

## Yêu cầu

Chủ dự án, về trang `docs/lo-vip-nhieu-nhay.html`: "bảng này sai hoàn toàn mục đích, toàn lựa chọn
những con số khan và không có khả năng về, tôi muốn có những con số tỉ lệ về ngày hôm sau trên 2 nháy
cao".

## Chẩn đoán: bộ lọc VIP đẩy con gan lên đầu

Tái hiện walk-forward của bộ lọc VIP (`src/forecast/multi_hit_vip.py`) cho mười kỳ 06 → 15-10-2026.

**Con 32 đứng đầu cả mười kỳ.** Trong suốt mười kỳ ấy, 32 không về một nháy nào:

- độ gan tăng từ 10 lên 19 kỳ;
- tần suất 0,27–0,30 nháy/kỳ, ngang mức chung 27/100 = 0,27;
- thành phần "dị thường Poisson" của 32 đứng ở +4,3 đến +4,8 độ lệch chuẩn, cao nhất trong 100 con.

**Thủ phạm là chỉ số phân tán.** Chỉ số phân tán = phương sai/trung bình của số nháy − 1, tính trên
cửa sổ 30 kỳ. Một con về đúng một lần với 2 nháy trong 30 kỳ có phân tán +0,93. Một con về đều mỗi lần
1 nháy có phân tán âm. Tức là chỉ số này thưởng cho con về thưa nhưng dồn cục — đúng loại con người
chơi gọi là "khan".

Hai con đi kèm, 92 và 19, cũng là con có hai đến ba kỳ ≥ 2 nháy trong cửa sổ rồi im.

**Trọng số đổi theo nhiễu.** Mỗi ngày bộ lọc chọn lại trọng số trong 286 vector, trên đúng 30 kỳ
(150 lượt chọn, trung bình 4–5 lượt trúng). Vì vậy trọng số nhảy giữa các ngày:

| Ngày | Trọng số |
|---|---|
| 06/10 | (0; 0,8; 0,2; 0) |
| 08/10 | (0,2; 0,5; 0,3; 0) |
| 15/10, cho kỳ tới | (0,9; 0; 0; 0,1) |

**Kết quả của bộ lọc:**

| Phạm vi | Bộ lọc VIP | Chọn bừa cùng kỳ |
|---|---|---|
| 10 kỳ trên trang | 0/50 lượt | 1,70 lượt kỳ vọng |
| 4 176 kỳ walk-forward | 2,90% | 2,91% |
| Tiến cứu sau 12-10-2026 (3 kỳ) | 0 lượt | 0,55 lượt kỳ vọng |

Tiến cứu dừng ở đây vì bộ lọc nghỉ.

## Số đo: tỉ lệ về ≥ 2 nháy ở kỳ sau

Đếm trên mọi cặp kỳ liên tiếp của `data/xsmb-2-digits.csv`, 4 236 kỳ đến 15-10-2026, 100 con mỗi kỳ:

| Kỳ này con số… | Kỳ sau về ≥ 2 nháy | Tỉ lệ |
|---|---|---|
| về ≥ 2 nháy | 384 / 12 353 | **3,11%** |
| về 1 nháy | 2 565 / 88 554 | 2,90% |
| không về | 9 404 / 322 593 | 2,92% |

**Nhóm "về ≥ 2 nháy" cao nhất, nhưng không có ý nghĩa thống kê.** So với mức chung 2,917%, z = +1,27.
Chiều chênh lệch giữ nguyên qua hai giai đoạn:

| Giai đoạn | Tỉ lệ của nhóm |
|---|---|
| Phát triển 2016-09 → 2024-01 | 3,38% |
| 1 000 kỳ cuối | 3,09% |

Lượt thử thứ hai (12-10-2026) đã chọn trước chính ý này ("Lặp số nháy kỳ trước") trên giai đoạn phát
triển: kiểm một lần cho 3,08% so với 2,95%, p = 0,293.

**Xu hướng riêng của từng con chỉ cỡ dao động ngẫu nhiên.** Phương sai giữa 100 con của tỉ lệ kỳ về
≥ 2 nháy bằng 0,98 lần phần mà dao động nhị thức tự sinh ra. Tương quan giữa hai nửa lịch sử là +0,19.
Mười con cao nhất ở nửa đầu (3,53%) chỉ còn 3,28% ở nửa sau, trong khi mức chung là 2,95%.

## Luật thay thế: `src/multi_hit_next_day.py`

1. Chỉ xét các con đã về ở kỳ mới nhất. Con không về không được chọn, nên không còn con "khan".
2. Nhóm của một con là số nháy của nó ở kỳ ấy: 0, 1 hay ≥ 2. Tỉ lệ của nhóm là số đếm ở bảng trên,
   cập nhật mỗi kỳ.
3. Xu hướng riêng là tỉ lệ kỳ về ≥ 2 nháy của con trên toàn lịch sử, co về mức chung theo Bayes thực
   nghiệm. Độ co ước lượng bằng phương pháp mômen; hiện trọng số của xu hướng riêng là 0,13.
4. Xác suất = xu hướng riêng × hệ số nhóm. Hệ số nhóm = số lần quan sát / số lần kỳ vọng theo xu hướng
   riêng của các con trong nhóm, với tiên nghiệm 10 lần đúng như kỳ vọng.

   Nhân thẳng tỉ lệ thô của nhóm thì đếm hai lần, vì con có xu hướng cao cũng hay rơi vào nhóm ≥ 2
   nháy. Trên lịch sử cài tín hiệu (120 kỳ):

   | Cách tính | Xác suất trung bình đã in | Tỉ lệ trúng thật |
   |---|---|---|
   | Nhân thẳng | 18,96% | 10,67% |
   | Chia kỳ vọng | 10,83% | 10,67% |

5. Hoà thì xếp theo hoán vị cố định của kỳ (`tie_keys`).

Mọi đại lượng của kỳ t chỉ đọc các kỳ < t. Bước đo mất 6 giây trên 4 236 kỳ, so với khoảng 25 giây
của bộ lọc VIP.

## Kết quả walk-forward (mô tả hồi cứu)

| | Luật lô rơi | Chọn bừa cùng kỳ |
|---|---|---|
| 4 206 kỳ (31/01/2015 → 15/10/2026) | 639/21 030 = **3,04%** | 2,91% |
| Xác suất đã in, trung bình | 2,92% | — |
| z, p một phía | +1,09, 0,137 | — |
| 10 kỳ gần nhất | 3/50 lượt | 1,70 lượt kỳ vọng |

Xác suất in ra khớp tỉ lệ trúng thật (2,92% so với 3,04%). Trang vì thế không hứa hơn mức đo được.

**Tỉ lệ cao hơn chọn bừa chưa có ý nghĩa thống kê.** Luật được thiết kế sau khi đã xem lịch sử đến
15-10-2026 (`FROZEN_AT`), nên mức tin chỉ tính trên các kỳ quay sau ngày ấy, bằng p luôn hợp lệ như
trước.

**Kết luận trung thực:** không cách chọn nào đã đo đưa tỉ lệ về ≥ 2 nháy lên rõ rệt trên 2,9%. Luật
này sửa đúng điều chủ dự án chỉ ra — không còn chọn con không về — và in con số thật thay cho lời hứa.

## Đã kiểm

- **`tests/test_multi_hit_next_day.py`** (13 phép kiểm) ghim:
  - không nhìn trước;
  - số đếm nhóm khớp phép đếm thẳng mọi cặp kỳ;
  - hệ số nhóm không đếm hai lần;
  - độ co trên lịch sử công bằng và lịch sử cài tín hiệu;
  - chỉ chọn con vừa về;
  - thứ tự hoà;
  - số đo đã xuất bản: năm con và mười kỳ gần nhất đều là con đã về ở kỳ trước.
- **`tests/test_multi_hit_page.py`**: dải số in xác suất và số nháy vừa về; dòng tỉ lệ nhóm in đúng
  phân số; ô "Xác suất đã in" đặt cạnh tỉ lệ trúng thật.
- **17 đột biến** đều đỏ đúng chỗ.
- Kỳ có ít hơn 5 con khác nhau bị từ chối thẳng (`multi_hit_next_day.picks`) thay vì lấp chỗ trống
  bằng con không về. Lịch sử thật không có kỳ nào như vậy: ít nhất 15 con khác nhau trên 4 236 kỳ.
