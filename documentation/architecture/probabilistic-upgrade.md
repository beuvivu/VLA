# Nâng cấp kiến trúc ước lượng xác suất — thiết kế dựa trên số đo

Tài liệu này trả lời một đề bài kiến trúc ML/DL cho lớp dự đoán xác suất. Mọi
khuyến nghị đều neo vào số đo trên chính kho này, không vào lý thuyết chung.

## 0. Kết luận trước, lập luận sau

**Ràng buộc thắt cổ chai của hệ thống này là CÔNG SUẤT THỐNG KÊ, không phải
sức chứa của mô hình.** Thêm GNN, Transformer hay TFT làm tăng số giả thuyết
được kiểm định ngầm, và điều đó **nâng** ngưỡng hiệu ứng tối thiểu phát hiện
được — tức làm bài toán khó hơn, không dễ hơn.

Ba số đo dẫn tới kết luận ấy nằm ở mục 1. Hai trong ba đã có sẵn trong kho từ
trước; cái thứ ba do tài liệu này đo mới.

## 1. Hiện trạng đo được

### 1.1 Kỹ năng của mô hình sản xuất (`models/train_report_*.csv`)

| | lô tô | đề |
|---|---|---|
| `val_brier` | 0,18101945 | 0,00989678 |
| `baseline_brier` | 0,18100658 | 0,00990000 |
| **`brier_skill`** | **−0,0000711** | **+0,0003248** |
| `logloss_skill` | −0,0000642 | +0,0030649 |
| `quality_pass` | **False** | True |
| `model_trust` | 0,35 | 0,356 |

Lô tô: kỹ năng **âm** — mô hình kém hơn việc đoán bằng tần suất cơ sở. Cổng
chất lượng đã bắt đúng và đặt `quality_pass = False`. Đề: dương nhưng ở mức
+0,03 %.

### 1.2 Phân tích công suất (`data/research/randomness_report.json`)

2 392 kỳ, 2 000 mô phỏng, tần suất nền 0,2377.

| Số giả thuyết kiểm định | Hiệu ứng tối thiểu phát hiện được |
|---|---|
| 1 (một mô hình duy nhất) | +2,44 điểm % — tương đối **+10,3 %** |
| 20 (bộ đặc trưng đã xây) | +3,36 điểm % — **+14,2 %** |
| 100 (một giả thuyết mỗi con số) | +3,76 điểm % — **+15,8 %** |
| 412 164 (họ cầu ghép chéo ngày) | +5,34 điểm % — **+22,5 %** |

Đọc bảng này theo chiều ngược lại mới thấy điểm quan trọng: **càng quét rộng
thì càng phải tìm ra hiệu ứng LỚN hơn mới dám tin.** Với họ cầu 412 nghìn quy
tắc, bất kỳ quy luật nào dưới +22,5 % tương đối đều không phân biệt được với
nhiễu — và +22,5 % là một hiệu ứng khổng lồ.

Kiểm tra tái lặp: nửa đầu z = −0,40, nửa sau z = −2,50, **`replicates = False`**.
Một tín hiệu duy nhất sống sót qua Bonferroni đã không tái lặp được.

### 1.3 Đo mới: hàm mất mát và hiệu chuẩn

`scripts/demo_probability_losses.py`, 203 200 hàng (ngày × con số),
2021-01-27 → 2026-09-13, cắt theo thời gian 70/15/15, huấn luyện thật bằng
LightGBM với hàm mục tiêu tùy biến.

Đường nền (hằng số = tần suất cơ sở 0,2378): Brier 0,181266 · LogLoss 0,548563
· **ECE 0,000040**

| Hàm mục tiêu | Hiệu chuẩn | Brier | LogLoss | ECE | skill Brier |
|---|---|---|---|---|---|
| log-loss | không | 0,181504 | 0,549213 | 0,002970 | −0,00132 |
| log-loss | **Platt** | 0,181263 | 0,548555 | 0,000863 | **+0,00002** |
| log-loss | Isotonic | 0,181374 | 0,549946 | 0,001609 | −0,00059 |
| **Focal** | **không** | **0,250000** | **0,693147** | **0,262172** | **−0,37919** |
| Focal | Platt | 0,181267 | 0,548566 | 0,000887 | −0,00000 |
| Focal | Isotonic | 0,181267 | 0,548566 | 0,000886 | −0,00000 |
| Brier (proper) | không | 0,181428 | 0,549001 | 0,002028 | −0,00089 |
| Brier (proper) | Platt | 0,181264 | 0,548558 | 0,000881 | +0,00001 |
| Brier (proper) | Isotonic | 0,181398 | 0,550733 | 0,001560 | −0,00073 |

Bốn kết luận rút ra, tất cả đều là số đo:

1. **Focal Loss phá huỷ xác suất.** Không hiệu chuẩn, nó cho Brier đúng 0,25 và
   LogLoss đúng 0,693 — tức mọi dự đoán co về 0,5. ECE tệ hơn đường nền **6 500
   lần**. Focal Loss không phải proper scoring rule: nó tối ưu khả năng PHÂN
   BIỆT, không tối ưu tính ĐÚNG của xác suất. Với bài toán này, dùng nó mà
   không hiệu chuẩn lại là sai về bản chất.
2. **Hiệu chuẩn làm gần như toàn bộ công việc.** Platt kéo cả ba cấu hình về
   sát đường nền, kể cả cấu hình đã bị Focal phá hỏng hoàn toàn.
3. **Isotonic THUA Platt ở mọi cấu hình.** Không có tín hiệu để một ánh xạ đơn
   điệu bám vào, nên nó bám vào nhiễu của tập hiệu chuẩn 30 480 hàng. Đây là ví
   dụ sạch của việc "mạnh hơn" không đồng nghĩa "tốt hơn".
4. **Trần đo được là +0,00002.** Cấu hình tốt nhất hơn đường nền hai phần trăm
   nghìn.

## 2. Sơ đồ kiến trúc tổng thể

```
  data/xsmb.csv  (nguồn sự thật duy nhất, 2 399 kỳ)
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ TẦNG ĐẶC TRƯNG  ml_features.py · cau_keo_feature_groups.py│
│  · tần suất theo cửa sổ, gan theo KỲ, số nháy             │
│  · thứ của NGÀY ĐÍCH (không phải ngày neo)                │
│  · path support ma trận (họ cầu ghép chéo)                │
│  ⟂ chốt rò rỉ: test_cau_keo_future_mutation.py            │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ CỔNG Ý NGHĨA  significance_stats.py · bridges/firewall.py  │
│  · BH-FDR trên toàn họ giả thuyết                          │
│  · chỉ quy tắc sống sót mới được đi tiếp                    │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Thống kê EB  │ Cầu kèo ML   │ ML bảng      │ Động lực số  │
│ statistical_ │ cau_keo_ml   │ ml_train     │ number_      │
│ signal.py    │              │ (LGBM/Cat/   │ dynamics     │
│              │              │  HistGB)     │ (Markov-2,   │
│              │              │              │  hazard)     │
└──────────────┴──────────────┴──────────────┴──────────────┘
        │              │              │              │
        └──────────────┴──────┬───────┴──────────────┘
                              ▼
┌───────────────────────────────────────────────────────────┐
│ HỢP NHẤT  learn_ensemble_weights.py · meta_predictor.py    │
│  · trọng số học được + Thompson Sampling chiết khấu        │
│    (ml_engine/bandit.py, γ = 0,98)                         │
│  · phát hiện trôi khái niệm: ADWIN + KS (drift.py)         │
└───────────────────────────────────────────────────────────┘
                              ▼
┌───────────────────────────────────────────────────────────┐
│ HIỆU CHUẨN  calibration.py                                 │
│  · lô tô: Platt (a, b)   · đề: temperature scaling         │
│  · học trên lát HIỆU CHUẨN tách riêng, không phải tập kiểm │
└───────────────────────────────────────────────────────────┘
                              ▼
┌───────────────────────────────────────────────────────────┐
│ CỔNG CHẤT LƯỢNG  ml_validation.py                          │
│  · walk-forward (ml_engine/validation.py)                  │
│  · Brier skill, LogLoss skill, ECE, reliability            │
│  · skill ≤ 0 → quality_pass = False → model_trust bị hạ     │
└───────────────────────────────────────────────────────────┘
                              ▼
              xác suất đã hiệu chuẩn + mức tin cậy
```

Điểm đáng chú ý của sơ đồ này: **cổng ý nghĩa nằm TRƯỚC mô hình, không phải
sau.** Đó là điều đúng đắn với dữ liệu có tỷ lệ tín hiệu/nhiễu cực thấp, và
nhiều kiến trúc đề xuất bỏ qua nó.

## 3. Đối chiếu bốn khu vực yêu cầu với hiện trạng

### 3.1 Kỹ thuật đặc trưng

| Hạng mục | Trạng thái |
|---|---|
| Ma trận kề / mạng liên kết vị trí | **ĐÃ CÓ** — `_path_support_matrix` quét toàn bộ cặp vị trí bằng phép ma trận |
| Streak length, historical accuracy, volatility | **ĐÃ CÓ** — `cau_keo_feature_groups.py` |
| Gap analysis, chu kỳ lặp | **ĐÃ CÓ** — `gap_cycle_stats.py`, đếm theo KỲ chứ không theo ngày lịch |
| Phân phối Poisson/Binomial | **ĐÃ CÓ một phần** — `significance_stats.py` dùng nhị thức + BH-FDR |
| Embedding cặp vị trí–giá trị | **CHƯA CÓ** |
| GNN | **CHƯA CÓ** |

### 3.2 Kiến trúc mô hình

| Hạng mục | Trạng thái |
|---|---|
| LightGBM / CatBoost / HistGB với chuỗi dự phòng | **ĐÃ CÓ** — `ml_engine/models.py` |
| Ranking (LGBMRanker) | **ĐÃ CÓ** |
| Mô hình chuỗi thời gian | **ĐÃ CÓ khung** — `TemporalSequenceModel` |
| Transformer / TFT | **CHƯA CÓ** |
| GCN quét ma trận cầu | **CHƯA CÓ** |
| Loss tùy biến (Focal / Brier) | **CHƯA CÓ trong sản xuất** — demo ở mục 1.3 |
| Platt scaling | **ĐÃ CÓ** |
| Temperature scaling | **ĐÃ CÓ** (chế độ đề) |
| Isotonic Regression | **ĐÃ CÓ** — là ứng viên trong `select_calibration`, lưu được dưới dạng nút |

### 3.3 Học liên tục

| Hạng mục | Trạng thái |
|---|---|
| Trọng số động theo hiệu suất cầu | **ĐÃ CÓ** — Thompson Sampling chiết khấu γ = 0,98 |
| Phát hiện trôi khái niệm | **ĐÃ CÓ** — ADWIN + KS |
| Bayesian Model Averaging | **ĐÃ CÓ một phần** — `learn_ensemble_weights.py` |
| Online/incremental cập nhật trọng số | **CHƯA CÓ** — hiện huấn luyện lại toàn phần |
| Chống quên thảm khốc (EWC/replay) | **CHƯA CÓ** |

Ghi chú về chống quên thảm khốc: nó là vấn đề của mạng nơ-ron huấn luyện tuần
tự. Kho này dùng bộ tăng cường huấn luyện lại từ cửa sổ 2 000 ngày mỗi lần
(mất **10,2 giây**), nên vấn đề ấy **không tồn tại** ở kiến trúc hiện tại. Đưa
online learning vào sẽ tạo ra một vấn đề mới để rồi phải giải nó.

### 3.4 Đánh giá

| Hạng mục | Trạng thái |
|---|---|
| Brier Score | **ĐÃ CÓ** (316 chỗ nhắc tới) |
| ECE | **ĐÃ CÓ** (259) |
| Log Loss | **ĐÃ CÓ** (332) |
| Reliability diagram | **ĐÃ CÓ** (30) |
| Precision@K / Recall@K | **ĐÃ CÓ** |
| AUC-ROC | **ĐÃ CÓ** — `MetaMetrics.auc_roc`, khớp `sklearn` kể cả khi có hoà |
| Walk-forward validation | **ĐÃ CÓ** — `ml_engine/validation.py` |
| Chống rò rỉ | **ĐÃ CÓ, có kiểm ngược** — đột biến kết quả tương lai không được đổi đặc trưng quá khứ |

Về AUC-ROC: nó đo khả năng XẾP HẠNG, bất biến với mọi phép biến đổi đơn điệu —
nghĩa là **một mô hình hiệu chuẩn sai bét vẫn có AUC hoàn hảo**. Với bài toán
mà giá trị nằm ở độ đúng của xác suất, AUC là chỉ số phụ. Brier và ECE mới là
chỉ số chính, và cả hai đã có.

## 4. Ba tầng ưu tiên

### Tầng 1 — ĐÃ TRIỂN KHAI

**1. Cổng tái lập** — `src/bridges/replication.py`

Quét + BH-FDR + kiểm data snooping **chỉ trên đoạn phát hiện**, rồi chấm điểm
các đường sống sót trên đoạn giữ riêng vốn chưa từng tham gia vào việc chọn.
Hiệu chỉnh đa kiểm định ở đoạn sau chạy trên đúng số đường đã đăng ký trước,
không phải 412 164.

Chạy thật trên `data/xsmb.csv`: cắt tại 2024-01-17 (1439/959 kỳ), 228 giây cho
cả ba chế độ, **0 đường qua FDR, 0 đường tái lập**. Bộ quét không nằm trong
quy trình hằng ngày nên chi phí này không chạm đường găng.

Không đường nào trong dữ liệu thật sống sót nổi đoạn phát hiện, nên đường tái
lập được kiểm bằng tín hiệu cài vào dữ liệu tổng hợp. Ca quyết định cài tín
hiệu **chỉ ở nửa đầu**: mọi cổng trước đó đều cho qua, chỉ cổng này bắt được.

**2. Mẫu số đi kèm mọi con số** — `run_bridge_scan.py`, `run_daily_prediction.py`

`bridge_scan_summary.json` nay mang cả khối `replication`, và bằng chứng kèm
dự đoán mang `replicated_out_of_sample` cạnh `hypotheses`. "3 đường tái lập"
mà không nói đã quét bao nhiêu giả thuyết là cách trình bày sai lệch nhất ở
đây, nên hai con số không bao giờ tách nhau.

**3. Chọn hiệu chuẩn bằng số đo** — `calibration.select_calibration`

Ba ứng viên — `identity`, `parametric` (Platt hoặc temperature), `isotonic` —
khớp trên lát đầu, chấm bằng Brier trên lát cuối cắt theo thời gian, giữ cái
thắng. Hoà điểm thì phương pháp đơn giản hơn thắng.

Ứng viên `identity` mới là điểm chính: trước đây **không gì kiểm xem phép hiệu
chuẩn có làm tệ đi hay không**. Cửa sổ dưới 60 kỳ thì bộ chọn giữ nguyên hành
vi cũ và ghi `selected: false` thay vì chọn bừa.

Isotonic nay lưu được dưới dạng nút đơn điệu trong `CalibParams`; tệp hiệu
chuẩn ghi trước khi có trường này vẫn nạp nguyên vẹn.

**4. AUC-ROC như chỉ số phụ** — `MetaMetrics.auc_roc`

Khớp `sklearn.metrics.roc_auc_score` tuyệt đối, kể cả khi có hoà. Trả `NaN`
thay vì 0,5 khi một lớp vắng mặt — 0,5 đọc thành "đoán mò", còn sự thật là
"không đo được".

Phép kiểm đi kèm chứng minh bằng số vì sao nó chỉ là chỉ số phụ: hai bộ xác
suất có **cùng AUC tuyệt đối** mà Brier chênh nhau hơn hai lần.

### Tầng 2 — gộp thông tin: ĐÃ TRIỂN KHAI

**5. Học độ co ngót thay vì đặt tay** — `src/hierarchical_pooling.py`

`statistical_signal.py` vốn ĐÃ là Beta-Binomial phân cấp: nó dựng tiên nghiệm
Beta quanh tần suất nền với `prior_strength = 80`. Vấn đề duy nhất là con số 80
được chọn bằng cảm tính. Nay nó được ước lượng từ chính dữ liệu bằng Bayes thực
nghiệm (phương pháp mô men trên phương sai giữa/trong đơn vị).

Đo walk-forward trên 938 kỳ của chính kho này, chế độ **lô tô**:

| Cách | Brier |
|---|---|
| gộp hoàn toàn (1 tham số) | **0,18138190** |
| gộp một phần (học κ) | 0,18138272 |
| `prior_strength = 80` (đặt tay) | 0,18149968 |
| không gộp (MLE riêng) | 0,18150858 |

Chế độ **đề** cho cùng thứ tự: 0,0099000000 / 0,0099000179 / 0,0099048218 /
0,0099052394.

κ học được có trung vị **1 000 000** (chạm trần) và nhỏ nhất 23 626 — tức dữ
liệu đòi co ngót mạnh hơn 80 từ ba trăm tới hơn mười nghìn lần. Con số 80 đặt
tay chỉ nhỉnh hơn việc **không gộp gì cả**.

Trên toàn bộ lịch sử, cả hai chế độ đều kết luận **co ngót hoàn toàn**: phương
sai giữa 100 con số không vượt nổi dao động nhị thức nội bộ. Số tham số hiệu
dụng **1,20 trên 100**.

Đó mới là phần thắng thật, và nó nối thẳng vào bảng công suất ở mục 1.2: ngưỡng
phát hiện với 100 giả thuyết là +15,8 % tương đối, với một giả thuyết là
+10,3 %. Kéo 100 tham số xuống ~1 là hạ ngưỡng ấy khoảng một phần ba — lớn hơn
nhiều lần so với vài phần trăm nghìn Brier.

**Mỗi phép đo học κ RIÊNG.** Bản đầu dùng một κ chung học từ tần suất tổng thể,
và cái sai ấy có hướng rõ ràng: tần suất chung đồng nhất kéo κ lên rất lớn, rồi
κ ấy nghiền nát một nhịp theo thứ **có thật**. Đo trên tín hiệu thứ Hai cài
sẵn: biên tách tụt từ 1,87 lần xuống 1,08 lần. Sau khi tách κ theo từng phép
đo, biên tách lên **2,24 lần** — tức mô hình nay **nhạy hơn** ở chỗ có tín hiệu
đồng thời **dè dặt hơn** ở chỗ không có. Đó chính là điều gộp phân cấp phải làm.

**6. Embedding cặp vị trí–giá trị** — chưa triển khai.

Khác với hạng mục 5, embedding **thêm** tham số chứ không bớt, nên nó đi ngược
lập luận công suất trừ khi số chiều bị ràng buộc rất chặt (8–16) và phải qua
cùng cổng ý nghĩa như mọi đặc trưng khác. Với số đo hiện tại — co ngót hoàn
toàn, tham số hiệu dụng 1,20 — dữ liệu đang nói rằng không có cấu trúc theo
từng con số để mà nhúng.

### Tầng 3 — kỳ vọng giá trị âm với dữ liệu hiện tại

7. **GNN / GCN trên ma trận vị trí.** Họ cầu ghép chéo đã là 412 164 giả
   thuyết; GNN học biểu diễn trên chính đồ thị ấy sẽ mở rộng không gian tìm
   kiếm thêm nữa, đẩy ngưỡng phát hiện lên trên +22,5 %.
8. **Transformer / TFT.** Cần hàng chục nghìn tới hàng triệu chuỗi để không
   khớp quá mức. Ở đây có 2 399 kỳ. Tỷ lệ tham số trên quan sát sai lệch nhiều
   bậc độ lớn.
9. **Focal Loss.** Đo được: phá hiệu chuẩn 6 500 lần, và sau khi hiệu chuẩn lại
   thì không hơn gì log-loss thường.

Nếu vẫn muốn thử tầng 3, điều kiện tối thiểu để kết quả có nghĩa: **đăng ký
trước** (pre-registration) giả thuyết và tiêu chí thành công trước khi nhìn dữ
liệu kiểm, cộng cổng tái lặp ở mục 1.

## 4b. Nâng cấp kiến trúc liên kết — kết quả đo

### Khảo sát: bốn tầng trộn lồng nhau, 32 hằng số, 5 được học

```
Tầng 1  number_dynamics    0,20·base + 0,20·markov2 + 0,17·hazard
                         + 0,20·trans + 0,13·lag + 0,10·regime
Tầng 2  statistical_signal 0,55·ewm + 0,25·weekday + 0,20·p90
                           rồi trộn dynamics ở 0,30 (lô tô) / 0,20 (đề)
Tầng 3  _blend_linear      w_ml + w_cau + w_stat + w_active + w_stable
Tầng 4  blend_predictions  p_linear vs p_meta theo meta_trust
```

Chỉ 5 trọng số tầng 3 từng được học. `stat ↔ dynamics = 0,681` không phải trùng
hợp — dynamics nằm SẴN trong stat ở trọng số cứng 0,30, nên trọng số hiệu dụng
của nó là 0,06 và bộ học không nhìn thấy. `cau_keo ↔ stat = −0,026`: gần trực
giao, và là chỗ duy nhất việc hợp tín hiệu còn dư địa thật.

### Giới hạn cấu trúc của trộn số học

`Σ wᵢpᵢ` luôn nằm trong `[min pᵢ, max pᵢ]`. Đo trên đầu ra thật: thành phần sắc
nhất có dải **73,0 %** của tần suất nền, đầu ra chỉ còn **23,0 %**.

Với tín hiệu **tiêm** +25 % vào một con, 180 kỳ giữ riêng:

| Phép hợp | Thu hồi tín hiệu |
|---|---|
| log-odds s=3 | 20,3 % |
| log-odds s=2 | 13,4 % |
| **trộn số học (đang dùng)** | **6,8 %** |
| log-odds s=0,7 | 4,7 % |

Kiến trúc hiện tại vứt bỏ **93 %** của một tín hiệu có thật.

### Nhưng trên dữ liệu THẬT, không gì đủ bằng chứng để đổi

Thống kê t cặp đôi so với trộn số học, 90 kỳ giữ riêng:

| | t | | t |
|---|---|---|---|
| s=0 | −1,13 | s=1 | −1,37 |
| s=0,3 | −1,17 | s=1,5 | +1,32 |
| s=0,5 | −1,20 | s=2 | +1,40 |
| s=0,7 | −1,24 | | |

**Không ứng viên nào đạt \|t\| ≥ 2.** Lý do: Brier trung bình trên cả 100 con,
nên cải thiện một con gần như không lay chuyển nó. Thu hồi tín hiệu và Brier đo
hai thứ khác nhau, và Brier mới là proper scoring rule.

Vì thế `SIGNIFICANCE_SIGMAS = 2.0`: **bản đương nhiệm chỉ bị soán ngôi khi ứng
viên vượt 2 sai số chuẩn.** Ở ngưỡng 1 SE, bộ chọn đã chọn `s = 0` — tức vứt
sạch tín hiệu và trả về đúng tần suất nền — trên một chênh lệch Brier 7e-6.

Kết quả: **trên dữ liệu thật, phép hợp giữ nguyên trộn số học.** Bộ chọn vẫn
chạy mỗi lần và sẽ tự đổi nếu bằng chứng đủ mạnh — đo được: với thành phần là
quan sát độc lập về cùng một tỉ lệ thật, nó chuyển sang log-odds với độ sắc > 1.

### Chu kỳ bán rã: hằng số duy nhất đổi được bằng bằng chứng

Chẩn đoán từ chính khung đo: thành phần `ewm` — trọng số lớn nhất tầng 2 (0,55)
— thu hồi **0,0 %** của tín hiệu tiêm +100 %, trong khi `weekday` thu 48,9 %.
Truy ra `half_life = 45` cho cỡ mẫu hiệu dụng 130 trên 2 398 kỳ.

| bán rã | ESS | Brier | ngụy tín hiệu | thu hồi @+100 % |
|---|---|---|---|---|
| 45 | 130 | 0,18134089 | 0,00001 | 0,0 % |
| 180 | 519 | 0,18133923 | 0,00002 | 36,0 % |
| 365 | 1031 | 0,18133891 | 0,00003 | 63,9 % |
| ∞ | 2398 | 0,18133866 | 0,00009 | 90,4 % |

Cổng hai chiều, đo trực tiếp:

| Tiêm | Chu kỳ chọn |
|---|---|
| không | **45** (giữ nguyên) |
| +25 % | **1460** |
| +100 % | **1460** |

Giữ bản đương nhiệm khi không có gì, nhảy sang cửa sổ dài nhất ngay khi có tín
hiệu thật. Trên dữ liệu thật hiện tại nó giữ 45 — nhưng nay đó là **kết luận đo
được**, không còn là hằng số đặt tay.

### Điều này có nghĩa gì

Đợt nâng cấp kiến trúc **không đổi hành vi sản xuất trên dữ liệu hôm nay**, và
đó là kết quả đúng: không thay đổi nào tự chứng minh được ở mức 2 SE.

Thứ đã đổi là: ba hằng số từng đặt tay (`prior_strength`, `half_life`, cách
hợp) nay được **kiểm tra lại mỗi lần chạy** trên lát giữ riêng cắt theo thời
gian. Nếu tín hiệu xuất hiện, hệ thống chuyển sang cấu hình thu hồi nó — đo
được là 0 % → 36 % ngay ở mức tiêm +25 %.

## 4c. Nhóm B — học các hằng số co ngót

Ba việc trong nhóm B. Hai việc đã làm và đo được là tốt hơn; việc thứ ba **dừng
lại**, kèm số liệu chứng minh lý do dừng.

### B1 — mười một hằng số κ trong `number_dynamics`: ĐÃ ĐỔI

Đường nền từng con trước đây co ngót với κ đặt tay `max(20, κ·0,5)` = 22,5; năm
ước lượng có điều kiện dùng mười hằng số theo chế độ (45/160, 35/100, 60/180,
45/120, 35/100). Nay tất cả được học bằng Bayes thực nghiệm.

Walk-forward qua chính `build_dynamics_signal`, t cặp đôi (âm là tốt hơn):

| | đặt tay | học | t |
|---|---|---|---|
| đường nền, lô tô, 400 kỳ | 0,18143488 | 0,18132998 | **−3,09** |
| năm thành phần, lô tô, 500 kỳ | 0,18149960 | 0,18145090 | **−2,90** |
| năm thành phần, lô tô, 1000 kỳ | 0,18139358 | 0,18134064 | **−4,05** |
| năm thành phần, đề, 500 kỳ | 0,00990056 | 0,00990003 | −1,22 |
| năm thành phần, đề, 1000 kỳ | 0,00990057 | 0,00990005 | −1,64 |

Ở chế độ **đề** phép học không vượt ngưỡng 2 SE — đó là hoà, không phải thắng.
Vẫn dùng cho cả hai chế độ vì thay đổi này **bớt** mười một hằng số chứ không
thêm tham số nào.

Kết luận đáng chú ý hơn Brier: trên dữ liệu ngẫu nhiên thuần, ba trong năm ước
lượng có điều kiện co ngót **hoàn toàn** (lệch tuyệt đối khỏi đường nền, trung
vị / lớn nhất):

| thành phần | học | đặt tay |
|---|---|---|
| chuyển trạng thái | 0,00000 / 0,00000 | 0,00499 / 0,01990 |
| Markov bậc hai | 0,00000 / 0,00002 | 0,01400 / 0,06184 |
| nhân độ trễ | 0,00018 / 0,01344 | 0,00914 / 0,03315 |

### B2 — bảng đề → lô tô ngày sau: ĐÃ ĐỔI

Khớp 1 792 cặp đầu, chấm điểm 598 cặp đuôi mà phép khớp chưa từng thấy:

| | Brier | log-loss | t |
|---|---|---|---|
| κ = 60 (đặt tay) | 0,18208903 | 0,550738 | — |
| co ngót hoàn toàn | 0,18162217 | 0,549427 | −6,02 |
| **học κ** | 0,18166797 | 0,549560 | **−6,15** |

Trung vị κ học được là 1 000 000 — co ngót hoàn toàn. Với dữ liệu hiện có,
"đề về s hôm nay" **không** phân biệt được phân phối lô tô ngày mai so với
phân phối chung; BH-FDR trên chính bảng ấy cũng cho đúng 0 ô có ý nghĩa.

### B3 — không gian trạng thái cho tần suất nền: **DỪNG**

Ý định là thay tần suất nền toàn cục tĩnh bằng một mô hình mức cục bộ một tham
số, để nó trôi theo thời gian. Đo trước khi viết, và số liệu nói không.

**Thứ nhất — không có trôi chậm.** Phương sai của trung bình trượt 90 kỳ:
quan sát 2,137e-06, so với 2 000 lần hoán vị thời gian cho 2,399e-06.
p một phía = **0,656**. Chuỗi thật trôi **ít hơn** chuỗi xáo trộn ngẫu nhiên.

**Thứ hai — không có tự tương quan.** Trên 2 399 kỳ (SE ≈ 0,0204):

| trễ | 1 | 2 | 7 | 30 | 90 | 365 |
|---|---|---|---|---|---|---|
| z | −1,05 | +0,10 | −0,03 | −2,41 | +0,78 | +0,43 |

Một giá trị vượt 2 trên sáu phép thử là đúng mức kỳ vọng ngẫu nhiên.

**Thứ ba, và quyết định — mọi bộ lọc đều tệ hơn.** So ngoài mẫu trên 1 999 kỳ
với trung bình toàn cục mở rộng dần (MSE 2,31085e-04); **dấu dương là tệ hơn**:

| α | MSE | chênh | t |
|---|---|---|---|
| 0,001 | 2,31144e-04 | +5,86e-08 | +0,69 |
| 0,003 | 2,31423e-04 | +3,38e-07 | +1,80 |
| 0,01 | 2,32393e-04 | +1,31e-06 | **+2,36** |
| 0,03 | 2,34889e-04 | +3,80e-06 | **+3,34** |
| 0,1 | 2,44022e-04 | +1,29e-05 | **+5,59** |
| 0,2 | 2,58089e-04 | +2,70e-05 | **+7,63** |
| 0,3 | 2,73978e-04 | +4,29e-05 | **+9,43** |
| 0,5 | 3,12416e-04 | +8,13e-05 | **+12,63** |

Thiệt hại tăng **đơn điệu** theo độ nhạy. Đó không phải "chưa chỉnh đúng tham
số" — đó là hình dạng của một mô hình đang đuổi theo nhiễu. Một mô hình không
gian trạng thái sẽ thêm ít nhất một tham số phương sai trạng thái để làm tệ đi
một đại lượng vốn đã hằng số.

Có một lý do cơ học đứng sau: số giải mỗi kỳ là **cố định**, nên tần suất nền
chỉ xê dịch được qua số con trùng trong cùng một kỳ. Nó bị chặn chặt từ trong
thiết kế trò chơi, không phải từ dữ liệu.

**Kết luận: giữ trung bình toàn cục. Đã khoá bằng phép kiểm hồi quy**
(`tests/test_global_rate_is_stationary.py`) để lần sau ai muốn thêm mô hình
động thì phải đo lại trước.

## 5. Checklist rủi ro kỹ thuật

### Rò rỉ dữ liệu (look-ahead bias)

- [ ] **Không bao giờ trộn ngẫu nhiên chuỗi thời gian.** Mọi lát cắt phải theo
      thời gian. Kho đã tuân thủ; demo ở mục 1.3 cũng vậy.
- [ ] **Đặc trưng theo thứ phải dùng thứ của NGÀY ĐÍCH**, không phải ngày neo.
      Đây là bẫy lệch một ngày đã được khoá bằng phép kiểm riêng.
- [ ] **Hiệu chuẩn học trên lát riêng**, không phải trên tập kiểm — nếu không,
      ECE đẹp là ảo.
- [ ] **Chuẩn hoá/scaling phải fit trên tập huấn luyện rồi mới áp cho tập sau.**
- [ ] **Kiểm ngược bằng đột biến tương lai**: đổi kết quả của mọi ngày sau mốc
      cắt, rồi đòi đặc trưng trước mốc KHÔNG đổi một bit. Kho có phép kiểm này;
      đó là cách duy nhất chứng minh không rò rỉ thay vì tin là không.
- [ ] **Gan phải đếm theo KỲ QUAY, không theo ngày lịch** — XSMB nghỉ Tết và
      nghỉ 01–22/04/2020.

### Khớp quá mức trên chuỗi nhiễu

- [ ] **Hiệu chỉnh đa kiểm định là bắt buộc, không tùy chọn.** BH-FDR tối
      thiểu; Bonferroni cho kết luận mạnh.
- [ ] **Ghi lại số giả thuyết đã quét.** Một p = 0,001 trong 412 164 phép thử
      là kỳ vọng có ~412 kết quả như vậy hoàn toàn do may rủi.
- [ ] **Đòi tái lặp trên tập giữ riêng theo thời gian**, không chỉ p-value.
- [ ] **So với đường nền ở mọi báo cáo.** Một Brier 0,18 nghe có vẻ tốt cho tới
      khi biết đường nền cũng là 0,18.
- [ ] **Cổng chất lượng phải có quyền phủ quyết.** Skill ≤ 0 thì hạ `model_trust`
      — kho đã làm đúng và đang để lô tô ở `quality_pass = False`.
- [ ] **Cẩn thận với isotonic khi ít dữ liệu hiệu chuẩn** — đo được là thua
      Platt ở đây.

### Chỉ số đánh giá gây hiểu nhầm

- [ ] **Accuracy vô nghĩa với lớp mất cân bằng.** Đoán "không về" luôn đúng
      76,2 % ở bài toán lô tô.
- [ ] **AUC bất biến với phép biến đổi đơn điệu** — hiệu chuẩn sai vẫn AUC đẹp.
- [ ] **Proper scoring rule là bắt buộc**: Brier hoặc log-loss. Focal Loss
      không phải, và số đo ở mục 1.3 cho thấy hậu quả.

### Rủi ro vận hành

- [ ] **Phiên bản scikit-learn phải khớp** giữa lúc huấn luyện và lúc nạp — kho
      đã cảnh báo `InconsistentVersionWarning` khi nạp mô hình cũ.
- [ ] **Phiên bản lược đồ đặc trưng phải được kiểm**; mô hình cũ với bộ đặc
      trưng mới là hỏng âm thầm.
- [ ] **Không để mô hình mở rộng danh sách đặc trưng cho phép** — kho đã có
      phép kiểm chặn.

## 6. Mã demo

`scripts/demo_probability_losses.py` — chạy được, trên dữ liệu thật:

```bash
PYTHONPATH=src python3 scripts/demo_probability_losses.py
```

Nó minh hoạ đúng ba thứ đề bài yêu cầu:

1. **Hàm mất mát tùy biến** cho LightGBM: Focal Loss và Brier objective, viết
   đầy đủ gradient và hessian, kèm chốt kẹp hessian (Brier không lồi theo logit
   — không kẹp thì bộ tăng cường đi ngược hướng ở đúng những mẫu khó nhất).
2. **Hiệu chuẩn** Platt và Isotonic, học trên lát riêng.
3. **Đo** Brier, LogLoss, ECE và skill score so với đường nền.

Một chi tiết dễ mất nửa tiếng để lần ra, đã ghi trong mã: LightGBM gọi hàm mục
tiêu theo thứ tự `(dự_đoán_thô, Dataset)`, ngược với quy ước `(y_thật, thô)`
của sklearn; và khi dùng hàm tùy biến thì LightGBM **không** áp sigmoid nội bộ
nữa, nên phải tự áp — quên là "xác suất" nằm ngoài khoảng [0, 1].

## 7. Điều tài liệu này KHÔNG khẳng định

Nó không khẳng định XSMB là ngẫu nhiên thuần. Nó khẳng định điều hẹp hơn và đo
được: **với 2 399 kỳ hiện có, không cấu hình nào trong số đã thử tách được
khỏi đường nền, và bất kỳ quy luật nào yếu hơn +22,5 % tương đối đều không
phân biệt được với nhiễu ở quy mô quét hiện tại.**

Đó là một phát biểu về CÔNG SUẤT của phép đo, không phải về bản chất của thế
giới. Cách duy nhất làm nó đổi là thêm dữ liệu hoặc thu hẹp mạnh không gian
giả thuyết — không phải thêm tầng mạng.
