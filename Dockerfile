# Wild Joker: the game server with the built frontend, in one image.
#
#   docker build -t wildjoker .
#   docker run -p 127.0.0.1:8000:8000 wildjoker
#
# deploy/publish.sh builds it and pushes it to Docker Hub; see
# deploy/README.md for running it in production.

# -- frontend -------------------------------------------------------------------
# The built app is the same on every platform, so build it natively even when
# the image is for another architecture.
FROM --platform=$BUILDPLATFORM node:20-slim AS frontend
WORKDIR /src/frontend
COPY frontend/ ./
# Builds the Svelte app into dist/. Without a frontend/package.json (a branch
# without the app), the image still builds and the server says "frontend not
# built" at /.
RUN if [ -f package.json ]; then \
      npm ci --no-audit --no-fund && npm run build; \
    else \
      echo "no frontend/package.json, skipping the frontend build" && mkdir -p dist; \
    fi

# -- Python dependencies ----------------------------------------------------------
FROM python:3.13-slim AS backend
RUN pip install --no-cache-dir uv==0.12.23
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev --no-editable

# -- runtime ----------------------------------------------------------------------
FROM python:3.13-slim
RUN useradd --system --uid 10001 --home-dir /app wildjoker
COPY --from=backend /app/.venv /app/.venv
COPY --from=frontend /src/frontend/dist /app/static
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    WILDJOKER_STATIC=/app/static
USER wildjoker
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["python", "-m", "wildjoker.server", "--host", "0.0.0.0", "--port", "8000"]
