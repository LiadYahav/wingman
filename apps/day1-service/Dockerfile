# The Wingman day1 image, built from the repository root:
#
#   podman build -f apps/day1-service/Dockerfile -t wingman-day1:$(git rev-parse --short HEAD) .
#
# Nothing is resolved at build time (ADR-0003, docs/ops/images.md): the
# third-party packages come from uv.lock's hash-pinned export, and the
# workspace members are built from this checkout with the hash-pinned build
# backend, with no package index at all.

ARG TARGETARCH
# Air gap: point this at the internal artifact store; the checksums below
# still decide which bytes are accepted.
ARG PYTHON_BUILD_STANDALONE_URL=https://github.com/astral-sh/python-build-standalone/releases/download

FROM registry.access.redhat.com/ubi9/ubi-minimal:9.8@sha256:4b79c93106c14ad1c234907f83441ff0e4f8d24e78426a36e159098e9f7e6fa5 AS base

# CPython 3.13 from python-build-standalone (UBI 9 ships no 3.13), checked
# against the release's SHA256SUMS. One stage per architecture, since each
# tarball has its own checksum; only the target's is built.
FROM base AS python-amd64
ARG PYTHON_BUILD_STANDALONE_URL
ADD --checksum=sha256:cbda6f7767884fc456860b11fd184391a9320cae00a86c0f49a1c7ac6e236f7a \
    ${PYTHON_BUILD_STANDALONE_URL}/20261021/cpython-3.13.17+20261021-x86_64-unknown-linux-gnu-install_only.tar.gz /tmp/python.tar.gz

FROM base AS python-arm64
ARG PYTHON_BUILD_STANDALONE_URL
ADD --checksum=sha256:616ab0a31b2a3f28119582f4d1943e342f13bac2ec5a8dfe8572c3c0bcadb95a \
    ${PYTHON_BUILD_STANDALONE_URL}/20261021/cpython-3.13.17+20261021-aarch64-unknown-linux-gnu-install_only.tar.gz /tmp/python.tar.gz

FROM python-${TARGETARCH} AS python
RUN microdnf install -y --setopt=install_weak_deps=0 tar gzip \
    && tar -xzf /tmp/python.tar.gz -C /opt \
    && rm /tmp/python.tar.gz

FROM base AS build
COPY --from=python /opt/python /opt/python
ENV PATH=/opt/python/bin:$PATH \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
COPY deploy/python/requirements-day1.txt deploy/python/requirements-build.txt /tmp/
# 1. Third-party packages, only from the export: every one hash-checked,
#    none resolved (--no-deps).
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --require-hashes --no-deps -r /tmp/requirements-day1.txt
# 2. The pinned build backend, in a venv of its own that never ships.
RUN python3 -m venv /opt/build \
    && /opt/build/bin/pip install --require-hashes --no-deps -r /tmp/requirements-build.txt
# 3. The workspace members this service imports, as wheels built from this
#    checkout, installed with --no-deps from those wheels alone.
COPY packages/wingman-core /src/packages/wingman-core
COPY apps/day1-service /src/apps/day1-service
RUN /opt/build/bin/pip wheel --no-deps --no-build-isolation --no-index --wheel-dir /wheels \
        /src/packages/wingman-core /src/apps/day1-service \
    && /opt/venv/bin/pip install --no-deps --no-index /wheels/*.whl

FROM base AS runtime
COPY --from=python /opt/python /opt/python
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
# OpenShift's arbitrary UID runs in group 0: give the group the owner's rights.
RUN chgrp -R 0 /app && chmod -R g=u /app
USER 1001
EXPOSE 8001

# Last, so a new version or commit rebuilds only these layers. The service
# reads them for wingman_build_info (ADR-0010).
ARG VERSION=dev
ARG COMMIT=unknown
ENV WINGMAN_VERSION=${VERSION} \
    WINGMAN_COMMIT=${COMMIT}
LABEL org.opencontainers.image.title="wingman-day1" \
      org.opencontainers.image.description="Wingman day1 service: hosted cluster provisioning" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${COMMIT}"

CMD ["uvicorn", "wingman_day1.main:app", "--host", "0.0.0.0", "--port", "8001"]
