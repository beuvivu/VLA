# Soi cầu vị trí — giải mã luật của trang tham chiếu và kiểm chứng trên 4 217 kỳ

Ngày: 28-09-2026. Dữ liệu đến kỳ 28-09-2026, cầu cho kỳ 29-09-2026.

## 1. Luật — đã đối chiếu từng con số

Trang tham chiếu (một trang soi cầu công khai) bị proxy của môi trường phát triển chặn,
nên đọc qua runner Actions bằng `.github/workflows/inspect-reference-bridge.yml`. Mọi
điểm dưới đây được xác nhận bằng cách tái tạo đúng con số trang ấy in ra.

| Điểm | Luật |
|---|---|
| Vị trí | 107 chữ số, từ 0: ĐB 0–4, G1 5–9, G2 10–19, G3 20–49, G4 50–65, G5 66–89, G6 90–98, G7 99–106 |
| Cầu `a×b` | số `10·d[a] + d[b]` của kỳ hôm trước; lộn thì cả hai chiều và chỉ xét a < b |
| Không lộn | thứ tự có nghĩa (`95x74` ≠ `74x95`); trang tô chữ số thứ hai to hơn |
| Trúng LOTO | tổng số lần về của các số trong cặp ≥ số nháy — lộn thì CỘNG GỘP (45 + 54 = 2 nháy) |
| Trúng Đặc Biệt | hai số cuối giải ĐB nằm trong cặp |
| Độ dài | số KỲ QUAY liên tiếp gần nhất đều trúng |
| Số kép | là MỘT số; số bóng (0↔5, 1↔6, 2↔7, 3↔8, 4↔9: 44 → 99) chỉ hiện kèm |
| Tô màu | bảng mỗi kỳ tô chữ số ở vị trí cầu (xanh) và các số về theo cầu của KỲ TRƯỚC (vàng) |

Đối chiếu kỳ 29-09-2026:

| Chế độ | Trang tham chiếu | Bộ máy của kho |
|---|---|---|
| LOTO ≥ 5 ngày | 43 cầu, 18 dài hơn, 27 cặp, 16 cặp dài hơn | trùng |
| 2 nháy ≥ 3 ngày | 14 cầu (38x84 … 22x45), 11 cặp | trùng từng vị trí |
| Đặc Biệt ≥ 1 ngày | 132 cầu, 29 cặp, 47,74 có 18 cầu | trùng |
| LOTO không lộn ≥ 5 ngày | 7 cầu: 95x74 63x31 32x22 33x70 44x104 59x43 78x6 | trùng |
| Thống kê cầu lặp | 38,83 · 44 · 27,72 · 15,51 · 29,92 … | trùng thứ tự (hoà thì theo lần xuất hiện đầu) |

Tính số bóng vào phép trúng thì ra 64 cầu LOTO chứ không phải 43 — nên số bóng chỉ là
phần hiển thị. Trang tham chiếu không nói nó xếp ba ô "đẹp nhất" thế nào; kho dùng quy
tắc tự đặt và công khai: mỗi cặp số một cầu, xếp theo độ dài rồi số cầu cùng báo.

## 2. Cầu dài hơn có đáng tin hơn? — không

`position_bridges.streak_backtest`: với MỌI cặp vị trí, MỌI kỳ trong lịch sử, cầu đã
chạy k kỳ thì kỳ kế tiếp trúng bao nhiêu phần trăm. Kỳ vọng tính riêng số kép (một số,
dễ trượt) và số thường. z đếm mỗi kỳ là một cụm vì mọi cầu cùng kỳ dùng chung 27 giải.

| LOTO (1 nháy, lộn) | Số lần | Kỳ sau trúng | Kỳ vọng | z |
|---|---:|---:|---:|---:|
| 0 kỳ (vừa trượt) | 14 232 668 | 40,50% | 40,48% | +0,31 |
| 3 kỳ | 942 437 | 40,43% | 40,48% | −0,54 |
| 5 kỳ | 154 402 | 40,29% | 40,48% | −1,27 |
| 7 kỳ | 25 203 | 39,98% | 40,45% | −1,45 |
| ≥ 10 kỳ | 2 648 | 39,24% | 40,54% | −1,38 |

2 nháy và Đặc Biệt cho cùng một hình: không hàng nào (đủ mẫu) trúng nhiều hơn kỳ vọng
với z ≥ 3. Nhiều cầu cùng báo một cặp (`consensus_backtest`, đếm theo CẶP chứ không theo
cầu) cũng không hơn: cặp có 4–5 cầu LOTO trúng 41,1% so với kỳ vọng 41,4%.

Vì sao lúc nào cũng có nhiều "cầu đẹp": 5 671 cặp vị trí mỗi ngày, mỗi cặp trúng LOTO
~40% — trung bình mỗi ngày có 61 cầu LOTO chạy ≥ 5 ngày chỉ do ngẫu nhiên. Trang in
chính các bảng này, và kết luận trên trang được rút từ số đo mỗi lần dựng, không viết cứng.

Phép kiểm có đỏ được không: `test_the_backtest_finds_a_signal_when_one_is_planted` cài một
tín hiệu (50% kỳ chép y nguyên kỳ trước) và yêu cầu z > 4 ở k = 3; đo được z = 5,4.

## 3. Đã dựng

- `src/position_bridges.py` — bộ máy, ghi `data/position_bridges/latest.json` sau mỗi kỳ.
- `src/build_position_bridges.py` — trang `docs/soi-cau-vi-tri.html` và ô cạnh bảng LOTO.
- `src/templates/position_bridges.js` — bộ máy trình duyệt, cùng luật; trang đường cầu kiểu
  Sổ kết quả, bộ chọn số ngày, bảng vị trí cầu (bấm vị trí đậm → vị trí ghép màu đỏ).
- Pipeline chạy hai bước trên TRƯỚC trang chủ; ô trang chủ từ chối báo cáo của kỳ khác.
