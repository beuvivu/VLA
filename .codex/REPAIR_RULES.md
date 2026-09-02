# Codex Repair Rules

These rules store repository-specific engineering constraints. They do not modify any model weights.

1. Reproduce a defect before changing production logic whenever a deterministic reproduction is available.
2. Fix root cause; do not suppress failing validation or weaken a scientific gate to obtain a positive result.
3. For temporal prediction, every feature for target date D must be computable before the draw on D.
4. Keep all 100 candidate rows from one draw/date in the same temporal partition.
5. Baseline/challenger ablations must reuse identical train/calibration/test dates, downsampled row IDs, hyperparameters and random states.
6. Evaluate the probability representation that production actually serves. Đề is categorical over 00..99; Loto uses Bernoulli marginals.
7. Uncertainty for candidate-row models is bootstrapped at DATE/DRAW cluster level, never independent row level.
8. Experimental features require an explicit production allowlist. Extra dataframe columns are research-only unless explicitly promoted.
9. No selection/tuning is allowed after viewing an untouched final holdout. Post-holdout diagnostics cannot feed the same promotion decision.
10. Invalid/unknown/NaN scientific evidence fails closed to the established baseline.
11. Public lottery websites are terminology/statistics research sources, not predictive proof. Do not copy private/proprietary implementations.
12. Prefer existing canonical domain/statistics modules over duplicate definitions.
13. Record every meaningful accepted/rejected ML tuning attempt in `TUNING_HISTORY.md`.
14. After a bug fix: add a regression test, run targeted checks, then full CI-equivalent checks.
15. No more than three materially distinct repair hypotheses for one root failure without escalation.
