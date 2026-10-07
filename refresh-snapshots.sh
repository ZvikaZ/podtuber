#!/usr/bin/env bash
# Some sites (Meir TV) refuse GitHub's servers, so the daily GitHub run reads them from snapshots/ instead.
# This refreshes those snapshots, from a computer the sites do serve, and pushes them; run it whenever you like.
set -euo pipefail
cd "$(dirname "$0")"
git pull --quiet
uv run podtuber --snapshot
git add snapshots
if git diff --cached --quiet; then
    echo "The snapshots haven't changed"
else
    git commit --quiet -m "Refresh the snapshots of sites that refuse GitHub's servers"
    git push --quiet
    echo "Pushed; GitHub will publish them shortly"
fi
