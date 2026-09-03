# Statistical and ML tuning history

No result is accepted until the exact executed experiment and metrics are recorded.

## TUNE-0001 — Loto domain feature-family ablation

Hypothesis: canonical `partner_cap50`, `bo`, `bong`, `cham`, or `tong`
features improve the established Loto probability model.

Change: add one family at a time to the unchanged 39-feature baseline, using
the same model configuration and deterministic seed as the baseline in each
fold.

Baseline: existing calibrated HistGradientBoosting cầu-kèo model.

Evaluation period: screening targets 2026-05-05 through 2026-07-03;
confirmation targets 2026-07-04 through 2026-08-02.

Walk-forward configuration: two 30-date screening folds, one later 30-date
confirmation fold, 3,000 candidate rows per fold, 30-day calibration windows,
minimum 90 training dates, fold seeds 20260921--20260923. Fold 4 was left
untouched because no feature family survived confirmation.

Metrics before: on the confirmation fold, baseline Brier
`0.17978977348391928`; baseline LogLoss `0.5452884628088981`.

Metrics after: `partner_cap50` was the only screening survivor (mean screening
Brier skill `0.0003206176421596`, LogLoss skill `0.0002979147155654`). On
confirmation its Brier was `0.17980858415189657` (improvement
`-0.000018810667977292583`, skill `-0.00010462590620581122`) and LogLoss was
`0.5453288150708151` (improvement `-0.00004035226191700936`, skill
`-0.0000740016792380792`). The all-family confirmation diagnostic also
degraded: Brier skill `-0.0004418862358147222`, LogLoss skill
`-0.0003934576989665303`.

Confidence interval: not computed; the candidate failed before the untouched
final paired-bootstrap gate.

Result: rejected

Production impact: none

Reason: `unstable_across_folds`, `negative_brier_skill`, and
`negative_logloss_skill` on confirmation.

## TUNE-0003 — Tách `partner` và `cap_50` cho lô tô

Hypothesis: đánh giá riêng hai quan hệ tránh che lấp tín hiệu và giúp một trong
sáu nhóm `partner`, `cap_50`, `bo`, `bong`, `cham`, `tong` cải thiện baseline.

Change: tách nhóm gộp cũ thành sáu nhóm có danh sách cột/provenance riêng; giữ
nguyên mô hình, lịch, nhãn và seed theo từng lát.

Baseline: HistGradientBoosting cầu-kèo đã hiệu chỉnh, 39 đặc trưng production.

Evaluation period: sàng lọc 2026-05-05 đến trước 2026-07-04; chẩn đoán xác nhận
2026-07-04 đến trước 2026-08-03.

Walk-forward configuration: hai lát sàng lọc 30 ngày, 3.000 dòng/lát; một lát
xác nhận 30 ngày; seed 20260921--20260923; fold 4 chưa bị tiêu thụ.

Metrics before: Brier sàng lọc trung bình `0.18161378605038656`; LogLoss
`0.5493306699013754`.

Metrics after: không nhóm nào vượt cả hai ngưỡng. Skill Brier/LogLoss trung bình:
`partner -0.000001912/-0.000006188`; `cap_50 -0.000009248/+0.000007546`;
`bo -0.000162134/-0.000177645`; `bong -0.000052860/-0.000049849`;
`cham -0.000566116/-0.000500757`; `tong -0.000152701/-0.000144174`.
Chẩn đoán toàn nhóm ở fold 3 cũng giảm: Brier skill `-0.000441886`, LogLoss
skill `-0.000393458`.

Confidence interval: không tính; ứng viên thất bại trước cổng holdout cuối.

Result: rejected

Production impact: none

Reason: `negative_brier_skill`, `negative_logloss_skill`, hoặc
`insufficient_support`; không nhóm nào sống sót qua sàng lọc.

## TUNE-0004 — Tách `partner` và `cap_50` cho đề

Hypothesis: hai nhóm được tách có thể duy trì cải thiện xác suất đề trên lát xác
nhận muộn hơn.

Change: cùng schema sáu nhóm, cùng baseline/hyperparameter/seed với champion.

Baseline: HistGradientBoosting cầu-kèo đã hiệu chỉnh, 39 đặc trưng production.

Evaluation period: sàng lọc 2026-05-05 đến trước 2026-07-04; xác nhận 2026-07-04
đến trước 2026-08-03.

Walk-forward configuration: hai lát sàng lọc 30 ngày và một lát xác nhận 30
ngày, 3.000 dòng/lát; seed 20260921--20260923; fold 4 chưa bị tiêu thụ.

Metrics before: ở fold xác nhận, Brier `0.0098952628807682`; LogLoss
`0.055759349297486`.

Metrics after: `partner` qua sàng lọc nhưng xác nhận giảm (Brier
`0.0099012469493265`, skill `-0.000604741`; LogLoss `0.0560731084553794`,
skill `-0.005627023`). `cap_50` cũng giảm khi xác nhận (Brier
`0.0098973991649627`, skill `-0.000215890`; LogLoss `0.05587255522254`,
skill `-0.002030259`). Chẩn đoán toàn nhóm: Brier skill `-0.000626864`, LogLoss
skill `-0.005682528`.

Confidence interval: không tính; cả hai ứng viên thất bại trước cổng holdout cuối.

Result: rejected

Production impact: none

Reason: `unstable_across_folds`, `negative_brier_skill`,
`negative_logloss_skill`.

## TUNE-0002 — Đề domain feature-family ablation

Hypothesis: canonical `partner_cap50`, `bo`, `bong`, `cham`, or `tong`
features improve the established đề probability model.

Change: add one family at a time to the unchanged 39-feature baseline, using
the same model configuration and deterministic seed as the baseline in each
fold.

Baseline: existing calibrated HistGradientBoosting cầu-kèo model.

Evaluation period: screening targets 2026-05-05 through 2026-07-03;
confirmation targets 2026-07-04 through 2026-08-02.

Walk-forward configuration: two 30-date screening folds, one later 30-date
confirmation fold, 3,000 candidate rows per fold, 30-day calibration windows,
minimum 90 training dates, fold seeds 20260921--20260923. Fold 4 was left
untouched because no feature family survived confirmation.

Metrics before: on the confirmation fold, baseline Brier
`0.009895262880768219`; baseline LogLoss `0.05575934929748601`.

Metrics after: `partner_cap50` was the only screening survivor (mean screening
Brier skill `0.0001768701575816525`, LogLoss skill `0.0013974827634871498`).
On confirmation its Brier was `0.009900142656321904` (improvement
`-0.000004879775553684809`, skill `-0.0004931425887804173`) and LogLoss was
`0.05600624436857474` (improvement `-0.0002468950710887291`, skill
`-0.004427868585257338`). The all-family confirmation diagnostic also
degraded: Brier skill `-0.0006268639278702464`, LogLoss skill
`-0.005682528122628515`.

Confidence interval: not computed; the candidate failed before the untouched
final paired-bootstrap gate.

Result: rejected

Production impact: none

Reason: `unstable_across_folds`, `negative_brier_skill`, and
`negative_logloss_skill` on confirmation.
