# Legacy repository retirement acceptance

Date: 2026-09-01

This document records the final migration and production-acceptance criteria for retiring these legacy repositories after their useful algorithms were consolidated into `beuvivu/VLA`:

- `beuvivu/Vietnam-Lottery-Analysis`
- `beuvivu/xsmb-analysis`
- `beuvivu/xoso`

## Migration record

The scientific consolidation was merged through PR #18 (`Consolidate legacy algorithms into scientific Research Lab`) at commit `816c40ebd3acafa80dbcdbbcd1a8bc14a547aad9`.

Preserved/reimplemented capabilities include the canonical number ontology, descriptive head/gap/recency extensions, randomness/dependence diagnostics, chronological research firewall, multiple-testing/FDR controls, data-snooping reality checks, a standardized strategy laboratory, agreement/diversity diagnostics, and the Research Lab UI.

Legacy server deployment stacks, duplicated generated artifacts, older scraper/parser implementations, and superseded ML/path implementations were intentionally not migrated.

## Production acceptance — 2026-09-01

- Canonical XSMB date: `2026-09-01`
- Data health: OK; no missing dates; no duplicate dates; sparse draw total = 27
- Canonical result was committed before downstream analytics
- Strict statistics/AI/ML pipeline completed successfully
- Research plane executed on real production history
- `data/research/` and `data/descriptive_ext/` were generated on `main`
- `docs/research-lab.html` was generated
- Next-day prediction artifacts target `2026-09-02`
- README/dashboard refresh completed
- GitHub Pages deployment completed successfully
- Explicit post-finalization workflow dispatch completed successfully
- `live/live.json` was reconciled to canonical status `complete_verified`

## Consensus safety hardening

Before retirement approval, canonical and live consensus were additionally hardened so configured source priority cannot break an equal-support verification tie. If two distinct results each reach the same independent-provider support at or above the required threshold (for example 2-vs-2), neither is accepted as verified/canonical. Regression tests cover both equal independent ties and the valid case where two independent providers beat two mirrors belonging to only one provider group.

## Scientific promotion policy

Research outputs are descriptive/challenger evidence only. No migrated legacy strategy is automatically promoted into production prediction weights. Promotion requires chronological out-of-sample validation, multiple-testing control, effect-size persistence, dependence-aware reality checks, and the existing production quality gates.

## Retirement decision

Once the consensus-hardening PR passes the complete VLA CI/research gates and is merged to `main`, the three repositories above are functionally redundant with respect to the retained capabilities. They may then be archived or deleted without losing the algorithms/features intentionally selected for preservation.

For maximum auditability, archiving the old repositories for a short retention period before permanent deletion is preferable, but no runtime dependency from VLA to those repositories is required.
