# `src/ml_engine/` — Autonomous Continuous Learning & Accuracy Enhancer

> Bản thiết kế kỹ thuật kèm kết quả đo. Mọi con số trong tài liệu này tái lập
> được bằng `python src/ml_engine/main_pipeline.py`; không con số nào viết tay.

---

## 1. Hợp đồng dữ liệu đầu vào

Toàn bộ bảo đảm chống rò rỉ thời gian của module dựa trên **một** giả định:
chỉ số hàng bằng thứ tự thời gian. Nếu giả định đó sai — thiếu ngày, trùng
ngày, hay dữ liệu chưa sắp xếp — thì `counts[:t]` không còn nghĩa là "quá khứ",
và mọi phép kiểm không-rò-rỉ sẽ *đạt* trong khi hệ thống vẫn nhìn thấy tương
lai. Vì vậy `ObservationMatrix` từ chối dựng nếu giả định không giữ.

### Schema chuẩn

| Trường | Kiểu | Ràng buộc |
|---|---|---|
| `dates` | `pd.DatetimeIndex` | tăng nghiêm ngặt, **liên tục từng ngày**, không trùng |
| `counts` | `np.ndarray (n_days, 100)` | không âm; **mỗi hàng tổng đúng 27** |

Bảng thô đầu vào cần cột `date` cùng 27 cột giải của `xsmb_domain.PRIZE_FIELDS`.

```python
ObservationMatrix.from_frame(pd.read_csv("data/xsmb.csv"))
```

**Một chi tiết dễ mất dữ liệu.** Tệp CSV lưu giải dưới dạng số nguyên nên số 0
đứng đầu bị mất: giải 7 `"08"` nằm trong tệp là `8`, giải 4 `"0000"` là `0`.
Trên dữ liệu hiện tại có **1 093** ô bị mất ít nhất một số 0 đứng đầu, trong đó
**160** ô co lại còn dưới hai chữ số. Phải đệm 0 về đúng bề rộng khai báo của
từng giải *trước khi* lấy hai chữ số cuối. Kết quả được đối chiếu bit-for-bit
với `DigitTensor` sẵn có của kho, và một phép kiểm giữ nguyên ràng buộc đó.

### JSON yêu cầu hằng ngày

```json
{ "anchor_date": "2026-09-06", "top_k": 10 }
```

`target_date` suy ra là ngày kế tiếp và bị kiểm: một yêu cầu dự đoán cách ngày
neo nhiều hơn một ngày sẽ bị từ chối chứ không âm thầm chấp nhận.

---

## 2. Cấu trúc module

```
src/ml_engine/
├── __init__.py          Bề mặt công khai (25 ký hiệu)
├── capabilities.py      Dò thư viện tùy chọn MỘT LẦN, ở MỘT CHỖ
├── schema.py            ObservationMatrix, DailyRequest — chặn rò rỉ từ gốc
├── features.py          Sinh đặc trưng tự động, bảo đảm chỉ dùng quá khứ
├── selection.py         SHAP → tầm quan trọng hoán vị
├── models.py            TabularBooster · RankingBooster · TemporalSequenceModel
├── bandit.py            DiscountedThompsonSamplingMAB
├── drift.py             ConceptDriftDetector (ADWIN + KS)
├── fallback.py          SafeModeController
├── metrics.py           Quy tắc chấm điểm chặt + chỉ số kinh tế
├── validation.py        WalkForwardValidator + Optuna
└── main_pipeline.py     Tầng điều phối, điểm vào dòng lệnh
```

Nguyên tắc SOLID được áp dụng ở ba chỗ có hệ quả thật:

* **Trách nhiệm đơn lẻ** — `drift.py` không biết gì về mô hình; nó nhận một
  chuỗi số thực. Nhờ vậy nó kiểm thử được bằng chuỗi tổng hợp có tính chất đã
  biết, không cần dựng cả pipeline.
* **Đảo ngược phụ thuộc** — tầng điều phối phụ thuộc giao thức `Learner`
  (`fit` + `predict_proba`), không phụ thuộc LightGBM. Thêm hay bỏ một họ mô
  hình không chạm phần còn lại.
* **Đóng/mở** — thêm một "cánh tay" là thêm một mục vào `_build_arms()`; bandit,
  chỉ số và chế độ an toàn không đổi một dòng nào.

### Suy giảm khi thiếu thư viện

Mỗi khả năng thiếu đều có **đường lui đã cài và đã kiểm thử**, không phải nhánh
chết:

| Thư viện | Vai trò | Đường lui |
|---|---|---|
| `lightgbm` | boosting bảng, LambdaMART | `catboost` → `HistGradientBoosting` |
| `optuna` | dò siêu tham số có cắt tỉa | dò ngẫu nhiên có hạt giống cố định |
| `shap` | tầm quan trọng đặc trưng | tầm quan trọng hoán vị |
| `river` | ADWIN trực tuyến | ADWIN tự cài trong `drift.py` |
| `torch` | GRU chuỗi thời gian | ridge đa nhãn trên cửa sổ trễ |

`torch` (~11 GB) và `catboost` không nằm trong `requirements-ml-engine.txt`:
chúng được dùng tự động nếu môi trường đã có.

---

## 3. Các thành phần lõi

### 3.1 `DiscountedThompsonSamplingMAB`

**Cơ sở.** Mỗi cánh tay có tỉ lệ trúng ẩn `θᵢ`. Tiên nghiệm liên hợp
`θᵢ ~ Beta(α₀, β₀)`; sau `Sᵢ` lần trúng và `Fᵢ` lần trượt, hậu nghiệm là
`Beta(α₀+Sᵢ, β₀+Fᵢ)`. Lấy mẫu Thompson rút `θ̃ᵢ ~ Beta(αᵢ, βᵢ)` rồi lấy `argmax`
— *xác suất khớp*: mỗi cánh tay được chọn đúng bằng xác suất hậu nghiệm rằng nó
tốt nhất, nên khai thác và thăm dò cân bằng mà không cần tham số `ε`.

**Vì sao chiết khấu.** Thompson thuần giả định `θᵢ` cố định. Trong miền này giả
định đó sai theo cách nguy hiểm nhất: cầu "chạy" rồi "gãy", và bandit không
chiết khấu còn tin nó rất lâu sau khi gãy.

```
Sᵢ ← γ·Sᵢ + r      Fᵢ ← γ·Fᵢ + (1−r)
```

**Hệ quả quan trọng nhất — và là giới hạn thật của phương pháp.** Tổng quan sát
hiệu dụng bị chặn:

```
n_eff = Σ γᵏ = 1/(1−γ)          γ = 0.98 → n_eff = 50
```

Với `n_eff = 50` quanh nền 0.2377, sai số chuẩn là **0.0602**. Bandit *không
thể* phân giải chênh lệch nhỏ hơn khoảng hai lần con số đó, dù chạy bao nhiêu
năm. `power_floor()` trả về đúng đại lượng này để người gọi không nhầm dao động
với phong độ.

Con số 0.0602 gần trùng với ngưỡng phát hiện +0.0603 tính được từ phân tích
công suất trên 391 kỳ ở [báo cáo định lượng](../research/quantitative-architecture.md).
Hai phép tính độc lập, cùng một trần.

**Trọng số trộn.** `select_weights()` rút `draws` lần từ hậu nghiệm và đếm tần
suất mỗi cánh tay thắng — ước lượng Monte Carlo của `P(cánh tay i tốt nhất | dữ
liệu)`. Trộn theo đó giữ tính chất khớp xác suất nhưng cho dự báo trơn thay vì
nhảy giữa các cánh tay.

**Tuần tự hóa.** `to_dict()` lưu **cả trạng thái bộ sinh ngẫu nhiên**. Thiếu
điều đó thì mỗi lần khởi động lại tiến trình sẽ đổi hành vi thăm dò và không
bản chạy nào tái lập được. Một phép kiểm khẳng định `select_weights()` trước và
sau vòng JSON cho kết quả *giống hệt*.

### 3.2 `ConceptDriftDetector`

Hai phương pháp, hai vai trò khác nhau:

* **ADWIN** giữ cửa sổ thích ứng, xét các điểm cắt và so chênh lệch trung bình
  hai nửa với chặn Hoeffding; vượt chặn thì **vứt nửa cũ**. Cửa sổ tự điều
  chỉnh, không có tham số "dùng bao nhiêu ngày" — và tham số đó chính là thứ dễ
  bị chỉnh cho tới khi ra kết quả mong muốn.
* **Kolmogorov–Smirnov** so toàn bộ *hình dạng* phân phối. Cần cả hai vì mô hình
  có thể giữ nguyên sai số trung bình trong khi phương sai bung ra — ADWIN
  không thấy, KS thấy.

> **Một lỗi đã sửa trong lúc xây.** Bản đầu của ADWIN tự cài xét **cả `n` điểm
> cắt**, nên phải hiệu chỉnh đa kiểm định theo `δ/n`. Chặn rộng đến mức nó
> **không bao giờ báo động** trên cùng dữ liệu mà river bắt được — một đường lui
> chết. Cách sửa đúng là lấy điểm cắt trên **lưới cấp số nhân** (tinh thần cấu
> trúc bucket của ADWIN2): chỉ `O(log n)` giả thuyết, hiệu chỉnh nhẹ hơn nhiều,
> vẫn phủ mọi thang thời gian. Đo lại trên 10 hạt giống:

| Bản cài | Báo giả / 3000 quan sát ổn định | Phát hiện sau (trung vị) | Tệ nhất |
|---|---:|---:|---:|
| `river` | 0 | 83 | 115 |
| tự cài (đã sửa) | 0 | 87 | 121 |

**Cảnh báo về giá trị p của KS.** KS giả định quan sát độc lập; sai số theo ngày
thường tự tương quan, nên p danh nghĩa **lạc quan quá mức**. Ngưỡng mặc định
đặt chặt hơn thông lệ (0.01 thay vì 0.05), và lớp trả về cả thống kê lẫn p để
người gọi tự quyết định.

### 3.3 `WalkForwardValidator` + Optuna

Rò rỉ tinh vi nhất **không** nằm ở vòng huấn luyện mà ở việc dò siêu tham số:
chọn tham số bằng cách nhìn điểm trên tập đánh giá rồi báo cáo chính điểm đó là
rò rỉ, dù mỗi lần khớp riêng lẻ đều sạch. Lịch sử vì vậy chia **ba đoạn không
chồng lấn**, theo đúng thứ tự thời gian:

```
[0 ────── warmup) [warmup ────── tune_end) [tune_end ────── n)
   khởi động         Optuna chỉ thấy đoạn này    chạm đúng MỘT lần
```

Cắt tỉa dùng `MedianPruner`, sampler dùng `TPESampler(seed=...)`. Không gian
tham số cố ý **hẹp**: không gian rộng trên dữ liệu gần như ngẫu nhiên chỉ làm
tăng số giả thuyết được thử, và giá trị "tốt nhất" sẽ phản ánh may rủi của tìm
kiếm chứ không phải cấu trúc.

Mục tiêu tối ưu là **log-loss**, không phải Hit-Rate: Hit-Rate không phải quy
tắc chấm điểm chặt, nên chọn tham số theo nó sẽ chọn ra mô hình xếp hạng nhỉnh
hơn mà xác suất tệ hơn hẳn.

---

## 4. Luồng điều phối

```
JSON → ObservationMatrix (kiểm hợp đồng)
     → sinh đặc trưng (20 cột, không rò rỉ)
     → chọn đặc trưng bằng SHAP
     → 6 cánh tay khai báo xác suất độc lập
     → MAB trộn theo trọng số hậu nghiệm
     → CHẾ ĐỘ AN TOÀN có quyền phủ quyết   ← đứng sau MAB, không phải trước
     → Top-K
     → kết quả thật → phần thưởng → cập nhật MAB
                    → sai số → phát hiện trôi lệch
                    → chỉ số → nhật ký
```

Hai quyết định thiết kế mang tính quyết định:

**Chế độ an toàn đứng *sau* MAB.** MAB tối ưu trong giả định "có ít nhất một
cánh tay đáng dùng". Chế độ an toàn là nơi duy nhất chất vấn chính giả định đó,
nên nó phải có tiếng nói sau cùng.

**Nền là một cánh tay.** `baseline` được đăng ký như cánh tay bình thường, cạnh
tranh sòng phẳng. Nhờ vậy hệ thống *kết luận bằng dữ liệu* rằng không mô hình
nào đáng tin — trọng số dồn về nền — thay vì cần người quyết định. Không có
cánh tay nền thì trọng số luôn bị chuẩn hóa **giữa các mô hình**, và hệ thống
không có cách nào diễn đạt câu "không cái nào đáng dùng".

**Phần thưởng chấm theo lựa chọn của chính cánh tay.** Mỗi cánh tay được chấm
theo Top-10 *của riêng nó*, không theo lựa chọn chung — nếu không thì mọi cánh
tay nhận cùng phần thưởng và bandit không học được gì.

### Ngưỡng `T_min` neo vào miền

Một ngưỡng tùy chọn kiểu "dưới 30% thì chuyển chế độ an toàn" có vấn đề: không
ai biện minh được con số đó, nên khi hệ thống chạm ngưỡng, phản xạ tự nhiên là
hạ ngưỡng.

`T_min` mặc định bằng đúng **tỉ lệ nền** (0.2377). Lập luận thẳng: chọn Top-K
ngẫu nhiên trong 100 con đã cho tỉ lệ trúng bằng nền. Nếu Top-K của mô hình rơi
*xuống dưới* mức đó thì mô hình đang xếp hạng tệ hơn cả bốc ngẫu nhiên. Đó là
ngưỡng duy nhất không cần biện minh thêm.

Rời chế độ an toàn cần 5 kỳ liên tiếp đạt lại, không phải một kỳ may mắn — nếu
không hệ thống sẽ dao động vào ra liên tục.

---

## 5. Chỉ số, và vì sao không dùng độ chính xác

Ở nền 23.77%, mô hình luôn nói "không về" đạt **76.23% độ chính xác** mà không
mang một bit thông tin nào.

| Nhóm | Chỉ số | Dùng để |
|---|---|---|
| Quy tắc chấm điểm **chặt** | log-loss, Brier, kỹ năng, t ghép cặp | **quyết định** |
| Xếp hạng | Hit-Rate@3/5/10/27, precision, recall | **báo cáo** |
| Kinh tế | tỉ suất lời/lỗ, ngưỡng hòa vốn | quy ra đơn vị người chơi chịu |

### Ngưỡng hòa vốn là con số quan trọng nhất

Với luật chi trả lô tô thông thường (đặt 23, trúng 80):

```
ngưỡng hòa vốn        = 23/80 = 0.2875
nền                   =         0.2377
lợi thế người chơi ở nền      = −17.34%
cải thiện tương đối cần để hòa vốn = +21.0%
```

Con số **+21.0%** gần trùng với mức chênh lệch nhỏ nhất mà 391 kỳ đủ sức phát
hiện (**+25.4%**). Hai đại lượng đến từ hai phép tính hoàn toàn độc lập — một
từ luật chi trả, một từ lý thuyết thống kê — và việc chúng gặp nhau nói lên
điều cốt lõi: **ngưỡng để có lãi nằm đúng ở ranh giới khả năng phát hiện của dữ
liệu.** Một hệ thống báo rằng nó vượt ngưỡng đó, trên lịch sử cỡ này, gần như
chắc chắn đang đo may rủi.

---

## 6. Kết quả đo trên 192 kỳ

```bash
python src/ml_engine/main_pipeline.py --start 200 --stop 392 --refit-every 24
```

| Chỉ số | Giá trị |
|---|---:|
| Kỹ năng log-loss | **−0.000670** |
| t ghép cặp (mức ngày) | **−1.79** |
| Kỹ năng Brier | −0.000832 |
| Vượt nền | **KHÔNG** |

| K | Trúng@K | Chọn ngẫu nhiên | Lời/lỗ |
|---|---:|---:|---:|
| 3 | 0.7240 | 0.7130 | −16.1% |
| 5 | 1.2552 | 1.1883 | −12.7% |
| 10 | 2.4740 | 2.3766 | −13.9% |

| Cánh tay | Trung bình hậu nghiệm | Khoảng tin cậy 95% | Vượt nền |
|---|---:|---|:---:|
| `temporal_sequence` | 0.2395 | [0.1357, 0.3620] | ✗ |
| `ranking_lambdamart` | 0.2331 | [0.1306, 0.3547] | ✗ |
| `frequency` | 0.2320 | [0.1297, 0.3534] | ✗ |
| `gap_hazard` | 0.2279 | [0.1265, 0.3488] | ✗ |
| `baseline` | 0.2218 | [0.1216, 0.3418] | — |
| `tabular_boosting` | 0.2193 | [0.1197, 0.3389] | ✗ |

**Chế độ an toàn: 120/192 kỳ (62%). Trôi lệch: 0 lần.**

Ba điều đáng đọc kỹ:

1. **Mọi khoảng tin cậy chồng lên nhau và đều chứa nền.** Sau 192 kỳ, hệ thống
   không phân biệt được sáu phương pháp với nhau, cũng không phân biệt được cái
   nào với việc bốc ngẫu nhiên. Đây không phải hạn chế của cài đặt — đó là trần
   `n_eff = 50` ở §3.1 hiện ra đúng như dự đoán.
2. **Trúng@K nhỉnh hơn ngẫu nhiên (+4.1% ở K=10) trong khi kỹ năng log-loss
   âm.** Chính là hiện tượng §5 cảnh báo: chỉ số xếp hạng và quy tắc chấm điểm
   chặt cho hai câu trả lời ngược nhau, và chỉ câu thứ hai đáng tin.
3. **Lời/lỗ âm ở mọi mức K**, dù có nhỉnh hơn mức −17.34% của việc đặt cược
   thuần theo nền. Hệ thống chuyển một phần lợi thế nhà cái về phía người chơi
   nhưng không xóa được nó, và đúng như §5 dự đoán, khoảng cách còn lại lớn hơn
   những gì dữ liệu đủ sức chứng minh là thật.

Kết quả đúng ở đây là hệ thống **tự chuyển sang chế độ an toàn 62% thời gian**
mà không cần ai can thiệp. Đó chính là hành vi mà kiến trúc được thiết kế để
tạo ra: khi không có bằng chứng, mặc định là nền.

---

## 7. Vận hành

```bash
# Cài phụ thuộc tùy chọn (torch/catboost dùng tự động nếu có sẵn)
pip install -r requirements-ml-engine.txt

# Chạy backtest học tiếp diễn, ghi báo cáo và lưu trạng thái MAB
python src/ml_engine/main_pipeline.py \
    --start 200 --stop 392 --refit-every 24 \
    --out data/research/ml_engine_report.json \
    --bandit-state data/ml_engine/bandit_state.json

# Bỏ các cánh tay nặng khi chạy trên máy yếu
python src/ml_engine/main_pipeline.py --no-temporal --no-ranking

# Kiểm thử
python -m pytest tests/test_ml_engine.py -q     # 88 phép kiểm
```

Trạng thái MAB tích lũy qua các lần chạy nhờ `--bandit-state`: đó là cơ chế
"học tiếp diễn" ở mức vận hành — hậu nghiệm của hôm nay là tiên nghiệm của ngày
mai, và chiết khấu bảo đảm dữ liệu quá cũ mờ dần đi.

## 8. Điều gì sẽ làm đổi kết luận

1. Một cánh tay có **cận dưới** khoảng tin cậy vượt nền (`beats_baseline` trả
   `True` trong báo cáo) — không phải trung bình hậu nghiệm vượt nền, vốn rất
   dễ xảy ra do may rủi.
2. Kỹ năng log-loss dương với **t ghép cặp > 2.5** trên ít nhất 200 kỳ.
3. Chế độ an toàn tự rời trạng thái `safe` và **giữ** `normal` qua một quý.
4. Thêm dữ liệu: ngưỡng phát hiện co theo `1/√n`. Riêng trần `n_eff` của bandit
   thì **không** — muốn hạ nó phải nâng `γ`, và điều đó đánh đổi bằng tốc độ
   thích ứng khi cầu gãy.
