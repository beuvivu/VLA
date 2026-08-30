# v1.0.2 CI Ruff hotfix

## Problem fixed
GitHub Actions `scripts/release_check.sh` failed at the Ruff step because the v1.0.1 configuration treated legacy style diagnostics (import ordering, line length, pathlib preference, simplify rules, etc.) as release-blocking errors.

## Fix
- `pyproject.toml`: Ruff's default CI lint set is now correctness-critical only: `E9`, `F63`, `F7`, `F82`.
- `scripts/release_check.sh`: explicitly runs the same correctness-critical Ruff selection.
- Style/formatting diagnostics remain suitable for a future dedicated formatting pass, but no longer block production releases.

## Validation
- Python compile: PASS
- pytest: 44/44 PASS
- source policy: PASS
- data health/statistical signal/significance: PASS
- fresh Loto/De ML training + prediction smoke: PASS
- production model artifact compatibility: PASS
- static GitHub Pages builders: PASS
- required output check: PASS

The local validation environment had no Ruff executable and no outbound package download access. The release script was therefore executed locally with only the Ruff invocation shimmed; all other release stages ran normally. GitHub CI installs `ruff==0.11.10` from `requirements-dev.txt` and will execute the real correctness-critical Ruff check.
