#!/usr/bin/env bash
set -euo pipefail

# This is deliberately an explicit maintenance action.  It never runs from a
# data-refresh schedule, because deleting every Actions cache is destructive
# to build performance and must be auditable.
repo="${GITHUB_REPOSITORY:-beuvivu/VLA}"
if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required to purge Actions caches." >&2
  exit 127
fi
if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "GH_TOKEN is required (use a token with Actions write permission)." >&2
  exit 2
fi

echo "Existing workflow caches for ${repo}:"
gh cache list --repo "${repo}"
echo "Deleting all workflow caches for ${repo}..."
gh cache delete --all --confirm --repo "${repo}"
echo "Cache purge complete."
