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
