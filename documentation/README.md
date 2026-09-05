# VLA documentation

Hand-written project documentation. This directory is **not** published: GitHub
Pages serves `docs/`, which holds generated HTML artifacts only.

Historical patterns do not guarantee future lottery results. Every document here
treats descriptive and research material as evidence for validation, never as a
forecasting guarantee.

## Index

| Document | Scope |
| --- | --- |
| [`domain/number-ontology.md`](domain/number-ontology.md) | Canonical two-digit number relations (lộn, bóng, bộ, chạm, tổng, cặp 50), their provenance, generated data contracts and Excel integrity rules. |
| [`research/algorithm-definitions.md`](research/algorithm-definitions.md) | Data/time semantics, canonical number relations and safety contracts for the analysis layer. |
| [`research/method-catalog.md`](research/method-catalog.md) | Catalog of publicly observed Vietnamese lottery methods with mathematical definitions, parameters, leakage risk and VLA equivalents. |
| [`research/source-comparison.md`](research/source-comparison.md) | Per-source public behaviour and the method comparison matrix. |
| [`history/legacy-consolidation.md`](history/legacy-consolidation.md) | Consolidated migration, retirement acceptance and forensic re-audit record for the three predecessor repositories. |

## Related material outside this directory

| Location | Content |
| --- | --- |
| `README.md` (root) | Operating overview and setup. **Generated** by `src/update_readme.py` from `src/templates/README.j2` — do not edit by hand. |
| `DASHBOARD.md` (root) | Analysis dashboard. **Generated** by `src/build_markdown_dashboard_v3.py` — do not edit by hand. |
| `SECURITY.md` (root) | Vulnerability reporting, trust boundaries and model-artifact policy. |
| `.codex/` | Agent memory bank: repair rules, verified repair patterns, known failures, research memory, tuning history and incident records. |

## Conventions

- The implementation is the source of truth. When a document and the code
  disagree, the code wins and the document is a bug.
- Each document states its own verification date where the content is
  time-sensitive.
- Research-plane material is descriptive or challenger evidence only. Promotion
  into production prediction weights requires a separate code change plus the
  chronological out-of-sample gates described in the relevant document.
