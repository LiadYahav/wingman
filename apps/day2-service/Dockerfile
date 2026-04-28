# Build context: repo root (cluster-platform/)
# Build with: docker build -f apps/day2-service/Dockerfile -t wingman-day2 .

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── Dependency stage ───────────────────────────────────────────────────────────
FROM base AS deps
WORKDIR /build

COPY packages/shared-python /build/shared-python
RUN pip install --no-cache-dir /build/shared-python

RUN pip install --no-cache-dir \
    "fastapi>=0.115,<1" \
    "uvicorn[standard]>=0.30,<1"

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM base AS runtime
WORKDIR /app

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn

COPY apps/day2-service/src /app/src

RUN useradd --system --no-create-home --shell /bin/false wingman
USER wingman

EXPOSE 8002
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
