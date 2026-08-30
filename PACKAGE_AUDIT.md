# Package audit — GitHub-only v1.1.0

This package is intentionally a GitHub-only distribution. VPS/DigitalOcean/Docker/Nginx/systemd/Passenger deployment artifacts are not included.

## Required top-level structure

- `.github/workflows/` — CI, daily finalization, near-live and Pages workflows
- `src/` — statistics, data collection, AI/ML, ensemble, live and dashboard builders
- `tests/` — regression/unit tests
- `data/` — canonical seed/history and generated analytical datasets
- `models/` — production model artifacts
- `docs/` — GitHub Pages static site
- `images/` — generated visual assets
- `scripts/` — release utilities

Prediction history is intentionally compacted into `data/history/pred_loto.csv` and `data/history/pred_de.csv` rather than thousands of dated snapshots.

## Removed server-only components

The GitHub-only release does not contain Docker, Nginx, systemd, Passenger, cPanel, DigitalOcean deployment scripts or server webapp/scheduler services.

## Data source policy

Priority: xoso.com.vn → mketqua.net → www.minhngoc.net.vn → xosominhngoc.com → xosodaiphat.com → hainhay.net.

`ketqua04` is not part of the release.
