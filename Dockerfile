# syntax=docker/dockerfile:1

# Stage 1: Build the React + Tailwind v4 frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /build

COPY src/calobot/telemetry/frontend/package*.json ./
RUN npm ci

COPY src/calobot/telemetry/frontend/ ./
RUN npm run build


# Stage 2: Build Python virtual environment
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src/ src/
# Copy the compiled static assets from the frontend build stage
COPY --from=frontend-builder /build/dist /app/src/calobot/telemetry/frontend/dist

COPY alembic.ini README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# Stage 3: Python runtime
FROM python:3.12-slim AS runtime

# Single-replica correctness constraint: see the "single-writer" comment in
# stack.yml. This image assumes it is the only writer to /data.
RUN groupadd --gid 1000 calobot && \
    useradd --uid 1000 --gid calobot --create-home --shell /usr/sbin/nologin calobot

WORKDIR /app

COPY --from=builder --chown=calobot:calobot /app/.venv /app/.venv
COPY --from=builder --chown=calobot:calobot /app/src /app/src
COPY --from=builder --chown=calobot:calobot /app/alembic.ini /app/alembic.ini

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    CALOBOT_DATABASE_PATH=/data/calobot.db

RUN mkdir -p /data /tmp/matplotlib && chown -R calobot:calobot /data /tmp/matplotlib

VOLUME ["/data"]

USER calobot

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import pathlib,sys; sys.exit(0 if pathlib.Path('/data/calobot.db').exists() else 1)"

ENTRYPOINT ["python", "-m", "calobot.main"]
