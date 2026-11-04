# Chi tiết của CLAUDE.md: số đo, lý do và lịch sử

Ngày 04-11-2026 bốn mục dài nhất của `CLAUDE.md` được chép NGUYÊN VĂN sang đây; `CLAUDE.md` giữ bản tóm tắt
luật (mọi điều «đừng / phải») và trỏ về tệp này. `CLAUDE.md` được nạp vào mọi phiên làm việc, nên số đo và câu
chuyện vì sao đặt từng luật nằm ở đây cho gọn ngữ cảnh. Luật nào hai nơi nói khác nhau thì phải sửa cả hai; số
đo mới ghi ở đây.

## Độ tin thành phần ML — không có kỹ năng thì không tin

`ml_train.model_trust` = `clip(20·s, 0, 1)`, s là kỹ năng thẩm định (kém hơn trong logloss/Brier).
Sàn 0,35 cũ trộn 35% mô hình thô cả khi s ≤ 0; walk-forward 997 kỳ đo nó làm LOTO kém hằng số
(z = −2,40), bỏ sàn hơn sàn z = +2,44 (`scripts/research/benchmark_model_trust.py`). Đừng khôi phục sàn. Khi
trust = 0 mọi xác suất ML bằng nền; `ml_predict.rank_predictions` xếp hoà theo xác suất thô.

Cầu-kèo (`cau_keo_ml`, trọng số tổ hợp 0,30) dùng CÙNG luật từ 04-10-2026: cột `prob` =
`trust·thô + (1 − trust)·nền`, trust và nền học trên khối thẩm định, lưu trong gói và đọc CHỈ qua
`cau_keo_ml.trust_from_pack` — không có mặc định; gói thiếu luật tin thì học lại. `ml_prob_raw` giữ
xác suất thô cho điểm và lý do. Walk-forward 1 000 kỳ đo xác suất thô kém hằng số (Đặc Biệt
z = −2,18); `validate_cau_keo_domain` canh `prob` đúng bằng bản đã co. Dòng `p_cau` cũ trong sổ
`data/evaluation/history/pred_<mode>.csv` là xác suất THÔ: sổ ghi `policy_cau` cho dòng mới, và nơi HỌC từ sổ
(trọng số, hiệu chỉnh, xếp chồng) và bảng đóng góp thành phần gọi
`availability_from_history_day(..., current_policy=True)`.
Đổi định nghĩa một thành phần thì tăng `ensemble_components.COMPONENT_POLICY`, đừng viết lại sổ.
Tác tử mẫu hình của hệ ba tác tử XSMB (`forecast.xsmb_agents.algorithms.pattern`) dùng CÙNG luật từ 20-10-2026:
`trust = model_trust(s)`, s là kỹ năng so với nền trên 30 kỳ thẩm định cuối; định nghĩa 1 trộn cố định
20% mạng dù logloss thẩm định Đặc Biệt kém nền. Mỗi định nghĩa một SỔ: họ `online.AGENT_RECIPE` =
`xsmb_three_agents_v<AGENT_POLICY>`; sổ họ cũ được `retire_superseded_ledgers` CẤT NGUYÊN thành
`data/forecast/online/agents_<mode>.<họ>.json` (không chấm lại) và sổ mới bắt đầu rỗng, để Hedge, bước chọn
η/độ quên và cổng đề bạt không thừa hưởng điểm của bộ dự báo khác. Đổi định nghĩa tác tử thì tăng
`AGENT_POLICY`, đổi họ và thêm họ cũ vào `RETIRED_AGENT_FAMILIES`.
Khung nghiên cứu `ml_engine` dùng CÙNG luật từ 20-10-2026: bandit Thompson và ngưỡng Hit-Rate 7 kỳ
đã gỡ (kém hằng số z = −3,40 trên 1 000 kỳ); nay trộn bằng trọng số mũ trên log-loss CỘNG 100 con
(`aggregation.ExponentialWeights`, η = 1 là Bayes, chia sẻ cố định α = 0,001, chốt trước khi đo) rồi
qua cổng `fallback.SafeModeController`: `trust = model_trust(kỹ năng 60 kỳ của phép trộn TRƯỚC cổng)`,
chưa đủ 30 kỳ hoặc trôi lệch/lỗi mô hình thì trust = 0 và dự báo đúng bằng nền. Ngang hằng số, hơn bản
cũ z = +3,40 (`scripts/research/benchmark_ml_engine_aggregation.py`,
`data/research/ml_engine_aggregation.json`). Đừng đo kỹ năng trên dự báo đã qua cổng: trust = 0 thì
dự báo trùng nền và cổng không bao giờ mở lại.

## Engine Vietlott `vietlott/` — chép từ VLM, chạy riêng

Ngày 07-10-2026 chủ dự án yêu cầu VLA có ĐỦ tính năng của VLM (kho `beuvivu/VLM`,
"Vietlott Quant Engine") nhưng hai bên chạy riêng rẽ, để sau còn tách thành hai
trang. Toàn bộ VLM (bản `6bec0c9`, trừ `.github`) nằm ở `vietlott/` như một dự án
TỰ ĐỦ: `pyproject.toml`, `src/vietlott_engine`, `src/vlm`, `data/`, `scripts/`,
`tests/`, `reports/`. Đừng trộn nó vào `src/` hay `data/` của VLA, và đừng sửa
logic của nó ở đây khi không cần — engine tự tìm thư mục dự án qua `paths.py`.

- Chạy: `cd vietlott && python -m pip install -e ".[dev,crawler]" && python -m pytest`
  (369 phép kiểm). Lệnh: `vietlott`, `vlm-update`, `vlm-forecast`, `vlm-audit`.
- Workflow ở `.github/workflows/vlm-*.yml` (GitHub chỉ đọc workflow ở gốc kho),
  `working-directory: vietlott`, đường dẫn cache có tiền tố `vietlott/`. Chúng KHÔNG
  triển khai Pages; trang riêng của engine chỉ được dựng và lưu thành artifact.
  `tests/repo/test_vietlott_engine_layout.py` canh cả ba điều.
- Phép kiểm của engine tìm workflow ở cả hai bố cục (`tests/conftest.py`,
  `find_workflows`): kho riêng thì `.github/workflows/*.yml`, nằm trong VLA thì
  `../.github/workflows/vlm-*.yml`.
- Tag phát hành của engine là `vlm-v<phiên bản>`.

Trang Vietlott của site (`vietlott.html` + 7 trang sản phẩm) dựng bằng
`src/pages/build_vietlott_results.py` từ `vlm.web.dashboard.build_dashboard` của engine:
kết quả đã xác thực, bảng giải ĐÚNG mã kỳ (khuyết in "—", không mượn kỳ trước), dự
báo ghi trước kỳ + đối chiếu, kết luận e-value. Trình dựng KHÔNG in `source`,
`source_url`, `official_url` hay cảnh báo của engine (chúng nhắc tên nguồn) —
`tests/pages/test_vietlott_results.py` canh. Workflow `vietlott-results.yml` không gọi
mạng: khôi phục (chỉ đọc) cache trạng thái `vqe-state-` rồi dựng và triển khai.
Câu kết luận về độ ngẫu nhiên ở trang tổng quan in TỪ e-value của engine
(`randomness_summary`), không viết cứng: Max 3D và Max 3D Pro lệch thật ở hàng đơn vị (số 6
≈ 11%, lặp lại trên hai sản phẩm), dù mọi cửa Max 3D mà mô hình tính được vẫn có RTP < 1 (Mega/Power/Lotto không có RTP trong phân tích nên không được gộp vào câu ấy)
(`documentation/research/2026-10-07-max3d-hang-don-vi.md`).
API của engine mặc định an toàn (08-10-2026): CORS đóng, `VQE_API_TOKEN` (khi đặt) bắt mọi
POST/PUT/PATCH/DELETE và mọi `?record=` mà FastAPI đọc là True (`on`, `y`… cũng vậy, đọc bằng
chính `TypeAdapter(bool)`) gửi `Authorization: Bearer`; ba GET làm mới dự báo (`/forecast/{p}`,
`/forecast/{p}/evidence`, `/ml/forecast/{p}`) cũng là lệnh ghi. Không có token thì lệnh ghi do trình
duyệt gửi từ trang khác (`Sec-Fetch-Site`/`Origin`) bị 403; `vietlott serve` và compose chỉ nghe
`127.0.0.1`. CORS phải nằm NGOÀI middleware xác thực (thêm sau cùng). `vietlott/tests/test_api_security.py` canh; bản vá đã đưa ngược về kho VLM ở beuvivu/vlm#9 (01-11-2026).
Kiểm chứng xác suất và số khớp H cho Mega/Power (13-10-2026, `vietlott/docs/VLM_HIT_BENCHMARK.md`):
`vlm.forecast.hits` (H = |vé ∩ 6 số chính| so với siêu bội C(6,h)C(N−6,6−h)/C(N,6), đơn vị KỲ, số đặc biệt
Power KHÔNG cộng vào H), `vlm.forecast.challengers`, `vlm.forecast.hit_benchmark` (giao thức `PROTOCOL` đăng ký
13-10-2026: 300 kỳ khởi động, dev 50% · validation 20% · test 30%, chọn/ablation/hiệu chuẩn chỉ trên
dev/validation, test nhìn một lần, năm điều kiện đề bạt, Holm). Đừng sửa `PROTOCOL` rồi gọi test là độc lập —
đăng ký giao thức mới. H ≥ 4 không đủ công suất để đề bạt (phát hiện ×2 cần 6.502 kỳ Mega, 14.647 kỳ Power); báo cáo nó, đừng
dùng nó. Benchmark và bảng điều khiển phải chấm ĐÚNG vé đã phát: ML là bộ đầu của `Law.top(PUBLISHED_TOP_N)` (cùng lệnh gọi với
bảng điều khiển), legacy là 6 số π cao nhất.
Checkpoint ML version 3: `pair_link`/`triple_link` không gộp tần suất của chính số ấy (bản cũ tương quan 0,99
với `lag1`). Trang Vietlott in "chọn bừa k/n" cạnh tỷ lệ trùng theo vé (`FAIR_MATCH_RATE`).
Vé công bố từ 15-10-2026 (`ticket_rule = coverage-v1`, ghi vào `pending` CÙNG lần ghi luật): năm vé RỜI NHAU
chia xoay vòng từ 30 số (Lotto: 25) có xác suất biên cao nhất (`distribution.coverage_tickets`). Luật ML gần
đều nên `Law.top` cho năm vé chung 5/6 số, và ngày 14-10-2026 hệ số nhiễu của `lag2` đẩy vé đầu Power chép
nguyên kỳ #1409. Với cùng năm vé, "ít nhất một vé trúng ≥ 2 số" lên 70,9% (Mega), 53,7% (Power), 61,1%
(Lotto) — dò cục bộ không tìm được cách xếp nào hơn; xác suất TỪNG vé không đổi, đừng nói là "tăng xác suất
trúng". Lần ghi KHÔNG có khoá ấy giữ `Law.top` (không chấm lại kỳ cũ bằng quy tắc mới); benchmark H đã đăng
ký vẫn chấm `Law.top`. Mốc in trên trang lấy từ `dashboard.coverage_summary` (`hits.any_ticket_tail`), không
viết cứng. Kỳ đã qua giờ quay mà chưa có kết quả: thẻ hiện chính bộ số đã ghi, nhãn "Đã quay, đang chờ kết
quả" (`build_vietlott_results.shown_forecast`). Kết quả Mega/Power/Lotto: chuỗi `auto` hỏi `xskt` (trang
đăng lại, đọc được từ runner) SAU bản sao NhanAZ (trễ hàng giờ); `vlm-results.yml` nhận `repository_dispatch`
`vietlott-results` và chạy sau lượt `daily-finalize` — lịch mười phút của GitHub chạy cách nhau 1–5 giờ.
Bộ chữ số của nhánh ML (Lotto đặc biệt, Max 3D/Pro, Max 4D, Bingo18) có chuyên gia `bayes_mixture` (31-10-2026,
`vlm.forecast.bayes_expert`, checkpoint ML version 5): luật hậu nghiệm của hỗn hợp Bayes của engine cũ, chạy chấm trước –
học sau trên đúng các kỳ bộ ML học. Không có nó, bộ ML bỏ qua độ lệch thật của Max 3D (chữ số 6 hàng đơn vị 10,6–11,3% ở
cả sáu giai đoạn 2019 → 2026) và kém công bằng (−0,158 log10); có nó +0,771. Đừng thay bằng Dirichlet đầy đủ: 27 tham số
tốn nhiều hơn lợi ích. Lần ghi `ticket_rule = coverage-v2`: vé Lotto thứ j mang số đặc biệt hạng j và được chấm đúng số ấy
(ít nhất một vé trúng giải 45,7% so với 14,7% khi chung một số, `dashboard.prize_coverage`); lần ghi v1 giữ số chung.
Kết luận e-value trên trang dùng ngưỡng HỌ 7/α = 140 (`build_vietlott_results.family_signal`), không phải 20 của từng
sản phẩm (`documentation/research/2026-10-31-ra-soat-engine-vietlott.md`).
Challenger mẫu hình `vlm.forecast.patterns` (PR #190, ghép 01-11-2026) mặc định TẮT (`MLConfig.patterns`,
`VQE_ML_PATTERNS`). Nó dùng chung checkpoint version 5 với `bayes_mixture`: khoá `patterns` là TUỲ CHỌN, nên đừng tăng
`VERSION` vì nó. Tăng thì mọi sản phẩm có bộ chữ số học lại và mất bằng chứng live. Thứ tự chuyên gia là cơ sở → bayes →
mẫu hình, trùng thứ tự xác suất trong `predict`. Đo lại trên mã đã ghép: tắt thì trùng `main` từng bit; bật thì không
cải thiện (q = 0,99, `vietlott/reports/vlm/pattern-learning-2026-11-01/`). Muốn bật mặc định thì phải qua phép đo
trước khi bật, như mọi challenger.
Keno/Bingo18 từ 01-11-2026: vietlott.vn chặn runner bằng Cloudflare (không vượt) và kho NhanAZ chỉ đăng lại
từ trang thứ cấp, nên bản sao `vietvudanh` được nhập qua cổng hồ sơ `product_store._vet_fast_mirror`: trùng
tuyệt đối ≥ 10 000 kỳ seed CHÍNH THỨC (không đếm dòng trong kho — tự chứng nhận) và ≥ 50 kỳ đăng lại độc lập
của NhanAZ, lệch một kỳ là loại cả lượt. Khoảng hở lịch sử không nguồn nào có nằm ở
`vietlott/data/seed/known_gaps.json` (chỉ đổi báo cáo, không suy ra số); khoảng hở mới vẫn đỏ.
Cửa sổ đối chiếu neo theo ngày mới nhất của BẢN SAO (không theo ngày của kho: sau lần nhập đầu nó ra 0); kỳ
đăng lại mới hơn bản sao là «chờ xác minh», không phải lỗi; `not_advancing` theo nhịp nguồn vừa làm kho tiến
(bản sao ~00:00/~12:00 UTC → `runner.MIRROR_GRACE` 13 giờ; nguồn khác 20 phút).
Crawler Vietlott cũ (`src/vietlott_results.py`) đã nghỉ; `data/vietlott/vietlott.sqlite3`
giữ nguyên làm lưu trữ, không còn được ghi.

## Phòng thử thách mô hình `src/research/vla/`

`src/research/vla/` (đặc trưng → tiên nghiệm Dirichlet/Beta → LightGBM phần dư → hiệu chỉnh,
walk-forward, ROI) là KHUNG THÁCH ĐẤU, không nằm trong pipeline. Ngày 03-10-2026 nó không
hơn dự báo hằng số trên 1 000 kỳ và không thắng ML production, nên không được đề bạt
(`documentation/research/2026-10-03-kiem-toan-mo-hinh-xac-suat.md`). Ý tưởng mô hình mới
phải qua `scripts/research/benchmark_probability_models.py` (kèm `--power-check`) trước; chỉ đề
bạt khi thắng CẢ hằng số LẪN mô hình đang chạy. Bộ lọc "lô nhiều nháy" `src/forecast/multi_hit_vip.py`
(08-10-2026) cũng là khung thách đấu: top-5 trúng 2,91% trên 4 228 kỳ, đúng bằng chọn bừa trên chính các kỳ ấy, nên không
vào tổ hợp xác suất; mọi xác suất/Confidence nó in ra đều suy từ walk-forward, đừng viết cứng
(`documentation/research/2026-10-08-lo-nhieu-nhay.md`). Lượt thử thứ hai (12-10-2026,
`src/forecast/multi_hit_benchmark.py`, vỏ dòng lệnh `scripts/research/benchmark_multi_hit.py`): 22 chiến lược kể cả
logistic/GBM, chọn trên giai đoạn phát triển, kiểm một lần trên 1 000 kỳ cuối — không đạt; hạng giữa
hai giai đoạn tương quan −0,02. Trang `docs/lo-vip-nhieu-nhay.html` (13-10-2026) in cả hai TỪ số đo:
`multi_hit_report.py` ghi `data/forecast/multi_hit/vip.json` mỗi ngày; `benchmark.json` là phép kiểm MỘT
lần, đóng băng ở `SECOND_ROUND_UNTIL` (12-10-2026) — đừng dời ngày ấy hay đo lại trên cửa sổ trượt
(nhìn lại cùng tập kiểm ở cùng α làm sai số loại I cộng dồn); muốn kiểm kỳ mới thì đăng ký phép kiểm
tiến cứu mới. Bộ lọc thì đo lại MỖI ngày, nên mức tin của nó dùng p luôn hợp lệ (e-process,
`multi_hit_report.anytime_p`): 2 000 lịch sử không kỹ năng xem lại sau mỗi kỳ với p thường vượt 0,05 ở
30,9%, với p luôn hợp lệ ở 3,45%. e-process CHỈ chạy trên kỳ quay sau ngày chốt của mô hình đang in
(`multi_hit_forecast.FROZEN_AT` = 15-10-2026; bộ lọc VIP cũ: `VIP_FROZEN_AT` = 12-10-2026): mô hình được
thiết kế sau khi đã xem lịch sử trước đó, nên walk-forward hồi cứu chỉ là mô tả.
Từ 15-10-2026 năm con trên trang là DỰ BÁO KỲ SAU của mô hình Lô VIP (`src/forecast/multi_hit_forecast.py`), theo
yêu cầu "dựa trên dữ liệu và kinh nghiệm cầu kèo, không phải thống kê hôm nay": đặc trưng cầu kèo của
`cau_keo_ml` (trừ 6 đặc trưng định danh/lịch), số cầu hai nháy (≥ 2 kỳ) và cầu LOTO (≥ 3 kỳ) đang chạy báo
con ấy — đếm khớp `bridge_rules.find` —, và dữ liệu nhiều nháy; logistic, C chọn bằng thẩm định trong theo
thời gian, walk-forward học lại mỗi 250 kỳ, xác suất in ra hiệu chỉnh Platt CHỈ trên lượt chọn ngoài mẫu
của các khối trước; lý do mỗi con = đóng góp dương lớn nhất. Năm con công bố do mô hình CỦA KHỐI đang chạy
chọn (`WalkForward.forecast`) — đừng học lại trên mọi kỳ để công bố: phần tiến cứu sẽ chấm năm con khác năm
con người đọc đã thấy. Kỳ được dự báo bỏ qua `known_non_draw_days` (`next_draw_date`), và đặc trưng thứ/tháng/
năm của kỳ ấy tính theo đúng ngày quay (`build_cau_keo_feature_frame(next_date=...)`). Đo đến 15-10-2026: 2,99% so với 2,92% chọn bừa
(z = +0,58), xác suất đã in TB 2,86%; kinh nghiệm cầu hai nháy ngang mức chung (0 cầu 2,94%, 1–4 cầu
2,82%, 5+ cầu 3,95% trên 481 lần) — trang in các số ấy TỪ phép đo, đừng viết "tỉ lệ cao"
(`documentation/research/2026-10-15-lo-vip-cau-keo.md`, `tests/forecast/test_multi_hit_forecast.py`). Đã nghỉ: bộ
lọc VIP (chỉ số phân tán đẩy con gan lên đầu — con 32 đứng đầu mười kỳ khi gan 10 → 19 kỳ) và luật lô rơi
(chỉ liệt kê con vừa về). `build_cau_keo_feature_frame` nhận `raw`/`two` để kiểm trên lịch sử giả định.
Thước theo KỲ (31-10-2026): kỳ "đạt" khi ít nhất một trong năm con về ≥ 2 nháy. Quay công bằng thì MỌI cách
chọn 5 con chỉ đạt `multi_hit_vip.any_multi_chance(5)` = 14,11% số kỳ (khoảng 1 kỳ trong 7), và 2,1% số kỳ không con
nào về ≥ 2 nháy; trang in số kỳ đạt của mô hình, của chọn bừa cùng kỳ (`random_any_hit`) và mức ấy TỪ `vip.json`
(`MEASURE_VERSION` 10). "Đa số kỳ trượt" là bản chất phép chọn: mô hình gần như hằng số (C mạnh nhất ở 12/16 khối,
lợi log-loss ±3·10⁻⁵) và ngang chọn bừa cả theo lượt lẫn theo kỳ — đừng "sửa" bằng mô hình phức tạp hơn khi chưa qua
`scripts/research/benchmark_probability_models.py` (`documentation/research/2026-10-31-kiem-toan-lo-vip-nhieu-nhay.md`,
`scripts/research/audit_multi_hit_vip.py`).
`build_multi_hit_page.py` suy "hơn / không hơn / chưa kết luận"
từ mức tin, ứng viên lượt hai và phép kiểm độ nhạy. Từ 13-10-2026 trang GỌN theo yêu cầu: năm con ≥ 2 nháy và
năm cặp xiên 2 (`src/forecast/multi_hit_pairs.py`: số kỳ cùng về trong 100 kỳ, luật chốt trước, mốc C(d, 2)/4 950
cùng kỳ; 4 133 kỳ trúng 5,49% so với 5,52% chọn bừa) ở trên cùng, mỗi khối MỘT dòng số đo; giải thích
thu vào «Chi tiết phép đo». Cặp không có phép kiểm độ nhạy nên chỉ được nói "chưa có bằng chứng", không
"không hơn". `benchmark.json` có phiên bản riêng (`BENCHMARK_VERSION`): đổi khuôn `vip.json`
(`MEASURE_VERSION`) không được mở lại phép kiểm một lần. `tests/forecast/test_multi_hit_page.py` dựng cả lịch sử
có cài tín hiệu để trang PHẢI nói "hơn" — đừng viết sẵn câu kết luận nào. Top-5 Đặc Biệt từng ra 7,0% chỉ vì PMI làm
trơn sai (cặp chưa có dữ liệu được PMI = log N); sửa xong còn 5,4% — đừng trích nó như tín hiệu.

# Cầu theo đường (`path_prob`, trang `soi-path-*`) — Bayes thực nghiệm, 16-10-2026

Xác suất kỳ tới của một đường cầu KHÔNG phải tỉ lệ lịch sử của nó: cầu được chọn top 300 từ ~5 671
cầu mỗi độ trễ nên tỉ lệ ấy mang lời nguyền người thắng (nhánh ổn định từng in tổng LOTO 24,40 so với
23,76). `fit_paths_with_evidence` học `BridgeEvidence` từ MỌI cầu của mọi độ trễ: `p_post` co phần
riêng theo mức chênh thật giữa các cầu (`fit_shrinkage_to_prior`, một tâm và một κ chung cho 30 độ
trễ — tâm riêng từng độ trễ là đưa cú sốc theo kỳ vào), và nhánh "đang chạy" cộng `streak_shift` —
tỉ lệ trúng tiếp theo độ dài chuỗi, co bằng DerSimonian–Laird với phương sai THEO CỤM KỲ QUAY
(`streak_experience`; phương pháp mô men không trọng số giữ 1,4 điểm % nhiễu ở nhóm ít dữ liệu,
và coi hàng nghìn cầu cùng kỳ là độc lập thì cú sốc theo kỳ thành τ² dương), đo so với tỉ lệ riêng
THÔ của từng cầu bỏ ra chuỗi đang chạy (không phải tỉ lệ chung hay `p_post`: thế là tính chất lượng
cầu hai lần). Phần riêng giữ
`N/(N + κ)` theo số lần chấm của TỪNG độ trễ; trang in phạm vi/độ trễ đúng cấu hình. Đo 15-10-2026 trên cửa sổ 2 000 kỳ của pipeline: độ tản
giữa 170 130 cầu bằng 1,00 lần nhị thức, chuỗi 0–8+ trúng tiếp 23,5–24,0% so với nền 23,8% — mọi cầu co
về nền. Walk-forward 2 000 kỳ trên cửa sổ production: nhánh LOTO ổn định mới hơn cũ z = +9,69 (tổng 24,42 → 23,84), đang chạy z = +0,22; tổ hợp không đổi (z = −0,09; +1,01) vì `finalize_blend` đã neo mức; nhánh mới ngang hằng số ở cả bốn ô (LOTO z = +0,12 / −0,62). Phép đo chạy theo phần (`--parts/--part/--merge`); bước gộp đòi cùng danh tính lượt đo. Đừng quay lại độ co đặt tay, và đừng in `p_mean` như xác suất (cột "Tỷ lệ lịch sử" là thống kê
trong mẫu). Trang in câu kết luận TỪ `bridge_evidence_<mode>.json`
(`documentation/research/2026-10-16-tran-du-bao-va-suy-luan-cau.md`, `tests/soi_cau/test_bridge_inference.py`).
Trần dự báo của cả hệ thống (lệch chữ số, phụ thuộc giữa các kỳ, mô hình tần suất gần) đo bằng
`scripts/research/audit_forecast_ceiling.py`: không có cấu trúc nào để học; kỹ năng đã công bố
không phân biệt được với 0.
