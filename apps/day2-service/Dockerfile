# Build context: the repository root.
#   docker build -f apps/day2-service/Dockerfile -t wingman-day2 .
#
# Installs wingman-core and the service from their pyprojects, whose direct
# dependencies are pinned exactly (ADR-0003). Installing every transitive
# dependency from uv.lock (hash-pinned per-service exports) is the next step of
# the foundation, tracked in CLAUDE.md.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

FROM base AS build
WORKDIR /build
COPY packages/wingman-core /build/wingman-core
COPY apps/day2-service /build/day2-service
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install /build/wingman-core /build/day2-service

FROM base AS runtime
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Numeric, non-root, group 0: OpenShift runs the image as an arbitrary UID in group 0.
RUN useradd --uid 10001 --gid 0 --no-create-home --shell /usr/sbin/nologin wingman
USER 10001
EXPOSE 8002
CMD ["uvicorn", "wingman_day2.main:app", "--host", "0.0.0.0", "--port", "8002"]
