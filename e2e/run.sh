#!/bin/bash
# Run the browser tests in the Playwright Docker image.
#
#   e2e/run.sh [pytest args]
#
# Builds the frontend if needed, starts a backend on $PORT (default 8101)
# unless one is running, and runs pytest in the container. Python packages
# for the container are installed once into $E2E_DEPS.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=${PORT:-8101}
IMAGE=${IMAGE:-mcr.microsoft.com/playwright/python:v1.58.0-noble}
E2E_DEPS=${E2E_DEPS:-$HOME/envs/wildjoker-e2e}
export UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT:-$HOME/envs/wildjoker-frontend}
export PATH=$HOME/.local/bin:$PATH

if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && NODE_OPTIONS=--max-old-space-size=1024 npm run build)
fi

server=""
if ! curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null; then
  (cd backend && uv run python -m wildjoker.server --port "$PORT" >/tmp/wildjoker-e2e-server.log 2>&1) &
  server=$!
  trap 'pkill -P $server 2>/dev/null; kill $server 2>/dev/null; wait $server 2>/dev/null || true' EXIT
  for _ in $(seq 50); do curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null && break; sleep 0.2; done
fi

mkdir -p "$E2E_DEPS" screenshots
docker_run=(docker run --rm --memory=1.5g --network host -u "$(id -u):$(id -g)" -e HOME=/tmp
  -v "$E2E_DEPS:/deps" -v "$PWD/e2e:/e2e" -v "$PWD/screenshots:/screenshots"
  -e PYTHONPATH=/deps -e WILDJOKER_URL="http://127.0.0.1:$PORT" -e WILDJOKER_SCREENSHOTS=/screenshots
  -e PYTHONDONTWRITEBYTECODE=1 -w /e2e "$IMAGE")
if [ ! -d "$E2E_DEPS/playwright" ]; then
  "${docker_run[@]}" python3 -m pip install -q --target /deps playwright==1.58.0 pytest
fi
"${docker_run[@]}" python3 -m pytest -p no:cacheprovider "$@"
