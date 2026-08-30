# Release validation — v1.1.0

Validated on 2026-08-31 for the GitHub-only distribution.

## Release gates

- 46/46 unit + regression tests: PASS
- Python compileall: PASS
- GitHub workflow YAML parse: PASS
- Source policy: PASS
- `ketqua04`: absent
- Path engine: PASS
- Base ML Loto + De: PASS
- Cau-keo ML: PASS
- Position evidence: PASS
- Five-component ensemble: PASS
- Probability evaluation: PASS
- Static GitHub Pages builders: PASS
- Artifact cleanup: PASS
- Bootstrap trigger after first push: ENABLED
- Cutoff-aware freshness check: ENABLED
- Daily schedule: 18:38 / 18:53 / 19:13 Asia/Ho_Chi_Minh
- Near-live schedule: 18:04 Asia/Ho_Chi_Minh, ~25s in-job polling

## Data source priority

1. xoso.com.vn
2. mketqua.net
3. www.minhngoc.net.vn
4. xosominhngoc.com
5. xosodaiphat.com
6. hainhay.net

Canonical recent results require cross-source consensus. Minh Ngoc mirror domains share one provider-independence group.

## v1.1.0 bootstrap fixes

- A newly published repository now runs the production pipeline on the first push.
- Before the 18:35 draw cutoff, the health gate correctly expects yesterday as the newest completed draw.
- At/after 18:35, the health gate expects today's completed draw.
- Pages deployment is isolated from data/ML finalization so Pages configuration cannot block canonical data/model updates.
- Generated commits use `GITHUB_TOKEN`; GitHub's normal anti-recursion behavior prevents the bot commit from recursively triggering the push workflow.

## Environment note

The local validation environment had no network access and no `ruff` executable. Correctness lint rules remain pinned in `requirements-dev.txt` and are executed by GitHub CI after dependency installation. Local validation therefore used compileall + the complete pytest regression suite plus componentized strict integration execution.
