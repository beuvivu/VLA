# Bộ máy Bayes theo đoạn cho lồng chục và lồng đơn vị

Ngày 24-11-2026. Mã: `src/forecast/cage_bayes.py`. Số đo: `data/forecast/cage_bayes/summary.json`. Phép
kiểm tiến cứu: `data/research/hypotheses/cage_bayes.json` (đăng ký) và `cage_bayes.csv` (sổ chỉ nối thêm).
Thẻ «Bộ máy Bayes theo đoạn» trên `docs/research-lab.html` in kết quả từ tệp số đo.

## Câu hỏi

Chủ dự án yêu cầu «đầu tư chuyên sâu, nâng cấp thuật toán AI và ML lên một tầm cao mới».

## Hiện trạng trước đợt này

Sổ đăng ký mô hình ngày 23-11-2026 (`data/evaluation/model_registry/registry.json`) cho thấy mọi thành phần
học đều ở mức nền hoặc sát nền:

- ML thành phần có trust 0,17%; Cầu Kèo LOTO có trust 0,18%.
- Xếp chồng và hiệu chỉnh bị cổng chặn; trọng số tổ hợp giữ vector mặc định.
- Kỹ năng của xác suất đã công bố trên 87 kỳ có khoảng tin cậy chứa 0.

Một máy quay công bằng phải cho đúng kết quả ấy, nên thêm một mô hình phức tạp nữa trên cùng đặc trưng sẽ không
đổi gì.

Chỗ duy nhất có thể kiếm lời thật là khi máy quay **không** công bằng. Ngày 23-11-2026 kho xác nhận một trường
hợp như thế: độ lệch lồng đơn vị 20-04 → 24-11-2024 nằm trong kết quả công bố, và 306 kỳ trùng từng ô với hai
nơi ghi khác (`documentation/research/2026-11-23-dai-quay-mien-bac.md`).

## Dư địa đo được

Trần lý thuyết: biết trước đúng phân bố lồng đơn vị của cửa sổ 03–12/2024 (306 kỳ) thì LOTO hơn hằng số 23,9
nat (0,078 nat mỗi kỳ, z = 3,2), Đặc Biệt hơn 3,3 nat. Trần này tính trong mẫu nên hơi cao hơn mức đạt được.
Mô hình lồng thích nghi bật theo báo động có sẵn (`stats.xsmb_venue_effects.adaptive_cage_benchmark`) chỉ thu
khoảng 0,07 nat trên toàn bộ lịch sử. Khoảng cách giữa hai con số là chỗ để nâng cấp.

## Thuật toán

1. **Mô hình quan sát.** Lồng đơn vị cho 27 chữ số mỗi kỳ (chữ số cuối của 27 giải), lồng chục cho 27 chữ số
   (chữ số áp cuối). Trong một đoạn máy quay ổn định, chữ số của một lồng là đa thức với xác suất `θ`. Tiên
   nghiệm của `θ` là Dirichlet tâm ở phân bố đều, độ co `κ` tính bằng số chữ số giả.
2. **Phát hiện điểm đổi Bayes trực tuyến** (BOCPD, Adams & MacKay 2007):
   - Sau mỗi kỳ, đoạn hiện tại kết thúc với xác suất `H`.
   - Hậu nghiệm trên độ dài đoạn `r` được cập nhật chính xác.
   - Dự báo là trung bình theo `r` của dự báo hậu nghiệm Dirichlet–đa thức. Đoạn mới bắt đầu ở tiên nghiệm,
     nên khi máy trở lại đều, dự báo cũng về lại đều.
   - Thống kê của mỗi `r` là tổng `r` kỳ gần nhất, dùng chung cho mọi chuyên gia. Vì vậy cả hỗn hợp chạy hết
     4 273 kỳ trong khoảng 45 giây.
3. **Trung bình mô hình kèm chia sẻ cố định** (fixed-share, Herbster & Warmuth 1998):
   - Có sáu chuyên gia `(κ, H)` với `κ ∈ {300, 1000, 3000}` và `H ∈ {1/250, 1/1000}`, cộng chính dự báo đều
     (tiên nghiệm 0,5).
   - Trọng số cập nhật bằng hợp lý chữ số của kỳ vừa quay. Sau đó 0,05% trọng số trả về tiên nghiệm mỗi kỳ.
   - LOTO và Đặc Biệt suy từ hỗn hợp: xác suất một giải tận cùng `ab` là `θ_chục(a)·θ_đơn vị(b)`, và xác suất
     con `ab` về là `1 − (1 − ·)²⁷`. Phép này lấy trung bình trên chuyên gia và trên `r`.

**Bảo đảm tất định.** Trên log-loss chữ số, với mọi dãy kết quả, tổng log-loss của hỗn hợp không vượt của dự
báo đều cộng `−ln 0,5 − T·ln(1 − 0,0005)`. Với 3 910 kỳ, phần ấy là 2,65 nat, tức 0,0007 nat mỗi kỳ.
`fixed_share_bound` tính cận này, và phép kiểm ghim nó trên từng tiền tố của hai dãy giả lập.

## Kết quả walk-forward (sổ chuẩn 01-01-2015 → 23-11-2026)

Học 365 kỳ đầu, rồi chấm 3 910 kỳ. Dự báo cho mỗi kỳ chỉ đọc các kỳ trước nó. Số dương nghĩa là mô hình hơn dự
báo đều; đơn vị là nat, cộng trên các kỳ.

| Giai đoạn | Kỳ | LOTO | z | Đặc Biệt | z | Trọng số dự báo đều | log₁₀ e chữ số |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2016–2021 (gộp) | 2 142 | −0,59 | — | −0,12 | — | 93–98% | −0,21 |
| 2022 | 361 | +2,07 | 0,59 | +0,18 | 0,28 | 52% | +0,25 |
| 2023 | 361 | −0,44 | −0,55 | −0,07 | −0,48 | 85% | −0,13 |
| 2024 | 362 | +7,63 | 1,30 | +2,42 | 2,01 | 42% | +4,55 |
| 2025 | 361 | −0,36 | −0,36 | +0,14 | 0,61 | 82% | −0,42 |
| 2026 | 323 | −0,03 | −0,24 | +0,01 | 0,29 | 97% | 0,00 |
| **Toàn bộ** | 3 910 | **+8,29** | **1,19** | **+2,56** | **1,83** | 84% | +4,05 |
| 730 kỳ cuối | 730 | −0,52 | −0,32 | +0,04 | 0,13 | 86% | −0,57 |

Cách đọc bảng:

- **Năm 2024:** mô hình thu khoảng một phần ba trần LOTO và ba phần tư trần Đặc Biệt. So với mô hình bật theo
  báo động, phần thu được gấp khoảng 100 lần.
- **Năm 2022:** mô hình tự tìm ra một đợt lệch nhỏ hơn mà bộ phát hiện cũ không báo.
- **Những năm máy đều:** mỗi năm mất 0,03–0,44 nat, đúng như cận lý thuyết cho phép.
- **Đề bạt:** toàn bộ chưa đạt ngưỡng z ≥ 2,326. Phần lợi dồn vào hai đợt; giữa hai đợt, LOTO là 100 kết cục
  nhị phân rất nhiễu.

Bằng chứng chữ số trong năm 2024 đạt 10^4,55. Nếu phép kiểm tiến cứu đã chạy từ trước, nó vượt ngưỡng 10² ngay
trong đợt ấy. Đây là minh hoạ, không phải bằng chứng: tham số được đặt sau khi đã thấy đợt 2024.

## Độ nhạy theo tham số

Mọi tham số được chọn SAU khi đã thấy đợt 2024. Vì thế kho đo lại với bốn biến thể của nguyên mẫu (trong
nguyên mẫu, các đoạn dài hơn 1 500 kỳ được gộp theo trọng số):

| Biến thể | LOTO toàn bộ (z) | Đặc Biệt toàn bộ (z) | Ngoài 03–12/2024: LOTO |
| --- | --- | --- | --- |
| Lưới chính (3 κ × 2 H, share 5·10⁻⁴, tiên nghiệm 0,5) | +8,52 (1,20) | +2,61 (1,84) | +0,99 |
| Lưới rộng (5 κ × 4 H) | +7,55 (1,14) | +2,56 (1,92) | −0,33 |
| share 10⁻⁴ | +5,81 (0,86) | +2,77 (2,03) | −0,42 |
| Tiên nghiệm dự báo đều 0,9 | +7,02 (1,14) | +2,60 (2,08) | +0,39 |
| Một chuyên gia (κ = 1 000, H = 1/1 000) | +7,94 (1,07) | +2,65 (1,84) | +1,12 |

Kết quả không phụ thuộc một bộ tham số may mắn. Nhưng mọi biến thể đều dựa vào cùng hai đợt đã thấy, nên chỉ
phép kiểm tiến cứu mới phân xử được.

## Phép kiểm tiến cứu (đăng ký 24-11-2026, trên dữ liệu tới kỳ 23-11-2026)

- `CONFIG` đóng băng cùng `VERSION = 1` (lưới, share, tiên nghiệm, độ dài đoạn tối đa).
- Chỉ chấm các kỳ có ngày SAU 23-11-2026. Kỳ đầu tiên được chấm là kỳ 24-11-2026, chưa quay lúc đăng ký.
- Mỗi kỳ nhân `e` với `p_hỗn hợp(54 chữ số của lồng chục và đơn vị | các kỳ trước) / p_đều`. Dưới giả thuyết
  máy đều, mỗi thừa số có kỳ vọng 1. Tích là một martingale không âm, nên xác suất nó TỪNG vượt 100 không quá
  1% (Ville).
- Sổ `cage_bayes.csv` chỉ nối thêm. Nếu tính lại khác dòng đã ghi, sổ vẫn giữ dòng cũ và
  `ledger_consistent = false` báo rằng lịch sử đã đổi.
- Đổi tham số thì tăng `VERSION`. Đăng ký cũ được cất vào `retired`, đăng ký mới bắt đầu từ ngày dữ liệu mới
  nhất, và kỳ cũ không bị chấm lại.

## Triển khai

- **Chạy bóng.** `evaluation.model_registry` thêm mục `xsmb/cage_bayes`, luôn `shadow`. Mô hình được chấm mỗi
  kỳ nhưng không đổi xác suất công bố.
- **Điều kiện xét đưa vào tổ hợp:** walk-forward LOTO z ≥ 2,326 VÀ phép kiểm tiến cứu vượt 10². Khi đủ điều
  kiện, việc đưa vào là quyết định riêng, theo luật đề bạt của kho: phải thắng CẢ hằng số LẪN mô hình đang
  chạy.
- **Bước pipeline** chạy ngay sau `stats/xsmb_venue_effects.py`, trước sổ đăng ký mô hình và trang Phòng
  nghiên cứu.
- `state` trong tệp số đo ghi trạng thái trước kỳ tới: trọng số của dự báo đều, xác suất đoạn hiện tại mới bắt
  đầu trong 60 kỳ, và độ lệch lớn nhất của xác suất LOTO so với mức đều. Ngày 23-11-2026 các số ấy là 89,3%,
  3,3% và 0,79%: máy đang đều, và mô hình gần như trùng dự báo đều.

## Phép kiểm

`tests/forecast/test_cage_bayes.py` canh:

- phân bố Dirichlet–đa thức (khi bỏ hệ số đa thức) cộng đúng bằng 1;
- cận fixed-share trên mọi tiền tố;
- thích nghi khi có đoạn lệch cài sẵn và đứng yên khi kỳ quay đều;
- dự báo đều lấy lại trọng số sau đoạn lệch, việc chỉ có được nhờ chia sẻ cố định;
- điểm của kỳ k bằng điểm của dự báo dựng chỉ từ các kỳ trước k;
- bằng chứng vượt ngưỡng chỉ khi máy lệch;
- sổ tiến cứu chỉ nối thêm;
- tệp đã commit mang đúng luật đang chạy.

Đột biến từng luật (không học, nhìn trước, sai công thức, bỏ chia sẻ cố định, ghi đè sổ, chấm cả ngày đăng ký,
không bao giờ đổi đoạn) đều làm phép kiểm đỏ.

## Việc tiếp theo

1. **XSMT/XSMN.** Mỗi đài miền là một bộ lồng riêng với 18 giải. Riêng Bến Tre, mô hình chữ số theo lồng đã
   thắng ngoài mẫu (`evaluation.regional_benchmark`) và có phép kiểm tiến cứu riêng
   (`research.regional_cage_test`). Áp bộ máy này cho từng đài cần bố cục lồng của `core.regional_domain` và
   một đăng ký tiến cứu mới.
2. **Năm lồng thay vì hai.** Lồng trăm, nghìn, chục nghìn không ảnh hưởng LOTO, nhưng góp bằng chứng cho phép
   kiểm chữ số. Thêm chúng vào phép kiểm cũng cần một phiên bản đăng ký mới.
