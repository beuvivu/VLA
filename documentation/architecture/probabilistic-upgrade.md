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
| Isotonic Regression | **CHƯA CÓ** — và mục 1.3 cho thấy nó **thua** Platt ở đây |

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
| AUC-ROC | **CHƯA CÓ** |
| Walk-forward validation | **ĐÃ CÓ** — `ml_engine/validation.py` |
| Chống rò rỉ | **ĐÃ CÓ, có kiểm ngược** — đột biến kết quả tương lai không được đổi đặc trưng quá khứ |

Về AUC-ROC: nó đo khả năng XẾP HẠNG, bất biến với mọi phép biến đổi đơn điệu —
nghĩa là **một mô hình hiệu chuẩn sai bét vẫn có AUC hoàn hảo**. Với bài toán
mà giá trị nằm ở độ đúng của xác suất, AUC là chỉ số phụ. Brier và ECE mới là
chỉ số chính, và cả hai đã có.

## 4. Ba tầng ưu tiên

### Tầng 1 — giá trị thật, rủi ro thấp (nên làm)

1. **Cổng tái lặp bắt buộc.** Báo cáo ngẫu nhiên cho thấy tín hiệu duy nhất
   sống sót Bonferroni đã **không tái lặp** giữa hai nửa dữ liệu. Biến phép
   kiểm tái lặp thành cổng chặn: quy tắc nào không tái lặp thì không được vào
   ensemble, bất kể p-value đẹp đến đâu.
2. **Ghi nhận số giả thuyết vào nhật ký mỗi lần chạy.** Hiện `randomness_report`
   tính công suất theo họ giả thuyết, nhưng con số ấy không đi kèm từng dự
   đoán. Gắn "quét bao nhiêu quy tắc để ra kết quả này" vào đầu ra khiến việc
   đọc kết quả trung thực hơn nhiều.
3. **Chọn phương pháp hiệu chuẩn bằng số đo, không bằng niềm tin.** Thử Platt,
   temperature và isotonic trên lát hiệu chuẩn rồi giữ cái tốt nhất trên lát
   kiểm. Mục 1.3 cho thấy isotonic thua, nhưng điều đó có thể đổi khi dữ liệu
   dài thêm — nên hãy để số liệu quyết định mỗi lần chạy.
4. **Thêm AUC-ROC như chỉ số PHỤ**, kèm ghi chú rõ nó không đo hiệu chuẩn.

### Tầng 2 — có thể có giá trị, cần thận trọng

5. **Gộp thông tin (partial pooling / hierarchical).** Đây là hướng DUY NHẤT
   thực sự nâng công suất thống kê: thay vì 100 mô hình độc lập cho 100 con,
   dùng một mô hình phân cấp có hiệu ứng ngẫu nhiên theo con số, co về trung
   bình chung. Nó giảm số tham số hiệu dụng, tức giảm số giả thuyết hiệu dụng.
6. **Embedding cặp vị trí–giá trị**, nhưng học có ràng buộc chiều thấp (8–16)
   và phải qua cùng cổng ý nghĩa như mọi đặc trưng khác.

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
