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
- **Kiểm chứng 4 224 kỳ:** cả năm quy tắc ngang chọn bừa (|z| < 1). Câu "nổ như dự đoán" mà bài
  nào cũng có đến từ cách chấm theo KHUNG: hai chữ số đầu Đặc Biệt chấm cả tuần thì chọn bừa
  cũng "nổ" 78,5% số tuần.

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

## 4. Kiểm chứng lịch sử (4 224 kỳ, 01-01-2015 → 04-10-2026)

Mỗi quy tắc đọc kỳ t, chấm kỳ t + 1. Mốc là xác suất chính xác để một bộ chọn bừa CÙNG CỠ trúng
(LOTO: 1 − (1 − k/100)²⁷; Đặc Biệt: k/100; đầu/đuôi: k/10).

| Quy tắc | Trúng | Chọn bừa | z |
|---|---:|---:|---:|
| Đầu Đặc Biệt | 20,55% | 20,00% | +0,89 |
| Đuôi Đặc Biệt | 19,77% | 20,00% | −0,38 |
| Dàn đề chạm | 18,06% | 17,60% | +0,80 |
| Lô cặp G5 | 40,06% | 40,23% | −0,23 |
| Song thủ lô G2–G1 | 39,84% | 40,15% | −0,41 |

Chấm như bài viết — "nổ" nếu trúng ít nhất một lần trong cả khung:

| Quy tắc (khung) | Số khung | "Nổ" | Chọn bừa cũng "nổ" | z |
|---|---:|---:|---:|---:|
| Đầu ĐB (cả tuần) | 603 | 79,4% | 78,5% | +0,57 |
| Đuôi ĐB (cả tuần) | 603 | 76,8% | 78,5% | −1,03 |
| Dàn đề chạm (4 / 3 ngày) | 1 203 | 47,9% | 47,9% | −0,00 |
| Lô cặp G5 (2 / 3 ngày) | 1 203 | 70,7% | 70,9% | −0,14 |
| Song thủ lô (1 ngày) | 1 203 | 39,6% | 40,0% | −0,29 |

Phép đo không mù: trên lịch sử tổng hợp có cài "đầu ĐB kỳ sau = tổng 2 số cuối ĐB kỳ trước",
quy tắc trúng 100% và z > 20 (`test_backtest_finds_a_rule_that_really_works`).

## 5. Cách dùng trong kho

- `tong_hop_ky(kỳ)`: bảng điểm nhấn kỳ trước, đúng định nghĩa của bài, đếm từ bảng kết quả.
- `next_picks(raw)`: bộ số mỗi quy tắc cho kỳ kế tiếp — là MÔ TẢ quy tắc, không phải dự báo có
  kỹ năng.
- `backtest`, `frame_backtest`: chấm mọi quy tắc mới theo cùng mốc. Quy tắc nào muốn vào tổ hợp
  xác suất phải qua `scripts/benchmark_probability_models.py` và thắng CẢ hằng số LẪN mô hình đang
  chạy; năm quy tắc này không thắng hằng số nên không vào.
