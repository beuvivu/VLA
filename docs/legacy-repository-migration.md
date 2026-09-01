# Legacy repository algorithm migration audit

This document records the selective migration of useful algorithms from the three public predecessor repositories into `VLA` before those repositories are retired.

## Repositories reviewed

- `beuvivu/Vietnam-Lottery-Analysis`
- `beuvivu/xsmb-analysis`
- `beuvivu/xoso`

## Findings

### Vietnam-Lottery-Analysis

Most source modules are direct ancestors of modules already present in VLA. The current VLA implementations supersede the older path, ML, calibration, source, sync and dashboard code. The unique descriptive value retained from this repository is the VIP-style head table plus gap-by-digit-sum and gap-by-touch views.

### xsmb-analysis

This repository is an earlier snapshot of the same path/ML lineage. Its path backtest, conditional-next-day, Markov, hazard, pair statistics, probability evaluation and static path UI have newer or expanded equivalents in VLA. The descriptive VIP module is the same legacy feature family preserved through `src/descriptive_extensions.py`.

### xoso

This repository contained the largest set of ideas not already represented in VLA. The following concepts were retained and strengthened:

- canonical two-digit ontology: reverse, bóng, bộ, chạm, tổng and kép;
- randomness/dependence diagnostics;
- weekday-effect and serial-dependence falsification;
- chronological auto-discovery evaluation;
- multiple-testing control;
- max-statistic reality check for data snooping;
- standardized deterministic strategy registry;
- strategy agreement and diversity diagnostics;
- recency/evidence timelines.

The original implementations were not copied wholesale. VLA uses chronology-preserving splits, training-only baselines, Benjamini-Hochberg FDR, explicit effect-size gates and circular-shift permutation tests so the research layer is harder to overfit.

## Deliberately not migrated

The following predecessor features are intentionally excluded because they conflict with VLA architecture or are superseded:

- Docker/cPanel/Passenger/systemd/server deployment stacks;
- FastAPI/MySQL/SQLite server architecture;
- duplicate source fetchers and parsers;
- older base-ML/path implementations already superseded by VLA;
- fixed or unvalidated betting heuristics promoted directly to production;
- any rule that uses same-day/future information to score the next draw;
- duplicate large historical artifacts that would unnecessarily increase repository size.

## New VLA preservation layer

- `src/number_reference.py` — one source of truth for two-digit combinatorics.
- `src/descriptive_extensions.py` — head tables, tổng/chạm gaps, number and pair recency.
- `src/research_diagnostics.py` — FDR/permutation-based falsification diagnostics.
- `src/research_firewall.py` — 27×27 positional hypothesis search with chronological train/validation/holdout and reality check.
- `src/strategy_lab.py` — standardized walk-forward comparison of deterministic strategy families, agreement curves and diversity.
- `src/build_research_lab.py` — static GitHub Pages research interface.
- `scripts/research_release_check.sh` — strict real-data CI gate for the research plane.

## Separation from production prediction

Research outputs are generated automatically but do not alter the production ensemble. A strategy or rule being marked `research_gate_pass` or `production_eligible` means only that it survived the stated research protocol. Promotion into the production probability stack requires an explicit implementation and the existing VLA leakage-safe validation/model-quality gates.

## Retirement criterion for predecessor repositories

The predecessor repositories are feature-preservation-safe to retire only after the consolidated migration PR passes both the core release check and the research-plane release check on VLA, is merged to `main`, and the post-merge production pipeline successfully regenerates the research artifacts and `docs/research-lab.html`.
