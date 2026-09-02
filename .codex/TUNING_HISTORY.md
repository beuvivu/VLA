# Tuning History

## TUNE-0001 — Domain challenger scientific-gate hardening

Hypothesis:
Traditional partner/cặp-50/bộ/bóng/chạm/tổng features should affect production only when their improvement is robust to strict temporal evaluation and draw-level uncertainty.

Change:
Split `partner` and `cap_50`; control per-fold training rows/random state; evaluate Đề in categorical serving space; add paired date-cluster bootstrap CIs; freeze blend trust before final holdout; test the actual production blend on fold 4.

Baseline:
Existing `cau_keo_ml` HistGradientBoosting + Platt champion using `FEATURE_COLS`.

Evaluation period:
Pending branch CI execution against repository canonical history.

Walk-forward configuration:
Folds 1-2 screen; fold 3 confirms and fixes trust; fold 4 untouched final production-blend test. Calibration is temporally between training and OOS test.

Metrics before:
The previous point-estimate gate produced no active challenger on the latest persisted run, but lacked valid confidence intervals and controlled ablation randomness.

Metrics after:
Pending actual CI experiment.

Confidence interval:
Pending actual CI experiment; configured paired DATE-cluster percentile CI.

Result:
inconclusive

Production impact:
none until a challenger passes all gates; inactive state preserves baseline.

Reason:
Code has been changed but experiment results must not be recorded before actual execution.

Last updated:
2026-09-02
