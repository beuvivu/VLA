# Incident 2026-09-02 — Domain challenger scientific-gate audit

Status: remediation in progress on `codex/scientific-gate-research`.

## Observe

The merged domain challenger had green regression/CI checks and current `domain_trust=0`, but independent audit found that future promotions were not scientifically protected.

## Reproduce

Direct source inspection established:
- candidate-specific seeds changed `_downsample` and HGB realization;
- no bootstrap confidence interval existed;
- Đề gate scored raw Bernoulli outputs while production served a normalized categorical distribution;
- `partner` and `cap_50` were one combined selection unit.

## Classification

P1 / production-promotion safety. Current prediction output was baseline-equivalent because no group was active, but the future automatic gate could accept noise or the wrong evaluation object.

## Root cause

The initial implementation emphasized chronological folds and point-estimate rollback but did not fully control experiment randomness, probability-serving semantics or uncertainty.

## Minimal repair

- shared fold seed and exact fit-row fingerprint;
- six independent feature groups;
- paired draw-cluster bootstrap;
- categorical Đề metrics;
- trust fixed on pre-final evidence;
- final untouched test of the actual production blend;
- explicit feature allowlist and validation.

## Regression guards

See:
- `tests/test_ml_validation.py`
- `tests/test_cau_keo_domain_challenger.py`
- `tests/test_cau_keo_future_mutation.py`
- `scripts/domain_challenger_check.sh`

## Remaining verification

Run repository CI on the branch/PR and record actual experiment outcomes before marking remediation complete.
