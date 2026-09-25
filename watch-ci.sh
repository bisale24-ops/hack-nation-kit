#!/usr/bin/env bash
# Wait for the CI run belonging to THIS commit, and exit non-zero if it fails.
#
#   ./watch-ci.sh                 # in the project you just pushed
#
# `gh run watch $(gh run list --limit 1)` looks right and is a race: right after a push the newest
# run is still the previous commit's, so it watches that one and reports green for work it never
# saw. This resolves the run by the HEAD sha instead, and waits for it to appear.
set -uo pipefail
repo=${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)}
[ -n "$repo" ] || { echo "no repository: pass owner/name" >&2; exit 2; }
sha=$(git rev-parse HEAD) || exit 2

printf 'waiting for a run on %s in %s' "${sha:0:7}" "$repo"
id=""
for _ in $(seq 1 40); do
  id=$(gh run list --repo "$repo" --limit 20 --json databaseId,headSha \
       --jq "[.[] | select(.headSha == \"$sha\")] | first | .databaseId // empty" 2>/dev/null)
  [ -n "$id" ] && break
  printf '.'
  sleep 3
done
echo
[ -n "$id" ] || { echo "no run appeared for $sha — is CI enabled on this repository?" >&2; exit 1; }

gh run watch --repo "$repo" "$id" --exit-status
status=$?
gh run view --repo "$repo" "$id" --json conclusion,jobs \
  --jq '"\(.conclusion)  " + ([.jobs[] | "\(.conclusion) \(.name)"] | join(" · "))'
exit $status
