#!/usr/bin/env bash
# The whole gate, on every interpreter CI uses. Nothing is pushed until this exits zero.
#   ./check.sh ~/.venvs/py39/bin/python python3
set -uo pipefail
cd "$(dirname "$0")"
status=0
if [ $# -gt 0 ]; then pythons=("$@")
else pythons=("$HOME/.venvs/py39/bin/python" "$HOME/.venvs/py313/bin/python"); fi
for python in "${pythons[@]}"; do
  printf '\n=== %s ===\n' "$("$python" -V 2>&1)"
  PYTHONPATH=src "$python" -m pytest tests -q || status=1
  PYTHONPATH=src "$python" -m PKG --repo . --quiet; code=$?
  [ $code -le 1 ] || { echo "exit $code"; status=1; }
  err=$(PYTHONPATH=src "$python" -m PKG --repo . 2>&1 >/dev/null)
  [ -z "$err" ] || { echo "wrote to stderr: $err"; status=1; }
done
[ $status -eq 0 ] && echo && echo "all green"
exit $status
