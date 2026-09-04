#!/usr/bin/env bash
set -euo pipefail

# This is deliberately an explicit maintenance action.  It never runs from a
# data-refresh schedule, because deleting every Actions cache is destructive
# to build performance and must be auditable.  The Python implementation uses
# GitHub's REST API, so local repair environments do not need the gh binary.
exec python3 "$(dirname "$0")/purge_github_caches.py" "$@"
