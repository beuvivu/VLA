# Known failures and open risks

Last verified: 2026-09-03

## KF-0001 — Historical pattern selection bias

Large positional searches can surface impressive streaks by chance. The new
engine records the number of hypotheses and `PATTERN_SELECTION_BIAS_RISK`, but
its rules have not completed untouched-future validation. Status: research only.

## KF-0002 — Pascal candidate extraction underspecified

Public pages expose an adjacent-sum modulo-10 recurrence but not a stable,
independently reproducible seed and candidate-selection rule. No code was added.

## KF-0003 — Fibonacci lottery mapping unavailable

No sufficiently precise public history-to-candidate mapping was found. Creating
one would fabricate a researched method. No code was added.

## KF-0004 — Graph features unevaluated

Canonical co-occurrence and transition matrices now exist, but graph centrality
features remain unimplemented and unvalidated. They must remain research-only
if later introduced.

## KF-0005 — Joblib artifacts require a trusted provenance

`joblib.load` is pickle-based and can execute code before post-load schema checks
run. Production artifacts must therefore originate from reviewed repository
workflows; hostile or user-supplied model files remain unsupported.

## KF-0006 — Static-page CSP still permits inline code

Generated pages are self-contained and currently require `'unsafe-inline'` for
scripts and styles. Context-safe JSON escaping and the ban on dynamic HTML sinks
remain mandatory until assets are split and a nonce/hash policy is practical.

## KF-0007 — GitHub Actions are version-pinned, not SHA-pinned

Actions use reviewed major-version tags and Dependabot, but tags are mutable.
Immutable commit-SHA pinning remains a supply-chain hardening follow-up.
