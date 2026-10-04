# VLA documentation

Hand-written project documentation. This directory is **not** published: GitHub
Pages serves `docs/`, which holds generated HTML artifacts only.

Historical patterns do not guarantee future lottery results. Every document here
treats descriptive and research material as evidence for validation, never as a
forecasting guarantee.

## Index

| Document | Scope |
| --- | --- |
| [`ui/nexlink-completion-2026-09-23.md`](ui/nexlink-completion-2026-09-23.md) | Hoàn thiện khung Nexlink, sửa điều hướng và ghi rõ kiểm chứng cùng giới hạn trực quan. |
| [`qa/2026-09-18-visual-system.md`](qa/2026-09-18-visual-system.md) | Rà soát và đồng bộ giao diện 29 trang, bảo toàn chức năng, kiểm thử và giới hạn kiểm chứng. |
| [`domain/number-ontology.md`](domain/number-ontology.md) | Canonical two-digit number relations (lộn, bóng, bộ, chạm, tổng, cặp 50), their provenance, generated data contracts and Excel integrity rules. |
| [`research/algorithm-definitions.md`](research/algorithm-definitions.md) | Data/time semantics, canonical number relations and safety contracts for the analysis layer. |
| [`research/method-catalog.md`](research/method-catalog.md) | Catalog of publicly observed Vietnamese lottery methods with mathematical definitions, parameters, leakage risk and VLA equivalents. |
| [`research/source-comparison.md`](research/source-comparison.md) | Per-source public behaviour and the method comparison matrix. |
| [`research/quantitative-architecture.md`](research/quantitative-architecture.md) | Quantitative research report: power analysis, seven Monte Carlo structure tests, eleven model families benchmarked walk-forward, backtesting protocol, evaluation metrics, and the proposed shrinkage-ensemble architecture. Written in Vietnamese. |
| [`research/2026-09-28-ma-tran-suy-luan-bayes-markov-cau.md`](research/2026-09-28-ma-tran-suy-luan-bayes-markov-cau.md) | Bayes / Markov / cầu inference matrix with a three-tier confidence score, family-wise calibrated against 10 000 simulated fair histories, plus out-of-sample checks. Reproduce with `scripts/inference_matrix_audit.py`. Written in Vietnamese. |
| [`research/2026-09-28-duoi-4-va-gia-thuyet-duoi-nong.md`](research/2026-09-28-duoi-4-va-gia-thuyet-duoi-nong.md) | Why all ten published LOTO picks for 2026-09-28 ended in 4 (the cầu-kèo `tail_freq_7d` feature, shown by ablation), the tail cap on top lists, and the pre-registered prospective test of the "hot tail" hypothesis. Written in Vietnamese. |
| [`research/2026-09-28-soi-cau-vi-tri.md`](research/2026-09-28-soi-cau-vi-tri.md) | Position bridges ("soi cầu vị trí"): the reference site's rules decoded and matched number-for-number (107 digit positions, pooled two-way hits, shadow numbers display-only), and a 4 217-draw backtest showing longer or more-agreeing bridges do not hit more often. Written in Vietnamese. |
| [`research/2026-09-29-bay-kieu-cau-vi-tri.md`](research/2026-09-29-bay-kieu-cau-vi-tri.md) | Seven bridge types of the second reference site (LOTO, two-hit, single-number, special prize, number-set, by weekday) decoded cell-for-cell — the number-set rule recovered from the page's per-digit bridge ids — plus a full-history backtest per type and the weekly special-prize sheet tool. Written in Vietnamese. |
| [`research/2026-10-03-kiem-toan-mo-hinh-xac-suat.md`](research/2026-10-03-kiem-toan-mo-hinh-xac-suat.md) | Audit of the reported "accuracy drop" (none: skill has sat at zero since 02-2026; the special-prize Brier jump is a mean→sum unit change; no marginal-frequency drift and flat monthly prediction error, no leakage) and a three-tier challenger (Dirichlet/Beta prior → LightGBM residual → Platt/isotonic) benchmarked walk-forward on 1 000 draws against the retrained production ML. It does not beat the constant forecast, so it is not promoted; a top-5 special-prize "signal" turned out to be an artifact of a PMI smoothing bug; a synthetic power check shows it does detect planted signals. Reproduce with `scripts/benchmark_probability_models.py`. Written in Vietnamese. |
| [`research/2026-10-04-ra-soat-thanh-phan-to-hop.md`](research/2026-10-04-ra-soat-thanh-phan-to-hop.md) | Component-by-component review of the published LOTO/special-prize ensemble (the 03-10 audit scored models; this one scores the blend). Two defects made the published forecast worse than the constant: the two position-bridge branches inflate the LOTO probability level (median sums 24.49 and 26.47 against the 23.77 expected distinct numbers per draw), and the cầu-kèo component emitted raw probabilities with no skill-based shrinkage. Fixes: one shared `finalize_blend` that anchors the LOTO sum, and the `model_trust` rule applied to cầu-kèo. Walk-forward 1 000 draws: new vs current z = +3.23 (LOTO) and +1.77 (special); the trust rule alone is slightly negative on LOTO once anchored (z = −1.65), reported rather than hidden. Reproduce with `scripts/benchmark_component_trust.py`. Written in Vietnamese. |
| [`architecture/data-schema.md`](architecture/data-schema.md) | Schema ĐANG DÙNG của lịch sử KQXS Miền Bắc, đo trực tiếp từ dữ liệu chứ không phải schema đề xuất: bảng gốc `data/xsmb.csv` và các bảng dẫn xuất. Viết bằng tiếng Việt. |
| [`architecture/traditional-results.md`](architecture/traditional-results.md) | Hợp đồng dữ liệu, REST API, thứ tự VLA → xskt.vn, cache và quy trình triển khai trang Sổ kết quả truyền thống. Viết bằng tiếng Việt. |
| [`architecture/vietnamese-calendar.md`](architecture/vietnamese-calendar.md) | Bảng kết quả gọn và lịch vạn niên UTC+7: nguồn công thức, dữ liệu Đặc Biệt thật, tương tác và kiểm thử. |
| [`architecture/soi-cau-ml-mapping.md`](architecture/soi-cau-ml-mapping.md) | Đối chiếu bốn ánh xạ "soi cầu" sang ML thường được đề xuất với mã đã có trong kho, kèm hai lỗi thiết kế trong bản đề xuất và số đo. Viết bằng tiếng Việt. |
| [`architecture/probabilistic-upgrade.md`](architecture/probabilistic-upgrade.md) | Thiết kế nâng cấp lớp ước lượng xác suất, neo vào số đo: kỹ năng mô hình sản xuất, phân tích công suất (412 164 giả thuyết → ngưỡng phát hiện +22,5 %), và phép đo mới về hàm mất mát tùy biến cùng hiệu chuẩn trên 203 200 hàng. Gồm sơ đồ pipeline, đối chiếu bốn khu vực yêu cầu với hiện trạng, ba tầng ưu tiên và checklist rủi ro. Viết bằng tiếng Việt. |
| [`architecture/ml-engine.md`](architecture/ml-engine.md) | Technical blueprint for `src/ml_engine/`: input schema, module layout, discounted Thompson-sampling bandit, ADWIN/KS drift detection, walk-forward validation with Optuna, evaluation metrics and safe-mode fallback, with measured results. Written in Vietnamese. |
| [`architecture/ui-dock-redesign.md`](architecture/ui-dock-redesign.md) | UI/UX redesign: floating dock replacing the sidebar, self-hosted Inter, six-card metrics panel, two-tier data matrix, three-column prediction row, merged evidence card, with before/after measurements. Written in Vietnamese. |
| [`architecture/ui-design-system.md`](architecture/ui-design-system.md) | Quy tắc hệ thiết kế đã ĐO được, kèm tên phép kiểm canh giữ từng quy tắc: bốn chủ thể tạo kiểu, tách sắc thương hiệu khỏi màu dữ liệu (40°), một-phép-đo-một-sắc, phân cấp số nháy, dữ liệu thắng điều hướng, ba trạng thái ô ma trận, sàn rãnh lưới, ngưỡng tính theo khung nội dung, chế độ máy tính, thang 8pt. Viết bằng tiếng Việt. |
| [`operations/live-worker.md`](operations/live-worker.md) | Worker đúng giờ: đồng hồ và nguồn phát `live.json`, chạy đúng khung quay số mà không phụ thuộc bộ lập lịch của GitHub. Gồm số đo độ trễ lịch GitHub (trung vị 4h04m trên 32 mốc), kiến trúc, các bước triển khai Cloudflare, bốn phép kiểm đối chiếu chống trôi lệch hai bản mã, và phần nói rõ điều CHƯA kiểm chứng được. Viết bằng tiếng Việt. |
| [`operations/on-time-trigger.md`](operations/on-time-trigger.md) | Chẩn đoán độ trễ lịch chạy và cách dựng bộ hẹn giờ ngoài gọi `repository_dispatch`. Viết bằng tiếng Việt. |
| [`operations/scheduling.md`](operations/scheduling.md) | Lịch chạy các workflow và ràng buộc thời gian. |
| [`history/legacy-consolidation.md`](history/legacy-consolidation.md) | Consolidated migration, retirement acceptance and forensic re-audit record for the three predecessor repositories. |

## Related material outside this directory

| Location | Content |
| --- | --- |
| `README.md` (root) | Operating overview and setup. **Generated** by `src/update_readme.py` from `src/templates/README.j2` — do not edit by hand. |
| `DASHBOARD.md` (root) | Analysis dashboard. **Generated** by `src/build_markdown_dashboard_v3.py` — do not edit by hand. |
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
