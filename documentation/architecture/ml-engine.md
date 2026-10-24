# `src/research/ml_engine/` — Autonomous Continuous Learning & Accuracy Enhancer

> Bản thiết kế kỹ thuật kèm kết quả đo. Mọi con số trong tài liệu này tái lập
> được bằng `python src/research/ml_engine/main_pipeline.py`; không con số nào viết tay.

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
src/research/ml_engine/
├── __init__.py          Bề mặt công khai (24 ký hiệu)
├── capabilities.py      Dò thư viện tùy chọn MỘT LẦN, ở MỘT CHỖ
├── schema.py            ObservationMatrix, DailyRequest — chặn rò rỉ từ gốc
├── features.py          Sinh đặc trưng tự động, bảo đảm chỉ dùng quá khứ
├── selection.py         SHAP → tầm quan trọng hoán vị
├── models.py            TabularBooster · RankingBooster · TemporalSequenceModel
├── aggregation.py       ExponentialWeights — trọng số mũ trên log-loss
├── drift.py             ConceptDriftDetector (ADWIN + KS)
├── fallback.py          SafeModeController — cổng độ tin model_trust
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
* **Đóng/mở** — thêm một "cánh tay" là thêm một mục vào `_build_arms()`; phép
  trộn, chỉ số và cổng độ tin không đổi một dòng nào.

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

### 3.1 `ExponentialWeights` — thay bandit Thompson từ 20-10-2026

**Vì sao gỡ bandit.** Bản trước trộn bằng Thompson Sampling có chiết khấu
γ = 0,98, thưởng `1 − Brier`. Chiết khấu chặn số quan sát hiệu dụng ở 50, nên độ
lệch chuẩn hậu nghiệm không xuống dưới ~0,05, trong khi chênh Brier thật giữa
các cánh tay cỡ 10⁻⁵–10⁻⁴: trọng số là nhiễu của bộ sinh ngẫu nhiên. Beta với
thưởng liên tục cũng không phải hậu nghiệm của thứ gì. Đo trên 1 000 kỳ (§6), bản
bandit kèm ngưỡng Hit-Rate kém hằng số **z = −3,40**.

**Phép trộn mới.** Sau khi biết kết quả kỳ `t`:

```
w_i ← w_i · exp(−η · L_i,t)          L = log-loss CỘNG 100 con của kỳ
w   ← (1 − α) · w / Σw + α / K       chia sẻ cố định (Herbster–Warmuth)
p_j = Σ_i w_i p_ij                   biên của hỗn hợp
```

Với `η = 1`, `L` là âm log-hợp lý của kỳ dưới luật của cánh tay, nên `w` là hậu
nghiệm Bayes của các cánh tay; chia sẻ cố định là Bayes với tiên nghiệm "đổi
cánh tay đúng nhất với xác suất α mỗi kỳ". Hỗn hợp đầy đủ thua cánh tay tốt nhất
không quá `ln(K/α) + (T − 1)·ln(1/(1 − α))` nat. Biên trộn không thừa hưởng đúng
chặn ấy, nên phép kiểm đo hối tiếc của chính nó trên ba hạt giống.

**Tham số chốt trước khi đo, không dò trên dữ liệu.**

* `η = 1` trên loss CỘNG — Bayes, không ủ. Đặt `η = 1` trên log-loss TRUNG BÌNH
  mỗi con là ủ hợp lý đi 100 lần: chênh 10⁻³ nat/con mỗi kỳ, đủ phân biệt sau vài
  trăm kỳ, chỉ dời trọng số `e⁻⁰·¹` sau 100 kỳ.
* `α = 0,001`. Trọng số cân bằng của một cánh tay kém đều `Δ` nat mỗi kỳ là
  khoảng `(α/K)/(α + ηΔ)`; `α = 0,01` giữ ~15% trọng số cho MỖI cánh tay kém
  0,1 nat/kỳ trong sáu cánh tay.

Không có bộ sinh ngẫu nhiên: cùng lịch sử loss cho cùng trọng số, nên dự báo lặp
lại hay khôi phục sau lỗi không cần lưu trạng thái RNG. Cánh tay vắng ở một kỳ
(khớp hoặc dự đoán lỗi) giữ nguyên phần khối lượng của nó.

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
     → trọng số mũ trên log-loss trộn các cánh tay
     → CỔNG ĐỘ TIN: trust·trộn + (1 − trust)·nền   ← đứng sau phép trộn
     → Top-K
     → kết quả thật → log-loss cộng 100 con từng cánh tay → cập nhật trọng số
                    → điểm của phép trộn (trước cổng) → trôi lệch, kỹ năng → trust
                    → điểm của dự báo công bố → nhật ký
```

Ba quyết định thiết kế mang tính quyết định:

**Cổng độ tin đứng *sau* phép trộn.** Phép trộn chỉ bảo đảm không thua cánh tay
tốt nhất quá xa. Cổng là nơi duy nhất hỏi phép trộn có kỹ năng ĐO ĐƯỢC hay không,
nên nó có tiếng nói sau cùng.

**Nền là một cánh tay.** `baseline` cạnh tranh sòng phẳng trong phép trộn, nên hệ
thống *kết luận bằng dữ liệu* rằng không mô hình nào đáng tin — trọng số dồn về
nền. Không có cánh tay nền thì trọng số luôn chuẩn hoá giữa các mô hình, và hệ
thống không diễn đạt được câu "không cái nào đáng dùng".

**Mỗi cánh tay được chấm trên xác suất của chính nó**, bằng log-loss — quy tắc
chấm chặt, phạt cả sai mức xác suất khi thứ hạng không đổi.

### Cổng độ tin `model_trust` — thay ngưỡng Hit-Rate 7 kỳ

`trust = ml_train.model_trust(s_logloss, s_brier) = clip(20·min(s), 0, 1)`, với
`s` là kỹ năng tương đối của phép trộn so với nền trên 60 kỳ gần nhất đã chấm;
chưa đủ 30 kỳ thì `trust = 0`. Đây là cùng luật của thành phần ML production,
cầu-kèo và tác tử mẫu hình: không có kỹ năng thì không tin, và khi `trust = 0`
dự báo công bố **đúng bằng** nền.

* Kỹ năng đo trên phép trộn TRƯỚC cổng. Đo trên dự báo đã qua cổng thì khi
  `trust = 0` dự báo trùng nền, kỹ năng bằng 0 mãi và cổng không bao giờ mở lại.
* Trôi lệch hoặc lỗi mô hình xoá bằng chứng cũ: nó mô tả một chế độ hoặc một bộ
  dự báo không còn chạy. Cổng đo lại từ đầu.
* Trôi lệch cũng đo trên sai số của phép trộn: khi `trust = 0`, sai số của dự báo
  công bố chỉ còn phản ánh kết quả quay.

**Vì sao bỏ ngưỡng Hit-Rate.** Bản trước vào chế độ an toàn khi Hit-Rate@10 trung
bình 7 kỳ dưới nền 0,2377. Với 70 lượt chọn, độ lệch chuẩn của tỉ lệ ấy là 0,051,
nên một mô hình đúng bằng nền rơi dưới ngưỡng khoảng một nửa số kỳ. Trên 1 000 kỳ
nó bật 764 kỳ: phán đoán bằng tung đồng xu. Hit-Rate lại không phải quy tắc chấm
chặt, nên nó bỏ qua đúng thứ cần canh là mức xác suất. "Chế độ an toàn" cũ còn
phát `0,8·nền + 0,2·tần suất dài hạn` — một mô hình khác, không phải nền.

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

Với luật chi trả lô tô thông thường (đặt 23, nhận 80 mỗi nháy):

```
ngưỡng hòa vốn (nháy/con/kỳ) = 23/80 = 0.2875
nền (nháy/con/kỳ)            = 27/100 = 0.27
lợi thế người chơi ở nền             = −6.09%
cải thiện tương đối cần để hòa vốn   = +6.48%
```

Tiền thưởng tính theo số nháy thực, kể cả một con về nhiều lần; Hit-Rate,
precision, recall, Brier và log-loss vẫn chấm việc con đó có về hay không.
Nền **23,77%** là xác suất về ít nhất một lần, không phải số nháy kỳ vọng.
Phép tính công suất cho biến nhị phân không trực tiếp xác định công suất cho
ROI; muốn kết luận có lãi cần đánh giá riêng doanh thu theo số nháy ngoài mẫu.

---

## 6. Kết quả đo trên 1 000 kỳ (12-01-2024 → 19-10-2026)

```bash
# Báo cáo của bản đang chạy (cánh tay, trọng số, độ tin)
python src/research/ml_engine/main_pipeline.py --start 3240 --stop 4240 \
    --out data/research/ml_engine_report.json
# So ghép cặp với bản cũ chạy trên mã của main (luật quyết định chốt trước khi đo)
PYTHONPATH=src python3 scripts/research/benchmark_ml_engine_aggregation.py --last 1000 \
    --days-out /tmp/moi.csv --against /tmp/cu.csv --against-label cu
```

Cấu hình mặc định, đủ sáu cánh tay (`temporal_sequence` chạy đường lui tuyến
tính vì môi trường không có torch). Sai số của z lấy max(theo ngày, khối 7 kỳ),
đúng như cổng đề bạt của `online_learning`.

| Bản | Kỹ năng log-loss so với hằng số | z so với hằng số | Kỳ về đúng nền |
|---|---:|---:|---:|
| Cũ: bandit Thompson + ngưỡng Hit-Rate 7 kỳ | −0,036% | **−3,40** | 764 (chế độ an toàn) |
| Mới: trọng số mũ log-loss + cổng `model_trust` | −0,000001% | −1,02 | 699 (trust = 0) |
| **Mới so với cũ** | | **+3,40** | |

Luật chốt trước: bản mới được nhận khi không kém hằng số với z ≤ −2 và không kém bản
cũ với z ≤ −2 — đạt (`data/research/ml_engine_aggregation.json`). Độ tin trung
bình 0,0002: khi cổng mở, nó chỉ mở vì kỹ năng ngẫu nhiên vừa dương trên 60 kỳ,
và `20·s` giữ phần trộn ở mức 10⁻⁴.

| Cánh tay | Kỹ năng log-loss ngoài mẫu | t ghép cặp | Trọng số cuối |
|---|---:|---:|---:|
| `baseline` | 0 | — | 0,482 |
| `temporal_sequence` | −0,0009% | −0,28 | 0,342 |
| `gap_hazard` | −0,0032% | −0,99 | 0,136 |
| `frequency` | −0,031% | −3,61 | 0,008 |
| `tabular_boosting` | −0,33% | −9,54 | 0,011 |
| `ranking_lambdamart` | −0,85% | −6,56 | 0,021 |

Ba điều đáng đọc kỹ:

1. **Không cánh tay nào hơn nền**, và ba cánh tay học máy kém nền có ý nghĩa: chúng
   học nhiễu của cửa sổ 240 kỳ. Phép trộn tự dồn trọng số về nền và các cánh tay
   gần nền mà không cần ai quyết định.
2. **Bản cũ thua hằng số vì phán đoán, không vì mô hình.** 89% phần thua nằm ở 236
   kỳ "bình thường", nơi bandit trộn các cánh tay gần đều tay — kể cả
   `temporal_sequence` khi nó còn kém nền 61,5% — mất trung bình 0,00075 nat mỗi
   con mỗi kỳ. 11% còn lại ở 764 kỳ "an toàn": `0,8·nền + 0,2·tần suất dài hạn`
   cũng thua nền (t ≈ −2,6). Ngưỡng Hit-Rate chọn giữa hai chế độ ấy theo nhiễu.
3. **Lỗi thật của `temporal_sequence` lộ ra nhờ báo cáo từng cánh tay.** Đường lui
   ridge cũ cố định λ = 10 cho 1 401 tham số mỗi đầu ra trên ~226 mẫu và phạt cả
   hệ số chặn: độ lệch chuẩn xác suất 0,166 quanh nền, 9,5% dự báo kẹp ở 10⁻⁶,
   log-loss kém nền 61,5% (t = −58,8). Bản sửa chọn λ trên 20% cửa sổ cuối và co
   về nền: λ chọn 10⁴–10⁶, độ lệch chuẩn 0,0026, kém nền 0,0009% (t = −0,28).
   Trên dữ liệu có cài bạc nhớ, cùng phép chọn λ hạ xuống ≤ 10⁴ và hơn nền
   0,2–1,7% (phép kiểm hai chiều trong `tests/test_ml_engine.py`).

Chỉ số xếp hạng (Trúng@3/5/10: 0,709 / 1,164 / 2,309 so với chọn ngẫu nhiên
0,714 / 1,190 / 2,380) không có nghĩa ở đây: khi trust = 0 mọi con cùng xác suất,
Top-K chỉ là thứ tự chỉ số.

---

## 7. Vận hành

```bash
# Cài phụ thuộc tùy chọn (torch/catboost dùng tự động nếu có sẵn)
pip install -r requirements-ml-engine.txt

# Chạy backtest học tiếp diễn, ghi báo cáo
python src/research/ml_engine/main_pipeline.py --start 3240 --stop 4240 \
    --out data/research/ml_engine_report.json

# Bỏ các cánh tay nặng khi chạy trên máy yếu
python src/research/ml_engine/main_pipeline.py --no-temporal --no-ranking

# Kiểm thử
PYTHONPATH=src python3 -m pytest tests/test_ml_engine.py \
    tests/test_ml_engine_integrity.py tests/test_ml_engine_economics.py -q   # 169 phép kiểm
```

Module không lưu trạng thái giữa các lần chạy: phép trộn tất định, mỗi lượt học
lại từ đầu trên đoạn được chỉ định. Tệp `data/ml_engine/bandit_state.json` và cờ
`--bandit-state`/`--discount` đã gỡ cùng bandit.

## 8. Điều gì sẽ làm đổi kết luận

1. Một cánh tay có kỹ năng log-loss dương với **t ghép cặp > 2,5** trên ít nhất
   200 kỳ trong bảng `arm_skill` của báo cáo.
2. Cổng độ tin **giữ** trust > 0,5 qua một quý — tức kỹ năng 60 kỳ của phép trộn
   đều đặn trên 2,5%, gấp hàng trăm lần mức dao động đo được hôm nay.
3. Thêm dữ liệu: ngưỡng phát hiện co theo `1/√n`. Phép trộn Bayes không có trần
   số quan sát hiệu dụng như bandit cũ; chia sẻ cố định α = 0,001 chỉ thêm khoảng
   `T·α` nat hối tiếc.
