#!/usr/bin/env bash
# Build the video environment once, so the sprint never waits on a download.
#   kit/video/setup.sh
# Leaves ~/.venvs/video with playwright (+ chromium) and edge-tts, and proves the whole
# pipeline by rendering a real ten-second mp4.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
venv=${VIDEO_VENV:-$HOME/.venvs/video}

command -v ffmpeg  >/dev/null || { echo "ffmpeg missing: brew install ffmpeg" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe missing: brew install ffmpeg" >&2; exit 1; }

[ -x "$venv/bin/python" ] || python3 -m venv "$venv"
"$venv/bin/python" -m pip install -q --upgrade pip playwright edge-tts
"$venv/bin/playwright" install chromium

echo
echo "--- smoke: a real render, end to end ---"
rm -rf "$here/smoke/build" "$here/smoke/smoke.mp4"
"$venv/bin/python" "$here/render.py" "$here/smoke/script.py" --out "$here/smoke/smoke.mp4"
ffprobe -v error -show_entries stream=codec_name,width,height -of csv=p=0 "$here/smoke/smoke.mp4"
echo
echo "video environment ready: $venv/bin/python"
