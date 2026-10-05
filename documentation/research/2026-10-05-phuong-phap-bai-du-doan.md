# Phương pháp của chuyên mục bài dự đoán XSMB tham chiếu — học, giải mã, kiểm chứng

Ngày: 05-10-2026. Nguồn: 10 bài (28-09 → 05-10-2026) của chuyên mục bài dự đoán XSMB mà chủ dự án
chỉ định, đọc toàn văn qua `.github/workflows/inspect-reference-articles.yml` (proxy của môi
trường phát triển chặn trang). Không lưu nội dung bài vào kho; chỉ ghi phương pháp.

Mã: `src/digit_sum_rules.py`. Phép kiểm: `tests/test_digit_sum_rules.py`. Số đo:
`data/research/digit_sum_rules.json` (tái lập: `PYTHONPATH=src python3 src/digit_sum_rules.py`).

## Tóm tắt

- Chuyên mục có **hai loạt bài**: loạt bài tuần (3 bài) viết rõ công thức; loạt bài hằng ngày
  (7 bài) chỉ gọi tên phương pháp.
- **Loạt bài tuần tái lập được 100%:** năm quy tắc "tổng – bóng – chạm" tính lại từ bảng kết quả
  của kho ra đúng từng con số trong bài. Chúng thành thuật toán riêng của kho.
- **Loạt bài hằng ngày không tái lập được:** số in ra không khớp chính phương pháp mà bài nêu.
- **Kiểm chứng 4 225 kỳ:** cả năm quy tắc ngang chọn bừa (|z| < 1, p Holm nhỏ nhất 0,966). Câu "nổ như dự đoán" mà bài
  nào cũng có đến từ cách chấm theo KHUNG: hai chữ số đầu Đặc Biệt chấm cả tuần thì chọn bừa
  cũng "nổ" 78,4% số tuần.

## 1. Cấu trúc chung của mọi bài

1. **Tổng hợp kỳ trước** ("điểm nhấn"): đề đầu, đuôi, tổng; lô kép; lô về ≥ 2 nháy; lô về cả cặp
   (bài ghi `080` = 08 và 80 cùng về); đầu, đuôi câm (không con nào); đầu, đuôi về nhiều nhất.
   Kho tính lại tự động: `tong_hop_ky`. Khi đối chiếu, chính bài có lỗi chép tay — kỳ 03-10 bài
   bỏ sót lô 68 về 2 nháy và ghi "câm đầu 2" trong khi đầu câm là 0.
2. **Thống kê** lô gan, cặp lô gan, đề gan (bài chỉ dẫn link, không có số).
3. **Chốt số.**
4. **Tổng kết** dạng bảng.
5. Mở bài bằng "thành quả" kỳ trước — chỉ liệt kê phần trúng.

## 2. Loạt bài tuần — năm quy tắc đã giải mã

Ký hiệu: `tổng(xy) = (x + y) mod 10`; `bóng(x) = (x + 5) mod 10`; cặp lộn của x, y là {xy, yx}
(bài ghi `xyx`). Mọi giải được đệm số 0 đủ độ dài (G5 `566` là `0566` — bỏ số 0 thì sai).

| Quy tắc | Công thức | Ví dụ khớp bài |
|---|---|---|
| Đầu Đặc Biệt | {tổng 2 số CUỐI ĐB, bóng} | 82951 → 51 → 6 → đầu 6–1 |
| Đuôi Đặc Biệt | {tổng 2 số ĐẦU ĐB, bóng} | 82951 → 82 → 0 → đuôi 0–5 |
| Chạm | {tổng 2 số cuối giải nhất, bóng} | 28235 → 35 → 8 → chạm 8–3 |
| Dàn đề chạm | mỗi chạm c ghép {cd, dc}, d ∈ 3 số đầu ĐB và bóng | 40208: chạm 8 → 848 898 808 858 828 878 |
| Lô cặp G5 | cặp lộn {tổng 2 số đầu G5.2, tổng 2 số cuối G5.4} | 7927, 2889 → 6, 7 → 676 |
| Song thủ lô | cặp lộn {tổng 2 số cuối G2.1, tổng 2 số đầu giải nhất} | 82614, 28235 → 5, 0 → 050 |

Khung trong bài: kỳ **Chủ Nhật** mở tuần mới (đầu – đuôi cả tuần, dàn chạm thứ Hai – thứ Năm,
lô G5 thứ Hai – thứ Ba, song thủ thứ Hai); kỳ **thứ Năm** mở khung cuối tuần (dàn chạm và lô G5
thứ Sáu – Chủ Nhật, song thủ thứ Sáu). Bài 05-10 có hai lỗi in: viết "chạm 8 và chạm 3" nhưng
liệt kê "Chạm 2", và `849` thay cho `848`. Kho theo công thức, không theo lỗi in. Riêng cặp
`404` (khung cuối tuần 02-10) không suy ra được từ quy tắc nào trong bài nên không đưa vào.

## 3. Loạt bài hằng ngày — không tái lập được

Mỗi bài chốt: bạch thủ lô (BTL) "theo cầu lô động chạy thường xuyên trong 7 ngày"; song thủ lô
(STL) "bắt các con lô rơi liên tiếp 3 ngày"; đầu – đuôi đề (luôn là cặp bóng); lô kép "từ giải
Đặc Biệt". Kiểm lại cả 7 bài trên dữ liệu thật:

- **BTL:** chỉ 1/6 ngày có một cầu vị trí (thẳng hoặc lộn) đã chạy ≥ 7 kỳ báo đúng số ấy. Xếp theo
  số lần trúng trong 7 kỳ của cầu tốt nhất, BTL đứng hạng 1–82 trên 100 — không phải số dẫn đầu.
- **STL:** hầu như không con nào trong cặp đã về liên tiếp 3 kỳ trước đó. Hai ngày (02-10, 05-10)
  STL chính là cặp lô của loạt bài tuần.
- **Đầu – đuôi đề:** không cặp vị trí nào trong 107 chữ số có tổng (mod 5) khớp cả 7 bài; một
  vị trí đơn lẻ cũng không.
- **Lô kép:** không khớp quy luật nào từ chữ số Đặc Biệt hay bóng của chúng.

Kết luận: số của loạt bài hằng ngày là lựa chọn của người viết, không phải phép tính tái lập
được. Chấm 6 kỳ đã có kết quả: BTL 2 (kỳ vọng ngẫu nhiên 1,4), STL 3 (4,0), đầu đề 0 (1,2), đuôi
đề 1 (1,2), lô kép 5 (2,5) — 6 kỳ quá ít để kết luận theo hướng nào.

## 4. Kiểm chứng lịch sử (4 225 kỳ, 01-01-2015 → 05-10-2026)

Mỗi quy tắc đọc kỳ t, chấm kỳ t + 1. Mốc là xác suất chính xác để một bộ chọn bừa CÙNG CỠ trúng
ở đúng kỳ ấy: Đặc Biệt k/100; đầu/đuôi k/10; LOTO 1 − C(100 − m, k)/C(100, k) với m là số con khác
nhau đã về ở kỳ được chấm (thay cho xấp xỉ 1 − (1 − k/100)²⁷). p một phía là đuôi Poisson-nhị thức
P(X ≥ trúng) — mỗi kỳ một xác suất riêng; p Holm hiệu chỉnh cho năm quy tắc kiểm cùng lúc.

| Quy tắc | Trúng | KTC Wilson 95% | Chọn bừa | z | p | p Holm |
|---|---:|---:|---:|---:|---:|---:|
| Đầu Đặc Biệt | 20,54% | 19,4–21,8% | 20,00% | +0,88 | 0,193 | 0,966 |
| Đuôi Đặc Biệt | 19,76% | 18,6–21,0% | 20,00% | −0,38 | 0,656 | 1,000 |
| Dàn đề chạm | 18,06% | 16,9–19,2% | 17,60% | +0,79 | 0,219 | 0,966 |
| Lô cặp G5 | 40,05% | 38,6–41,5% | 40,33% | −0,37 | 0,650 | 1,000 |
| Song thủ lô G2–G1 | 39,83% | 38,4–41,3% | 40,25% | −0,55 | 0,714 | 1,000 |

Chấm như bài viết — "nổ" nếu trúng ít nhất một lần trong cả khung:

| Quy tắc (khung) | Số khung | "Nổ" | Chọn bừa cũng "nổ" | z | p Holm |
|---|---:|---:|---:|---:|---:|
| Đầu ĐB (cả tuần) | 604 | 79,3% | 78,4% | +0,55 | 1,000 |
| Đuôi ĐB (cả tuần) | 604 | 76,7% | 78,4% | −1,05 | 1,000 |
| Dàn đề chạm (4 / 3 ngày) | 1 204 | 47,8% | 47,9% | −0,02 | 1,000 |
| Lô cặp G5 (2 / 3 ngày) | 1 204 | 70,7% | 71,1% | −0,29 | 1,000 |
| Song thủ lô (1 ngày) | 1 204 | 39,5% | 40,1% | −0,39 | 1,000 |

Phép đo không mù: trên lịch sử tổng hợp có cài "đầu ĐB kỳ sau = tổng 2 số cuối ĐB kỳ trước",
quy tắc trúng 100% và z > 20 (`test_backtest_finds_a_rule_that_really_works`).

### 4.1 Đối chiếu với bộ `xsmb_methods` (06-10-2026)

Chủ dự án gửi bộ mã `xsmb_methods` — một cài đặt độc lập của cùng năm quy tắc, kèm 500 kỳ dữ liệu
mẫu và báo cáo kiểm thử ngược. Đối chiếu:

- **Dữ liệu:** 500/500 kỳ (20-05-2025 → 05-10-2026) khớp từng chữ số với `data/xsmb.csv`.
- **Quy tắc:** hai cài đặt ra cùng bộ số ở cả 500 kỳ gốc × 6 đầu ra (0 lệch / 3 000 phép so).
- **Cách chấm:** kho lấy từ bộ ấy mốc có điều kiện theo số con đã về, p Poisson-nhị thức, khoảng
  Wilson và hiệu chỉnh Holm. Chạy trên đúng 500 kỳ ấy, kho in lại ĐÚNG từng số trong báo cáo của
  bộ ấy (số trúng, tỉ lệ, khoảng tin cậy, mốc, p, p Holm) —
  `test_the_500_draw_report_matches_the_independent_implementation` ghim.
- **Không lấy:** dữ liệu mẫu (kho có nguồn chuẩn riêng), lô gan / cặp lô gan (kho đã có trên
  trang Lô gan), lịch chấm khung chồng nhau (`window` > 1: p giả định độc lập không còn đúng — chính
  bộ ấy cũng cảnh báo).
- Kết quả của bộ ấy đáng chú ý nhất — dàn chạm nửa sau 22,3% so với 17,5%, p 0,022 — không còn ý
  nghĩa sau Holm (0,109) và biến mất trên toàn lịch sử (p 0,219). Đó đúng là loại tín hiệu chỉ phép
  kiểm tiến cứu mới phân xử được.

### 4.2 Kiểm tiến cứu: phần "tự học tích luỹ"

`src/digit_sum_hypothesis.py` đăng ký ngày 05-10-2026: từ kỳ 06-10-2026, mỗi lượt pipeline ghi bộ
số của năm quy tắc cho từng kỳ mới vào `data/hypotheses/digit_sum_rules.csv` (dòng đã ghi không bị
đè) và chấm với kết quả thật. Sau 180 kỳ: p một phía Poisson-nhị thức, Holm cho năm quy tắc,
α = 0,01. Kết luận chốt trên ĐÚNG 180 kỳ đầu rồi đóng băng — sổ ghi tiếp nhưng không tính lại,
vì tính lại mỗi ngày trên sổ dài dần là nhìn nhiều lần và phá α. Trang Độ tin cậy in trạng thái và bộ số kỳ kế tiếp (mô tả quy tắc, không phải dự báo).
Quy tắc được XÁC NHẬN vẫn phải qua `scripts/benchmark_probability_models.py` trước khi vào tổ hợp
xác suất. Không sửa tham số đã đăng ký; muốn đổi thì đăng ký giả thuyết mới.

## 5. Cách dùng trong kho

- `tong_hop_ky(kỳ)`: bảng điểm nhấn kỳ trước, đúng định nghĩa của bài, đếm từ bảng kết quả.
- `next_picks(raw)`: bộ số mỗi quy tắc cho kỳ kế tiếp — là MÔ TẢ quy tắc, không phải dự báo có
  kỹ năng.
- `backtest`, `frame_backtest`: chấm mọi quy tắc mới theo cùng mốc (kèm p, Wilson, Holm).
- `digit_sum_hypothesis.evaluate`: trạng thái phép kiểm tiến cứu, cộng dồn từng kỳ. Quy tắc nào muốn vào tổ hợp
  xác suất phải qua `scripts/benchmark_probability_models.py` và thắng CẢ hằng số LẪN mô hình đang
  chạy; năm quy tắc này không thắng hằng số nên không vào.
