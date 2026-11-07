# Images

Wingman ships three images: `wingman-day1`, `wingman-day2` and `wingman-web`.
Every one is built from the **repository root**, so it can read the two
lockfiles, and everything inside it comes from them: nothing is resolved at
build time (ADR-0003). CI builds all three on every pull request without
pushing, and publishes them from `main` (ADR-0030).

## What CI publishes

`ghcr.io/<owner>/wingman-<name>`, linux/amd64:

| Tag | When | Moves? |
|---|---|---|
| `<short sha>` | every commit on `main` | never |
| `latest` | every commit on `main` | yes; never deploy it |
| `v<VERSION>` | the commit that cuts that release (VERSION names a version that does not exist yet) | never |

Deploy a `v<VERSION>` or a `<short sha>` (`--set image.<name>.tag=...`).

Each pushed image carries:

- OCI labels (`org.opencontainers.image.{title,description,source,url,version,revision,created}`)
  from `docker/metadata-action`; `version` is the release tag, or the short sha.
- An SBOM and BuildKit provenance as attestation manifests in the image index:
  `docker buildx imagetools inspect <image>:<tag> --format '{{ json .SBOM }}'`.
- Signed SLSA build provenance (Sigstore, `actions/attest`), stored by GitHub and
  pushed to the registry beside the image:
  `gh attestation verify oci://ghcr.io/<owner>/wingman-web:<tag> --owner <owner>`.

The build arguments `VERSION` and `COMMIT` reach `wingman_build_info`
(ADR-0010) and the labels.

## Building locally

```bash
SHA=$(git rev-parse --short HEAD)
podman build -f apps/web/Dockerfile          -t wingman-web:$SHA  .
podman build -f apps/day1-service/Dockerfile -t wingman-day1:$SHA .
podman build -f apps/day2-service/Dockerfile -t wingman-day2:$SHA .
# production (amd64) with docker: docker buildx build --platform linux/amd64 -f <file> -t <tag> . --load
```

Each Dockerfile has its own allowlist, `<Dockerfile>.dockerignore` beside it
(BuildKit and podman both read it), so a file reaches an image only when it is
named there.

## Base images

Red Hat UBI, which the air-gapped mirror carries (as for server-scan), pinned by
tag **and** by the digest of the multi-arch manifest list, so the same line
builds amd64 in CI and arm64 on a laptop:

| Image | Used by |
|---|---|
| `registry.access.redhat.com/ubi9/nodejs-24:9.8@sha256:8783eefc…` | web, build stage |
| `registry.access.redhat.com/ubi9/nodejs-24-minimal:9.8@sha256:da724df0…` | web, runtime |
| `registry.access.redhat.com/ubi9/ubi-minimal:9.8@sha256:4b79c931…` | day1, day2 |
| python-build-standalone `cpython-3.13.17+20261021` (`ADD --checksum`) | day1, day2 (UBI 9 has no Python 3.13) |

**Bumping a base image** (part of "Keeping CI current" in CLAUDE.md):

```bash
# the digest of the manifest list a tag points at now
curl -sI -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
  https://registry.access.redhat.com/v2/ubi9/nodejs-24/manifests/9.8 | grep -i docker-content-digest
# or: skopeo inspect --raw docker://registry.access.redhat.com/ubi9/nodejs-24:9.8 | sha256sum
```

Replace the tag and the digest together, build the image, and run it.
**Bumping CPython**: take both `install_only` checksums from the release's
`SHA256SUMS` (`https://github.com/astral-sh/python-build-standalone/releases/download/<release>/SHA256SUMS`)
and replace the version, the release and both checksums.

**Air gap:** mirror each image by digest (`skopeo copy --all docker://<image>@sha256:… docker://<mirror>/…`);
a digest-pinned `FROM` resolves through the registry mirror configuration
(registries.conf, or an ImageDigestMirrorSet on OpenShift) unchanged. Point
`PYTHON_BUILD_STANDALONE_URL` at the internal artifact store: the checksum still
decides which bytes are accepted. Python packages come from
`deploy/python/*.txt` (`pip download --require-hashes --no-deps -r … -d wheelhouse`
fills a mirror); npm packages from the root `package-lock.json`.

## The web image

`apps/web/Dockerfile`: `npm ci --ignore-scripts` against the root
`package-lock.json`, `next build`, then the standalone server
(`node apps/web/server.js`, port 3000) on the minimal Node image as UID 1001,
with `chgrp -R 0 /app && chmod -R g=u /app` for OpenShift's arbitrary UID.

## The Python images: the pattern day1 and day2 follow

The service images install from the hash-pinned exports that
`scripts/export-requirements.sh` writes from `uv.lock` (CI fails when they
drift):

1. third-party packages: `pip install --require-hashes --no-deps -r deploy/python/requirements-<service>.txt`;
2. the build backend, into a throwaway venv: `pip install --require-hashes --no-deps -r deploy/python/requirements-build.txt`;
3. the workspace members the service imports: wheels built from the checkout
   with that backend (`pip wheel --no-deps --no-build-isolation --no-index`),
   installed with `pip install --no-deps --no-index`.

No step reads a package index without a hash, so the image is the lock. Step 2
exists because `pip install --no-deps <member dir>` alone would download an
unpinned hatchling to build the member.

`apps/day1-service/Dockerfile`, as verified with podman against the legacy
day1 service (the rewrite changes only the lines marked `# per service`):

```dockerfile
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
COPY packages/shared-python /src/packages/shared-python
COPY apps/day1-service /src/apps/day1-service
RUN /opt/build/bin/pip wheel --no-deps --no-build-isolation --no-index --wheel-dir /wheels \
        /src/packages/shared-python /src/apps/day1-service \
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

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

`apps/day1-service/Dockerfile.dockerignore`:

```
**
!deploy/python/requirements-day1.txt
!deploy/python/requirements-build.txt
!packages/shared-python/
!packages/shared-python/**
!packages/wingman-core/
!packages/wingman-core/**
!apps/day1-service/
!apps/day1-service/**
**/tests
**/__pycache__
**/.pytest_cache
**/.ruff_cache
**/.venv
**/Dockerfile*
```

What changes per service, and with the rewrite:

| | day1 | day2 |
|---|---|---|
| export | `requirements-day1.txt` | `requirements-day2.txt` |
| service directory | `apps/day1-service` | `apps/day2-service` |
| port | 8001 | 8002 |
| title, description | `wingman-day1`, hosted cluster provisioning | `wingman-day2`, charts on clusters |

- **Members** (step 3 and the `COPY` lines): every workspace member the
  service depends on. After the rewrite that is `packages/wingman-core` and the
  service; drop `packages/shared-python` once nothing imports it. Order does
  not matter: nothing resolves.
- **CMD**: the rewritten service's ASGI app (the legacy one is `src.main:app`,
  because its wheel installs a top-level package named `src`).
- **`WINGMAN_VERSION` / `WINGMAN_COMMIT`**: rename to whatever the service's
  settings read for `wingman_build_info`; keep them as the last layers.
- After any `pyproject.toml` change: `uv lock`, then `scripts/export-requirements.sh`,
  and commit both. The `images` job builds every image on every pull request,
  with `VERSION` and `COMMIT` build arguments, so a pattern that breaks fails there.
