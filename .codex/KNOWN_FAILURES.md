# Known Failures

## KF-0001 — Domain challenger scientific gate before schema v2

Status: repaired on branch `codex/scientific-gate-research`; pending CI/PR review.

Verified failure modes:
- baseline/challenger used different training randomness;
- no clustered bootstrap confidence interval existed;
- Đề was scored in raw Bernoulli space instead of served categorical space;
- `partner` and `cap_50` were conflated into one promotion unit.

Production observation at discovery:
Both persisted domain challengers were inactive (`domain_trust=0`), so the then-current production probabilities were baseline-equivalent despite the unsafe future promotion mechanism.

Required guards:
- identical per-fold training row fingerprint and seed;
- date-cluster paired bootstrap;
- categorical Đề evaluation;
- six independent feature families;
- explicit production allowlist.

Last verified: 2026-09-02

## KF-0002 — Local audit runner cannot resolve github.com

Status: environmental / unresolved outside repository code.

Symptom:
`git clone --depth=1 --branch main https://github.com/beuvivu/VLA.git ...` fails with `Could not resolve host: github.com` in the local analysis container.

Impact:
Do not claim local test execution from that environment. Use actual GitHub Actions execution evidence for full CI and report the limitation explicitly.

Last verified: 2026-09-02
