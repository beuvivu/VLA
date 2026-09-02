# INC-0001 — Domain challenger scientific gate defects

Date: 2026-09-02

Severity: P1 (promotion mechanism), with current production impact contained by inactive challenger.

## Observe

Merged PR #27 added feature-family ablation and production gating.

## Reproduce / evidence

Direct source audit showed:

1. baseline and challenger called `_fit_fold` with different seeds;
2. those seeds controlled both negative downsampling and HGB randomness;
3. no bootstrap implementation existed;
4. Đề gate scored raw binary candidate probabilities while production normalized
   each 100-number vector;
5. `partner` and `cap_50` were one `partner_cap50` group.

## Classification

P1 / block future automated promotion.

## Root cause

The first implementation treated chronological splitting as sufficient scientific
control, but did not isolate stochastic variation, sampling uncertainty or the
serve-time probability contract.

## Patch

Branch `codex/ml-challenger-validation`:

- immutable same-seed/same-sample fold plans;
- separate partner and cặp-50 families;
- categorical Đề metrics matching serving;
- deterministic paired date-cluster bootstrap;
- CI-lower-bound confirmation/final gates;
- fixed production trust evaluated as the exact final blend;
- explicit serialized feature allowlist;
- fail-closed validator and adversarial tests.

## Regression guards

- `tests/test_ml_validation.py`
- `tests/test_cau_keo_domain_challenger.py`
- `tests/test_cau_keo_future_mutation.py`

## Remaining uncertainty

Real-data branch execution is required before reporting any v2 challenger gain.
Repeated future tuning against the same holdout remains a selection-bias risk and
should use a later shadow/preregistered period.
