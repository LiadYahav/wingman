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

`apps/day1-service/Dockerfile` and `apps/day2-service/Dockerfile` follow it,
each with an allowlist `Dockerfile.dockerignore` beside it. The two differ only
in the export, the service directory, the port (8001, 8002), the title and
the `CMD` (`uvicorn wingman_day1.main:app`, `wingman_day2.main:app`); keep
everything else identical. Both run as UID 1001 in group 0 and read
`WINGMAN_VERSION` and `WINGMAN_COMMIT` (the `VERSION` and `COMMIT` build
arguments, set last so a new commit rebuilds only those layers) for
`wingman_build_info`, so `WingmanVersionSkew` compares like with like.

Verified on 2026-11-07 with podman: both build with no unhashed download, and
each image, run against the local GitLab, answers `/health/ready` with
`gitlab: ok`, reports `component`, `version` and `commit` on `/metrics`, and
serves its API (day1 lists the clusters after a dev login; day2 lists them for
a viewer token).

After any `pyproject.toml` change: `uv lock`, then `scripts/export-requirements.sh`,
and commit both. The `images` job builds every image on every pull request,
with `VERSION` and `COMMIT` build arguments, so a pattern that breaks fails there.
