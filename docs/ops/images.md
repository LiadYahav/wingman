# Images

Wingman ships three images: `wingman-day1`, `wingman-day2` and `wingman-web`.
Every one is built from the **repository root**, so it can read the two
lockfiles, and everything inside it comes from them: nothing is resolved at
build time (ADR-0003). CI builds all three on every pull request without
pushing, and publishes them from `main` (ADR-0030, ADR-0031).

## What CI publishes

Every commit on `main` is a release. Its version is computed from the
Conventional Commit subjects since the previous release (ADR-0031), so it
gets a git tag `v<X.Y.Z>`, a GitHub release with notes, and these image tags
on `ghcr.io/<owner>/wingman-<name>`, linux/amd64:

| Tag | Example | Moves? |
|---|---|---|
| `<X.Y.Z>` | `3.0.1` | never |
| `<X.Y>` | `3.0` | yes, to the newest `3.0.z` |
| `<X>` | `3` | yes, to the newest `3.y.z` |
| `latest` | | yes, to the newest release |
| `sha-<short sha>` | `sha-1b7c805` | never |

**Deploy a full version** (`--set image.<name>.tag=3.0.1`), the same for all
three images: it is the only tag that names one build and that the release
notes describe. Never deploy `latest`, `3.0` or `3` (they move), and never a
`sha-` tag (it names no release). The image tag has no `v`; the git tag and
the release do (`v3.0.1`). Releases up to `v3.0.0` were cut by the retired
`VERSION` file and their images are tagged `v3.0.0` and `<short sha>`.

Each pushed image carries:

- OCI labels (`org.opencontainers.image.{title,description,source,url,version,revision,created}`)
  from `docker/metadata-action`; `version` is the release, `X.Y.Z`.
- An SBOM and BuildKit provenance as attestation manifests in the image index:
  `docker buildx imagetools inspect <image>:<tag> --format '{{ json .SBOM }}'`.
- Signed SLSA build provenance (Sigstore, `actions/attest`), stored by GitHub and
  pushed to the registry beside the image:
  `gh attestation verify oci://ghcr.io/<owner>/wingman-web:3.0.1 --owner <owner>`.

The build arguments `VERSION` (the release, `X.Y.Z`; `dev` by default) and
`COMMIT` reach `wingman_build_info` (ADR-0010) and the labels. No file holds
the version: CI computes it and passes it in.

## Building locally

A development build is named by its commit; it reports version `dev`:

```bash
SHA=$(git rev-parse --short HEAD)
podman build -f apps/web/Dockerfile          -t wingman-web:$SHA  .
podman build -f apps/day1-service/Dockerfile -t wingman-day1:$SHA .
podman build -f apps/day2-service/Dockerfile -t wingman-day2:$SHA .
```

A production build by hand (amd64, for example inside the air gap) builds a
release: check out its git tag and name the images by its version, as CI does:

```bash
git checkout v3.0.1
VERSION=3.0.1
docker buildx build --platform linux/amd64 -f apps/day1-service/Dockerfile \
  --build-arg VERSION=$VERSION --build-arg COMMIT=$(git rev-parse HEAD) -t wingman-day1:$VERSION . --load
# the same for apps/day2-service/Dockerfile (wingman-day2) and apps/web/Dockerfile (wingman-web)
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
