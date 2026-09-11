# Loto frequency matrix

## Audit

- Production entry: `src/build_stat_pages.py`, `PAGES` entry `tan-suat-loto`,
  `render_page()` and `build()`. `python src/build_stat_pages.py` rebuilds all
  fourteen statistical pages; `render_page()` can regenerate the affected page.
- `src/build_statistics_dashboard.py` generates `docs/statistics.html`, a
  separate dashboard with its own evidence drill-down. `src/build_docs.py`
  generates path pages. Neither generates the Loto frequency page.
- `load_draws()` reads `data/xsmb.csv`, normalizes the 27 prize fields to their
  canonical `xsmb_domain.FIELD_WIDTHS`, and embeds chronological `{d,s,n}` records.
  `n` includes duplicates; `s` retains the five-digit special prize.
- `data/xsmb.json` mirrors raw prize results; `xsmb-2-digits.csv/json` contain
  derived endings. Advanced `period_matrix_loto_day_last31` already has counts
  but only 31 dates and no special marker. Reusing the page's existing history
  avoids another copy or client fetch.
- Missing values previously became zeros through `zfill`. The loader now rejects
  blank/malformed fields before padding and only includes complete draws.
- `src/pipeline.py` invokes the stat-page builder. `update-data.yml` runs that
  pipeline and commits `docs` with generated data. GitHub Pages serves committed
  HTML. Only the affected HTML is regenerated for this UI change.
- Existing protections: `test_stat_pages.py`, dashboard UI/evidence tests,
  design-system, Vietnamese UI, GitHub-only and workflow tests. Release commands
  are in `scripts/release_check.sh`; its ML retraining steps are outside this task.
- Existing table marks use localStorage, and column hints use document delegation.
  The new component uses stable `lfm:number:date` mark keys in the same store and
  a separate mark action. Existing marks on other tables stay intact. The picker
  identifies comparison numbers in the row header; all 100 rows remain available.
  The independent statistics dashboard's evidence behavior is untouched.

## Phase A

Component assets are embedded only for this page, after the shared stat-page
engine. The page-specific renderer replaces its legacy matrix renderer. Misses,
hits and special cards share their classes with the legend. Sticky axes have
opaque backgrounds. Delegated interaction caches column elements once per render;
crosshair movement updates only the previous/current row and column. Arrow keys
move a roving focus target. Details stay above the matrix, avoiding viewport-clipped
tooltips and preserving touch scrolling. Explicit theme preference uses defensive
localStorage access.

Phase A checkpoint commands (local interpreter `.venv/Scripts/python.exe`):

- `python src/build_stat_pages.py --page tan-suat-loto`: generated one page.
- With `VLA_BROWSER_TESTS=1` and `VLA_BROWSER_PATH` pointing to installed Chrome:
  `python -m pytest -q tests/test_loto_frequency_matrix.py tests/test_stat_pages.py tests/test_statistics_dashboard_ui.py --tb=short`:
  160 passed, including touch, denied storage, keyboard, marks, theme reload,
  special priority and fixed/sticky geometry at 320/360/390/430/768/1280 pixels.
- `python -m ruff check src tests`: passed (repository-pinned Ruff 0.11.10).
- Light/Dark screenshots inspected locally under `logs/lfm-visual/`.
  Caption alignment was corrected after visual inspection and regenerated.
- `git diff --check`: passed. Only the production Loto HTML changed. No runtime
  dependencies, framework, data files or model files were added/modified.

Before beginning Phase B:

- `python -m pytest -q tests/test_ui_redesign.py tests/test_ui_design_system.py tests/test_vietnamese_ui.py tests/test_github_only.py tests/test_contrast_and_scheduling.py tests/test_workflows.py --tb=short`:
  **418 passed** in 128.46 seconds.
- Final Phase A targeted/browser rerun after caption repair: **160 passed**.
- `python src/production_audit.py --consistency-only --strict --json-out logs/lfm-production-audit.json`:
  `ok: true`, no critical findings or warnings.

## Actual data cross-check

Inspected the original last three CSV rows, independently reduced all 27 fields
modulo 100, and compared their frequency counters with the embedded records:

| Date | Original special | Special cell | Other multiplicities | Unique / repeats / total |
|---|---|---|---|---|
| 2026-09-08 | 39687 | 87, 3 hits | 15:2, 22:2, 60:2 | 22 / 5 / 27 |
| 2026-09-09 | 94504 | 04, 2 hits | 07:2, 57:2 | 24 / 3 / 27 |
| 2026-09-10 | 30981 | 81, 1 hit | 24:3, 94:2 | 24 / 3 / 27 |

For example, September 8's `39687`, `11087`, `4287` all end in 87;
September 9's `94504` and `5504` end in 04; September 10's `94624`,
`72524`, `624` end in 24. The automated real-data test compares every number,
including misses, for each of these three dates.

Payload measured before Phase B: 2,395 draws, 411,941 bytes compact JSON,
95,930 bytes gzip. No second matrix dataset is needed.
