# VLA documentation

Hand-written project documentation. This directory is **not** published: GitHub
Pages serves `docs/`, which holds generated HTML artifacts only.

Historical patterns do not guarantee future lottery results. Every document here
treats descriptive and research material as evidence for validation, never as a
forecasting guarantee.

## Index

| Document | Scope |
| --- | --- |
| [`qa/2026-09-18-visual-system.md`](qa/2026-09-18-visual-system.md) | Rà soát và đồng bộ giao diện 29 trang, bảo toàn chức năng, kiểm thử và giới hạn kiểm chứng. |
| [`domain/number-ontology.md`](domain/number-ontology.md) | Canonical two-digit number relations (lộn, bóng, bộ, chạm, tổng, cặp 50), their provenance, generated data contracts and Excel integrity rules. |
| [`research/algorithm-definitions.md`](research/algorithm-definitions.md) | Data/time semantics, canonical number relations and safety contracts for the analysis layer. |
| [`research/method-catalog.md`](research/method-catalog.md) | Catalog of publicly observed Vietnamese lottery methods with mathematical definitions, parameters, leakage risk and VLA equivalents. |
| [`research/source-comparison.md`](research/source-comparison.md) | Per-source public behaviour and the method comparison matrix. |
| [`research/quantitative-architecture.md`](research/quantitative-architecture.md) | Quantitative research report: power analysis, seven Monte Carlo structure tests, eleven model families benchmarked walk-forward, backtesting protocol, evaluation metrics, and the proposed shrinkage-ensemble architecture. Written in Vietnamese. |
| [`architecture/data-schema.md`](architecture/data-schema.md) | Schema ĐANG DÙNG của lịch sử KQXS Miền Bắc, đo trực tiếp từ dữ liệu chứ không phải schema đề xuất: bảng gốc `data/xsmb.csv` và các bảng dẫn xuất. Viết bằng tiếng Việt. |
| [`architecture/traditional-results.md`](architecture/traditional-results.md) | Hợp đồng dữ liệu, REST API, thứ tự VLA → xskt.vn, cache và quy trình triển khai trang Sổ kết quả truyền thống. Viết bằng tiếng Việt. |
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
