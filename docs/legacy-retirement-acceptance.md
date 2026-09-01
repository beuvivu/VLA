# Legacy repository retirement acceptance — FINAL APPROVED

Date: 2026-09-01
Status: **APPROVED FOR RETIREMENT**

This document records the completed migration and production acceptance for retiring these legacy repositories after their useful algorithms were consolidated into `beuvivu/VLA`:

- `beuvivu/Vietnam-Lottery-Analysis`
- `beuvivu/xsmb-analysis`
- `beuvivu/xoso`

## Migration record

The scientific consolidation was merged through PR #18 (`Consolidate legacy algorithms into scientific Research Lab`) at commit `816c40ebd3acafa80dbcdbbcd1a8bc14a547aad9`.

Preserved/reimplemented capabilities include the canonical number ontology, descriptive head/gap/recency extensions, randomness/dependence diagnostics, chronological research firewall, multiple-testing/FDR controls, data-snooping reality checks, a standardized strategy laboratory, agreement/diversity diagnostics, and the Research Lab UI.

Legacy server deployment stacks, duplicated generated artifacts, older scraper/parser implementations, and superseded ML/path implementations were intentionally not migrated because VLA already contains newer or safer equivalents.

## Production acceptance — 2026-09-01

- Canonical XSMB date: `2026-09-01`
- Data health: OK; 387 rows; no missing dates; no duplicate dates; sparse draw total = 27
- Canonical result was committed before downstream analytics
- Strict statistics/AI/ML pipeline completed successfully
- Research plane executed on real production history
- `data/research/` and `data/descriptive_ext/` were generated on `main`
- `docs/research-lab.html` was generated
- Next-day prediction artifacts target `2026-09-02`
- README/dashboard refresh completed
- GitHub Pages deployment completed successfully
- Explicit post-finalization workflow dispatch completed successfully
- `live/live.json` was reconciled to canonical status `complete_verified`, 27/27 verified
- The 2026-09-01 canonical result was independently sanity-checked against additional public result sites outside VLA's configured source set and matched the canonical draw

## Consensus safety hardening

Final safety hardening was merged through PR #23 (`Harden source consensus against equal-support ties`) at commit `8d7ab3182094c87cd35b4c7a7c8d73d3dbc1ac2e`.

Canonical and live consensus now enforce a unique independent-provider winner. Configured source priority cannot promote a result through an equal-support verification tie. If two distinct results each reach the same independent-provider support at or above the required threshold (for example 2-vs-2), neither is accepted as verified/canonical.

Regression coverage includes:

- equal 2-independent-vs-2-independent full-result tie => rejected;
- equal-support live slot tie => provisional display only, never verified;
- two genuinely independent providers vs two mirrors belonging to one provider group => the independent winner is accepted;
- existing provider-independence and parser/source-policy tests remain intact.

The complete VLA Core release check and Research-plane release check passed before PR #23 merge and passed again on `main`. The post-merge production finalization, generated-output verification, dashboard deployment, and explicit post-finalization/live reconciliation also completed successfully.

## Scientific promotion policy

Research outputs are descriptive/challenger evidence only. No migrated legacy strategy is automatically promoted into production prediction weights. Promotion requires chronological out-of-sample validation, multiple-testing control, effect-size persistence, dependence-aware reality checks, and the existing production quality gates.

At the 2026-09-01 acceptance point, the Research Firewall and Strategy Lab remain conservative: exploratory patterns that do not clear the scientific gates do not affect production weights.

## Runtime dependency check

VLA does not require the three legacy repositories at runtime. There are no imports, workflow checkouts, downloads, or external repository dependencies needed from them for canonical collection, live operation, statistics, AI/ML, predictions, Research Lab, README/dashboard generation, or GitHub Pages deployment.

## Final retirement decision

**APPROVED.** The three legacy repositories are functionally redundant with respect to the capabilities intentionally selected for preservation. They may be archived or deleted without removing a required VLA runtime dependency or losing the algorithms/features intentionally migrated into VLA.

For maximum auditability, archiving the old repositories for a short retention period before permanent deletion is preferable. If permanent deletion is chosen immediately, this acceptance record, the migration record, tests, and retained implementations remain in VLA as the authoritative consolidated codebase.
