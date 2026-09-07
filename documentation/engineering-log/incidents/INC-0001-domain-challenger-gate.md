# INC-0001 — Domain challenger promotion gate was not paired

Observed: 2026-09-02

Classification: P0 production experiment validity

Reproduction: inspect fold seeds and final gate in `cau_keo_domain_challenger.py`; baseline and candidates used different seeds, and promotion used positive point estimates without uncertainty.

Root cause: the initial ablation implementation treated random seed as candidate-specific and had no reusable clustered-bootstrap gate.

Repair: use one seed per fold, retain paired OOS predictions/dates, bootstrap complete dates, require positive lower confidence bounds for both losses, enforce minimum OOS dates, and persist explicit rejection reasons/feature manifest.

Regression guards: `tests/test_ml_validation.py`, `tests/test_cau_keo_domain_challenger.py`, and artifact validation.

Status: repaired. The 2026-09-02 real-data experiment rejected every domain
challenger before the untouched final fold, so the established baseline remains
the production model. Final CI evidence is recorded in the pull request.
