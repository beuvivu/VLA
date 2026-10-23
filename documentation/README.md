# VLA documentation

Hand-written project documentation. This directory is **not** published: GitHub
Pages serves `docs/`, which holds generated HTML artifacts only.

Historical patterns do not guarantee future lottery results. Every document here
treats descriptive and research material as evidence for validation, never as a
forecasting guarantee.

## Bố cục thư mục

| Thư mục | Nội dung |
| --- | --- |
| `architecture/` | Thiết kế và hợp đồng: dữ liệu, ML, giao diện, Vietlott, đặc tả theme/search/icons |
| `domain/` | Quan hệ số chuẩn (lộn, bóng, bộ, chạm, tổng, cặp 50) |
| `engineering-log/` | Nhật ký kỹ thuật: luật sửa lỗi, lỗi đã biết, sự cố |
| `evaluations/` | Kết quả đánh giá đã đóng băng (JSON) |
| `history/` | Hồ sơ hợp nhất ba kho tiền nhiệm |
| `operations/` | Vận hành: Worker trực tiếp, lịch chạy, bộ hẹn giờ ngoài, tự học |
| `plans/` | Kế hoạch thi hành từng đợt (trước đây ở `docs/superpowers/plans/`) |
| `qa/` | Báo cáo kiểm toán và nghiệm thu (gồm các bản trước đây ở `docs/audit/`) |
| `research/` | Nghiên cứu có số đo, tái lập bằng `scripts/research/` |
| `ui/` | Hệ thiết kế, báo cáo giao diện, bản prompt UI/UX của chủ dự án (trước đây ở `docs/design/`, `docs/ui-ux/`) |

`docs/` ở gốc kho CHỈ chứa trang web xuất bản; `tests/test_repo_layout.py` canh việc ấy.

## Index

| Document | Scope |
| --- | --- |
| [`qa/2026-10-19-kiem-toan-dinh-luong.md`](qa/2026-10-19-kiem-toan-dinh-luong.md) | Kiểm toán định lượng VLA và engine Vietlott: đối chiếu toán học các hàm lõi (Bayes thực nghiệm, DerSimonian–Laird, Hedge, e-process, phân phối tập con), đo thời gian thật của pipeline và vector hoá các điểm nghẽn đã đo, đầu ra không đổi; phát hiện về độ tin của tác tử mẫu hình và công suất của bandit Thompson. |
| [`qa/2026-10-18-quality-plan.md`](qa/2026-10-18-quality-plan.md) | Phạm vi, ràng buộc và kế hoạch kiểm toán XSMB, Vietlott, UI, bảo mật và kiểm chứng. |
| [`qa/2026-10-18-repository-audit.md`](qa/2026-10-18-repository-audit.md) | Lỗi đã tái hiện, mã đã sửa, số đo hiệu năng, kiểm thử và checklist duy trì chất lượng toàn repo. |
| [`qa/2026-10-18-pairs-and-special-marks.md`](qa/2026-10-18-pairs-and-special-marks.md) | Kiểm chứng bố cục cặp lộn, dấu chọn Đặc Biệt và các bảng theo tổng. |
| [`plans/2026-10-17-ui-experience.md`](plans/2026-10-17-ui-experience.md) | Phạm vi và tiêu chí nghiệm thu giao diện trang chủ, ma trận, workspace phân tích và Đặc Biệt theo năm. |
| [`qa/2026-10-17-ui-experience.md`](qa/2026-10-17-ui-experience.md) | Bằng chứng kiểm thử và render, lỗi được phát hiện trong nghiệm thu, cách dựng giữ nguyên dữ liệu. |
| [`qa/2026-10-10-step-4-5-verification.md`](qa/2026-10-10-step-4-5-verification.md) | Đối chiếu và khép bước 4–5: dependency/BH-FDR, source manifest benchmark tự động, kiểm scan/source mutation, hai benchmark mới và bằng chứng kiểm thử/CI. |
| [`qa/2026-10-10-work-completion.md`](qa/2026-10-10-work-completion.md) | Chốt tiến trình VLA: độ bền tệp kết quả, retry xuất bản, độ mới XSMT/XSMN và bằng chứng CI/nguồn dữ liệu. |
| [`architecture/vietlott-comparison-ui.md`](architecture/vietlott-comparison-ui.md) | Khung responsive, màu bóng số, hiệu ứng nút, bảng đối chiếu theo từng bộ số và API JavaScript tính tỷ lệ/hạng giải; cập nhật trang ngay sau engine. |
| [`architecture/2026-10-08-vietlott-main-ui.md`](architecture/2026-10-08-vietlott-main-ui.md) | Đồng bộ font, màu ngày/đêm và bố cục với trang chính; Jackpot đúng kỳ và bộ số nháp Mega/Power trên thiết bị. |
| [`architecture/2026-10-08-vietlott-navigation.md`](architecture/2026-10-08-vietlott-navigation.md) | Phân hệ Vietlott trong shell Nexlink dùng chung, đích submenu, giới hạn dữ liệu và kiểm chứng. |
| [`architecture/2026-10-09-adaptive-forecast-design.md`](architecture/2026-10-09-adaptive-forecast-design.md) | Thiết kế phục hồi ML có giới hạn, running statistics nhân quả và challenger Vietlott; giữ score-before-learn và cổng kiểm định live. |
| [`architecture/2026-10-09-adaptive-forecast-plan.md`](architecture/2026-10-09-adaptive-forecast-plan.md) | Kế hoạch sửa lỗi vòng đời model, đồ thị/target context, kiểm thử hồi quy, benchmark ngoài mẫu và tích hợp main. |
| [`ui/nexlink-completion-2026-09-23.md`](ui/nexlink-completion-2026-09-23.md) | Hoàn thiện khung Nexlink, sửa điều hướng và ghi rõ kiểm chứng cùng giới hạn trực quan. |
| [`qa/2026-10-09-adaptive-forecast-audit.md`](qa/2026-10-09-adaptive-forecast-audit.md) | Lỗi model/ledger/runtime đã tái hiện, kiến trúc thực tế, recovery có giới hạn, benchmark7sản phẩm và quyết định không promote challenger. |
| [`qa/2026-10-08-deep-code-audit.md`](qa/2026-10-08-deep-code-audit.md) | Whole-repository code audit (Worker, Vietlott engine API, workflows, live page, ledgers, statistics helpers). Two HIGH findings, both fixed: the results API let any visitor amplify requests to the fallback source by varying the date range, and the engine API shipped with no auth, open CORS and a port published on every interface. Medium fixes cover source-name leakage, Worker crashes on KV write failure, a live-page polling race with no fetch timeout, and non-atomic ledger writes. Every fix was reproduced first and mutation-tested. Written in Vietnamese. |
| [`qa/2026-10-08-pending-work.md`](qa/2026-10-08-pending-work.md) | Khép sáu PR đang dở; sửa Worker/API/Swagger, marker Python 3.11/3.12 và kiểm menu điện thoại; bằng chứng kiểm thử, triển khai và giới hạn nguồn Vietlott. |
| [`qa/2026-09-18-visual-system.md`](qa/2026-09-18-visual-system.md) | Rà soát và đồng bộ giao diện 29 trang, bảo toàn chức năng, kiểm thử và giới hạn kiểm chứng. |
| [`domain/number-ontology.md`](domain/number-ontology.md) | Canonical two-digit number relations (lộn, bóng, bộ, chạm, tổng, cặp 50), their provenance, generated data contracts and Excel integrity rules. |
| [`research/algorithm-definitions.md`](research/algorithm-definitions.md) | Data/time semantics, canonical number relations and safety contracts for the analysis layer. |
| [`research/method-catalog.md`](research/method-catalog.md) | Catalog of publicly observed Vietnamese lottery methods with mathematical definitions, parameters, leakage risk and VLA equivalents. |
| [`research/source-comparison.md`](research/source-comparison.md) | Per-source public behaviour and the method comparison matrix. |
| [`research/quantitative-architecture.md`](research/quantitative-architecture.md) | Quantitative research report: power analysis, seven Monte Carlo structure tests, eleven model families benchmarked walk-forward, backtesting protocol, evaluation metrics, and the proposed shrinkage-ensemble architecture. Written in Vietnamese. |
| [`research/2026-09-28-ma-tran-suy-luan-bayes-markov-cau.md`](research/2026-09-28-ma-tran-suy-luan-bayes-markov-cau.md) | Bayes / Markov / cầu inference matrix with a three-tier confidence score, family-wise calibrated against 10 000 simulated fair histories, plus out-of-sample checks. Reproduce with `scripts/research/inference_matrix_audit.py`. Written in Vietnamese. |
| [`research/2026-09-28-duoi-4-va-gia-thuyet-duoi-nong.md`](research/2026-09-28-duoi-4-va-gia-thuyet-duoi-nong.md) | Why all ten published LOTO picks for 2026-09-28 ended in 4 (the cầu-kèo `tail_freq_7d` feature, shown by ablation), the tail cap on top lists, and the pre-registered prospective test of the "hot tail" hypothesis. Written in Vietnamese. |
| [`research/2026-09-28-soi-cau-vi-tri.md`](research/2026-09-28-soi-cau-vi-tri.md) | Position bridges ("soi cầu vị trí"): the reference site's rules decoded and matched number-for-number (107 digit positions, pooled two-way hits, shadow numbers display-only), and a 4 217-draw backtest showing longer or more-agreeing bridges do not hit more often. Written in Vietnamese. |
| [`research/2026-09-29-bay-kieu-cau-vi-tri.md`](research/2026-09-29-bay-kieu-cau-vi-tri.md) | Seven bridge types of the second reference site (LOTO, two-hit, single-number, special prize, number-set, by weekday) decoded cell-for-cell — the number-set rule recovered from the page's per-digit bridge ids — plus a full-history backtest per type and the weekly special-prize sheet tool. Written in Vietnamese. |
| [`research/2026-10-03-kiem-toan-mo-hinh-xac-suat.md`](research/2026-10-03-kiem-toan-mo-hinh-xac-suat.md) | Audit of the reported "accuracy drop" (none: skill has sat at zero since 02-2026; the special-prize Brier jump is a mean→sum unit change; no marginal-frequency drift and flat monthly prediction error, no leakage) and a three-tier challenger (Dirichlet/Beta prior → LightGBM residual → Platt/isotonic) benchmarked walk-forward on 1 000 draws against the retrained production ML. It does not beat the constant forecast, so it is not promoted; a top-5 special-prize "signal" turned out to be an artifact of a PMI smoothing bug; a synthetic power check shows it does detect planted signals. Reproduce with `scripts/research/benchmark_probability_models.py`. Written in Vietnamese. |
| [`research/2026-10-04-ra-soat-thanh-phan-to-hop.md`](research/2026-10-04-ra-soat-thanh-phan-to-hop.md) | Component-by-component review of the published LOTO/special-prize ensemble (the 03-10 audit scored models; this one scores the blend). Two defects made the published forecast worse than the constant: the two position-bridge branches inflate the LOTO probability level (median sums 24.49 and 26.47 against the 23.77 expected distinct numbers per draw), and the cầu-kèo component emitted raw probabilities with no skill-based shrinkage. Fixes: one shared `finalize_blend` that anchors the LOTO sum, and the `model_trust` rule applied to cầu-kèo. Walk-forward 1 000 draws: new vs current z = +3.23 (LOTO) and +1.77 (special); the trust rule alone is slightly negative on LOTO once anchored (z = −1.65), reported rather than hidden. Reproduce with `scripts/research/benchmark_component_trust.py`. Written in Vietnamese. |
| [`research/2026-10-05-phuong-phap-bai-du-doan.md`](research/2026-10-05-phuong-phap-bai-du-doan.md) | What a reference column of XSMB prediction articles actually does. The weekly series uses five digit-sum/shadow/touch rules (special-prize head and tail, touch set, two loto pairs) that `src/soi_cau/digit_sum_rules.py` reproduces number for number; the daily series names methods its own numbers do not follow. Over 4 224 draws every rule matches a same-size random pick (|z| < 1); "it hit as predicted" comes from scoring a whole week, where two random head digits also hit 78.5% of weeks. Written in Vietnamese. |
| [`research/2026-10-07-max3d-hang-don-vi.md`](research/2026-10-07-max3d-hang-don-vi.md) | Re-check of the Vietlott engine's e-value finding for Max 3D and Max 3D Pro. The data are clean (no duplicate or missing draw ids, every number zero-padded, within-draw repeats at the expected rate), and the deviation is real: the digit 6 in the units position appears 10.9% and 11.1% of the time instead of 10% (z ≈ 4.5 and 4.4), stable across six time blocks and replicated on two independent products. Every Max 3D bet the model prices still has RTP < 1 (best 0.63), so the overview page now states its randomness conclusion from the engine's measurement instead of a hard-coded "the draws are random". Written in Vietnamese. |
| [`research/2026-10-08-lo-nhieu-nhay.md`](research/2026-10-08-lo-nhieu-nhay.md) | A "VIP" filter for LOTO numbers that come out twice or more in one draw (`src/forecast/multi_hit_vip.py`): four feature layers (frequency/gap, Poisson anomaly, lagged co-occurrence, rhythm), weights re-chosen on the previous 30 draws, nested walk-forward, Platt-calibrated probability and a confidence level derived from a one-sided test against random picks on the same draws. On 4 228 real draws its top-5 hits 2.91% (606 hits; 95% CI 2.68–3.15%) against 2.91% (607.2 hits) for random picks on the same draws, so it is not promoted; a planted-signal run shows it does find real signals (19.5% against 3.65%). Also checks the specification's claims: the base rate is 2.975%, not 3.8–4.5%, and long-absent or recently-doubled numbers double at the base rate. A second attempt (`src/forecast/multi_hit_benchmark.py`, CLI `scripts/research/benchmark_multi_hit.py`) tries 22 strategies, including logistic regression and gradient boosting, selects one on the development period and tests it once on the last 1 000 draws: it fails (3.08%, p = 0.29), and strategy ranks between the two periods correlate at −0.02. Since 13-10-2026 the page `docs/lo-vip-nhieu-nhay.html` prints both measurements and derives its verdict from them (`src/forecast/multi_hit_report.py`, `src/pages/build_multi_hit_page.py`). Written in Vietnamese. |
| [`research/2026-10-15-lo-roi-ti-le-ky-sau.md`](research/2026-10-15-lo-roi-ti-le-ky-sau.md) | Why the "VIP" filter was retired from the page `docs/lo-vip-nhieu-nhay.html`: its dispersion component (variance/mean of hits) rewards numbers that appear rarely but in clumps, so number 32 stayed first for ten draws while absent for 10 → 19 draws. The replacement (`src/multi_hit_next_day.py`) only picks numbers that came in the latest draw and ranks them by the counted rate of coming twice or more in the NEXT draw: 3.11% (384/12 353) after a double, 2.90% after a single, 2.92% after none. Each number's own rate is shrunk by empirical Bayes (method of moments); the group factor divides by the expectation under those own rates, because multiplying the raw group rate counts the same effect twice (19.0% printed against 10.7% realised on a planted history; 10.8% after the fix). Walk-forward over 4 206 draws: 3.04% against 2.91% for random picks on the same draws (z = +1.09), printed probability 2.92% on average; not significant. Written in Vietnamese. |
| [`research/2026-10-15-lo-vip-cau-keo.md`](research/2026-10-15-lo-vip-cau-keo.md) | The "Lô VIP" page now forecasts the NEXT draw (the owner asked for a forecast built on the data and on "cầu kèo" experience, not a list of numbers that came today). `src/forecast/multi_hit_forecast.py` combines the `cau_keo_ml` features (minus six identity/calendar ones), counts of running two-hit and LOTO position bridges (matching `bridge_rules.find`) and multi-hit history in a logistic regression whose regularisation is chosen on an inner time split; it is refit every 250 draws walk-forward, and the printed probability is Platt-calibrated only on out-of-sample picks of earlier blocks. Measured to 2026-10-15: two-hit bridge experience is at the base rate (2.94% with no bridge, 2.82% with 1–4, 3.95% on 481 cases with 5+); the model's top-5 hits 2.99% against 2.92% for random picks on the same 3 810 draws (z = +0.58), with printed probability 2.86% on average. Written in Vietnamese. |
| [`research/2026-10-16-tran-du-bao-va-suy-luan-cau.md`](research/2026-10-16-tran-du-bao-va-suy-luan-cau.md) | Forecast ceiling of the whole system and empirical-Bayes bridge inference. Five tests find no learnable structure in 4 236 draws (digit bias does not persist between halves, digits within a draw are independent, no next-draw dependence, every recency digit-frequency model loses to uniform), and the published skill is indistinguishable from zero. The position-bridge engine (`path_prob`) printed the in-sample hit rate of the top 300 of ~5 671 rules per lag (winner's curse: at the production 2 000-draw window the stable LOTO branch summed to 24.42 vs 23.77); it now learns from every rule how much bridges really differ (spread = 1.00× binomial) and how a running streak changes the next hit (DerSimonian–Laird), so every bridge shrinks to the base rate unless the data show otherwise. Walk-forward over 2 000 draws: the stable LOTO branch beats the old one at z = +9.69, the ensemble is unchanged (z = −0.09 LOTO, +1.01 Đặc Biệt), and every new branch is level with the constant forecast. Reproduce with `scripts/research/audit_forecast_ceiling.py` and `scripts/research/benchmark_bridge_inference.py`. Written in Vietnamese. |
| [`architecture/2026-10-23-bo-cuc-src.md`](architecture/2026-10-23-bo-cuc-src.md) | Bố cục `src/` sau đợt 2: 144 module phẳng gom vào 11 gói theo chức năng (`core`, `ingest`, `ensemble`, `stats`, `soi_cau`, `ml`, `forecast`, `evaluation`, `research`, `web`, `pages`), tên module giữ nguyên. Đồ thị phụ thuộc giữa các gói (không vòng), luật import, chạy với `PYTHONPATH=src`, đường dẫn qua `core.paths`, tên `ml_models` cho pack joblib cũ, và phép so pipeline đầy đủ trước/sau. Viết bằng tiếng Việt. |
| [`architecture/2026-10-13-he-suy-luan-va-tu-hoc.md`](architecture/2026-10-13-he-suy-luan-va-tu-hoc.md) | Kiến trúc tổng thể hệ suy luận, tri thức và tự học (sơ đồ Mermaid, chức năng từng module, mã mẫu truyền dữ liệu A → B, vòng Hedge tự chỉnh trọng số, hàm dự đoán kèm độ tin cậy và giải thích, thư viện). Bổ sung kho tri thức `src/forecast/knowledge_base.py`: luật trễ tự khai phá chỉ chấm tiến cứu bằng e-process, bộ nhớ ngữ cảnh dạng vector (kém hằng số, z = −11,2, nên không vào tổ hợp). |
| [`architecture/data-schema.md`](architecture/data-schema.md) | Schema ĐANG DÙNG của lịch sử KQXS Miền Bắc, đo trực tiếp từ dữ liệu chứ không phải schema đề xuất: bảng gốc `data/xsmb.csv` và các bảng dẫn xuất. Viết bằng tiếng Việt. |
| [`architecture/traditional-results.md`](architecture/traditional-results.md) | Hợp đồng dữ liệu, REST API, thứ tự VLA → xskt.vn, cache và quy trình triển khai trang Sổ kết quả truyền thống. Viết bằng tiếng Việt. |
| [`architecture/vietnamese-calendar.md`](architecture/vietnamese-calendar.md) | Bảng kết quả gọn và lịch vạn niên UTC+7: nguồn công thức, dữ liệu Đặc Biệt thật, tương tác và kiểm thử. |
| [`architecture/soi-cau-ml-mapping.md`](architecture/soi-cau-ml-mapping.md) | Đối chiếu bốn ánh xạ "soi cầu" sang ML thường được đề xuất với mã đã có trong kho, kèm hai lỗi thiết kế trong bản đề xuất và số đo. Viết bằng tiếng Việt. |
| [`architecture/probabilistic-upgrade.md`](architecture/probabilistic-upgrade.md) | Thiết kế nâng cấp lớp ước lượng xác suất, neo vào số đo: kỹ năng mô hình sản xuất, phân tích công suất (412 164 giả thuyết → ngưỡng phát hiện +22,5 %), và phép đo mới về hàm mất mát tùy biến cùng hiệu chuẩn trên 203 200 hàng. Gồm sơ đồ pipeline, đối chiếu bốn khu vực yêu cầu với hiện trạng, ba tầng ưu tiên và checklist rủi ro. Viết bằng tiếng Việt. |
| [`architecture/ml-engine.md`](architecture/ml-engine.md) | Technical blueprint for `src/ml_engine/`: input schema, module layout, exponential weights on log-loss with fixed share, ADWIN/KS drift detection, walk-forward validation with Optuna, evaluation metrics and the `model_trust` gate, with measured results (the Thompson bandit and hit-rate safe mode were removed on 20-10-2026). Written in Vietnamese. |
| [`architecture/ui-dock-redesign.md`](architecture/ui-dock-redesign.md) | UI/UX redesign: floating dock replacing the sidebar, self-hosted Inter, six-card metrics panel, two-tier data matrix, three-column prediction row, merged evidence card, with before/after measurements. Written in Vietnamese. |
| [`architecture/ui-design-system.md`](architecture/ui-design-system.md) | Quy tắc hệ thiết kế đã ĐO được, kèm tên phép kiểm canh giữ từng quy tắc: bốn chủ thể tạo kiểu, tách sắc thương hiệu khỏi màu dữ liệu (40°), một-phép-đo-một-sắc, phân cấp số nháy, dữ liệu thắng điều hướng, ba trạng thái ô ma trận, sàn rãnh lưới, ngưỡng tính theo khung nội dung, chế độ máy tính, thang 8pt. Viết bằng tiếng Việt. |
| [`architecture/vietlott-subsystem.md`](architecture/vietlott-subsystem.md) | Yêu cầu kỹ thuật và kiến trúc phân hệ Vietlott, neo vào engine `vietlott/` đang chạy. Gồm: bảng đối chiếu sáu nhóm yêu cầu (thu thập, kho, thống kê, dự báo AI, tự học, đối soát) với module hiện có và phần còn thiếu; sơ đồ luồng một kỳ quay; hai chế độ vận hành (tĩnh / máy chủ thường trực); đề xuất công nghệ theo ràng buộc của kho; lược đồ DuckDB cho kết quả, giải, thu thập, thống kê có phiên bản, mô hình, dự báo, backtest; lộ trình ba giai đoạn có tiêu chí xong đo được. Nói rõ ranh giới: với máy quay công bằng không mô hình nào tăng xác suất trúng, nên vòng tự học được đo bằng log-loss so với luật công bằng và e-value, còn "độ tin cậy" là trạng thái kiểm định chứ không phải xác suất trúng. Viết bằng tiếng Việt. |
| [`operations/live-worker.md`](operations/live-worker.md) | Worker đúng giờ: đồng hồ và nguồn phát `live.json`, chạy đúng khung quay số mà không phụ thuộc bộ lập lịch của GitHub. Gồm số đo độ trễ lịch GitHub (trung vị 4h04m trên 32 mốc), kiến trúc, các bước triển khai Cloudflare, bốn phép kiểm đối chiếu chống trôi lệch hai bản mã, và phần nói rõ điều CHƯA kiểm chứng được. Viết bằng tiếng Việt. |
| [`operations/on-time-trigger.md`](operations/on-time-trigger.md) | Chẩn đoán độ trễ lịch chạy và cách dựng bộ hẹn giờ ngoài gọi `repository_dispatch`. Viết bằng tiếng Việt. |
| [`operations/scheduling.md`](operations/scheduling.md) | Lịch chạy các workflow và ràng buộc thời gian. |
| [`history/legacy-consolidation.md`](history/legacy-consolidation.md) | Consolidated migration, retirement acceptance and forensic re-audit record for the three predecessor repositories. |

## Kế hoạch, giao diện và nghiệm thu (chuyển từ `docs/` ngày 13-10-2026)

| Document | Scope |
| --- | --- |
| [`architecture/2026-09-26-theme-search-icons-design.md`](architecture/2026-09-26-theme-search-icons-design.md) | Đặc tả chủ đề sáng/tối, biểu tượng SVG và tìm kiếm toàn cục (nguồn chuẩn của hợp đồng giao diện 26-09-2026). |
| [`plans/2026-09-26-compact-results-calendar.md`](plans/2026-09-26-compact-results-calendar.md) | Kế hoạch: bảng kết quả gọn và lịch vạn niên. |
| [`plans/2026-09-26-crafto-integration.md`](plans/2026-09-26-crafto-integration.md) | Kế hoạch tích hợp ngôn ngữ thị giác Crafto Application. |
| [`plans/2026-09-26-theme-search-icons.md`](plans/2026-09-26-theme-search-icons.md) | Kế hoạch hoàn thiện theme, tìm kiếm và biểu tượng. |
| [`plans/2026-09-27-home-live-navigation.md`](plans/2026-09-27-home-live-navigation.md) | Kế hoạch tinh chỉnh trang chủ và trang trực tiếp. |
| [`plans/2026-09-27-pending-ci.md`](plans/2026-09-27-pending-ci.md) | Kế hoạch hoàn tất PR và khoảng trống CI. |
| [`plans/2026-10-07-leading-zero.md`](plans/2026-10-07-leading-zero.md) | Kế hoạch giữ số 0 đầu trong mọi bảng số. |
| [`plans/2026-10-08-dashboard-tables.md`](plans/2026-10-08-dashboard-tables.md) | Kế hoạch bố cục bảng của trang Dashboard. |
| [`plans/2026-10-08-pending-prs.md`](plans/2026-10-08-pending-prs.md) | Kế hoạch hoàn tất các PR đang dở ngày 08-10-2026. |
| [`qa/2026-09-25-soat-tu-phuc-hoi.md`](qa/2026-09-25-soat-tu-phuc-hoi.md) | Soát sâu, tự sửa và tự phục hồi ngày 25-09-2026. |
| [`qa/crafto-integration-2026-09-26.md`](qa/crafto-integration-2026-09-26.md) | Kiểm chứng tích hợp Crafto Application. |
| [`qa/theme-search-icons-2026-09-26.md`](qa/theme-search-icons-2026-09-26.md) | Nghiệm thu giao diện sáng/tối, tìm kiếm và SVG. |
| [`qa/vla-deep-audit-report.md`](qa/vla-deep-audit-report.md) | Báo cáo soát sâu và gia cố sản xuất. |
| [`ui/VLA_MASTER_UIUX_SPEC.md`](ui/VLA_MASTER_UIUX_SPEC.md) | Bản prompt UI/UX của chủ dự án, giữ để tham chiếu; CHƯA có hiệu lực (xem CLAUDE.md). |
| [`ui/crafto-integration-2026-09-26.md`](ui/crafto-integration-2026-09-26.md) | Thiết kế: Crafto Application × giao diện thống kê. |
| [`ui/crafto-landing-background.md`](ui/crafto-landing-background.md) | Nền Crafto cho trang chủ / landing: trạng thái thật. |
| [`ui/implementation-progress.md`](ui/implementation-progress.md) | Tiến độ giao diện. |
| [`ui/nexlink-design-system.md`](ui/nexlink-design-system.md) | Hệ thiết kế Nexlink áp cho kho: số đo, không phải ước. |
| [`ui/theme-contrast-2026-09-26.md`](ui/theme-contrast-2026-09-26.md) | Số đo độ tương phản bảng màu sáng/tối. |
| [`ui/vla-ui-transformation-report.md`](ui/vla-ui-transformation-report.md) | Báo cáo khung ứng dụng hai cấp. |

## Related material outside this directory

| Location | Content |
| --- | --- |
| `README.md` (root) | Operating overview and setup. **Generated** by `src/pages/update_readme.py` from `src/templates/README.j2` — do not edit by hand. |
| `DASHBOARD.md` (root) | Analysis dashboard. **Generated** by `src/pages/build_markdown_dashboard_v3.py` — do not edit by hand. |
| `SECURITY.md` (root) | Vulnerability reporting, trust boundaries and model-artifact policy. |
| `documentation/engineering-log/` | Engineering log: repair rules, verified repair patterns, known failures, research memory, tuning history and incident records. Renamed from `.codex/`, which read as a reference to the ChatGPT Codex app; it is unrelated to it. |

## Conventions

- The implementation is the source of truth. When a document and the code
  disagree, the code wins and the document is a bug.
- Each document states its own verification date where the content is
  time-sensitive.
- Research-plane material is descriptive or challenger evidence only. Promotion
  into production prediction weights requires a separate code change plus the
  chronological out-of-sample gates described in the relevant document.

## Nâng cấp xác suất và tự học ngày 27-09-2026

- [Kiến trúc](architecture/2026-09-27-adaptive-inference.md)
- [Kế hoạch và kiểm định](architecture/2026-09-27-adaptive-inference-plan.md)
- [Hướng dẫn vận hành tự học](operations/adaptive-inference.md)
- [Kết quả kiểm chứng và giới hạn](qa/2026-09-27-adaptive-inference.md)
- [Sửa tích hợp CI và vòng đời stacking](qa/2026-09-27-stacking-integration.md)

## Tích hợp đa thuật toán ngày 17-10-2026

- [Kiến trúc và kế hoạch tích hợp](architecture/2026-10-17-multi-agent-integration.md)
- [Kết quả kiểm chứng](qa/2026-10-17-multi-agent-integration.md)
- [Kiến trúc ba tác tử XSMB](architecture/2026-10-17-xsmb-multi-agent.md)
- [Kế hoạch triển khai ba tác tử XSMB](plans/2026-10-17-xsmb-multi-agent.md)
- [Kiểm chứng và số đo ba tác tử XSMB](qa/2026-10-17-xsmb-multi-agent.md)
- [Làm mới source, cache và tài nguyên xuất bản](operations/source-refresh.md)

## Đồng bộ Keno/Bingo18 ngày 19-10-2026

- [Khắc phục cơ chế đồng bộ Keno/Bingo18](qa/2026-10-19-vietlott-fast-results.md)
