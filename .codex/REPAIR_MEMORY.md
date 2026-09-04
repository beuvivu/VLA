# Verified repair memory

Last verified: 2026-09-03

## REP-0012 — Không nuốt lỗi làm mới mô phỏng

Context: pipeline dựng bảng mô phỏng xác suất cho ngày mục tiêu.

Symptom: khi snapshot dự báo thiếu hoặc lỗi, pipeline non-strict vẫn tiếp tục
và giữ `fun_draw_next.*` của ngày trước, khiến giao diện trông như bị đứng.

Root cause: bước `build_fun_prediction.py` dùng `allow_fail=soft_fail` dù đầu ra
là artifact user-visible, có ngày mục tiêu và được production audit kiểm tra.

Correct pattern: coi bước làm mới mô phỏng là hard-fail; ghi JSON/CSV vào tệp tạm
cùng thư mục rồi `os.replace` để không xuất bản tệp bị cắt dở.

Avoid: nuốt lỗi dựng artifact hoặc ghi trực tiếp vào tệp production.

Regression guard: `test_pipeline_treats_simulation_refresh_as_hard_failure` và
`test_artifact_write_replaces_both_snapshots_without_partial_files`.

Affected modules: `pipeline.py`, `build_fun_prediction.py`.

Confidence: high

Last verified: 2026-09-04

## REP-0013 — Cache production không được che khuất dữ liệu mới

Context: workflow live/daily/dashboard chạy trên GitHub Actions.

Symptom: cache phụ thuộc của runner có thể làm chẩn đoán stale khó tái lập;
không có cơ chế purge được kiểm soát.

Root cause: job production dùng cache pip mặc định trong khi mục tiêu chính là
khôi phục dữ liệu/artifact theo từng run.

Correct pattern: bỏ cache pip ở các job production, cài với `--no-cache-dir`,
ghi nhận `VLA_CACHE_BUST=${{ github.run_id }}`, và chỉ purge toàn bộ cache bằng
workflow `workflow_dispatch` có quyền `actions: write`; thao tác purge dùng REST
API chuẩn để không phụ thuộc binary `gh` trên máy chạy.

Avoid: xóa cache tự động theo lịch hoặc giả định cache package là dữ liệu mới.

Regression guard: `test_production_refreshes_do_not_restore_package_caches` và
`test_cache_purge_is_explicit_and_not_scheduled`.

Affected modules: `.github/workflows/*.yml`, `scripts/purge_github_caches.sh`.

Confidence: high

Last verified: 2026-09-04

## REP-0011 — Đồng nhất UTC+7 và bàn giao live→daily

Context: dữ liệu daily và bảng mô phỏng không cập nhật kịp sau giờ quay.

Symptom: lịch cron bắt đầu muộn, cutoff giữa các workflow không đồng nhất và
live đã xác minh nhưng daily vẫn chờ lượt cron tiếp theo.

Root cause: GitHub Actions dùng UTC trong khi logic nghiệp vụ dùng giờ Việt Nam;
workflow live không truyền lý do xác minh cho workflow daily.

Correct pattern: dùng `time_policy.py` làm nguồn giờ `Asia/Ho_Chi_Minh` (UTC+7),
cutoff 18:35, cron UTC được ghi rõ và dispatch `reason=live_verified` ngay khi
đủ đồng thuận.

Regression guard: `tests/test_time_policy.py`, `tests/test_live_sync.py` và
`tests/test_workflows.py`.

Affected modules: `time_policy.py`, `live_sync.py`, `sync.py`, `production_audit.py`,
`monitor_health.py`, các workflow live/daily/watchdog.

Confidence: high

Last verified: 2026-09-04

## REP-0008 — Dữ liệu nguồn phải được chuẩn hóa trước đồng thuận

Context: thu thập và hợp nhất 27 ô kết quả từ các trang công khai.

Symptom: phép ép kiểu rộng có thể nhận chữ số Unicode, số thực, giá trị không
hữu hạn hoặc chuỗi chứa HTML; closure kiểm tra đồng thuận cũng có thể tham chiếu
nhầm giá trị của vòng lặp cuối.

Root cause: biên tin cậy dùng chuyển đổi kiểu thuận tiện thay cho grammar dữ liệu
giải thưởng, và biến vòng lặp không được đóng băng khi tạo predicate.

Correct pattern: chỉ nhận token chữ số ASCII đúng độ rộng, số nguyên hữu hạn đúng
miền; chuẩn hóa từng nguồn trước khi tính đồng thuận và bind dữ liệu quan sát vào
tham số mặc định của closure.

Avoid: `int(float(value))`, `str.isdigit()` hoặc đưa token chưa kiểm tra vào bỏ
phiếu đồng thuận.

Regression guard: `tests/test_sources.py`, `tests/test_validate_data_strict.py`,
`tests/test_security_hardening.py`.

Affected modules: `sources.py`, `reconcile_live_canonical.py`, `validate_data.py`,
`lottery.py`.

Confidence: high

Last verified: 2026-09-03

## REP-0014 — Cặp lộn của số kép phải dùng quan hệ kép-bóng

Context: bảng `reverse_pair_frequency_*` và các dashboard hiển thị cặp lộn.

Symptom: số kép như 77 xuất hiện dưới dạng cặp tự lặp `77-77`, làm sai phân
hoạch cặp 50 và gây nhầm rằng phép đảo của số kép là một cặp hai phần tử.

Root cause: bộ sinh thống kê tự tạo `AB-BA` cho toàn bộ 00..99; với `AA`,
phép đảo trả lại chính nó và không chuyển sang đối tác bóng.

Correct pattern: luôn lấy 50 họ cặp từ `number_reference.all_cap_loto_50()`;
45 cặp thường dùng đảo chiều, còn 5 cặp kép dùng kép-bóng
`00-55`, `11-66`, `22-77`, `33-88`, `44-99`.

Avoid: tự dựng danh sách đảo trong từng báo cáo hoặc giữ nhánh đặc biệt
`a == b` rồi gắn số kép với chính nó.

Regression guard: `test_reverse_pair_frequency_uses_kep_bong_instead_of_self_pairs`,
`test_reverse_pair_frequency_has_all_five_kep_bong_families` và kiểm tra artifact
50 cặp/kỳ không có self-pair.

Affected modules: `statistical_matrices.py`, các builder dashboard và artifact
`data/advanced/reverse_pair_frequency_*`.

Confidence: high

Last verified: 2026-09-04

## REP-0009 — Dữ liệu dashboard không được đi qua HTML động

Context: trang tĩnh nhúng JSON và hiển thị dữ liệu nguồn/giải thích mô hình.

Symptom: chuỗi không tin cậy có thể đóng thẻ `<script>` hoặc đi vào `innerHTML`,
tạo đường chèn markup/script trên GitHub Pages.

Root cause: tuần tự hóa JSON hợp lệ chưa đủ an toàn cho ngữ cảnh HTML và builder
dùng chuỗi HTML để tạo node giao diện.

Correct pattern: escape `&`, `<`, `>`, U+2028 và U+2029 khi nhúng JSON; tạo DOM
bằng `createElement`/`textContent`; thêm CSP và `no-referrer` cho mọi trang sinh.

Avoid: ghép dữ liệu vào `innerHTML`, `document.write` hoặc thẻ script JSON chưa
escape theo ngữ cảnh.

Regression guard: `tests/test_landing_page.py`, `tests/test_security_hardening.py`,
`tests/test_vietnamese_ui.py`.

Affected modules: `web_security.py`, `build_landing_page.py`,
`build_statistics_dashboard.py`, các builder HTML và `docs/live.html`.

Confidence: high

Last verified: 2026-09-03

## REP-0010 — Artifact và cấu hình xác suất phải fail closed

Context: suy luận ML, calibration, ensemble và challenger nghiên cứu.

Symptom: model pack sai schema/allowlist, mảng có NaN, xác suất ngoài `[0,1]`,
mode lạ hoặc cấu hình kiểu `bool` có thể đi sâu vào pipeline hay kích hoạt model
không đủ điều kiện.

Root cause: kiểm tra trước đây rời rạc và một số nhánh tin vào type hint hoặc
metadata đã giải tuần tự.

Correct pattern: kiểm tra chính xác schema, mode, allowlist, shape, miền số và
tính hữu hạn tại biên; không gọi challenger bị từ chối; mọi trạng thái không hợp
lệ đều quay về baseline hoặc báo lỗi rõ ràng tùy API.

Avoid: suy luận feature từ toàn bộ cột, dùng `assert` cho điều kiện runtime hoặc
chuẩn hóa vector/trọng số có NaN.

Regression guard: `tests/test_ml_validation.py`, `tests/test_meta_predictor.py`,
`tests/test_ensemble_utils_security.py`, `tests/test_configuration_validation.py`.

Affected modules: `ml_predict.py`, `ml_validation.py`, `meta_predictor.py`,
`predict_nextday_2d.py`, `calibration.py`, `ensemble_utils.py` và các dataclass cấu
hình nghiên cứu.

Confidence: high

Last verified: 2026-09-03

## REP-0001 — Pair champion and challenger randomness

Context: domain-feature walk-forward ablation.

Symptom: baseline and challenger fits used different random seeds in the same fold.

Root cause: seeds were derived from candidate identity rather than fold identity.

Correct pattern: one deterministic fold seed is reused for baseline and every challenger in that fold.

Avoid: treating independently randomized fits as if the feature set were the only experimental difference.

Regression guard: ablation output records the fold seed; paired comparison requires identical OOS labels/dates.

Affected modules: `cau_keo_domain_challenger.py`, `ml_validation.py`

Confidence: high

Last verified: 2026-09-02

## REP-0002 — Validate raw/normalized history alignment

Context: base ML positional feature construction.

Symptom: raw prize rows and two-digit target rows could be consumed by row index without an exact date-axis equality check.

Root cause: each input was sorted independently, then assumed aligned.

Correct pattern: reject duplicate dates and require identical ordered date axes before constructing any cross-source feature.

Avoid: relying on equal row counts or sort order as proof of temporal alignment.

Regression guard: mismatched and duplicated date-axis tests in `tests/test_ml_features.py`.

Affected modules: `ml_features.py`

Confidence: high

Last verified: 2026-09-02

## REP-0003 — Adjacent-pair strict zip requires equal slices

Context: recurrence interval extraction.

Symptom: pairing `indices` with `indices[1:]` under `zip(..., strict=True)` raised on every non-empty hit sequence.

Root cause: the left iterable was not sliced to the same length.

Correct pattern: pair `indices[:-1]` with `indices[1:]` when strict adjacency validation is desired.

Avoid: strict zip over intentionally unequal full/tail sequences.

Regression guard: three-draw-cycle synthetic ground-truth test.

Affected modules: `gap_cycle_stats.py`

Confidence: high

Last verified: 2026-09-02

## REP-0004 — Pattern diagnostics must survive result truncation

Context: positional-cầu multiple-hypothesis accounting.

Symptom: applying `max_results` also reduced `surviving_hypotheses`, hiding
how many rules passed the historical filter. A streak could also remain marked
active when the newest draw lacked an exact prior-calendar source draw.

Root cause: presentation truncation and active-streak display state were mixed
with scientific search diagnostics.

Correct pattern: record the full survivor count before limiting returned rows,
and require an active streak to reach the newest evaluable draw.

Avoid: letting display limits or missing trailing dates make a pattern search
look smaller or more current than it was.

Regression guard: truncation and trailing-calendar-gap tests in
`tests/test_dynamic_cau.py`.

Affected modules: `dynamic_cau.py`

Confidence: high

Last verified: 2026-09-02

## REP-0005 — Canonicalize external candidate-score components

Context: configurable candidate ranking.

Symptom: a string key such as `"07"` passed validation but was never found by
integer candidate lookup, and unrestricted external scales could dominate the
weighted score.

Root cause: validation converted values transiently without storing the
canonical representation or enforcing the documented normalized scale.

Correct pattern: canonicalize number keys to integers, values to floats, reject
canonical duplicates, and require optional component scores in `[0,1]`.

Avoid: validating one representation and storing another.

Regression guard: optional-score canonicalization and scale tests in
`tests/test_candidate_scoring.py`.

Affected modules: `candidate_scoring.py`

Confidence: high

Last verified: 2026-09-02

## REP-0006 — Schema code và artifact phải được nâng cấp nguyên tử

Context: cổng challenger miền số trong PR #30.

Symptom: `validate_cau_keo_domain.py` dừng với `domain gate schema mismatch`
sau khi mã nguồn chuyển từ schema 2 sang schema 3.

Root cause: model pack, gate và manifest được theo dõi vẫn là artifact schema 2.

Correct pattern: tái tạo đầy đủ artifact cho cả lô tô và đề bằng đúng builder schema
mới, rồi chạy validator và kiểm tra challenger bốn lát.

Avoid: tăng hằng số schema nhưng giữ artifact cũ, hoặc hạ yêu cầu của validator.

Regression guard: `validate_cau_keo_domain.py`, `domain_challenger_check.sh` và
kiểm tra schema trong `tests/test_cau_keo_domain_challenger.py`.

Affected modules: `cau_keo_feature_groups.py`, `cau_keo_domain_challenger.py`,
`data/ai_ml/cau_keo_domain_*`, `models/cau_keo_*.joblib`

Confidence: high

Last verified: 2026-09-03

## REP-0007 — Không che khuất module HTML trong builder

Context: Việt hóa JSON hiển thị trong `build_dashboard.py`.

Symptom: builder dừng với `NameError` khi closure gọi `html.escape`.

Root cause: biến cục bộ `html` chứa toàn bộ trang làm che khuất module `html`
đã import trong phạm vi hàm.

Correct pattern: dùng tên `dashboard_html` cho chuỗi trang và giữ `html` dành
cho module escape.

Avoid: tái sử dụng tên module import cho biến cục bộ trong cùng phạm vi có closure.

Regression guard: `tests/test_vietnamese_ui.py` thực thi builder và kiểm tra hai
trang đầu ra.

Affected modules: `build_dashboard.py`

Confidence: high

Last verified: 2026-09-03
