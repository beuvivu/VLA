# Repair rules

Last verified: 2026-09-02

1. Reproduce a defect with a focused test before or with the patch.
2. Treat any feature change after future-result mutation as P0 temporal leakage.
3. Require raw and derived histories to share the same unique ordered date axis.
4. Keep all candidate rows from one draw in one temporal partition and one bootstrap cluster.
5. Compare champion and challenger on identical rows, labels, dates, hyperparameters and seeds.
6. Interpret Brier and LogLoss as losses; positive improvement is baseline minus challenger.
7. Promotion fails closed on non-finite state, insufficient OOS dates, non-positive skill, or an improvement CI crossing zero.
8. Pass production model inputs through an explicit feature allowlist.
9. Keep failed/rejected experiments out of production and record the reason.
10. Preserve deterministic domain definitions in `number_reference.py` rather than copying them into feature code.
