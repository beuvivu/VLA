# Verified repair memory

## REP-0001 — Pair champion and challenger randomness

Context: domain-feature walk-forward ablation.

Symptom: baseline and challenger fits used different random seeds in the same fold.

Root cause: seeds were derived from candidate identity rather than fold identity.

Correct pattern: one deterministic fold seed is reused for baseline and every challenger in that fold.

Avoid: treating independently randomized fits as if the feature set were the only experimental difference.

Regression guard: ablation output records the fold seed; paired comparison requires identical OOS labels/dates.

Affected modules: `cau_keo_domain_challenger.py`, `ml_validation.py`

Confidence: high

Last verified: 2026-09-02

## REP-0002 — Validate raw/normalized history alignment

Context: base ML positional feature construction.

Symptom: raw prize rows and two-digit target rows could be consumed by row index without an exact date-axis equality check.

Root cause: each input was sorted independently, then assumed aligned.

Correct pattern: reject duplicate dates and require identical ordered date axes before constructing any cross-source feature.

Avoid: relying on equal row counts or sort order as proof of temporal alignment.

Regression guard: mismatched and duplicated date-axis tests in `tests/test_ml_features.py`.

Affected modules: `ml_features.py`

Confidence: high

Last verified: 2026-09-02

## REP-0003 — Adjacent-pair strict zip requires equal slices

Context: recurrence interval extraction.

Symptom: pairing `indices` with `indices[1:]` under `zip(..., strict=True)` raised on every non-empty hit sequence.

Root cause: the left iterable was not sliced to the same length.

Correct pattern: pair `indices[:-1]` with `indices[1:]` when strict adjacency validation is desired.

Avoid: strict zip over intentionally unequal full/tail sequences.

Regression guard: three-draw-cycle synthetic ground-truth test.

Affected modules: `gap_cycle_stats.py`

Confidence: high

Last verified: 2026-09-02

## REP-0004 — Pattern diagnostics must survive result truncation

Context: positional-cầu multiple-hypothesis accounting.

Symptom: applying `max_results` also reduced `surviving_hypotheses`, hiding
how many rules passed the historical filter. A streak could also remain marked
active when the newest draw lacked an exact prior-calendar source draw.

Root cause: presentation truncation and active-streak display state were mixed
with scientific search diagnostics.

Correct pattern: record the full survivor count before limiting returned rows,
and require an active streak to reach the newest evaluable draw.

Avoid: letting display limits or missing trailing dates make a pattern search
look smaller or more current than it was.

Regression guard: truncation and trailing-calendar-gap tests in
`tests/test_dynamic_cau.py`.

Affected modules: `dynamic_cau.py`

Confidence: high

Last verified: 2026-09-02

## REP-0005 — Canonicalize external candidate-score components

Context: configurable candidate ranking.

Symptom: a string key such as `"07"` passed validation but was never found by
integer candidate lookup, and unrestricted external scales could dominate the
weighted score.

Root cause: validation converted values transiently without storing the
canonical representation or enforcing the documented normalized scale.

Correct pattern: canonicalize number keys to integers, values to floats, reject
canonical duplicates, and require optional component scores in `[0,1]`.

Avoid: validating one representation and storing another.

Regression guard: optional-score canonicalization and scale tests in
`tests/test_candidate_scoring.py`.

Affected modules: `candidate_scoring.py`

Confidence: high

Last verified: 2026-09-02
