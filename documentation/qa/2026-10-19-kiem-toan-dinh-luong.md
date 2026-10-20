# Kiểm toán định lượng VLA và engine Vietlott (19-10-2026)

## Yêu cầu

> Kiểm toán toàn diện, rà soát tỉ mỉ từng dòng mã nguồn: lỗi logic và runtime, dữ liệu biên, công
> thức xác suất và thống kê, vector hoá, thuật toán mới, chất lượng mã. Làm cùng một yêu cầu trên
> cả VLA và Vietlott của VLA.

**Về phạm vi.** Mã gồm 202 module Python của VLA (63 057 dòng) và 127 module của engine `vietlott/`
(24 722 dòng). Báo cáo này không tuyên bố đã đọc tay cả 87 779 dòng hay chứng minh mã hết lỗi.

Cách làm:

- quét toàn bộ bằng máy;
- đo thời gian thật của pipeline production;
- đọc từng dòng các module xác suất mới nhất và các hàm thống kê lõi dùng chung;
- với mỗi bản sửa: một phép kiểm đối chiếu với bản cũ, rồi đột biến để chắc phép kiểm đỏ được.

Kiểm toán ngày 18-10 (`qa/2026-10-18-repository-audit.md`) đã sửa các lỗi logic và độ bền tìm được
lúc ấy. Báo cáo này không lặp lại các phát hiện đó.

## 1. Tóm tắt

**Logic xác suất.** Không tìm thấy lỗi toán học nào trong các hàm lõi. Sáu hàm được đối chiếu lại
từ đầu (mục 2.5):

- Bayes thực nghiệm co về tiên nghiệm;
- DerSimonian–Laird;
- Hedge hai trí nhớ;
- e-process;
- phân phối tập con có chuẩn hoá chính xác của engine Vietlott;
- ngưỡng hoà vốn LOTO.

Tất cả khớp với lý thuyết.

**Điểm yếu cốt lõi là hiệu năng, không phải toán.** Các bước chậm nhất của pipeline tốn thời gian
vào vòng Python duyệt từng phần tử trên dữ liệu pandas, không vào phép tính thống kê:

- lấy từng phần tử `DatetimeIndex`;
- gọi lại sklearn cho mỗi lượt bootstrap;
- dựng hàng nghìn `DataFrame` 100 hàng;
- định dạng từng ô CSV.

Bốn chỗ ở VLA và một chỗ ở engine Vietlott đã được vector hoá (mục 4):

- bước `cau_keo_domain_challenger` giảm từ 51,8 s xuống 36,2 s;
- `statistical_matrices` giảm từ 22,5 s xuống 20,3 s mỗi lần chạy (pipeline chạy nó hai lần);
- phân phối tập con của engine Vietlott nhanh hơn 4–9 lần mỗi lần dựng;
- đầu ra trùng từng byte. Ngoại lệ duy nhất là khoảng tin cậy bootstrap, lệch ở chữ số thứ 11.

**Hai phát hiện về phương pháp, cần chủ dự án quyết:**

- tác tử "mẫu hình" của hệ ba tác tử XSMB trộn cố định 20% mạng nơ-ron dù kỹ năng thẩm định âm
  (mục 2.4) — đã sửa ngày 20-10-2026 theo quyết định của chủ dự án;
- bandit Thompson của khung `ml_engine` có phương sai hậu nghiệm lớn hơn tín hiệu hàng trăm lần
  (mục 2.6).

**Nợ chất lượng mã:**

- mypy báo 323 lỗi kiểu trên `src/`, phần lớn là `dict[str, object]` thiếu kiểu cụ thể. Không lỗi
  nào trong số đã soát là lỗi chạy thật.
- ruff với 30 quy tắc mở rộng ngoài bộ chặn CI không lộ lỗi logic: các biểu thức `and`/`or` bị
  cảnh báo đều đúng thứ tự ưu tiên.

**Thuật toán mới.** Không thêm mô hình dự báo "tiên tiến" nào, và đó là quyết định có số đo. Kiểm
toán trần dự báo ngày 16-10 (`research/2026-10-16-tran-du-bao-va-suy-luan-cau.md`):

- không có cấu trúc nào để học: lệch chữ số không bền giữa hai nửa lịch sử, các chữ số trong một
  kỳ độc lập, không phụ thuộc giữa các kỳ;
- kỹ năng đã công bố không phân biệt được với 0.

Một mô hình phức tạp hơn chỉ thêm phương sai. Phần nâng cấp có giá trị là độ chặt của phép suy
luận và chi phí tính toán (mục 3).

## 2. Chi tiết theo module

### 2.1 `src/lottery_codes.py` — định dạng mã từng ô (đã sửa)

**Vấn đề.** `write_code_csv` gọi `Series.map(lambda v: lottery_code(v, width))` cho mọi ô của mọi
cột mã, khoảng 2,5 triệu lần mỗi lượt `statistical_matrices`, dù chỉ có vài trăm mã khác nhau. Có 27
module ghi CSV qua hàm này.

**Sửa.** Hàm mới `code_column` định dạng mỗi giá trị khác nhau đúng một lần.

- **Cột số:** `pd.factorize` gom các giá trị bằng nhau. Mọi phần tử cùng một kiểu, nên hai giá trị
  bằng nhau cho cùng một mã. Ô thiếu (mã −1) trỏ vào chuỗi rỗng.
- **Cột `object`:** bộ nhớ đệm khoá theo cặp `(kiểu, giá trị)`. Lý do là `True == 1` trong Python,
  nhưng `lottery_code` nhận `1` và từ chối `True`. Khoá chỉ theo giá trị thì một cột trộn hai thứ
  ấy sẽ in `True` thành `"01"` thay vì báo lỗi.

**Kiểm.**

- `test_cached_code_column_equals_the_per_cell_formatter` so từng ô với cách gọi cũ trên sáu kiểu
  cột: int64, float có NaN, Int64 có NA, object trộn chuỗi/số/NaN/NA, và hai cột rỗng.
- `test_cached_code_column_rejects_what_the_formatter_rejects` kiểm sáu trường hợp bị từ chối.
- Ba đột biến đều đỏ: khoá đệm bỏ kiểu, ô thiếu thành `"00"`, làm tròn số thực trước khi gom.

### 2.2 `src/ml_validation.py` — bootstrap theo kỳ (đã sửa)

**Vấn đề.** `_paired_date_bootstrap` lặp 1 000 lượt. Mỗi lượt ghép lại mọi hàng của các kỳ rút được
và chấm lại hai lần qua `sklearn.metrics` (kèm toàn bộ kiểm đầu vào): 2 036 lời gọi
`evaluate_predictions`, 15 trong 75 giây của `cau_keo_domain_challenger` khi đo bằng cProfile.

**Cơ sở toán học.** Brier và logloss là trung bình theo hàng. Với tập kỳ rút được S (có lặp), gọi
L_g là tổng loss của kỳ g và n_g là số hàng của nó:

    mean_S = Σ_{g∈S} L_g / Σ_{g∈S} n_g

Chỉ cần tổng loss và số hàng theo kỳ, tính một lần bằng `np.bincount`. Mỗi lượt còn hai phép cộng
O(G) trên G kỳ, thay cho ghép lại O(N) hàng rồi chấm lại.

Dòng số ngẫu nhiên giữ nguyên: mỗi lượt vẫn gọi `rng.integers(0, G, size=G)`. Gom một lần
`size=(R, G)` thì luồng số có thể khác, vì numpy đệm 32 bit trong một lời gọi.

**Kiểm.** `test_grouped_bootstrap_equals_the_row_concatenating_bootstrap` dựng các kỳ có số hàng
khác nhau, các hàng của một kỳ không liền nhau, và xác suất ở biên (0, 1, 1e−12). Kết quả phải
khớp bản cũ ở sai số tương đối 1e−10.

Ba đột biến đều đỏ: chia cho số kỳ thay vì số hàng, bỏ chặn biên xác suất, lệch trục kỳ.

Trên dữ liệu thật, hai tệp `cau_keo_domain_gate_*.json` trùng từng trường với bản cũ. Riêng bốn
cận khoảng tin cậy bootstrap của LOTO lệch ở chữ số thứ 11 (sai số tương đối ≤ 9,3·10⁻¹²), do thứ
tự cộng.

### 2.3 `src/cau_keo_ml.py` — đặc trưng cầu kèo (đã sửa)

Hàm `build_cau_keo_feature_frame` được dùng bởi `cau_keo_ml`, `cau_keo_domain_challenger`,
`multi_hit_forecast` và `multi_hit_report`. Hai điểm nghẽn:

1. **`_build_same_weekday_feature`.**
   - Vấn đề: hàm duyệt từng ngày trong cửa sổ 364 ngày bằng `dates[i].weekday()`. Mỗi lần như vậy
     bọc một `Timestamp`, tổng cộng 1,47 triệu lần mỗi lần dựng khung (16 s dưới cProfile).
   - Sửa: dùng một mặt nạ vector `dates[start:t+1].weekday == thứ_đích` trên lát cửa sổ, rồi cộng
     các hàng được chọn.
   - Kiểm: `test_same_weekday_feature_equals_the_per_day_scan` so với vòng duyệt cũ ở năm cặp (kỳ
     neo, thứ), kể cả kỳ neo 0. Đột biến lệch một ngày làm phép kiểm đỏ.
2. **Ghép khung theo kỳ neo.**
   - Vấn đề: mỗi kỳ neo dựng một `pd.DataFrame` 100 hàng × 46 cột, rồi `pd.concat` cả loạt (4 185
     khung, khoảng 2,3 ms mỗi khung).
   - Sửa: `_stack_anchor_columns` nối từng cột bằng `np.concatenate` rồi dựng một khung duy nhất.
     Danh sách chuỗi thành mảng chuỗi numpy, pandas đổi về `object`, nên kiểu cột trùng với khi
     pandas suy kiểu từ danh sách.
   - Kiểm: `test_feature_frame_built_once_equals_concatenated_anchor_frames` so cả khung (giá trị
     chính xác và kiểu từng cột) với cách ghép cũ. Phép kiểm chạy trên cả hai chế độ, có và không
     có nhãn. Hai đột biến đều đỏ: ép mọi cột về `object`, đảo thứ tự kỳ neo.

### 2.4 `src/xsmb_agents/` — ba tác tử XSMB (rà; đã sửa ngày 20-10-2026)

Đã đọc từng dòng `algorithms.py`, `engine.py`, `knowledge.py` và `benchmark.py`. Các điểm đã kiểm
và đúng:

- Đặc trưng `temporal_features` dùng `X[t]` chỉ từ `Y[:t]`:
  - tần suất cửa sổ lấy từ tổng tích luỹ;
  - độ "nóng" cập nhật mốc xuất hiện SAU khi ghi đặc trưng kỳ t;
  - truy xuất ngữ cảnh bỏ 30 kỳ chồng cửa sổ.
- n-gram, Markov và đồ thị trễ chỉ đếm cặp ngày lịch liên tiếp. Mỗi hàng của ma trận chuyển Đặc
  Biệt có tổng bằng 1 khi tiên nghiệm có tổng bằng 1.
- Hazard theo nhóm độ gan dùng độ gan TRƯỚC từng nhãn.

**Phát hiện (trung bình): trộn cố định 20% mạng nơ-ron, không xét kỹ năng.** `pattern()` trả về
`feasible(0,8·nền + 0,2·thô)` bất kể khối thẩm định nói gì. Điều này lệch luật của kho ("Độ tin
thành phần ML — không có kỹ năng thì không tin": `ml_train.model_trust = clip(20·s, 0, 1)`).

Ở ba kỳ gần nhất, logloss thẩm định của tác tử này ở chế độ Đặc Biệt là 4,6146 / 4,6121 / 4,6112. Cả
ba đều kém mức hằng số log 100 = 4,6052, tức kỹ năng âm, mà 20% mạng vẫn được trộn vào.

Tác động hiện nhỏ:

- đây là ứng viên "shadow", không thay xác suất công bố;
- Hedge tự hạ trọng số theo loss thật;
- walk-forward 60 kỳ đo mọi tác tử ngang hằng số (|z| ≤ 1,02).

**Đã sửa (20-10-2026, theo quyết định của chủ dự án).**

- `pattern()` phát `trust·mạng + (1 − trust)·nền`, với
  `trust = ml_train.model_trust(s_logloss, s_brier)` và s là kỹ năng so với nền trên chính 30 kỳ thẩm
  định. Khối ấy cũng chọn α nên s hơi lạc quan: lệch về phía tin, không về phía bịa tín hiệu.
- Sổ được đánh phiên bản theo định nghĩa: họ `online.AGENT_RECIPE` = `xsmb_three_agents_v2`.
  - Sổ họ v1 được cất nguyên (chỉ đổi tên) thành `agents_<mode>.xsmb_three_agents_v1.json`; sổ
    mới bắt đầu rỗng. Lọc riêng phần báo cáo là chưa đủ, vì Hedge, bước chọn η/độ quên và cổng
    đề bạt sẽ vẫn thừa hưởng điểm do bộ dự báo cũ kiếm được (review Codex).
  - Họ lạ hay bản cất đã có làm dừng sạch trước khi đổi tên hay ghi sổ nào.
  - Mỗi bản ghi mang `agent_policy` và được kiểm khi nạp.
- Trang Độ tin cậy in độ tin cùng kỹ năng thẩm định của kỳ đang dự báo.
- Trên dữ liệu thật (ngày neo 19-10-2026):
  - Đặc Biệt: kỹ năng logloss −0,13%, độ tin 0, tức phát đúng mức nền;
  - LOTO: kỹ năng +0,015%, độ tin 0,3% thay cho 20%.
- Bản ghi kỳ 20-10 đã đóng băng theo định nghĩa 1; bản ghi mới đầu tiên theo định nghĩa 2 là kỳ
  21-10.
- Phép kiểm `tests/test_xsmb_agents.py`:
  - lịch sử công bằng cho độ tin 0 và vector đúng mức nền;
  - lịch sử cài tín hiệu (con 07 về mọi kỳ) cho độ tin bằng luật và vector đúng công thức trộn;
  - họ sổ đi theo định nghĩa; sổ họ cũ được cất nguyên từng byte và sổ mới bắt đầu rỗng;
  - họ lạ hay bản cất đã có thì dừng trước khi đổi tên hay ghi;
  - sổ đúng họ chỉ chứa bản ghi của định nghĩa đang chạy;
  - thẻ trang chỉ in độ tin từ định nghĩa 2.
- Mười đột biến đều đỏ: trộn cố định, đảo dấu kỹ năng, chỉ dùng Brier, không ghi phiên bản, in ghi chú
  cho định nghĩa cũ, bỏ bước cất sổ, đổi tên trong lúc còn kiểm, ghi đè bản cất, không đổi họ sổ, bỏ
  kiểm bản ghi khi nạp.

### 2.5 Hàm thống kê lõi dùng chung (rà, đúng)

| Hàm | Kiểm | Kết luận |
|---|---|---|
| `hierarchical_pooling.fit_shrinkage_to_prior` | Với p ~ Beta(m, κ): E[(r − m)²] = m(1−m)/n + m(1−m)(1 − 1/n)/(κ + 1). Hàm trừ phần nhị thức rồi giải κ = trung bình[m(1−m)(1 − 1/n)] / phần_vượt − 1 | Đúng; không có phần vượt thì co hẳn |
| `hierarchical_pooling.dersimonian_laird_tau2` | Q quanh trung bình nghịch đảo phương sai, τ² = max(0, (Q − (k−1)) / (Σw − Σw²/Σw)) | Đúng |
| `online_learning._weights`, `tune_agent_weights` | Hedge hai trí nhớ (tích luỹ và có quên) cộng fixed-share; trọng số tính TRƯỚC nhãn, loss cộng SAU nhãn; điểm replay chỉ dùng chọn η/độ quên | Đúng; điểm replay không cộng vào cổng đề bạt |
| `online_learning._gain_stats`, `promotion_gate` | SE = max(SE theo ngày, SE khối 7 kỳ); cận dưới = trung bình − 4·SE; đòi cả Brier lẫn logloss và đoạn 20 kỳ gần nhất | Đúng; tự ghi rõ là không anytime-valid khi kiểm lặp |
| `vlm.multi_agent.models.SubsetDistribution` | Quy hoạch động log-sum-exp O(n·k) cho P(S) ∝ exp(Σ logit) trên tập đúng k phần tử, chuẩn hoá cột theo tập j phần tử tốt nhất | Đúng; chuẩn hoá chính xác nên tỉ số hợp lý là xác suất thật |
| `vlm.multi_agent.meta.MetaLearner.update` | log e += log C(n,k) − loss_shadow, với vector shadow khoá TRƯỚC kết quả (trọng số, logit, nhiệt độ, ngữ cảnh đều lấy từ `pending`) | Martingale kiểm tra hợp lệ dưới H₀ phân phối đều; bật thích nghi khi e ≥ 1/α là hợp lệ theo bất đẳng thức Ville |
| `vlm.forecast.hits.predictable_p_value` | Tỉ số hợp lý Bernoulli(min(r·pₜ, 1)) / Bernoulli(pₜ), trung bình đều trên lưới r, p = 1 / max E | Hợp lệ ở mọi thời điểm dừng. Khi pₜ = 1 và không đạt, hàm bỏ qua kỳ đó thay vì báo bằng chứng vô hạn: bảo thủ, không sai |
| `ml_engine.metrics.EconomicModel` | Hoà vốn LOTO = 23/80 = 0,2875 nháy mỗi con mỗi kỳ; nền 27/100 = 0,27 nháy; cần +6,48% | Đúng (đã sửa ngày 18-10; trước đó dùng nhầm 23,77%) |

### 2.6 `src/ml_engine/bandit.py` — Thompson có chiết khấu (rà, phát hiện về công suất)

Phần toán của lớp này đúng:

- hậu nghiệm Beta liên hợp;
- chiết khấu áp lên MỌI cánh tay, và chỉ một bước cho mỗi ngày (`update_batch`);
- trọng số trộn ước lượng P(cánh tay i tốt nhất) bằng Monte Carlo;
- trạng thái bộ sinh ngẫu nhiên được lưu lại, nên chạy lại tái lập được.

**Phát hiện (trung bình, chỉ ở khung nghiên cứu): phương sai hậu nghiệm lớn hơn tín hiệu hàng trăm
lần.** `ml_engine.main_pipeline` thưởng mỗi cánh tay `1 − Brier` của kỳ. Hai giới hạn gặp nhau:

- Với γ = 0,98, số quan sát hiệu dụng bị chặn ở 1/(1 − γ) = 50. Quanh mức thưởng khoảng 0,82, độ
  lệch chuẩn hậu nghiệm vì thế không xuống dưới √(0,82·0,18/54) ≈ 0,052.
- Chênh lệch Brier giữa các mô hình trong miền này cỡ 10⁻⁵–10⁻⁴ mỗi kỳ (walk-forward 60 kỳ của ba
  tác tử, mục 2.4).

Như vậy P(cánh tay tốt nhất) chỉ phản ánh nhiễu lấy mẫu, kể cả sau hàng nghìn kỳ, đúng như
`power_floor()` tự cảnh báo.

Pipeline production không dùng lớp này. Tệp `data/ml_engine/bandit_state.json` không đổi từ
29-09-2026. Tổ hợp thật dùng Hedge theo logloss có cổng đề bạt (`online_learning`), là công cụ
đúng cho tín hiệu cỡ này.

**Khuyến nghị:** đừng nối MAB vào production. Muốn dùng thì phần thưởng phải là chênh lệch loss so
với hằng số đã chuẩn hoá theo độ lệch chuẩn của chính nó, và bỏ trần n_eff.

### 2.7 Dữ liệu biên và đầu ra

- Không có `NaN`/`Infinity` trong mọi JSON xuất bản (`data/`, `docs/`, `vietlott/data`,
  `vietlott/reports`, `vietlott/docs`) và trong mọi trang HTML. Một token `NaN` là đủ làm
  `JSON.parse` của trình duyệt hỏng.
- Phép kiểm toàn bộ dự án trước khi sửa: 3 897 đạt, 1 bỏ qua, 1 đỏ. Phép đỏ là mục lục tài liệu
  thiếu báo cáo Keno/Bingo18 vừa vào main; đã sửa trong PR #172.

**Quan sát (thấp): ngày đích của dự báo hằng ngày.** Cả hệ thống dự báo cho "ngày neo + 1"
(`predict_nextday_2d`, `online_learning`, `xsmb_agents`). Riêng `daily_forecast` và Lô VIP dùng
`next_draw_date`, hàm bỏ qua ngày nghỉ quay đã khai báo. Ngày nghỉ hiện chỉ được khai SAU khi dữ
liệu lộ ra, nên hai cách cho cùng một ngày. Nếu một ngày khai trước lịch nghỉ Tết, thẻ Top 5 trên
trang chủ sẽ ẩn quanh dịp ấy, vì hai tệp không cùng ngày đích. Đây là hành vi "chờ cập nhật" có chủ
đích, không phải số sai.

### 2.8 Quét tĩnh

- **ruff:** thêm `PLW`, `BLE001`, `S110`/`S112`, `PD`, `ASYNC`, `PERF`, `RUF005–024` ngoài bộ chặn
  CI.
  - VLA: 120 cảnh báo; engine: 49.
  - Đã soát hết các nhóm có thể là lỗi logic:
    - `RUF021` (`and`/`or` lồng nhau): đúng ý ở cả 8 chỗ;
    - `PLR0124` (`x != x`): là phép kiểm NaN;
    - `PLW1510` ở `vqe130.py`: mã trả về được kiểm ngay sau lời gọi;
    - `BLE001` (except rộng): ở biên CLI/trình duyệt, có ghi lỗi.
  - Không bật thành luật CI, vì phần lớn là văn phong.
- **mypy** (`--ignore-missing-imports`): 323 lỗi trên `src/`.
  - Phân bố: 139 `arg-type`, 36 `index`, 22 `assignment`, 20 `operator`, 19 `union-attr`… Đa số
    sinh từ `dict[str, object]` và kiểu trả về của pandas.
  - Đã soát các nhóm `attr-defined`, `name-defined`, `return-value`, `operator`, `valid-type`:
    không có lỗi chạy thật. Ví dụ `sync.py:20` chú thích `datetime.date` trong khi `date` không
    được import, nhưng `from __future__ import annotations` nên không bao giờ được đánh giá.
  - Đề xuất: bật mypy theo từng gói, bắt đầu từ `online_learning`, `hierarchical_pooling` và
    `ensemble_utils`, bằng `TypedDict` cho các bản ghi sổ.

### 2.9 `vietlott/src/vlm/multi_agent/models.py` — phân phối tập con (đã sửa)

**Đo.** Bước "Học ensemble ML và ghi dự báo" (`vlm-forecast next --product all`) là bước chậm thứ
hai của workflow `vlm-update.yml`: 157 s, sau bước đồng bộ mạng. Lấy mẫu ngăn xếp bằng `py-spy`
trong lúc chạy cho thấy luồng chính nằm ở:

    SubsetDistribution._differentiate ← mixture_marginals ← MultiAgentExpert._packet ← learn

Mỗi kỳ học dựng 16 phân phối: 4 chuyên gia trong `_packet`, cộng 4 × 3 nhiệt độ trong
`MetaLearner.update`. Tám trong số đó tính biên.

**Vấn đề.** Cả hai chiều quy hoạch động là vòng Python lồng nhau trên từng ô `longdouble`:

- chiều xuôi: chuẩn hoá trên mọi tập đúng k phần tử;
- chiều ngược (adjoint): xác suất biên.

Mỗi ô tốn vài lời gọi numpy vô hướng (`np.logaddexp`, `np.isneginf`, `np.exp`).

**Sửa (không đổi một bit nào).**

1. **Chiều xuôi:** hàng i chỉ đọc hàng i − 1, nên mọi cột j = 1..min(i, k) là MỘT lời gọi
   `np.logaddexp` theo phần tử, cùng phép tính `longdouble` trên từng ô.
2. **Xác suất rẽ nhánh:** xác suất "lấy phần tử i khi còn j chỗ" chỉ phụ thuộc bảng xuôi đã xong,
   nên cả ma trận n × k được tính trong một lượt. Lượt này giữ nguyên ba nhánh của bản cũ:
   - `excluded = −∞` cho xác suất 1;
   - `included = −∞` cho xác suất 0;
   - còn lại là logistic ổn định số theo dấu của hiệu.
3. **Chiều ngược:** chỉ còn lan khối lượng, mỗi hàng một bước vector. Thứ tự cộng giữ đúng như cũ:
   - tổng hàng cộng trái sang phải bằng `np.cumsum`;
   - ô j của hàng i − 1 nhận phần "ở lại" của ô j trước phần "chuyển" của ô j + 1.

Bit giống hệt là đòi hỏi thật, không phải thẩm mỹ: biên đi vào gradient của MLP trực tuyến và vào
sổ live. Lệch một ulp thì trạng thái đã lưu và trạng thái tái lập sẽ dần tách nhau.

**Kiểm.** `test_columns_vectorised_recursion_is_bit_identical_to_the_scalar_loop` so `_dp` và biên
với bản vô hướng cũ bằng `assert_array_equal`. Bộ thử có 49 ca:

- n từ 1 đến 80, k từ 1 đến 20, kể cả k = n;
- năm thang logit từ 0,01 đến 1 000;
- logit bằng nhau, ±1e308 và logit làm tròn có nhiều giá trị trùng.

Đột biến:

- Ba đột biến đều đỏ: lệch cột khi chuyển khối lượng, lệch cột khi đọc xác suất, tổng hàng chỉ lấy
  phần tử cuối.
- Một đột biến tương đương: đổi thứ tự hai nhánh −∞. Với logit hữu hạn, `included` và `excluded`
  không bao giờ cùng bằng −∞, nên thứ tự ấy không quan sát được.
- 57 phép kiểm và 92 phép con của `tests/multi_agent`, `test_multi_agent_integration` và
  `test_multi_agent_migration` đều đạt.

**Số đo toàn bước.** Chạy `vlm-forecast next --product all` từ trạng thái sạch (`git clean -x`: không có
checkpoint ML, mọi sản phẩm học lại từ đầu):

- bản cũ: 473 s;
- bản mới: 262 s (−45%);
- JSON đầu ra trùng hoàn toàn, trừ `made_at` và `elapsed_seconds`.

Hai lượt chạy nối tiếp trên cùng máy 4 lõi. Trong lượt cũ có vài phép kiểm ngắn chạy chồng, nên
mức giảm thật có thể nhỏ hơn đôi chút. Phần còn lại của 262 s là huấn luyện MLP trực tuyến và
các chuyên gia khác.

## 3. Nâng cấp thuật toán

**Vì sao không thêm mô hình mới.** Phần lớn "thuật toán tiên tiến" cho chuỗi thời gian đã có trong
kho và đều chạy qua cổng ngoài mẫu:

- LightGBM phần dư, GRU tuỳ chọn, logistic có hiệu chỉnh Platt;
- Hedge, e-process, Bayes thực nghiệm, DerSimonian–Laird;
- bandit/Thompson ở `strategy_lab`.

Trần dự báo đo ngày 16-10 cho thấy dữ liệu không có cấu trúc để học. Mọi mô hình mới chỉ được
đề bạt khi thắng CẢ hằng số LẪN mô hình đang chạy, và chưa mô hình nào làm được.

Phần nâng cấp có giá trị trong đợt này:

1. **Bootstrap theo kỳ ở dạng thống kê đủ.** Cùng phân phối bootstrap, chi phí mỗi lượt từ O(N)
   xuống O(G). Nhờ vậy tăng số lượt (ví dụ 1 000 → 10 000 để cận 2,5% ổn định hơn) mà không đổi
   thời gian chạy. Số lượt chưa đổi, vì cổng đề bạt đã đăng ký với 1 000.
2. **Độ tin cho tác tử mẫu hình** (mục 2.4): áp `model_trust` như mọi thành phần ML khác, kèm
   đánh phiên bản sổ tiến cứu (`AGENT_POLICY` = 2). Đã làm ngày 20-10-2026.
3. **Khuyến nghị kiểu nghiêm ngặt theo gói** (mục 2.8).

## 4. Hiệu năng và độ phức tạp

Đo trên cùng máy (4 lõi), cùng dữ liệu (4 236 kỳ), không bật profiler; mỗi lần đo chạy trọn bước.

| Bước pipeline | Trước | Sau | Ghi chú |
|---|---:|---:|---|
| `cau_keo_domain_challenger --mode both --window-days 2000` | 51,8 s | 36,2 s | −30%; trên CI bước này 57,2 s, chậm nhất pipeline |
| `statistical_matrices` | 22,5 s | 20,3 s | chạy hai lần mỗi lượt pipeline |
| `vlm-forecast next --product all` (engine, trạng thái sạch) | 473 s | 262 s | −45%; đầu ra trùng hoàn toàn |

| Hàm | Trước | Sau |
|---|---|---|
| `_paired_date_bootstrap` | O(R·N) thời gian, O(N) bộ nhớ mỗi lượt, cộng chi phí kiểm đầu vào của sklearn | O(N) một lần + O(R·G); bộ nhớ O(G) |
| `_build_same_weekday_feature` (gọi A lần) | O(A·W) lần tạo đối tượng `Timestamp` Python | O(A·W) phép so vector C, không tạo đối tượng |
| Ghép khung đặc trưng | A lần dựng `DataFrame` (khoảng 2,3 ms mỗi lần) + `concat` | một lần `np.concatenate` mỗi cột + một `DataFrame` |
| `write_code_csv` | O(N) lời gọi Python | O(N) mã hoá C (`factorize`) + O(U) lời gọi Python, U = số mã khác nhau |
| `SubsetDistribution` (xuôi + ngược) | O(n·k) lời gọi numpy vô hướng | O(n) lời gọi vector độ dài ≤ k + một lượt O(n·k) cho xác suất rẽ nhánh |

Ký hiệu: R = số lượt bootstrap (1 000), N = số hàng ngoài mẫu, G = số kỳ ngoài mẫu (N = 100·G),
A = số kỳ neo, W = 364 ngày.

Phần còn lại của các bước chậm là việc không né được:

- huấn luyện `HistGradientBoostingClassifier` và logistic;
- phép nhân ma trận BLAS của `bong_bridge_lab`, đã vector hoá từ trước;
- vẽ heatmap bằng matplotlib.

Bản này không đổi phép tính, ngưỡng hay dữ liệu nào.

## 5. Kiểm thử

- 6 phép kiểm mới, mỗi phép so bản mới với bản cũ: 5 ở VLA (24 trường hợp tham số hoá) và 1 ở
  engine (49 phép con).
- 12 đột biến: 11 đỏ, 1 tương đương (thứ tự hai nhánh −∞, mục 2.9).
- Bộ kiểm toàn phần trên bản cuối:
  - VLA: 3 923 đạt, 1 bỏ qua (`PYTHONPATH=src python3 -m pytest tests`, 11 phút 35 giây);
  - engine: 804 đạt, 3 bỏ qua, 92 phép con đạt (`cd vietlott && python3 -m pytest`, 4 phút 13 giây);
  - `ruff` sạch ở cả hai phía.
