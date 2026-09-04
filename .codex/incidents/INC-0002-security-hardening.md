# INC-0002 — Boundary validation and production security hardening

Observed: 2026-09-03

Classification: P0/P1 input integrity, browser injection and production-model
firewall

Reproduction: repository-wide review found permissive numeric coercion at public
source boundaries, untrusted dashboard strings reaching `innerHTML`, fixed
workflow temporary paths, over-broad job permissions, and model/configuration
paths that did not reject every non-finite or schema-invalid state.

Root cause: independent ingestion, HTML, workflow and ML paths had accumulated
local validation rules instead of sharing strict trust-boundary invariants.

Repair: introduce canonical HTML-script escaping and security metadata; replace
dynamic HTML sinks with DOM text nodes; require exact ASCII/integer/date schemas;
remove anti-bot tooling; randomize runner temporary paths; narrow workflow
permissions; validate model allowlists, shapes, probabilities, calibration,
weights and configuration; keep rejected challengers behind the baseline gate.

Regression guards: `tests/test_security_hardening.py`,
`tests/test_validate_data_strict.py`, `tests/test_sources.py`,
`tests/test_ml_validation.py`, `tests/test_meta_predictor.py`,
`tests/test_ensemble_utils_security.py`, `tests/test_configuration_validation.py`
and `tests/test_workflows.py`.

Verification: `277 passed`; Ruff CI and additional Bandit-oriented checks on
`src` passed; compileall and pip dependency checks passed; number-integrity,
domain-challenger, research-release and full release checks passed. Production
audit returned `ok: true` with no critical findings or warnings.

Status: repaired. No experimental feature was promoted and the production
baseline/feature allowlist remains authoritative.
