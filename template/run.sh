#!/usr/bin/env bash
# Run it without installing anything: ./run.sh --repo path/to/project
set -euo pipefail
cd "$(dirname "$0")"
PYTHONPATH=src exec python3 -m PKG "$@"
