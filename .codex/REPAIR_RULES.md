# Repair Rules

1. Reproduce before patching; do not suppress failures.
2. Temporal forecasting bugs outrank convenience/performance issues.
3. For target D, every feature must be derivable from information available before D.
4. Keep one lottery date/draw intact across train/calibration/test and bootstrap.
5. Baseline/challenger comparisons must use identical rows, labels, seeds,
   hyperparameters, sampling plans and calibration protocol.
6. Brier and LogLoss are losses: lower is better; positive skill means
   `(baseline_loss - challenger_loss) / baseline_loss > 0`.
7. Unknown/NaN/insufficient-history/bootstrap failure fails closed.
8. Evaluate the same probability object that production serves.
9. Research/descriptive columns may exist in a frame but cannot enter production
   without an explicit promoted feature manifest.
10. Every material fix gets a regression test and a concise memory entry.
11. After three distinct evidence-based failed repair hypotheses for one root
    failure, stop and report `REPAIR ESCALATION REQUIRED`.
12. Remove failed speculative patches before trying a materially different design.
13. Do not add a new domain definition when `number_reference.py` already owns it.
14. Do not present arbitrary ranking scores as calibrated probabilities.
15. Historical pattern discovery is not predictive evidence; promotion requires
    temporal OOS performance and uncertainty evidence.

Last verified: 2026-09-02
