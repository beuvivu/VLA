# Repair Memory

## REP-0001 — Controlled feature ablations require identical randomness

Context:
`cau_keo_domain_challenger` compares baseline features with experimental domain groups.

Symptom:
Baseline and challenger previously used different seeds, changing both negative-class downsampling and HistGradientBoosting randomness.

Root cause:
Candidate-specific seeds were treated as harmless reproducibility settings even though they changed the training sample/model realization being compared.

Correct pattern:
Within one temporal fold, baseline and challenger must share identical fit-row IDs and the same model random state. Only feature columns may differ.

Avoid:
Attributing a small loss delta to a feature group when sampling/model randomness also changed.

Regression guard:
`tests/test_cau_keo_domain_challenger.py::test_controlled_downsampling_is_deterministic_for_same_fold_seed` plus runtime fit-row fingerprint checks.

Affected modules:
`src/cau_keo_domain_challenger.py`

Confidence:
high

Last verified:
2026-09-02

## REP-0002 — Đề validation must match categorical production probabilities

Context:
Đề has exactly one two-digit special-prize outcome per draw.

Symptom:
The domain challenger previously evaluated 100 raw independent Bernoulli outputs while production normalizes the 100-number vector to a categorical distribution.

Root cause:
Training-model output semantics were confused with serving-probability semantics.

Correct pattern:
Normalize each Đề date exactly as production does, then score categorical LogLoss and multiclass Brier against the one-hot target.

Avoid:
Promoting a challenger because raw Bernoulli losses improve when the normalized production distribution is unchanged or worse.

Regression guard:
`tests/test_ml_validation.py::test_de_evaluation_matches_normalized_production_distribution`.

Affected modules:
`src/ml_validation.py`, `src/cau_keo_domain_challenger.py`, `src/validate_cau_keo_domain.py`

Confidence:
high

Last verified:
2026-09-02

## REP-0003 — Candidate-row uncertainty must be clustered by draw date

Context:
Each draw generates 100 correlated candidate-number rows.

Symptom:
The earlier domain gate used only point estimates and had no uncertainty interval.

Root cause:
Promotion logic treated a tiny OOS point improvement as sufficient evidence.

Correct pattern:
Use deterministic paired DATE-cluster bootstrap; sample dates with replacement and retain each date's complete candidate cluster/multiplicity.

Avoid:
Independent row bootstrap or CI-free promotion.

Regression guard:
`tests/test_ml_validation.py` clustered-bootstrap tests and persisted gate metadata `cluster_unit=date`.

Affected modules:
`src/ml_validation.py`, `src/cau_keo_domain_challenger.py`

Confidence:
high

Last verified:
2026-09-02

## REP-0004 — Final holdout cannot be reused to tune blend trust

Context:
A challenger can be blended conservatively with the production champion.

Symptom:
Deriving trust from final-holdout skill and then evaluating that same final period would tune the served blend on the evidence used to prove it.

Root cause:
Model selection and final evaluation boundaries were not fully separated conceptually.

Correct pattern:
Determine group selection and proposed trust on pre-final folds. Freeze them. Evaluate the actual fixed-trust production blend once on the untouched final fold.

Avoid:
Dropping groups, changing trust, or selecting weights after viewing final-fold results.

Regression guard:
Persisted gate documents fold roles and labels leave-one-group-out diagnostics as `selection_use=false`.

Affected modules:
`src/cau_keo_domain_challenger.py`

Confidence:
high

Last verified:
2026-09-02
