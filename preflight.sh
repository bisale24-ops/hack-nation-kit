#!/usr/bin/env bash
# Run this an hour before the start. Everything it checks has cost time at least once.
#   kit/preflight.sh            checks only
#   kit/preflight.sh --gate     also runs the kit's own tests (about a minute)
set -uo pipefail
kit=$(cd "$(dirname "$0")" && pwd)
bad=0
ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; }
warn() { printf '  \033[33mwarn\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; bad=1; }

echo "tools"
for binary in ffmpeg ffprobe git gh python3; do
  if command -v "$binary" >/dev/null; then ok "$binary — $(command -v "$binary")"
  else fail "$binary is not on PATH"; fi
done

echo "interpreters (the CI matrix)"
for venv in py39 py313; do
  python="$HOME/.venvs/$venv/bin/python"
  if [ -x "$python" ] && "$python" -m pytest --version >/dev/null 2>&1
  then ok "$venv — $("$python" -V 2>&1), $("$python" -m pytest --version 2>&1)"
  else fail "$venv: python3 -m venv ~/.venvs/$venv && ~/.venvs/$venv/bin/pip install pytest"; fi
done

echo "video"
video="$HOME/.venvs/video/bin/python"
if [ -x "$video" ]; then
  "$video" -c "import playwright" 2>/dev/null && ok "playwright installed" || fail "playwright missing: kit/video/setup.sh"
  [ -x "$HOME/.venvs/video/bin/edge-tts" ] && ok "edge-tts installed" || fail "edge-tts missing: kit/video/setup.sh"
  if "$video" -c "
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch().close()
" 2>/dev/null; then ok "chromium launches"; else fail "chromium will not launch: ~/.venvs/video/bin/playwright install chromium"; fi
else
  fail "no video environment: kit/video/setup.sh"
fi
[ -f "$kit/video/smoke/smoke.mp4" ] && ok "a rendered smoke video exists" || warn "no smoke video yet: kit/video/setup.sh"

echo "accounts"
gh auth status >/dev/null 2>&1 && ok "gh signed in as $(gh api user --jq .login 2>/dev/null)" || fail "gh auth login"
[ -n "$(git config --global user.email)" ] && ok "git identity $(git config --global user.email)" \
  || warn "no global git identity (new.sh sets one per commit anyway)"

echo "keys in ~/.config"
found=0
for key in "$HOME"/.config/*.key; do
  [ -e "$key" ] || continue
  found=1; ok "$(basename "$key") — $(wc -c <"$key" | tr -d ' ') bytes"
done
[ $found -eq 1 ] || warn "no ~/.config/*.key yet; sponsor keys arrive at kickoff"

echo "machine"
free=$(df -g "$HOME" | awk 'NR==2 {print $4}')
[ "${free:-0}" -ge 5 ] && ok "${free}G free" || fail "only ${free}G free — a render needs room"
for host in github.com api.anthropic.com; do
  curl -sS -m 6 -o /dev/null "https://$host" && ok "$host reachable" || warn "$host unreachable right now"
done

if [ "${1:-}" = "--gate" ]; then
  echo "gate"
  "$kit/check.sh" >/tmp/preflight-gate.log 2>&1 && ok "kit green" \
    || { fail "kit gate red — see /tmp/preflight-gate.log"; tail -5 /tmp/preflight-gate.log; }
fi

echo
[ $bad -eq 0 ] && echo "ready" || echo "not ready — fix the FAIL lines above"
exit $bad
