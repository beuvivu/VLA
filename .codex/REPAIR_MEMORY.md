# Repair Memory

Verified engineering lessons only. Do not record speculative fixes as facts.

## REP-0001 — Controlled feature ablation requires identical stochastic plans

Context: `cau_keo_domain_challenger.py` baseline-vs-feature-family ablation.

Symptom: baseline and challenger used different seeds, so negative downsampling
and HistGradientBoosting randomness differed.

Root cause: seed was derived from candidate/group rather than fold.

Correct pattern: construct one immutable fold plan containing temporal masks,
downsample indices and model seed; reuse it for baseline and every challenger.

Avoid: interpreting a loss difference as feature skill when sampling/model
randomness also changed.

Regression guard: `test_fold_plan_reuses_one_training_sample_for_all_challengers`.

Affected modules: `src/cau_keo_domain_challenger.py`.

Confidence: high

Last verified: 2026-09-02

## REP-0002 — Evaluate Đề in the same categorical probability space as serving

Context: exactly one Đề number is correct among 00..99.

Symptom: a raw Bernoulli vector could appear better/worse even when a scalar
rescaling produced the identical normalized production distribution.

Root cause: challenger gate scored raw per-row Bernoulli probabilities while
serving normalized the 100 values to sum to one.

Correct pattern: normalize each complete 100-number draw and use categorical
LogLoss plus multiclass Brier for both evaluation and bootstrap.

Avoid: selecting a Đề challenger on raw marginal scale when production consumes a
categorical distribution.

Regression guard: `test_de_scoring_matches_production_normalization`.

Affected modules: `src/ml_validation.py`, `src/cau_keo_domain_challenger.py`.

Confidence: high

Last verified: 2026-09-02

## REP-0003 — Bootstrap lottery forecasts at draw/date cluster level

Context: every OOS date contains 100 correlated candidate rows.

Symptom: row bootstrap would artificially treat candidates from one lottery draw
as independent evidence.

Root cause: wrong resampling unit.

Correct pattern: compute paired per-date losses, sample dates with replacement,
preserve repeated-date multiplicity and use the same sampled indices for baseline
and challenger.

Avoid: independently resampling candidate rows.

Regression guard: deterministic/paired cluster-bootstrap tests in
`tests/test_ml_validation.py`.

Affected modules: `src/ml_validation.py`.

Confidence: high

Last verified: 2026-09-02

## REP-0004 — Production features require an explicit serialized allowlist

Context: experimental domain columns can coexist with production DataFrames.

Symptom: implicit column selection could let rejected research features influence
a model after schema changes.

Root cause: production/research feature separation was encoded mainly by code path,
not a complete persisted manifest.

Correct pattern: persist baseline features, group mapping, promoted groups and
ordered production features; inference selects only that list.

Avoid: `all_dataframe_columns`, dtype-based feature discovery or silent fallback to
unknown columns.

Regression guard: rejected-feature extreme-value invariance test and artifact
validator.

Affected modules: `src/cau_keo_domain_challenger.py`,
`src/validate_cau_keo_domain.py`.

Confidence: high

Last verified: 2026-09-02
