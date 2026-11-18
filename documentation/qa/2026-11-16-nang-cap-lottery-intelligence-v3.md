# Kiểm toán và nâng cấp «Lottery Intelligence Engine V3» — 16 → 18-11-2026

## Yêu cầu và cách đọc yêu cầu

Chủ dự án gửi bản đặc tả «Master Prompt — Lottery Intelligence Engine V3»: kiểm toán sâu toàn bộ hệ
thống thống kê, xác suất, AI/ML, dự báo của VLA và engine Vietlott, rồi trực tiếp nâng cấp, kiểm thử,
backtest và bàn giao. Đặc tả tự đặt luật nền: không giả lập thành công, không gọi điểm xếp hạng là xác
suất, không rò rỉ dữ liệu tương lai, không overfit, chỉ đề bạt mô hình khi thắng ngoài mẫu, và ghi
**NO DEMONSTRATED PREDICTIVE EDGE** khi không chứng minh được lợi thế.

Kho đã đi khá xa trên đúng trục ấy trước đợt này (rà soát 03-10, 04-10, 16-10, 31-10, 15-11). Vì thế đợt
này không viết lại hệ thống. Nó làm bốn việc:

1. đối chiếu từng tầng của đặc tả với mã thật;
2. lấp các tầng còn thiếu thật sự;
3. đo lại mọi sản phẩm bằng thước ngoài mẫu;
4. nói rõ chỗ nào chưa làm và vì sao.

«Chính xác nhất» ở đây có nghĩa đo được: log-loss / Brier NGOÀI MẪU của xác suất công bố, so với kỳ quay
công bằng. Với kỳ quay đã kiểm là ngẫu nhiên, mức tốt nhất về kỳ vọng là **không thua** dự báo hằng số.
Không có mục tiêu "đúng 90%".

## Phạm vi, công cụ và mốc trước khi sửa

| Bước | Cách làm | Kết quả |
| --- | --- | --- |
| Mốc kiểm thử VLA | `pytest tests` trên Python 3.15 (đúng `.python-version`), bản thư viện đã ghim | 4 309 xanh, 17 bỏ qua, 1 đỏ: `test_the_real_engine_data_loads` chỉ vì môi trường cục bộ chưa cài `-e vietlott` (CI có cài); cài vào thì xanh |
| Mốc kiểm thử engine | `cd vietlott && pytest` | 940 xanh, 4 bỏ qua |
| Bản đồ mã | 187 tệp `src/` (~63 600 dòng), 205 tệp engine, 29 workflow | đồ thị phụ thuộc gói không vòng |
| Bản đồ thuật toán | đọc pipeline, các tài liệu rà soát trước, dò từ khoá (calibration, walk-forward, ECE, registry, Monte Carlo…) | bảng dưới |
| Dữ liệu | sổ chuẩn XSMB 4 268 kỳ (01-01-2015 → 16-11-2026); sổ miền 984 + 1 273 kỳ-đài | sạch cấu trúc (mục «Phát hiện») |

Máy phiên làm việc không gọi được nguồn kết quả bên ngoài (proxy chặn), nên mọi số đo dưới đây đứng trên
dữ liệu đã commit.

## Đối chiếu tầng của đặc tả với hệ thống

| Tầng đặc tả | Đã có trước đợt | Đợt này |
| --- | --- | --- |
| Data layer: thu thập, dự phòng, kiểm chất lượng | XSMB: một nguồn chính, hai dự phòng, đồng thuận, `validate_data`, ghi nguyên tử; Vietlott: cổng hồ sơ, nguồn không được sửa kỳ đã lưu | XSMT/XSMN: kiểm cấu trúc dừng hẳn bước thống kê; kiểm ngày trống, đài vắng lịch, kỳ chép nhầm, dấu vân tay nội dung |
| Statistical layer | thống kê mô tả, χ², gan/chu kỳ, Markov, ma trận có điều kiện Bayes thực nghiệm + BH, bộ kiểm ngẫu nhiên Monte Carlo | thống kê và tám phép kiểm cho TỪNG ĐÀI miền Trung/Nam |
| Feature engineering | `ml_features`, `research.vla.features` (gan, tần suất suy giảm, cầu, PMI, Louvain, Markov ĐB), phép kiểm "không nhìn trước" | — |
| ML layer | HGB + Platt (ML), Cầu Kèo, LightGBM ba tầng (phòng thử thách) | mốc tần suất thô; ứng viên perceptron nhiều lớp |
| Deep learning | GRU trong `research.ml_engine` (tuỳ chọn, ngoài pipeline) | không đưa vào production (mục riêng) |
| Ensemble / dynamic weights | trọng số học + cổng ngoài mẫu so với vector MẶC ĐỊNH; xếp chồng phải thắng cả tổ hợp lẫn hằng số; Hedge hai trí nhớ | — |
| Calibration | Platt/temperature có ứng viên `identity`; `model_trust` | ECE có mốc đúng trên vector đã công bố |
| Simulation | null 10 000 lịch sử (độ tin cậy), 20 000 kỳ mô phỏng (thành tích sổ phỏng đoán), bộ kiểm Monte Carlo | null mô phỏng đúng cấu trúc 18 giải cho từng đài |
| Backtesting | walk-forward cửa sổ mở rộng 1 000 kỳ, kiểm độ nhạy trên lịch sử cài tín hiệu, chấm chính vector đã công bố | walk-forward cho từng đài miền; benchmark XSMB đo lại với mốc mới |
| Prediction API / output | trang tĩnh, sổ phỏng đoán khoá 18:10, thành tích nhiều kỳ | — |
| Model registry | KHÔNG có | `evaluation.model_registry` + sổ lịch sử chỉ nối thêm |
| Monitoring | `skill_monitor` (z = 3 hai phía), `production_audit.stale_learners` | sổ đăng ký báo hồ sơ không đọc được; lượt `--strict` dừng |

Đặc tả đòi "database tables" (lịch sử dự báo, registry, kết quả backtest…). Kho này không có cơ sở dữ
liệu: mọi sổ là CSV/JSON trong git, ghi nguyên tử, sổ tiến cứu giữ lần ghi đầu, và lịch sử git là cơ chế
phiên bản/lùi. Mỗi bảng đặc tả nêu đã có sổ tương ứng (`pred_<mode>.csv`, `published_skill.csv`,
`ensemble_history.csv`, sổ phỏng đoán, sổ tiến cứu, nay thêm `model_registry/`). Dựng thêm một cơ sở dữ
liệu chỉ để khớp tên bảng sẽ tạo bản sao thứ hai của cùng dữ liệu, nên không làm.

## Ma trận đánh giá thuật toán

Cột "Ngoài mẫu" là số đo trên kỳ mô hình chưa thấy. z dương là tốt hơn dự báo hằng số.

| Thuật toán | Cơ sở toán | Ngoài mẫu (đo gần nhất) | Rủi ro rò rỉ / overfit | Quyết định |
| --- | --- | --- | --- | --- |
| Tần suất thô / "số nóng" (mọi lịch sử, 30, 90 kỳ) | tỉ lệ thực nghiệm | XSMB LOTO z −3,9 / −28,6 / −15,7; ĐB −2,5 / −35,6 / −20,6 (997 kỳ); đài miền: tần suất 20 kỳ thua dự báo đều mọi miền và chế độ | không rò rỉ; lời nguyền người thắng khi đọc như dự báo | giữ làm MỐC so sánh, không bao giờ làm xác suất công bố |
| Lô gan, lặp kỳ trước (xếp hạng) | khoảng cách hình học | đài miền: Top-10 ngang ngẫu nhiên (p Holm ≥ 0,3); XSMB: trúng tiếp theo độ dài chuỗi 23,5–24,0% (nền 23,81%) | — | chỉ mô tả |
| Tiên nghiệm Dirichlet/Beta (Bayes thực nghiệm) | hậu nghiệm co về nền | XSMB LOTO z +0,19, ĐB −1,14 | (h, α) chọn trên khối học | giữ trong phòng thử thách |
| LightGBM phần dư + Platt (`bayes_lgb`) | cây tăng cường từ logit tiên nghiệm | LOTO z −2,34, ĐB −0,89; kiểm độ nhạy z +6,1 / +5,1 | dừng sớm trên khối riêng | không đề bạt |
| Perceptron nhiều lớp (`mang_no_ron`, MỚI) | mạng truyền thẳng + Platt | LOTO z −0,25, ĐB −1,44; độ nhạy (Đặc Biệt cài 30%) z ≥ 5,3 trên ba hạt giống | cấu hình chọn trên lịch sử tổng hợp, không trên dữ liệu thật | không đề bạt |
| ML production (HGB + Platt + `model_trust`) | — | LOTO z −0,09, ĐB +1,64 (997 kỳ); trust hiện 0 (LOTO) và 0,3% (ĐB) | bốn khối thời gian | giữ; trust tự co về nền |
| Cầu Kèo + `model_trust` | HGB trên đặc trưng cầu | trust 0,4% (LOTO), 0,02% (ĐB) | trust học trên khối thẩm định | giữ |
| Cầu vị trí theo đường (`path_prob`) | Bayes thực nghiệm + DerSimonian–Laird | mọi cầu co về nền (độ tản 1,00× nhị thức) | sửa 16-10 | giữ |
| Bảy kiểu cầu, tổng–bóng–chạm | luật trang tham chiếu | ngang chọn bừa (\|z\| < 1, 4 224 kỳ) | — | chỉ mô tả, không vào tổ hợp |
| Tổ hợp tuyến tính + `finalize_blend` | neo Σp = 23,77 | xem "Xác suất đã công bố" | cổng so với vector MẶC ĐỊNH | giữ |
| Hiệu chỉnh xác suất | Platt/temperature/identity | đang giữ identity (lát hiệu chỉnh chưa đủ 60 ngày) | khối giữ riêng | giữ |
| Xếp chồng | hồi quy trên thành phần | LOTO chưa đủ 100 ngày; ĐB không thắng cả tổ hợp lẫn hằng số → trust 0 | hai cổng | giữ, đang bị cổng giữ |
| Hedge hai trí nhớ, hệ ba tác tử | trọng số mũ trên log-loss | cổng đề bạt chưa mở; tác tử chạy bóng | điểm trước, học sau | giữ |
| Kho tri thức (luật trễ) | e-process, ngân sách α theo lô | chưa luật nào đạt ngưỡng | chỉ chấm kỳ sau đăng ký | giữ |
| Ma trận có điều kiện | Bayes thực nghiệm một κ + BH | không ô nào q < 0,05 | sửa 31-10 | giữ |
| Lô VIP nhiều nháy | logistic theo khối | ngang chọn bừa | phép kiểm đóng băng | giữ, không vào tổ hợp |
| XSMT/XSMN: sáu mô hình xác suất (MỚI) | xem mục «Miền Trung / Nam» | không mô hình nào thắng dự báo đều ở cấp miền | chỉ đọc kỳ trước ngày đích | luật công bố vẫn là dự báo đều |
| Engine Vietlott: hỗn hợp Bayes fixed-share, e-process | tỉ số hợp lý so với máy công bằng | xem bảng hiệu năng | điểm trước, học sau | giữ, không sửa (dự án tự đủ) |

Không thuật toán nào bị xoá. Những thứ chỉ là mô tả đã được dán nhãn mô tả từ các đợt trước và không đi
vào tổ hợp xác suất.

## Mốc hiệu năng theo từng sản phẩm

| Sản phẩm | Dữ liệu chấm | Thước | Kết quả | Kết luận |
| --- | --- | --- | --- | --- |
| XSMB LOTO — xác suất ĐÃ CÔNG BỐ | 80 kỳ chấm từ chính vector công bố | kỹ năng log-loss | −4,4·10⁻⁵, khoảng 95% −1,8·10⁻⁴ … +9,3·10⁻⁵; AUC 0,508 (p 0,44); ECE 0,0138 so với 0,0147 kỳ vọng (p 0,58); không tháng nào khác 0 | **NO DEMONSTRATED PREDICTIVE EDGE**; hiệu chỉnh ngang một dự báo hiệu chỉnh hoàn hảo |
| XSMB Đặc Biệt — xác suất ĐÃ CÔNG BỐ | 80 kỳ | kỹ năng log-loss | +4,7·10⁻⁶, khoảng 95% ±1,1·10⁻³; MRR 0,054 so với 0,052 ngẫu nhiên (p 0,90); ECE 0,0037 so với 0,0035 (p 0,41) | **NO DEMONSTRATED PREDICTIVE EDGE** |
| XSMB — walk-forward 9 mô hình | 997 kỳ, 13-02-2024 → 16-11-2026, học lại mỗi 50 kỳ | log-loss so với hằng số | tốt nhất: tiên nghiệm LOTO z +0,19, ML production ĐB z +1,64; mọi z trong ±2 trừ các mô hình kém hằng số | không ứng viên nào được đề bạt |
| Miền Trung (14 đài) | 704 kỳ-đài ngoài mẫu (17-12-2025 → 15-11-2026) | log-loss so với dự báo đều, p hoán vị theo ngày, Holm | không mô hình nào thắng; 0/112 phép kiểm đài lệch | **NO DEMONSTRATED PREDICTIVE EDGE**; máy quay không phân biệt được với công bằng (phát hiện được lệch từ 21 điểm % mỗi con) |
| Miền Nam (21 đài) | 853 kỳ-đài ngoài mẫu | như trên | cấp miền không mô hình nào thắng; RIÊNG đài Bến Tre mô hình chữ số theo lồng thắng (+0,0050 log-loss/kỳ trên 38 kỳ, p Holm 0,026) | cấp miền **NO DEMONSTRATED PREDICTIVE EDGE**; hai đài đã đăng ký phép kiểm tiến cứu |
| Mega 6/45 | 1 569 kỳ | e-value hỗn hợp Bayes; phép đo số khớp H đăng ký 13-10 (test 382 kỳ) | e cao nhất 10^0,20 < 20; mọi nhánh ngang/kém công bằng | **NO DEMONSTRATED PREDICTIVE EDGE** |
| Power 6/55 | 1 405 kỳ | như trên | e cao nhất 10^0,33 | **NO DEMONSTRATED PREDICTIVE EDGE** |
| Lotto 5/35 | 920 kỳ | e-value | 10^0,12 | **NO DEMONSTRATED PREDICTIVE EDGE** |
| Keno | 297 367 kỳ | e-value | 10^0,18; trọng số "ngẫu nhiên" 99,2% | **NO DEMONSTRATED PREDICTIVE EDGE** |
| Bingo18 | 105 563 kỳ | e-value | 10^0,12 | **NO DEMONSTRATED PREDICTIVE EDGE** |
| Max 3D | 1 139 kỳ | e-value, ngưỡng họ 140 | 10^2,57 ≥ 10^2,15: chữ số 6 hàng đơn vị ×1,075 | lệch thống kê có thật; RTP tốt nhất 0,59 < 1 — vẫn mất trung bình ~41% tiền vé |
| Max 3D Pro | 786 kỳ | như trên | 10^2,84 | như Max 3D; RTP tốt nhất 0,63 |
| Max 4D (đã ngừng) | 722 kỳ | e-value | 10^0,72 | **NO DEMONSTRATED PREDICTIVE EDGE** |

Đặc tả đòi ROI chỉ khi có đủ giá vé, cơ cấu giải và thuế. Engine Vietlott tính RTP từ bảng giải thật;
mọi cửa đều dưới 1. Với XSMB/XSMT/XSMN kho không có bảng trả thưởng chính thức nên không in ROI.

## Thay đổi của đợt này

### 1. Bộ máy XSMT/XSMN (commit «XSMT/XSMN: miền 18 giải…»)

- `core.regional_domain`: bố cục 18 giải khai một lần, bộ thu thập đọc cùng đối tượng; mức nền một đài
  `1 − 0,99¹⁸ = 16,55%` (dùng 27 giải của miền Bắc là sai mức nền 7 điểm %); phân phối chính xác số nháy
  và số con khác nhau (bao hàm–loại trừ bằng số nguyên); lồng cầu của từng chữ số in.
- `stats.regional_stats`: kiểm cấu trúc (sai là `RegionalDataError`, không thống kê gì), chất lượng dữ
  liệu, bảng tần suất có p nhị thức chính xác, tám phép kiểm mỗi đài với null mô phỏng đúng 82 chữ số
  mỗi kỳ, Benjamini–Hochberg trên mọi (đài × phép kiểm), phép gộp cấp miền, độ lệch nhỏ nhất phát hiện
  được. Hạt giống theo TÊN đài: thêm đài không đổi kết quả đài khác.
- `evaluation.regional_benchmark`: dự báo đều, tần suất, tần suất 20 kỳ, Bayes thực nghiệm (một κ cho cả
  miền, học lại cho từng ngày đích), chữ số theo lồng, chữ số theo lồng co Bayes (thêm sau, đánh dấu
  `post_hoc`), hồi quy logistic học chung miền; ba cách xếp hạng dân gian. Chỉ đọc kỳ có ngày nhỏ hơn
  ngày đích; hai đài cùng ngày không thấy nhau.
- `research.regional_cage_test`: đài bị gắn cờ được đăng ký MỘT lần, luật đối đóng băng, chỉ chấm kỳ sau
  ngày đăng ký bằng e-process (Ville), ngưỡng `số đài / α`, sổ CSV chỉ nối thêm.
- Trang kết quả miền in khối «Kiểm định ngẫu nhiên và mốc xác suất» từ ba tệp số đo; workflow
  `regional-results.yml` chạy ba bước mới và commit số đo cùng lượt; bước hỏng thì trang ẩn khối và lượt
  chạy đỏ, kết quả vừa thu thập vẫn được ghi.

### 2. Benchmark XSMB (commit «Benchmark XSMB: mốc tần suất thô…»)

- `research.vla.models.FrequencyModel` (mốc "số nóng") và `NeuralModel` (perceptron trên cùng đặc
  trưng, cùng ba tầng với `bayes_lgb`); `benchmark_probability_models.py` chấm thêm bốn mô hình.
- `audit_forecast_ceiling.py` quét (quý × lồng) với BH trên mọi ô.

### 3. Sổ đăng ký mô hình (commit «Sổ đăng ký mô hình…»)

`evaluation.model_registry` → `data/evaluation/model_registry/registry.json` mỗi lượt pipeline: 19 mắt
xích, mỗi mắt xích có định nghĩa + dấu vân tay, mốc học, số đo thẩm định và trạng thái triển khai ĐỌC TỪ
CỔNG của chính nó (`production` / `gated` / `shadow` / `missing`). `history.csv` chỉ nối thêm khi một mắt
xích đổi định nghĩa hoặc đổi trạng thái cổng; đó là chỗ tìm bản cần lùi về. Trạng thái 16-11: 9 có hiệu
lực, 5 bị cổng giữ ở mức nền, 5 chạy bóng.

### 4. Chất lượng mô hình (commit «Chất lượng mô hình: ECE…»)

`model_quality` lược đồ 2 thêm ECE với mốc đúng, thứ hạng toàn vector (AUC / MRR, p hoán vị trong từng
kỳ) và kỹ năng theo tháng; trang in ba thẻ mới và sổ đăng ký.

Mốc của ECE là điểm dễ sai: ECE luôn dương kể cả khi hiệu chỉnh hoàn hảo. So với ECE của dự báo hằng
số cũng sai thước, vì hằng số dồn mọi ô vào một nhóm nên nhiễu nhỏ hơn hẳn. Mốc đúng là ECE của chính
các xác suất ấy khi kết cục được rút đúng theo chúng, với 27 giải mỗi kỳ để giữ cấu trúc của kỳ quay.
Phép kiểm `test_a_sharp_but_calibrated_forecast_is_not_flagged` đo đúng chênh lệch ấy (lớn hơn 2 lần).

## Phát hiện

**Miền Nam — hai đài lệch ở phép chữ số theo lồng.** Đài Bến Tre (58 kỳ, 07-10-2025 → 10-11-2026): mỗi lồng
có đúng một quả chỉ ra 30–60% mức đều (hàng đơn vị quả 6: 59/1 044 so với 104,4; hàng chục quả 4: 42;
hàng trăm quả 1: 34; hàng nghìn quả 2: 47; hàng chục nghìn quả 2: 20/696 so với 69,6). Độ thiếu có ở cả
hai nửa năm. p tiệm cận của χ²(45) là 2,2·10⁻²³; mô hình theo lồng thắng dự báo đều ngoài mẫu ở riêng
đài này. Đài Bình Phước: p = 4,5·10⁻⁴, q = 0,019. Phép gộp cấp miền cũng lệch ở phép này (q = 0,0016).

Không đọc phát hiện này là "lợi thế". Ba lý do:

- phép kiểm theo lồng được viết SAU khi một phép kiểm khác đã chỉ vào Bến Tre;
- sổ miền chỉ ghi từ một nơi, nên chưa phân biệt được bộ cầu lệch với kết quả bị ghi sai có hệ thống;
- máy phiên làm việc không gọi được nguồn khác để đối chiếu.

Cả hai đài đã được đăng ký phép kiểm tiến cứu (`data/research/hypotheses/regional_cage_bias.json`), ngưỡng
`35 đài / 0,01 = 3 500`. Việc nên làm tiếp là đối chiếu 58 kỳ Bến Tre với một nơi ghi độc lập: đó là
quyết định của chủ dự án, vì cần chọn nguồn.

**XSMB — lệch chữ số tạm thời 2022–2024.** 4/240 ô (quý × lồng) có q < 0,05, lệch nhất 2024Q2 lồng đơn vị
(p Bonferroni 1,1·10⁻⁴), và p của 240 ô không đều (KS p = 7·10⁻⁶). Nhưng mô hình chữ số trượt
(cửa sổ 60–730 kỳ, bốn độ co) vẫn thua dự báo đều; tốt nhất là z −0,62. Có độ lệch tạm thời có thật,
nhưng nó không bền đủ để dự báo, nên kết luận trần dự báo không đổi.

**Tần suất thô là cách dự báo tệ nhất.** Mọi sản phẩm, mọi cửa sổ: tin "số nóng" làm log-loss tệ đi rõ
rệt. Cửa sổ càng ngắn càng tệ. Đó là lý do trang không bao giờ in tần suất như xác suất.

## Học sâu: vì sao không đưa vào production

Đặc tả cho phép học sâu khi dữ liệu đủ và có lợi thế ngoài mẫu. Cả hai điều kiện đều không đạt.

- XSMB có 4 268 kỳ. Một GRU một lớp trên 100 con đã có nhiều tham số hơn số kỳ:
  `research.ml_engine.models.TemporalSequenceModel` tính đúng con số ấy và lui về hồi quy ridge khi thiếu
  PyTorch.
- Ứng viên mạng nơ-ron đợt này thấy được tín hiệu cài sẵn (z ≥ 5,3), nên công cụ đo không mù. Trên dữ
  liệu thật nó ngang hằng số (LOTO z −0,25, ĐB −1,44).
- Phép kiểm độ trễ không thấy phụ thuộc giữa các kỳ (z +0,75 / +0,66 / +0,51 / +1,13 ở độ trễ 1, 2, 3,
  7). Không có cấu trúc chuỗi nào để một mạng chuỗi học.

## Những gì KHÔNG làm, và vì sao

- Không đổi xác suất công bố của bất kỳ sản phẩm nào: không ứng viên nào vượt cổng đã có.
- Không công bố con số dự đoán cho đài miền. Cấp miền không mô hình nào thắng dự báo đều; độ lệch của
  hai đài chưa qua phép kiểm tiến cứu.
- Không nới cổng, không chỉnh tay siêu tham số trên dữ liệu đang chấm, không sửa giao thức đã đăng ký.
- Không thêm nguồn kết quả mới (luật kho: phải đo bằng `diagnose-live-sources.yml` trước).
- Không sửa engine Vietlott: nó là dự án tự đủ, có sổ phiên bản, checkpoint và phép đo đăng ký riêng.
- Không dựng cơ sở dữ liệu mới (mục «Đối chiếu tầng»).

## Kiểm thử

- Mỗi phép kiểm mới được thử bằng đột biến: **103/103** đột biến làm phép kiểm đỏ, chia theo phần:
  - miền 61;
  - benchmark XSMB 14;
  - sổ đăng ký 17;
  - chất lượng mô hình 11.
- Năm đột biến sống sót ở lượt đầu, mỗi cái chỉ ra một lỗ của phép kiểm, và cả năm lỗ đã vá:
  - phép theo lồng cộng cả lồng trăm nghìn mà không phép kiểm nào thấy;
  - vector phẳng trùng dự báo hằng số, nên mốc ECE sai không lộ;
  - hai phép kiểm đọc tệp đã commit thay vì chạy mã (bảng theo tháng, thẻ sổ đăng ký);
  - chuỗi "chưa có bằng chứng" chứa chuỗi "có bằng chứng".
- Mọi bước miền và sổ đăng ký chạy lại trên cùng dữ liệu cho cùng tệp, từng byte.
- Ảnh chụp trình duyệt (sáng, tối, 390 px) của trang miền và trang Chất lượng mô hình: không lỗi script,
  không tràn ngang.
- Số kiểm thử và bằng chứng của lần chạy cuối nằm trong PR.

## Vận hành

```bash
# Cài đặt (Python theo .python-version)
python -m pip install -r requirements-dev.txt
python -m pip install -e vietlott          # phép kiểm trang Vietlott cần engine

# Pipeline XSMB đầy đủ trên dữ liệu đã commit (không gọi mạng), dừng khi có lỗi
PYTHONPATH=src python src/pipeline.py --skip-sync --strict

# XSMT/XSMN: thống kê + kiểm định, phép kiểm tiến cứu, chấm walk-forward, dựng trang
PYTHONPATH=src python src/stats/regional_stats.py
PYTHONPATH=src python src/research/regional_cage_test.py
PYTHONPATH=src python src/evaluation/regional_benchmark.py
PYTHONPATH=src python src/pages/build_regional_results.py

# Sổ đăng ký mô hình và báo cáo chất lượng
PYTHONPATH=src python src/evaluation/model_registry.py --strict
PYTHONPATH=src python src/evaluation/model_quality.py
PYTHONPATH=src python src/pages/build_model_quality.py

# Backtest XSMB (khoảng 10 phút) và trần dự báo
PYTHONPATH=src python scripts/research/benchmark_probability_models.py --last 1000 --power-check --refit-check 200
PYTHONPATH=src python scripts/research/audit_forecast_ceiling.py

# Kiểm thử
PYTHONPATH=src python -m pytest tests -q
cd vietlott && python -m pytest
```

Mốc đọc nhanh trạng thái: `data/evaluation/model_registry/registry.json` (mắt xích nào đang có hiệu lực),
`data/evaluation/model_quality/report.json` (kỹ năng, ECE, thứ hạng của xác suất đã công bố),
`data/evaluation/regional_benchmark/benchmark.json` và `data/stats/regional/summary_<miền>.json` (miền).

## Còn mở — chủ dự án quyết

- Đối chiếu kết quả Bến Tre và Bình Phước với một nơi ghi độc lập. Lệch ở khâu ghi thì phải sửa bộ thu
  thập, lệch ở bộ cầu thì phép kiểm tiến cứu sẽ tự xác nhận.
- Sổ đăng ký chưa gồm các mô hình của engine Vietlott: engine giữ sổ riêng, và gộp thì phải đọc trạng
  thái của dự án tự đủ ấy từ VLA.
