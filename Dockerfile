FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./


FROM base AS runtime
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv sync --locked --no-dev
RUN useradd --system --no-create-home relay
USER relay
EXPOSE 8000
# Apply migrations, then serve. `exec` lets uvicorn receive SIGTERM.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn webhook_relay.main:create_app --factory --host 0.0.0.0 --port 8000"]


FROM base AS test
RUN uv sync --locked --no-install-project
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY tests ./tests
RUN uv sync --locked
CMD ["pytest"]
