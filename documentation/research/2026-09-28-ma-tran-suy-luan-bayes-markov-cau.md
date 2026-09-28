# Ma trận suy luận Bayes · Markov · cầu, hiệu chỉnh bằng 10 000 lịch sử Monte Carlo

Ngày đo: 28-09-2026. Dữ liệu: `data/xsmb-2-digits.csv`, 4 218 kỳ (01-01-2015 → 27-09-2026).
Tái lập:

    python3 scripts/inference_matrix_audit.py --sims 10000 --out-dir <thư mục>

(khoảng 8 phút trên 4 lõi; hạt giống cố định `20260928`, nên cùng dữ liệu cho cùng số.)
Bản production của phân tích này chạy mỗi lượt pipeline ở `src/confidence_matrix.py`
và in ra trang `docs/do-tin-cay.html` (Độ tin cậy dự báo), kèm thêm bốn phép kiểm
giả thuyết kỳ quay bị sắp đặt.
Script chỉ ĐỌC dữ liệu và mã hiện có — không đổi phép tính, mô hình hay hợp đồng dữ
liệu nào của production.

## Câu hỏi và cách trả lời

Yêu cầu: tính xác suất từng con bằng Bayes và Markov, tìm "cầu kèo" bằng ma trận tương
quan và chuỗi thời gian, mô phỏng Monte Carlo ≥ 10 000 kịch bản, rồi gắn mỗi dự báo
một Confidence Score ba tầng (High > 85 % khi Bayes + Markov + cầu cùng thoả; Medium
60–84 % khi 2/3; Low/Noise < 60 %).

Điểm mấu chốt của phương pháp — và là chỗ **tự phản biện (red teaming)** đầu tiên:
một con số "tin cậy 99 %" chỉ có nghĩa khi ta biết **lịch sử công bằng hoàn toàn**
cho ra con số ấy thường tới đâu. Vì vậy mọi thống kê được tính một lần trên dữ liệu
thật và 10 000 lần trên lịch sử giả lập công bằng cùng kích thước (4 218 kỳ × 27 giải,
mỗi giải 00–99 đều nhau, độc lập). Confidence của một tín hiệu =

    tỉ lệ lịch sử công bằng mà thống kê LỚN NHẤT của cả họ giả thuyết còn nhỏ hơn tín hiệu ấy
    = 1 − p hiệu chỉnh đa kiểm (family-wise)

Lấy "lớn nhất của cả họ" là bắt buộc: ta soi 100 con, 10 000 cặp bạc nhớ, 2 916 cầu
vị trí — con/cặp/cầu đẹp nhất luôn trông đẹp, kể cả trên dữ liệu ngẫu nhiên.

---

## 1. Bảng trích xuất trạng thái & mô hình

### Bước 1 — Làm sạch dữ liệu nguồn

| Kiểm tra | Kết quả |
|---|---|
| Số kỳ | 4 218 (01-01-2015 → 27-09-2026) |
| Ngày trùng / thứ tự | 0 trùng, tăng dần |
| Ô trống / ngoài 00–99 | 0 / 0 |
| Đuôi 2 số khớp bảng kết quả đầy đủ `data/xsmb.csv` | khớp **mọi ô** (4 218 × 27) |
| Ngày lịch thiếu | 70 ngày trong 13 đợt — các đợt Tết (4 ngày) và 01→22-04-2020 (22 ngày, tạm dừng quay) |

Không có dòng nào phải sửa hay bỏ. Các đợt thiếu là ngày không quay, không phải lỗi thu thập.

### Bước 2 — Tần suất, trục cầu, ma trận tương quan

Tỉ lệ nền: một con về ít nhất một lần trong 27 giải với xác suất
1 − 0,99²⁷ = **23,77 %**; Đặc Biệt đúng một con: **1 %**.

| Trục khảo sát (họ giả thuyết) | Cỡ họ | Giá trị thật (tốt nhất) | Trung vị lịch sử công bằng | p Monte Carlo |
|---|---:|---:|---:|---:|
| Tần suất LOTO, \|z\| lớn nhất | 100 | 2,55 (con 49) | 2,70 | 0,66 |
| Tần suất LOTO, χ² toàn bảng | 1 | 66,2 | 75,9 | 0,83 |
| Tần suất Đặc Biệt, χ² | 1 | 86,0 | 98,3 | 0,82 |
| Markov "về → về lại", z lớn nhất | 100 | 3,02 (con 52) | 2,47 | 0,12 |
| Bạc nhớ i hôm nay → j ngày mai, z lớn nhất | 10 000 | 3,13 (96→52) | 3,37 | 0,85 |
| Cầu vị trí → LOTO, tỉ lệ trúng cao nhất | 2 916 | 25,94 % | 26,08 % | 0,77 |
| Cầu vị trí → Đặc Biệt, tỉ lệ trúng cao nhất | 2 916 | 1,59 % | 1,57 % | 0,49 |
| Chuyển đầu Đặc Biệt → Đặc Biệt ngày mai, z lớn nhất | 1 000 | 3,83 | 3,85 | 0,53 |
| Đặc Biệt hôm nay → về LOTO ngày mai | 1 | 24,45 % | 23,76 % | 0,15 |
| Xu hướng dài hạn / đứt gãy từng con (CUSUM) | 100 | 2,80 | 2,92 | 0,63 |
| "Số nóng" năm trước còn nóng năm sau (tương quan) | 1 | −0,014 | −0,001 | 0,66 |
| Đứt gãy cấu trúc: số con KHÁC NHAU mỗi kỳ (CUSUM) | 1 | 2,91 | 1,14 | **0,0075** |

Cầu vị trí ở đây: lấy 54 chữ số (hàng chục và hàng đơn vị của 27 giải hôm nay), ghép
cặp có thứ tự thành 2 916 cầu; cầu trúng khi con ghép ra về ngày mai. Bộ quét cầu của
production rộng hơn nhiều — 412 164 giả thuyết trên chữ số đầy đủ, lọc FDR — và
`data/predictions_today.json` ghi **0 giả thuyết sống sót**.

Bạc nhớ 100 × 100: 1,91 % số ô có |z| > 2; 20 lịch sử công bằng cho 1,85–2,40 %
(trung bình 2,17 % — thấp hơn 4,6 % của phân phối chuẩn vì 27 giải cùng kỳ ràng buộc
nhau). Ô mạnh nhất cũng kém ô mạnh nhất điển hình của ngẫu nhiên (p = 0,85). Ma trận
tương quan trễ 1 kỳ này là nhiễu.

---

## 2. Luồng suy luận logic (chuỗi suy nghĩ từng bước, kèm phản biện)

**B1. Giả thuyết:** "Con 49 về nhiều nhất (25,44 % so với nền 23,77 %) nên đang có
xác suất cao hơn."
*Phản biện:* trong 100 con, con về nhiều nhất của một lịch sử công bằng lệch trung
vị z = +2,48; con 49 lệch +2,55 — ngang con đầu bảng điển hình của ngẫu nhiên
(p hiệu chỉnh = 0,46).
Kiểm ngoài mẫu: 10 con có hậu nghiệm cao nhất giai đoạn 2015–2023 về **23,56 %** trong
2024 → 27-09-2026 (9 890 lượt, z = −0,48). *Kết luận:* bác bỏ.

**B2. Giả thuyết Bayes:** "P(p₄₉ > nền | dữ liệu) = 99,37 %, vậy tin cậy 99 %."
*Phản biện:* với prior Beta tâm ở nền (100 kỳ giả), **60,0 %** lịch sử công bằng có ít
nhất một con đạt hậu nghiệm > 0,99, và **99,6 %** có một con > 0,95. Bản ngắn hạn
(60 kỳ gần nhất, kiểu "đang nóng"): 97,4 % lịch sử công bằng có con > 0,85. Hậu nghiệm
từng con là đúng về toán, nhưng **chọn con cao nhất trong 100 con** biến nó thành báo
động giả gần như chắc chắn. Sau hiệu chỉnh: con 49 chỉ đạt Confidence **54,5 %**.
*Kết luận:* hậu nghiệm Bayes đơn lẻ không phải Confidence Score.

**B3. Giả thuyết Markov:** "Con 52 về hôm nay thì mai về lại 28,2 %, cao hơn 23,6 %
khi hôm nay trượt (z = 3,02, p một phía danh nghĩa ≈ 0,001)."
*Phản biện:* đó là con tốt nhất trong 100 phép kiểm; p hiệu chỉnh = 0,12. Kiểm ngoài
mẫu: 10 con Markov mạnh nhất 2015–2023, sau khi về, về lại **22,34 %** trong 2024–nay
(2 372 lượt, z = −1,63 — thấp hơn nền). *Kết luận:* bác bỏ.

**B4. Giả thuyết cầu:** "Cầu giải 6.2 hàng chục + giải 3.6 hàng đơn vị trúng 25,94 %
suốt 11 năm."
*Phản biện:* lịch sử công bằng có cầu tốt nhất trung vị 26,08 % — cầu tốt nhất thật
còn **thấp hơn** cầu tốt nhất của ngẫu nhiên. 20 cầu LOTO tốt nhất 2015–2023 (trung
bình 26,01 % trong mẫu) chỉ còn **23,57 %** ngoài mẫu (19 780 lượt, z = −0,65).
20 cầu Đặc Biệt tốt nhất (1,51 % trong mẫu) còn 1,12 % ngoài mẫu (z = +1,66, không có
ý nghĩa, và là 1 trong 6 phép kiểm ngoài mẫu). Bạc nhớ top-50: 23,61 % (z = −0,41).
Chuyển đầu Đặc Biệt top-20: 0,96 % (z = −0,16). *Kết luận:* bác bỏ.

**B5. Tín hiệu duy nhất dưới 0,05 — đứt gãy "số con khác nhau mỗi kỳ".**
Trung bình 23,83 con khác nhau/kỳ so với kỳ vọng 23,77 — tức ít "nháy kép" hơn ngẫu
nhiên một chút; lệch dương ở 9/12 năm, rõ nhất 2015–2019 (z từng năm 0,9–2,1). p = 0,0075 là p nhỏ nhất
trong **17 họ** đã kiểm; ngưỡng Bonferroni 0,05/17 = 0,0029 → **không** vượt. Và dù có
thật, nó nói về việc số trùng nhau trong CÙNG một kỳ, không nói con nào sẽ về — không
dùng được để dự báo. Ghi lại để theo dõi, không đưa vào ma trận quyết định.

**B6. Vòng phản hồi (so dự báo đã công bố với kết quả thật).** Đã có trong production
từ PR #93: `src/skill_monitor.py` chấm đúng vector xác suất công bố TRƯỚC kỳ quay, ghi
sổ cái `data/model_quality/published_skill.csv`, và làm đỏ pipeline khi kỹ năng rời
vùng 0 theo hướng nào cũng vậy. Số đo 31-08 → 27-09-2026 (28 kỳ đã công bố):

| | LOTO mô hình | LOTO nền | Đặc Biệt mô hình | Đặc Biệt nền |
|---|---:|---:|---:|---:|
| Log-loss | 0,545292 | 0,545267 | 0,0559966 | 0,0560015 |
| Brier | 0,179791 | 0,179782 | 0,00989997 | 0,00990000 |
| MAE | 0,36075 | 0,36096 | 0,019800 | 0,019800 |
| Trạng thái bộ theo dõi (30 kỳ, z = 3) | vùng 0 | | vùng 0 | |

MAE được liệt kê vì được yêu cầu, nhưng **không dùng để quyết định**: MAE không phải
quy tắc chấm đúng đắn (nó thưởng dự báo co về 0/1), nên chỗ "mô hình hơn nền" ở cột
MAE LOTO là ảo; log-loss và Brier — hai quy tắc đúng đắn — cho thấy mô hình LOTO kém
nền một chút. Về "tối ưu trọng số khi độ lệch chuẩn tăng": độ lệch chuẩn kỹ năng
từng kỳ đang GIẢM (LOTO 0,00129 → 0,00048, Đặc Biệt 0,0110 → 0,0029 giữa hai nửa sổ
cái). Tái tối ưu theo biến động là cách chắc chắn nhất để khớp nhiễu; hệ thống giữ
cổng ngoài mẫu (`learn_ensemble_weights`, `meta_predictor.quality_gate`) chỉ đề bạt
trọng số mới khi nó thắng mặc định VÀ dự báo hằng số trên lát chưa thấy.

---

## 3. Ma trận xác suất & mô hình thống kê

### Bước 3 — Ba thành phần cho từng con, kỳ 28-09-2026

Với mỗi con (100 LOTO + 100 Đặc Biệt), trạng thái sau kỳ 27-09-2026:

- **Bayes**: hậu nghiệm P(p > nền | 4 218 kỳ), prior Beta tâm nền.
- **Markov**: LOTO — z của P(về | trạng thái hôm qua) theo đúng trạng thái hôm qua của
  con đó; Đặc Biệt — z của ô chuyển (đầu Đặc Biệt hôm qua = 7 → con này).
- **Cầu**: cầu vị trí tốt nhất (tỉ lệ trúng 11 năm) mà chữ số kỳ 27-09 ghép ra con này.

Mỗi thành phần đổi ra Confidence hiệu chỉnh đa kiểm như mô tả ở đầu. Luật tầng, đúng
như yêu cầu:

    High      : cả ba thành phần > 85 %          Score = thành phần yếu nhất
    Medium    : ít nhất hai thành phần ≥ 60 %     Score = thành phần mạnh thứ hai
    Low/Noise : còn lại                          Score = thành phần mạnh thứ hai

Thành phần mạnh nhất đạt được trên CẢ 100 con:

| | Bayes | Markov | Cầu |
|---|---:|---:|---:|
| LOTO | 54,5 % (con 49) | 46,8 % (con 01) | 23,1 % |
| Đặc Biệt | 16,6 % (con 65) | 0,08 % | 50,7 % |

Không thành phần nào của con nào chạm 60 %. Phân tầng:

| | High | Medium | Low/Noise |
|---|---:|---:|---:|
| LOTO | 0 | 0 | **100** |
| Đặc Biệt | 0 | 0 | **100** |

Các con đang công bố cho kỳ 28-09-2026 (`data/predictions_today.json`) cũng thế:
10 con LOTO (53, 95, 91, 23, 49, 97, 14, 77, 17, 55) và 10 con Đặc Biệt (10, 23, 13,
50, 78, 58, 87, 18, 05, 69) — tất cả **Low/Noise**, Score 0 %. Xác suất mô hình gán
cho các con LOTO ấy là 23,86–23,97 %, lệch nền 0,1–0,2 điểm phần trăm — đúng với việc
trang đã ghi "không phải dự báo đáng tin cậy". Ma trận đầy đủ 200 dòng nằm ở
`decision_matrix.csv` do script sinh ra.

### Rủi ro / lợi nhuận — 10 000 kỳ kế tiếp giả lập

Với 10 con LOTO đang công bố:

| Số con trong 10 con có về | 0 | 1 | 2 | 3 | 4 | ≥ 5 |
|---|---:|---:|---:|---:|---:|---:|
| Tỉ lệ trong 10 000 kỳ | 5,9 % | 20,6 % | 30,1 % | 24,9 % | 13,1 % | 5,5 % |

Trung bình 2,69 lượt về (lý thuyết 2,70). Mười con Đặc Biệt chứa con về trong 10,3 %
số kỳ (lý thuyết 10 %).

Hoà vốn: với mỗi đơn vị bỏ ra cho một con LOTO, cần trả **≥ 3,70 lần mỗi lượt về**
(= 100/27); Đặc Biệt cần **≥ 100 lần**. Mọi mức trả thấp hơn cho kỳ vọng âm, và vì
không con nào có xác suất cao hơn nền (mục 2), **chọn con nào cũng không đổi được kỳ
vọng**. Rủi ro/lợi nhuận của mọi con là như nhau.

---

## 4. Kết luận & Confidence Score

**Confidence Score của mọi dự báo LOTO và Đặc Biệt cho kỳ 28-09-2026: Low/Noise, 0 %
(thành phần cao nhất cả bảng: 54,5 %, dưới ngưỡng Medium 60 %).**

Lý do, đã đo chứ không suy ra:

1. 16/17 họ giả thuyết nằm trọn trong vùng của lịch sử công bằng; họ còn lại không
   qua hiệu chỉnh đa kiểm và không mang thông tin dự báo.
2. Mọi tín hiệu tốt nhất chọn trên 2015–2023 đều thoái lui về nền ngoài mẫu
   (6/6 phép kiểm, không phép nào có ý nghĩa).
3. Vector đã công bố không khác dự báo hằng số (28 kỳ): LOTO kém nền 0,005 % log-loss,
   Đặc Biệt hơn nền 0,009 % — cả hai nằm trong vùng 0 của bộ theo dõi.

Một hệ thống trả "High 90 %" cho kỳ quay này sẽ là hệ thống **đang báo động giả**:
ví dụ Bayes ngây thơ ở đây sẽ đạt "99 %" trên 60 % số lịch sử hoàn toàn ngẫu nhiên.
Khung ba tầng được giữ nguyên để nếu kỳ quay từng có cấu trúc thật (máy quay lệch,
thay quy trình), nó sẽ hiện lên — bộ theo dõi `skill_monitor` báo động theo cả hai
hướng cũng vì lẽ ấy.
