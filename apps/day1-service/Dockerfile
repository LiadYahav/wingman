# Wingman day1. Build context: the repository root.
#   docker build -f apps/day1-service/Dockerfile -t wingman-day1:$(git rev-parse --short HEAD) .
#
# Installs exactly what uv.lock pins (ADR-0003): `uv sync --locked`, no dev
# tools, the workspace packages (wingman-core, wingman-day1-service) installed
# non-editable into one virtualenv that the runtime stage copies.

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src

# uv checks the lock against every workspace member's manifest, so all of them
# are copied; only day1's dependencies are installed.
COPY pyproject.toml uv.lock .python-version ./
COPY packages/wingman-core/pyproject.toml packages/wingman-core/
COPY packages/shared-python/pyproject.toml packages/shared-python/
COPY apps/day2-service/pyproject.toml apps/day2-service/
COPY apps/day1-service/pyproject.toml apps/day1-service/
RUN uv sync --locked --no-dev --no-install-workspace --package wingman-day1-service

COPY packages/wingman-core/src packages/wingman-core/src
COPY apps/day1-service/src apps/day1-service/src
RUN uv sync --locked --no-dev --no-editable --package wingman-day1-service

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH
COPY --from=build /app/.venv /app/.venv
WORKDIR /app

# A numeric non-root user in group 0, so OpenShift's arbitrary UID works too.
USER 1001:0
EXPOSE 8001
CMD ["uvicorn", "wingman_day1.main:app", "--host", "0.0.0.0", "--port", "8001"]
