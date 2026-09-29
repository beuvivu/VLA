# Bảy kiểu cầu vị trí của trang tham chiếu thứ hai — giải mã và kiểm chứng

Ngày: 29-09-2026. Dữ liệu đối chiếu đến kỳ 28-09-2026.

## 1. Cách đọc

Trang tham chiếu thứ hai bị proxy chặn nên đọc qua runner Actions
(`inspect-reference-bridge.yml`, 8 URL một lượt). Mỗi trang có một bảng "Đầu 0–9": ô
là một số hai chữ số, giá trị là số cầu đang chạy báo số ấy; kèm các bảng kết quả của
`count + 1` kỳ gần nhất, trong đó từng chữ số mang lớp `digit.<id>…` liệt kê mã các cầu
đi qua nó.

## 2. Luật — khớp từng ô

| Trang | Luật một bước t → t+1 | Số ngày | Tổng cầu | Khớp |
|---|---|---:|---:|---|
| Cầu LOTO | ab hoặc ba về | 3 | 315 | 90/90 ô, cầu dài nhất 8 |
| Cầu hai nháy | ab về ≥ 2, hoặc ab và ba cùng về | 2 | 24 | 22/22, dài nhất 3 |
| Cầu bạch thủ | đúng ab về | 3 | 66 | 47/47, dài nhất 6 |
| Cầu Đặc Biệt | a hoặc b trùng hàng chục/đơn vị hai số cuối ĐB | 2 | 741 | 86/86, dài nhất 6; xếp hạng cặp 34–43 84, 47–74 55 … trùng |
| Cầu bộ số | ab giữ nguyên trong một bộ | 2 | 32 | 21/21, đúng 32 cặp vị trí |
| Cầu Đặc Biệt theo thứ | như Đặc Biệt, chỉ các kỳ Chủ Nhật (mặc định trang ấy) | 3 | 179 | 50/50, dài nhất 7 |
| Cầu LOTO theo thứ | "tất cả các ngày" = Cầu LOTO | 3 | 315 | 90/90 |

Mọi kiểu dùng cặp vị trí a < b (5 671 cặp) và số `10·d[a] + d[b]`.

**Hai điểm phản trực giác, đều đã kiểm bằng dữ liệu:**

- Hai nháy bất đối xứng: nếu chỉ số lộn ba về hai nháy thì KHÔNG tính (thêm vế ấy thì
  bảng lệch khỏi trang tham chiếu; bỏ nó thì khớp 22/22 ô, không thừa cầu nào).
- Bộ số KHÔNG phải "ĐB kỳ sau rơi vào bộ của số cầu báo" (thử cách đó ra 43 cầu, sai 20/21
  ô). Dựng lại 32 cặp vị trí từ lớp `digit.<id>` thì thấy số của mỗi cặp giữ nguyên trong
  MỘT bộ suốt ba kỳ (cầu 9×46: 35 → 03 → 85, đều thuộc bộ 03). Luật "giữ bộ ≥ 2 bước" cho
  đúng 32 cầu, 21/21 ô, không thừa.

## 3. Cầu dài có đáng tin hơn? — không, ở cả bảy kiểu

`bridge_rules.backtest` trên toàn lịch sử (4 217 bước; các trang theo thứ gộp bảy chuỗi
thứ), kỳ vọng tính riêng số kép / bộ bốn số:

| Kiểu | k = 0 | k = 3 | k = 5 | k ≥ 10 | Kỳ vọng |
|---|---:|---:|---:|---:|---:|
| LOTO | 40,50% | 40,43% | 40,29% | 39,24% | ≈ 40,5% |
| Bạch thủ | 23,91% | 23,83% | 24,02% | 16,7% (12 lần) | 23,9% |
| Đặc Biệt | 34,63% | 34,18% | 33,13% | 34,80% | ≈ 34,5% |
| Bộ số (ĐB rơi vào bộ) | 7,21% | 8,23% | 10,2% (59 lần) | — | 7,2–8,0% |

Không hàng nào đủ mẫu (≥ 200 lần) vượt kỳ vọng với z ≥ 3. Mỗi trang in bảng của kiểu
mình và rút kết luận từ số đo mỗi lần dựng.

## 4. Đã dựng

- `src/bridge_rules.py` (bộ máy + kiểm lịch sử) → `data/bridge_pages/latest.json`.
- `src/build_bridge_pages.py` → bảy trang `docs/soi-cau-*.html` và `docs/tao-phoi-tuan.html`.
- `src/templates/bridge_pages.js`: bảng đầu 0–9; rê chuột tô mọi vị trí của các cầu báo
  số ấy trên các bảng kiểu Sổ kết quả; bấm để chọn từng cầu — tô hai chữ số nguồn ở mỗi
  kỳ, tô ô đã về theo cầu kỳ trước; biên ngày, số ngày cầu chạy, thứ, "cả hai chữ số".
- `src/templates/weekly_sheet.js`: phôi giải Đặc Biệt theo tuần (5–80 tuần), cỡ chữ và
  màu 3 chữ số đầu / 2 chữ số cuối, in được.
- Kỹ năng được ghi lại cho các phiên sau ở `.claude/skills/soi-cau/SKILL.md`.
