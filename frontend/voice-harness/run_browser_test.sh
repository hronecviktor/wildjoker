#!/bin/sh
# Run browser_test.py in the Playwright image against a backend on the host.
# Usage: ./run_browser_test.sh [URL]   (default http://127.0.0.1:8103)
# Installs the playwright Python package once into $PW_CACHE.
set -e
cd "$(dirname "$0")"
IMAGE=mcr.microsoft.com/playwright/python:v1.58.0-noble
PW_CACHE=${PW_CACHE:-$HOME/envs/wildjoker-voice-pw}
if [ ! -d "$PW_CACHE/playwright" ]; then
  mkdir -p "$PW_CACHE"
  docker run --rm -u "$(id -u):$(id -g)" -v "$PW_CACHE:/pw" "$IMAGE" \
    pip install --quiet --target /pw playwright==1.58.0
fi
exec docker run --rm --network host -e PYTHONPATH=/pw:/t -v "$PW_CACHE:/pw:ro" -v "$PWD:/t:ro" \
  "$IMAGE" python3 /t/browser_test.py "${1:-http://127.0.0.1:8103}"
