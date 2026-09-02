# Known Failures and Risks

## KF-0001 — PR #27 point-estimate domain gate was not promotion-safe

Status: repaired on `codex/ml-challenger-validation`, pending CI/PR review.

Verified defects in the merged v1 gate:
- baseline/challenger used different random/downsample seeds;
- no bootstrap confidence interval existed;
- Đề was gated on raw Bernoulli probabilities rather than served categorical distribution;
- `partner` and `cap_50` were conflated as one family.

Production at the audit point remained protected because both v1 challengers were
inactive, but a future noisy positive point estimate could have promoted an invalid
comparison.

Regression guards: `tests/test_ml_validation.py`,
`tests/test_cau_keo_domain_challenger.py`,
`tests/test_cau_keo_future_mutation.py`.

Last verified: 2026-09-02

## KF-0002 — Repeated experiment selection can overfit the evaluator

Status: open statistical risk, non-blocking for the safety repair.

The same feature families may be re-evaluated as daily history advances. Fold-4
therefore ceases to be philosophically "untouched" if developers repeatedly tune
algorithms against its prior outcomes.

Mitigation: use final holdout only for preregistered candidate definitions; add a
future shadow period or nested/rolling selection before claiming durable signal.
Do not weaken CI gates to force promotion.

Last verified: 2026-09-02
