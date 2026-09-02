# Known failures and open risks

Last verified: 2026-09-02

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
