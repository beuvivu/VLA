# Legacy forensic audit matrix — PR #24

Date: 2026-09-02  
Repository: `beuvivu/VLA`  
Branch: `audit/legacy-feature-completeness`  
Legacy repositories under revalidation:

- `beuvivu/Vietnam-Lottery-Analysis`
- `beuvivu/xsmb-analysis`
- `beuvivu/xoso`

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `HARDENED` | Capability already existed in VLA but a semantic, chronology, validation, availability, or runtime contract was strengthened. |
| `MIGRATED` | A legacy capability not semantically equivalent in VLA was reimplemented in the consolidated codebase. |
| `SUPERSEDED` | A duplicate/older entrypoint remains only as a compatibility wrapper around the canonical implementation. |
| `RESEARCH-ONLY` | Capability exists for falsification/descriptive analysis and is not allowed to alter production prediction weights automatically. |
| `EXCLUDED` | Deliberately not retained because it is deployment-specific, duplicate generated state, or inferior to the canonical VLA implementation. |
| `VERIFIED` | The capability and its release/research gates passed on the recorded final-head verification run; any later code change requires a new final-head run. |

## Critical findings reopened after the 2026-09-01 retirement approval

The earlier retirement acceptance was re-opened because file-name/feature-level comparison was not sufficient to prove semantic equivalence. The second pass found concrete silent-failure risks:

1. missing ensemble component artifacts could be converted into legitimate all-zero probability vectors;
2. historical all-zero placeholders could be treated as fully available component predictions by ensemble learners;
3. structurally valid but stale prediction artifacts could be reused for the wrong target date;
4. several modules labeled row offsets as calendar days without enforcing daily continuity;
5. pipeline data validation ran after some analytics, allowing row-based artifacts to be produced before a gap was detected;
6. probability evaluation could reconstruct a historical prediction using a blend that had never actually been emitted;
7. three legacy next-day conditional matrices used row adjacency instead of exact `+1 calendar day` transitions;
8. the legacy statistics AI overlay could display yesterday's ML artifact as today's signal;
9. duplicate legacy CLIs/builders (`vip_stats.py`, `run_path.py`, `build_markdown_dashboard.py`) maintained independent logic or ambiguous artifacts;
10. release and production audits did not explicitly gate the new calendar/target-date contracts.

These findings are closed in code and were verified by GitHub CI run 120 on commit `5cab5fa3eff78d9fbd4975163cb9c521f65c55a7`: 148/148 regression tests passed, the core release gate passed, and the research-plane release gate passed. This documentation-only status commit must itself pass the same CI before merge.

## Capability audit matrix

| Capability / risk surface | Canonical implementation | Resolution | Verification evidence | Status |
| --- | --- | --- | --- | --- |
| Canonical result domain validation | `src/dtos.py`, `src/sources.py`, `src/validate_data.py` | Strict prize widths/ranges, source-boundary validation, sparse 27-position integrity | `test_result_domain_validation.py`, `test_source_boundary_validation.py`, `test_validate_data_strict.py` | HARDENED |
| Multi-source canonical consensus | `src/lottery.py`, `src/sources.py` | Independent-provider grouping; equal-support distinct-result ties cannot be promoted | existing consensus/source-policy regression suite | HARDENED |
| Calendar semantics primitive | `src/calendar_alignment.py` | Centralized normalized dates, exact lag pairs, exact next-day pairs, duplicate/gap detection, fail-fast contiguous contract | `test_calendar_alignment.py`, `test_calendar_gap_statistics.py` | MIGRATED |
| Pipeline chronology gate | `src/pipeline.py` | Canonical validation is a hard precondition immediately after sync and before statistics/path/ML/research | `test_pipeline_integrity_order.py` | HARDENED |
| Head-table day windows | `src/descriptive_extensions.py` | `N days` now means inclusive calendar window, not last `N` rows | `test_descriptive_calendar_windows.py` | HARDENED |
| Number recency / pair recency / gap evidence | `src/descriptive_extensions.py`, `src/research_legacy_extensions.py` | Calendar-day recency separated from draw-index interval metrics; descriptive only | calendar-gap + legacy-extension regression tests | MIGRATED / RESEARCH-ONLY |
| VIP statistics CLI | `src/vip_stats.py` -> `src/descriptive_extensions.py` | Removed duplicate statistical implementation; legacy filenames/CLI preserved through canonical functions | compile/unit suite + canonical descriptive tests | SUPERSEDED |
| Exact next-day conditional matrices | `src/conditional_matrices.py` | `ĐB→Loto`, `ĐB→ĐB`, `Loto→Loto` count only exact `+1 calendar day`; canonical outputs overwrite legacy row-adjacent outputs | `test_conditional_matrices.py`; release diagnostics gate | MIGRATED / HARDENED |
| Bayesian conditional next-day research | `src/conditional_nextday.py` | Calendar-safe chronology, shrinkage, no-lookahead research evidence | `test_conditional_nextday.py` | HARDENED / RESEARCH-ONLY |
| Markov-1 Loto | `src/markov_stats.py` | Exact next-calendar-day transitions rather than arbitrary adjacent rows | calendar-alignment regression coverage | HARDENED |
| Higher-order Markov / hazard / lag / regime dynamics | `src/number_dynamics.py` | Public builder requires full daily-contiguous date axis before Markov-2, hazard and 1/2/3/7/14/28-day kernels execute | `test_number_dynamics.py`; release dynamics integrity gate | HARDENED |
| Production statistical signal | `src/statistical_signal.py` | Two-digit and sparse calendars must both be contiguous and identical; dynamics receives actual dates | release smoke + number-dynamics tests | HARDENED |
| Cycle / hazard descriptive statistics | `src/cycle_stats.py`, `src/hazard_stats.py` | Calendar-day gap definitions and explicit boundary-censoring semantics | calendar-gap statistics tests | HARDENED |
| Positional path engine | `src/run_path_ui.py`, path model/probability core | Runtime verifies raw/two-digit daily continuity and date-axis equality before lag-day interpretation | strict pipeline + release checks | HARDENED |
| Legacy path CLI | `src/run_path.py` -> `src/run_path_ui.py` | Duplicate engine removed; old command delegates to date-scoped canonical runner | compile/unit suite | SUPERSEDED |
| Path walk-forward evaluation | `src/path_backtest.py`, `src/path_timeline_evidence.py` | Exact next-calendar-day scoring and no-lookahead timeline evidence | `test_path_timeline_evidence.py` + calendar regression coverage | HARDENED |
| Base ML | `src/ml_features.py`, `src/ml_train.py`, `src/ml_predict.py` | Existing leakage-safe chronology retained; schema/date-aware retraining and natural-prevalence calibration retained | fresh train/predict smoke in `release_check.sh` | HARDENED / RETAINED |
| Cầu-kèo ML | `src/cau_keo_ml.py` | Raw and two-digit histories must be daily-contiguous and date-aligned before rolling/gap/t-1/t+1/path features; model feature schema/hyperparameters unchanged | `test_cau_keo_calendar.py`, `test_cau_keo_ml.py`, production-path release smoke | HARDENED |
| Component artifact availability | `src/ensemble_components.py` | Exactly 100 unique `00..99` probabilities, finite/range/nonzero checks, strict availability flags, target/anchor date validation | `test_ensemble_component_availability.py` | HARDENED |
| Prediction history storage | `src/record_pred_history.py` | Missing components stored as `NaN + has_*=false`; legacy all-zero placeholders sanitized on write | ensemble availability tests | HARDENED |
| Ensemble weight learner | `src/learn_ensemble_weights.py` | Rejects unavailable/partial/legacy-zero component days instead of optimizing on fabricated predictions | ensemble availability tests | HARDENED |
| Production linear/meta blend | `src/predict_nextday_2d.py`, `src/meta_predictor.py` | Weights renormalize over valid components; calibration/meta challenger bypassed if full expected component contract is unavailable | ensemble tests + stacked-ML release smoke | HARDENED |
| Historical probability evaluation | `src/prob_eval_history.py` | Only evaluates exact emitted prediction artifact for that target date; removed synthetic 40/30/30 reconstruction fallback | `test_prob_eval_history.py` | HARDENED |
| Legacy statistics AI overlay | `src/statistics_ai_overlay.py` | Only accepts date-verifiable current target ML; stale/undated artifacts rejected; absent ML triggers renormalized descriptive-only score with explicit `ml_available=false` | `test_statistics_ai_overlay.py`; release + production audit gates | MIGRATED / HARDENED |
| Statistical matrices legacy builder | `src/statistical_matrices.py` | Retained for broad descriptive matrices; unsafe conditional/ML-overlay artifact families are always overwritten by canonical post-processors in pipeline | pipeline order + release canonical gates | HARDENED BY CANONICALIZATION |
| Randomness / dependence diagnostics | `src/legacy_advanced_diagnostics.py`, `src/research_diagnostics.py` | KS/Ljung-Box/ACF/FDR and dependence diagnostics preserved as descriptive/research evidence | `test_legacy_advanced_diagnostics.py`, research release check | MIGRATED / RESEARCH-ONLY |
| Research firewall | `src/research_firewall.py` | Full calendar continuity required before chronological split, FDR and circular-shift reality check | research release check | HARDENED / RESEARCH-ONLY |
| Standard strategy laboratory | `src/strategy_lab.py` | Two-digit/sparse axes must be daily-contiguous and identical before row-based warmup/holdout; strategies remain non-production | `test_strategy_lab_calendar.py`, research release check | HARDENED / RESEARCH-ONLY |
| Cross-lag positional laboratory | `src/crosslag_positional_lab.py` | Legacy positional hypothesis family consolidated with chronology, holdout and multiple-testing controls | `test_crosslag_positional_lab.py`, research release check | MIGRATED / RESEARCH-ONLY |
| Research Lab UI | `src/build_research_lab.py` | Source-backed research outputs rendered without automatic production promotion | research release check | MIGRATED / RESEARCH-ONLY |
| Markdown dashboard | `src/build_markdown_dashboard_v3.py` | V3 is sole canonical renderer | release static-builder smoke | RETAINED |
| Legacy Markdown dashboard command | `src/build_markdown_dashboard.py` -> v3 | Independent ~34KB old renderer removed; command delegates to v3 | release check invokes legacy command and validates output downstream | SUPERSEDED |
| End-to-end release gate | `scripts/release_check.sh` | Unit suite + real data integrity + canonical conditionals + date-safe overlay + dynamics + fresh ML + stacked ML + cầu-kèo + builders + production consistency | GitHub CI run 120; final documentation-head rerun required | HARDENED / VERIFIED |
| Research release gate | `scripts/research_release_check.sh` | Real-history research diagnostics, conditional, cross-lag, strategy and UI integrity | GitHub CI run 120; final documentation-head rerun required | HARDENED / VERIFIED |
| Runtime production audit | `src/production_audit.py` | Canonical gaps, consensus, prediction target dates, conditional pair counts, overlay target, dynamics calendar, cầu manifest target, docs | release check + post-finalization workflow | HARDENED / VERIFIED |
| Daily generated-state transaction | `.github/workflows/update-data.yml` | Strict pipeline runs before broad `git add data models images docs ...`; new artifacts persist in same analytics transaction | production workflow structure | RETAINED / VERIFIED BY FINALIZATION AFTER MERGE |
| Server-only deployment stacks | historical hosting/webapp/scheduler artifacts | Not part of GitHub-only architecture; explicitly forbidden by release check | forbidden-artifact loop in `release_check.sh` | EXCLUDED |
| Old scraper/parser stacks | legacy repositories | Not migrated where current VLA source adapters/consensus are newer and independently tested | source policy + parser/consensus tests | EXCLUDED / SUPERSEDED |
| Duplicate generated legacy datasets | legacy repositories | Not treated as source code or authoritative history | canonical `data/xsmb*` + source audit | EXCLUDED |

## File-level closure for PR #24 source changes

| File | Closure |
| --- | --- |
| `src/calendar_alignment.py` | Canonical calendar primitive; MIGRATED. |
| `src/cau_keo_ml.py` | Calendar/date-axis guard added without changing feature schema or model hyperparameters; HARDENED. |
| `src/conditional_matrices.py` | Canonical exact-calendar replacement for three legacy conditional families; MIGRATED. |
| `src/conditional_nextday.py` | Chronology-aware conditional research; HARDENED. |
| `src/crosslag_positional_lab.py` | Legacy cross-lag research family consolidated; MIGRATED / RESEARCH-ONLY. |
| `src/cycle_stats.py` | Calendar gap semantics; HARDENED. |
| `src/descriptive_extensions.py` | Real calendar windows/recency semantics; HARDENED. |
| `src/dtos.py` | Result-domain contract; HARDENED. |
| `src/ensemble_components.py` | Explicit artifact availability/date contract; MIGRATED/HARDENED. |
| `src/hazard_stats.py` | Calendar/boundary-censoring semantics; HARDENED. |
| `src/learn_ensemble_weights.py` | Unavailable component days excluded; HARDENED. |
| `src/legacy_advanced_diagnostics.py` | Advanced legacy diagnostics retained under research controls; MIGRATED / RESEARCH-ONLY. |
| `src/markov_stats.py` | Exact next-calendar-day transition contract; HARDENED. |
| `src/number_dynamics.py` | Full calendar guard around higher-order row-index math; HARDENED. |
| `src/path_backtest.py` | Exact next-day evaluation; HARDENED. |
| `src/path_timeline_evidence.py` | No-lookahead timeline evidence; MIGRATED/HARDENED. |
| `src/pipeline.py` | Validation-before-analytics and canonical post-processors; HARDENED. |
| `src/predict_nextday_2d.py` | Availability-aware degraded blend; HARDENED. |
| `src/prob_eval_history.py` | Honest emitted-artifact-only evaluation; HARDENED. |
| `src/production_audit.py` | Production target/calendar contracts expanded; HARDENED. |
| `src/record_pred_history.py` | Explicit availability history + legacy sanitation; HARDENED. |
| `src/research_firewall.py` | Calendar fail-fast before research inference; HARDENED / RESEARCH-ONLY. |
| `src/research_legacy_extensions.py` | Legacy descriptive evidence retained under research plane; MIGRATED. |
| `src/run_path.py` | Compatibility wrapper only; SUPERSEDED. |
| `src/run_path_ui.py` | Canonical path runner with date-axis guard; HARDENED. |
| `src/sources.py` | Source boundary/provider-independence contract; HARDENED. |
| `src/statistical_signal.py` | Calendar-validated production statistical signal; HARDENED. |
| `src/statistics_ai_overlay.py` | Date-safe canonical replacement for legacy overlay; MIGRATED. |
| `src/strategy_lab.py` | Calendar-safe holdout geometry; HARDENED / RESEARCH-ONLY. |
| `src/validate_data.py` | Strict data-domain/continuity gate; HARDENED. |
| `src/vip_stats.py` | Compatibility wrapper over canonical descriptive engine; SUPERSEDED. |
| `src/build_markdown_dashboard.py` | Compatibility wrapper over v3; SUPERSEDED. |
| `src/build_research_lab.py` | Research evidence presentation; MIGRATED. |

## Promotion and safety policy

No result in `data/research/`, no legacy strategy, no conditional matrix, and no diagnostic p-value is automatically promoted into production prediction weights. Promotion requires a separate code change plus chronological out-of-sample evidence, multiple-testing control, effect-size persistence, calibration/quality gates and review of dependency/data-snooping risk.

Missing or stale production inputs must degrade explicitly or fail. They must never be represented as apparently valid zero-probability models, silently reconstructed historical predictions, or wrong-date artifacts.

## Final approval gate

PR #24 must remain Draft until **all** of the following are true on the same final head:

1. `ruff`/compile gates pass;
2. full `pytest` passes;
3. source policy passes;
4. canonical data validation passes;
5. current production cầu-kèo artifacts are regenerated from the current code;
6. exact-calendar conditional diagnostics report zero skipped boundaries on canonical history;
7. date-safe AI overlay targets exactly `latest canonical + 1 day`;
8. higher-order dynamics report `calendar_contiguous=true` for Loto and ĐB;
9. fresh base-ML train/predict smoke passes;
10. stacked-ML challenger smoke passes;
11. production model schema/date checks pass with the supervised anchor correctly one day behind its newest known target;
12. Markdown/HTML builders pass;
13. strict production consistency audit passes;
14. research-plane release check passes;
15. PR is mergeable against the latest `main`;
16. after merge, strict daily finalization + Pages + post-finalization/live reconciliation pass on production.

**Current decision:** `VERIFIED-PRE-MERGE`. GitHub CI run 120 passed both core and research gates on `5cab5fa3eff78d9fbd4975163cb9c521f65c55a7`. This documentation-only status commit must pass the same CI before PR #24 leaves Draft. Post-merge production verification remains mandatory under gate 16.
