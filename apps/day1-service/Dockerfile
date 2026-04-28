# Build context: repo root (cluster-platform/)
# Build with: docker build -f apps/day1-service/Dockerfile -t wingman-day1 .

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── Dependency stage ───────────────────────────────────────────────────────────
FROM base AS deps
WORKDIR /build

# 1. Install shared library and its dependencies (python-gitlab, ruamel.yaml, etc.)
COPY packages/shared-python /build/shared-python
RUN pip install --no-cache-dir /build/shared-python

# 2. Install service-specific dependencies
RUN pip install --no-cache-dir \
    "fastapi>=0.115,<1" \
    "uvicorn[standard]>=0.30,<1" \
    "kubernetes>=26.1.0"

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM base AS runtime
WORKDIR /app

# Copy installed packages from deps stage (avoids dev tools in final image)
COPY --from=deps /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy service source preserving the package structure:
# main.py uses relative imports (from .config import ...) so it must run
# as "src.main" module from /app, not as "main" from /app/src.
COPY apps/day1-service/src /app/src

RUN useradd --system --no-create-home --shell /bin/false wingman
USER wingman

EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
