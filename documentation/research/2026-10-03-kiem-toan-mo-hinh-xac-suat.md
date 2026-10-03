# Kiểm toán mô hình xác suất LOTO / Đặc Biệt và mô hình thách đấu ba tầng

Ngày: 03-10-2026. Dữ liệu: 4 223 kỳ, 01-01-2015 → 02-10-2026.
Tái lập: `PYTHONPATH=src python3 scripts/benchmark_probability_models.py --last 1000 --power-check`
(≈ 7 phút, 4 lõi). Số liệu thô: `data/research/model_overhaul/benchmark.json`, `daily_logloss.csv`.

## Tóm tắt

1. **Không có sụt giảm độ chính xác.** Từ 02-2026 đến nay, kỹ năng ngoài mẫu của tổ hợp production
   luôn nằm trong vùng 0. Giai đoạn TỆ nhất là 12-2025 → 01-2026, và lỗi gây ra nó đã được sửa.
   Thứ trông như "sụt giảm" gần đây là Brier Đặc Biệt nhảy từ 0,0099 lên 0,99 ngày 04-09-2026.
   Đó là đổi ĐƠN VỊ đo (trung bình → tổng), không phải mô hình kém đi.
2. **Không có trôi khái niệm.** Tần suất 100 con đồng nhất qua bốn giai đoạn lịch sử
   (χ²: LOTO p = 0,68, Đặc Biệt p = 0,74). Tần suất 1 000 kỳ gần nhất cũng không khác phần trước đó
   (p = 0,76 và 0,93), và vẫn đều trên toàn lịch sử (p = 0,68 và 0,83).
3. **Không tìm thấy rò rỉ dữ liệu** trong đường ML production.
4. **Mô hình mới ba tầng (Bayes + LightGBM + hiệu chỉnh) hoà dự báo hằng số trên 1 000 kỳ** và không
   thắng mô hình ML đang chạy. Theo luật của kho, nó KHÔNG được đưa vào production.
5. **Công cụ đo không mù.** Trên lịch sử tổng hợp có cài tín hiệu, chính mô hình ấy bắt được tín hiệu
   Đặc Biệt (z = 6,6, kỹ năng +6,2%) và tín hiệu LOTO một cặp số (z = 3,2). Hoà trên dữ liệu thật vì
   dữ liệu không có tín hiệu để học, không phải vì phương pháp yếu.

## 1. Chẩn đoán nguyên nhân

### 1.1 Lịch sử kỹ năng thật (sổ `data/prob_eval/ensemble_history.csv`)

Kỹ năng = 1 − logloss mô hình / logloss dự báo hằng số; 0 là ngang hằng số.

| Tháng | LOTO | Đặc Biệt |
|---|---:|---:|
| 12-2025 | **−73,3%** | **−7,1%** |
| 01-2026 | **−72,5%** | **−4,7%** |
| 02-2026 | +0,34% | −0,16% |
| 03 → 09-2026 | −0,02% … −0,01% | −0,19% … +0,06% |
| 10-2026 (2 kỳ) | +0,04% | +0,08% |

Khi so với trước đây, mô hình hiện tại TỐT hơn hẳn, không tệ hơn. Hai tháng đầu tệ vì
`p_active`/`p_stable` ghi ở thang "gần 1,0 cho mọi con" (tổng ≈ 100). Lỗi được chặn ở
`src/ensemble_components.py:86` (`loto_marginal_sum_is_plausible`; docstring ghi 212/231 kỳ bị ảnh hưởng).

### 1.2 "Brier Đặc Biệt tăng gấp 100" là đổi đơn vị

`src/ensemble_utils.py:308` (`categorical_brier`, commit 1f4f537c, 05-09-2026) đổi Brier đa lớp từ
TRUNG BÌNH sang TỔNG trên 100 lớp. Đây là định nghĩa chuẩn và bản sửa ấy đúng. Nhưng sổ ghi
`data/prob_eval/ensemble_history.csv` giữ nguyên các dòng cũ, nên cột `brier` của Đặc Biệt lẫn hai
thang: 0,0099 đến 03-09 và 0,99 từ 04-09. Ai đọc thẳng tệp ấy sẽ thấy sai số "tăng gấp 100".

Trang Chất lượng mô hình đã quy đổi khi hiển thị (`brier_rows_rescaled` = 217 trong
`data/model_quality/report.json`). Còn logloss của cùng các kỳ ấy không đổi: 4,601–4,656, quanh mức
hằng số 4,605. Kiểm toán này không sửa sổ: nó là bằng chứng ghi theo thời gian, và luật của kho là
không viết lại lịch sử.

### 1.3 Bốn giả thuyết trong yêu cầu

| Giả thuyết | Kết luận | Bằng chứng |
|---|---|---|
| Quá khớp trên nhiễu | Có, nhưng nhỏ và đã bị chặn | ML production (`src/ml_train.py`) dùng cây nông (độ sâu 2–3), dừng sớm, chọn cấu hình trên khối riêng, rồi co về tỉ lệ nền. Mức co có SÀN: `model_trust` không xuống dưới 0,35 (`ml_train.py:231`, áp ở `ml_predict.py:170`), nên ngay cả khi không có kỹ năng, 35% xác suất vẫn đến từ mô hình thô. Đo walk-forward: ML production LOTO kém hằng số z = −1,30 (không có ý nghĩa thống kê). Đặc Biệt: z = +0,37. Tầng xếp chồng từng làm nhọn xác suất (a = 4,89 ngày 25-09) và đã bị chặn bởi cổng phải thắng cả dự báo hằng số (`meta_predictor.quality_gate`). |
| Xác suất chưa hiệu chỉnh | Không | Tổ hợp production: độ lệch hiệu chỉnh 0,00030 ≈ độ phân giải 0,00028. Mười nhóm dự báo 23,2–24,5% đều nằm trong khoảng tin cậy của tần suất thật (`data/model_quality/report.json`). Mô hình mới: dự báo 23,64–23,96%, thực tế 23,0–24,4% (bảng hiệu chỉnh trong `benchmark.json`). |
| Cửa sổ tĩnh, không suy giảm | Không phải nguyên nhân | ML production đã đánh trọng số giảm dần (bán rã 365 ngày khi học, 120 ngày khi hiệu chỉnh; `ml_train.py:191-192`) và có EWM 14/45 ngày. Tiên nghiệm Bayes mới tự CHỌN chu kỳ bán rã bằng Bayes thực nghiệm. Ở mọi lần học lại, nó chọn tiên nghiệm cực mạnh (α = 3 000, tức gần hằng số), đúng như dự đoán khi không có trôi (mục 2). |
| Rò rỉ dữ liệu | Không tìm thấy | Hàng neo t chỉ đọc kỳ ≤ t (`ml_features.py:235`). Bỏ các bước qua kỳ nghỉ (`ml_features.py:357`). Bốn khối thời gian liên tiếp (`ml_train.py:43`). Rò rỉ thật duy nhất từng có (so trọng số học với chính vector đương nhiệm) đã sửa trong `learn_ensemble_weights.py`. |

## 2. Thiết kế lại — mô hình thách đấu `src/vla/`

Đường dẫn `vla/…` trong yêu cầu được đặt dưới `src/vla/`, theo cấu trúc của kho (mọi mô-đun chạy với
`PYTHONPATH=src`).

- `src/vla/features/engineer.py`: 19 đặc trưng cho LOTO, 30 cho Đặc Biệt. Quy ước duy nhất: hàng t chỉ đọc kỳ ≤ t.
  - Gan và điểm z của gan so với chính các chu kỳ đã hoàn tất của con số (co về chu kỳ hình học khi còn ít dữ liệu).
  - Tần suất suy giảm `2^{-(T-t)/h}` với h = 7/30/90/180, chia cho tỉ lệ nền.
  - Cầu vị trí: số cầu đang chạy và độ dài cầu, khớp từng cầu với `bridge_rules`.
  - PMI cùng kỳ; PMI trễ 1 kỳ, cả trung bình lẫn lớn nhất.
  - Nhiệt của cộng đồng Louvain trên đồ thị PMI dương, chỉ tính lại từ dữ liệu đến mốc.
  - Riêng Đặc Biệt: tần suất suy giảm của đầu/đuôi/tổng/bộ/lớn-nhỏ/chẵn-lẻ, và Markov bậc 1 của tổng/đầu/đuôi.
- `src/vla/models/bayesian_lgb.py`, ba tầng:
  1. Tiên nghiệm Dirichlet (Đặc Biệt) hoặc Beta (LOTO) với số đếm suy giảm; (h, α) chọn bằng Bayes thực nghiệm.
  2. LightGBM nhị phân khởi đầu từ logit của tiên nghiệm (`init_score`), dừng sớm trên khối thời gian sau. Cây chỉ học PHẦN DƯ, nên khi không có tín hiệu thì mô hình đứng yên ở tiên nghiệm. Có tuỳ chọn focal loss.
  3. Hiệu chỉnh Platt hoặc isotonic trên khối thời gian riêng; Đặc Biệt được chuẩn hoá về tổng 1.
- `src/vla/backtest/walk_forward.py`: cửa sổ mở rộng, học lại mỗi 50 kỳ. Hàm tự ném lỗi nếu khối huấn luyện chạm kỳ đang chấm.
- `src/vla/backtest/evaluator.py`: logloss, Brier (Đặc Biệt dùng TỔNG), Top-5/10/20, ROI theo luật trả thưởng, chiến lược chỉ đánh khi kỳ vọng dương, bảng hiệu chỉnh, so cặp từng kỳ.
- `src/vla/backtest/production_ml.py`: tái dựng đúng `ml_train.train_one` + `ml_predict` của thành phần ML production để làm đối chứng "cũ".

Siêu tham số chốt TRƯỚC khi chạm dữ liệu thật. `min_data_in_leaf` = 500 chọn bằng kiểm độ nhạy trên dữ
liệu tổng hợp: giá trị 2 000 chỉ thấy tín hiệu LOTO cài sẵn ở z = 1,1, còn 500 thấy ở z = 3,0.

## 3. So sánh 1 000 kỳ (26-12-2023 → 02-10-2026, walk-forward)

997 kỳ được chấm; 3 kỳ ngay sau Tết bị loại khỏi MỌI mô hình vì bảng production không có hàng cho chúng.
Mỗi mô hình học lại mỗi 50 kỳ, chỉ trên dữ liệu trước khối kỳ được chấm. Riêng việc ML production thật
học lại mỗi kỳ được đo ở mục 3.1.

Mốc kỹ năng 0: tỉ lệ nền tích luỹ (LOTO) và 1/100 (Đặc Biệt). z là hiệu logloss từng kỳ so với mốc.

**LOTO**

| Mô hình | Logloss | Kỹ năng | z | Top-5 | Top-10 | Top-20 | ROI top-10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hằng số | 0,548757 | 0 | — | 22,8% | 23,1% | 23,6% | −9,1% |
| ML production (cũ) | 0,548763 | −0,001% | −1,30 | 23,1% | 23,1% | 23,7% | −10,0% |
| Tiên nghiệm Bayes | 0,548758 | −0,000% | −0,22 | 24,3% | 24,4% | 24,1% | −3,3% |
| **Bayes + LGB + Platt (mới)** | 0,548755 | +0,000% | +0,29 | 24,5% | 24,3% | 24,4% | −2,3% |
| Bayes + LGB focal + isotonic | 0,548866 | −0,020% | −2,06 | 23,1% | 23,8% | 23,9% | −6,0% |

Tỉ lệ một con LOTO về ở kỳ ngẫu nhiên là 23,6%. Sai số chuẩn của Top-10 trên 997 kỳ khoảng 0,6
điểm phần trăm, nên mọi chênh lệch trong bảng nằm trong nhiễu. Hằng số "chọn" 00–09 vì mọi xác suất bằng nhau.

**Đặc Biệt**

| Mô hình | Logloss | Kỹ năng | z | Top-5 | Top-10 | Top-20 | ROI top-10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hằng số | 4,605170 | 0 | — | 4,5% | 9,8% | 18,8% | −31,2% |
| ML production (cũ) | 4,604909 | +0,006% | +0,37 | 6,2% | 11,4% | 20,9% | −20,0% |
| Tiên nghiệm Bayes | 4,606216 | −0,023% | −2,15 | 4,6% | 10,1% | 18,8% | −29,1% |
| **Bayes + LGB + Platt (mới)** | 4,606609 | −0,031% | −0,73 | **7,0%** | 11,9% | 19,8% | −16,4% |
| Bayes + LGB focal + isotonic | 4,647522 | −0,920% | −2,28 | 4,4% | 9,1% | 18,5% | −36,1% |

Mô hình mới so với ML production: LOTO +0,000008 nats mỗi kỳ (z = +1,04), Đặc Biệt −0,0017 (z = −0,80).
**Không thắng.**

**Top-5 Đặc Biệt 7,0% có phải tín hiệu?** Không đủ căn cứ.
- Trên 1 000 kỳ này: 71/1 000 kỳ trúng so với kỳ vọng 50 (p = 0,002 một phía), đều ở cả hai nửa (7,2% và 7,0%).
- Đó là MỘT trong 30 chỉ số đọc sau khi chạy (5 mô hình × 3 mức K × 2 kiểu). Sau hiệu chỉnh Bonferroni, p ≈ 0,07.
- Chạy lại y hệt trên 1 000 kỳ TRƯỚC đó: 50/1 000 (5,0%, p = 0,52), tức không lặp lại.
- Logloss, chỉ số chấm chính đã chọn từ trước, kém hằng số.

Kết luận: chưa đủ căn cứ. Muốn kiểm thì phải đăng ký tiến cứu như `hot_tail_test`, với ngày bắt đầu mới.

**ROI.** Không chiến lược nào hoàn vốn. Theo luật trả thưởng, đánh ngẫu nhiên hoàn khoảng 0,94 (lô)
và 0,70 (Đặc Biệt). Chiến lược "chỉ đánh khi kỳ vọng dương theo xác suất mô hình":
- Mô hình mới: 0 cược LOTO; 21 cược Đặc Biệt, trượt cả 21.
- Bản focal (hiệu chỉnh kém): 3 632 cược LOTO (ROI −1,9%) và 1 032 cược Đặc Biệt (ROI −80%).
- ML production: 31 cược Đặc Biệt, lời +126%. Đó chỉ là 1 lần trúng nên không có ý nghĩa thống kê.

### 3.1 ML production học lại mỗi kỳ hay mỗi 50 kỳ

Production thật học lại mỗi kỳ (`ml_predict` coi mô hình cũ là hết hạn). Học lại mỗi kỳ cho cả 1 000 kỳ
tốn khoảng 4 giờ, nên phép đo này chạy trên 200 kỳ cuối, cùng mã, chỉ khác nhịp học lại:

| | Học lại mỗi kỳ | Mỗi 50 kỳ | Hiệu (z) | Mỗi kỳ so với hằng số (z) |
|---|---:|---:|---:|---:|
| LOTO | 0,547181 | 0,547191 | +0,73 | +1,56 |
| Đặc Biệt | 4,603863 | 4,604559 | +0,32 | +0,69 |

Học lại mỗi kỳ tốt hơn một chút nhưng không có ý nghĩa thống kê, và vẫn không hơn hằng số. Vì vậy
bảng 1 000 kỳ ở trên là xấp xỉ đủ dùng cho đối chứng production. Chạy đúng nhịp production cho cả
1 000 kỳ: `--production-refit-every 1`.

### 3.2 Tổ hợp production đã ghi sổ (241 kỳ trùng)

Trên cả 241 kỳ, tổ hợp production kém hằng số (LOTO z = −4,65) vì gồm hai tháng lỗi thang ở mục 1.1.
Từ 02-2026 (219 kỳ), nó ngang hằng số: LOTO z = −1,21, Đặc Biệt z = −1,72. Trên 32 kỳ chấm đúng tệp đã
công bố cũng vậy: z = −0,20 và −0,19.

## 4. Kiểm độ nhạy (lịch sử tổng hợp 2 600 kỳ, chấm 600 kỳ cuối)

| Tín hiệu cài | Kỹ năng mô hình mới | z | Top-5 / ngẫu nhiên |
|---|---:|---:|---:|
| Đặc Biệt kỳ sau = kỳ trước + 1, xác suất 15% | +6,25% | +6,6 | 19,2% / 5% |
| LOTO: 37 về thì kỳ sau 73 ở giải bảy, xác suất 50% | +0,083% | +3,2 | 25,7% / 23,8% |

Cùng mã, cùng siêu tham số. Có tín hiệu thì thắng rõ; trên dữ liệu thật thì hoà.

## 5. Quyết định

- **Không thay mô hình production.** Mô hình mới không thắng hằng số lẫn ML production, nên không qua
  cổng của kho: phải thắng CẢ hai trên lát ngoài mẫu.
- Gói `src/vla/` giữ lại làm khung thách đấu. Mọi ý tưởng đặc trưng mới nên đi qua
  `benchmark_probability_models.py` trước khi chạm production.
- Việc nên làm tiếp, chủ dự án quyết:
  1. Đăng ký tiến cứu giả thuyết "Top-5 Đặc Biệt của bayes_lgb trúng > 5%", từ kỳ 04-10-2026, 365 kỳ, một phía α = 0,01.
  2. Ghi chú đơn vị Brier ngay trong sổ `ensemble_history.csv`, để đọc tệp thô không còn thấy "tăng gấp 100".
  3. Xem lại sàn 0,35 của `model_trust`: khi không có kỹ năng, sàn ấy vẫn trộn 35% mô hình thô vào dự báo.

## 6. Kiểm thử

`tests/test_vla_lab.py`, 16 phép:
- Không nhìn trước: đổi mọi kỳ sau t thì hàng 0..t giữ nguyên từng bit, cho cả 30 đặc trưng.
- Nhãn đúng kỳ t+1.
- Điểm z của gan khớp tính tay.
- Số cầu khớp `bridge_rules.find`.
- Công thức hậu nghiệm Dirichlet/Beta.
- Platt sửa được dự báo nhọn.
- Walk-forward không học kỳ đang chấm.
- Bắt được tín hiệu cài sẵn, và không bịa kỹ năng trên nhiễu thuần.
- Logloss/Brier, Top-K, ROI, kỳ vọng dương khớp tính tay.

14 đột biến đều làm đỏ: ba kiểu rò rỉ tương lai, lệch một hàng ở walk-forward, sai công thức tiên
nghiệm, bỏ hiệu chỉnh, Brier trung bình thay tổng, ROI tính theo có/không thay vì số nháy…
