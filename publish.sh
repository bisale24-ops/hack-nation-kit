#!/usr/bin/env bash
# Push a project to GitHub, but only after the gate is green and nothing secret is in the tree.
#
#   cd ../mytool && ../hack-nation/kit/publish.sh            # creates bisale24-ops/mytool, public
#
# Two refusals, both from things that have already gone wrong: a red CI run arriving by email
# after the push, and an API key committed in a demo file.
set -euo pipefail
owner=${OWNER:-bisale24-ops}
project=$(basename "$PWD")

[ -d .git ] || { echo "not a git repository: $PWD" >&2; exit 2; }

echo "--- secrets ---"
# Long random-looking values and the well-known key prefixes. Tracked files only.
if git ls-files -z | xargs -0 grep -nEI \
     -e 'sk-ant-[A-Za-z0-9_-]{20,}' \
     -e 'sk-[A-Za-z0-9]{32,}' \
     -e 'gh[pousr]_[A-Za-z0-9]{30,}' \
     -e 'AKIA[0-9A-Z]{16}' \
     -e 'xox[abprs]-[A-Za-z0-9-]{20,}' \
     -e '(api[_-]?key|secret|token|password)[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9/_+-]{24,}' \
     2>/dev/null; then
  echo "refusing to push: the lines above look like credentials" >&2
  exit 1
fi
git ls-files | grep -E '\.(key|pem|p12|keystore)$' && { echo "refusing: a key file is tracked" >&2; exit 1; }
echo "clean"

echo
echo "--- gate ---"
if [ -x ./check.sh ]; then
  ./check.sh || { echo "refusing to push: the gate is red" >&2; exit 1; }
else
  echo "no check.sh here — push it yourself if that is really what you want" >&2
  exit 1
fi

if [ -n "${DRY_RUN:-}" ]; then echo; echo "dry run: everything above passed, not pushing"; exit 0; fi

echo
if git remote get-url origin >/dev/null 2>&1; then
  git push -u origin HEAD
else
  gh repo create "$owner/$project" --public --source=. --remote=origin --push
fi

url="https://github.com/$owner/$project"
echo
echo "$url"
echo "watch the first run finish before telling anyone about it:"
echo "  gh run watch --repo $owner/$project"
