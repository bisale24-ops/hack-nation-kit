#!/usr/bin/env bash
# The kit's own gate: the renderer's checks, and a project stamped out from the template.
set -uo pipefail
kit=$(cd "$(dirname "$0")" && pwd)
status=0
if [ $# -gt 0 ]; then pythons=("$@")
else pythons=("$HOME/.venvs/py39/bin/python" "$HOME/.venvs/py313/bin/python"); fi
for python in "${pythons[@]}"; do
  printf '\n=== %s ===\n' "$("$python" -V 2>&1)"
  "$python" -m pytest "$kit/tests" -q || status=1
done
scratch=$(mktemp -d)
printf '\n=== a stamped project ===\n'
TARGET="$scratch/probe" "$kit/new.sh" probe "a probe" >"$scratch/log" 2>&1 || { cat "$scratch/log"; status=1; }
grep -q "all green" "$scratch/log" || { echo "the stamped project did not come up green"; status=1; }
rm -rf "$scratch"
[ $status -eq 0 ] && echo && echo "kit green"
exit $status
