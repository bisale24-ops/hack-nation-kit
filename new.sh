#!/usr/bin/env bash
# Stamp out a working project and prove it works before handing it over.
#
#   kit/new.sh toolname ["one line about it"]
#
# Leaves a git repository whose first commit is green: tests pass on every interpreter in
# .github/workflows, the tool runs against itself, and stderr is empty.
set -euo pipefail

name=${1:-}
summary=${2:-}
if [ -z "$name" ]; then echo "usage: new.sh <name> [\"one line\"]" >&2; exit 2; fi
if ! printf '%s' "$name" | grep -Eq '^[a-z][a-z0-9]*$'; then
  echo "name must be lowercase letters and digits, no separators: '$name' is not" >&2
  exit 2
fi

kit=$(cd "$(dirname "$0")" && pwd)
target=${TARGET:-$(dirname "$kit")/../$name}
target=$(mkdir -p "$target" && cd "$target" && pwd)
if [ -n "$(ls -A "$target")" ]; then echo "$target is not empty" >&2; exit 2; fi

cp -R "$kit/template/." "$target/"
mv "$target/src/PKG" "$target/src/$name"

# Only the standalone token, so a word like PACKAGE survives untouched.
NAME="$name" SUMMARY="$summary" python3 - "$target" <<'PY'
import os, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
name, summary = os.environ["NAME"], os.environ["SUMMARY"]
token = re.compile(r"\bPKG\b")
for path in root.rglob("*"):
    if not path.is_file() or path.suffix in (".pyc", ".png", ".mp4", ".mp3"):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    new = token.sub(name, text)
    if summary:
        new = new.replace("{{ONE LINE}}", summary)
        new = new.replace("one line, the same one as the first line of the README", summary)
    if new != text:
        path.write_text(new, encoding="utf-8")
print("substituted into", root)
PY

cd "$target"
git init -q
git add -A
git -c user.name="Aleksandr Khrukalo" -c user.email="bisale24@gmail.com" \
    commit -qm "$name: skeleton from the Hack-Nation kit

Tests, the CI matrix, the model layer and the report renderings. No product logic yet.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

echo
echo "--- gate ---"
pythons=${PYTHONS:-"$HOME/.venvs/py39/bin/python $HOME/.venvs/py313/bin/python"}
# shellcheck disable=SC2086
./check.sh $pythons
echo
echo "$target is ready. Next: kit/video/setup.sh if the video environment is cold."
