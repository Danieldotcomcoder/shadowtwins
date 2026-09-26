# syntax=docker/dockerfile:1.7
# Single-container release: Node builds the frontend; Python serves API + frontend and runs the
# durable worker under a small supervisor. One exposed port, persistent /data, non-root.

ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm
ARG NODE_IMAGE=node:22.16.0-bookworm-slim

# ---- frontend -----------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS frontend
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@10.25.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/
RUN cd frontend && pnpm install --frozen-lockfile
COPY contracts/ contracts/
COPY frontend/ frontend/
RUN cd frontend && pnpm build

# ---- python environment --------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS python-build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_HTTP_TIMEOUT=120 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir --retries 10 --timeout 60 uv==0.11.29
WORKDIR /app
COPY pyproject.toml uv.lock README.md .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable

# ---- runtime -------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin shadowtwins \
 && mkdir -p /data && chown shadowtwins:shadowtwins /data
WORKDIR /app
COPY --from=python-build /app/.venv /app/.venv
COPY packs/ /app/packs/
COPY --from=frontend /build/frontend/dist /app/frontend/dist
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    ST_DATA_DIR=/data \
    ST_PACKS_DIR=/app/packs \
    ST_FRONTEND_DIST=/app/frontend/dist
USER shadowtwins
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD ["python", "-c", "import sys,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=4); sys.exit(0 if r.status == 200 else 1)"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["tini", "--", "benchserver"]
CMD ["supervise", "--host", "0.0.0.0", "--port", "8000"]
