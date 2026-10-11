#!/usr/bin/env bash
# Some sites (Meir TV) refuse GitHub's servers, so the daily GitHub run reads them from snapshots instead. This
# refreshes those snapshots, from a computer the sites do serve, and pushes them to the "snapshots" branch, as its
# one commit, replacing the last: so that old snapshots don't pile up in the repository's history. The next daily
# run publishes them (or "Run workflow", in the repository's Actions tab, publishes them now).
set -euo pipefail
cd "$(dirname "$0")"
uv run podtuber --snapshot

# a commit of the snapshots directory alone, made without touching the working copy or its branch
index=$(mktemp -u)
GIT_INDEX_FILE="$index" git --work-tree=snapshots add --force --all -- .
tree=$(GIT_INDEX_FILE="$index" git write-tree)
rm -f "$index"
commit=$(git commit-tree "$tree" -m "Snapshots of the sites that refuse GitHub's servers")
git push --force --quiet origin "$commit:refs/heads/snapshots"
echo "Pushed the snapshots; the next daily run publishes them"
