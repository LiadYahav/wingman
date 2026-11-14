# Images

Wingman ships three images: `wingman-day1`, `wingman-day2` and `wingman-web`.
The chart runs a fourth it does not build, Red Hat's UBI nginx ([The nginx
image](#the-nginx-image)). Every one of the three is built from the **repository root**, so it can read the two
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

Replace the tag and the digest together, build the image, and run it. The
chart's nginx is pinned the same way, in the chart ([The nginx image](#the-nginx-image)).
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

## The nginx image

The chart's nginx, the one entry point (ADR-0058), is Red Hat's UBI nginx and
no image of Wingman's: `registry.access.redhat.com/ubi9/nginx-124:9.8`, pinned
by the digest of its manifest list (amd64, arm64, s390x, ppc64le), `image.nginx`
in `deploy/helm/wingman/values.yaml`. It is nginx 1.24. The chart mounts its
own `nginx.conf` over the image's and starts `nginx -e /dev/stderr -g 'daemon
off;'`: the image is an S2I builder whose own command prints a usage note.

**Re-resolving the digest** (CLAUDE.md, "Keeping CI current", item 5): ask the
registry for the manifest list the tag points at now, and check its digest
against the bytes:

```bash
curl -sS -D headers.txt -o list.json \
  -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
  https://registry.access.redhat.com/v2/ubi9/nginx-124/manifests/9.8
grep -i docker-content-digest headers.txt; shasum -a 256 list.json   # the same digest twice
```

Set the tag and the digest in `values.yaml` and in the copy in
`templates/_helpers.tpl` (`wingman.nginxImage`) together:
`tests/repo/test_chart_nginx.py` fails until the two agree. Then run the check
below. Resolved on 2026-11-14: `9.8` (the same build as `9.8-1793639597`, built
2026-11-02) at
`sha256:d5cec86a9adf972dbfa0d87b134e7c404706cc1920fc2e6a2b146e290276f219`.

**The check**, in bash, as OpenShift's `restricted-v2` runs it: the chart's
rendered `nginx.conf`, a read-only root with only `/tmp` writable, an arbitrary
UID in group 0, no capabilities, no new privileges.
`--read-only-tmpfs=false` matters: podman otherwise makes `/tmp`, `/var/tmp`
and `/run` writable, which a Kubernetes read-only root does not.

```bash
helm template wingman deploy/helm/wingman -f deploy/helm/wingman/ci/default-values.yaml \
  | uv run python -c 'import sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d["kind"] == "ConfigMap" and d["metadata"]["name"] == "wingman-nginx":
        print(d["data"]["nginx.conf"], end="")' > nginx.conf
img=registry.access.redhat.com/ubi9/nginx-124:9.8@sha256:d5cec86a9adf972dbfa0d87b134e7c404706cc1920fc2e6a2b146e290276f219
run=(--read-only --read-only-tmpfs=false --tmpfs /tmp --user 1000680000:0 --cap-drop ALL
  --security-opt no-new-privileges -v "$PWD/nginx.conf:/etc/nginx/nginx.conf:ro,Z"
  --add-host wingman-day1:127.0.0.1 --add-host wingman-day2:192.0.2.1 --add-host wingman-web:127.0.0.1)
podman run --rm "${run[@]}" "$img" nginx -e /dev/stderr -t
podman run -d --name wingman-nginx-check -p 127.0.0.1:18080:8080 "${run[@]}" "$img" \
  nginx -e /dev/stderr -g 'daemon off;'
curl -i http://127.0.0.1:18080/healthz              # 200 ok
curl -i http://127.0.0.1:18080/api/day1/clusters    # 502, application/problem+json: no day1 listens
curl -i http://127.0.0.1:18080/api/day2/teams       # 504, application/problem+json, after 10 s: day2 unroutable
curl -i http://127.0.0.1:18080/                     # 502, nginx's HTML page: pages keep it
podman rm -f wingman-nginx-check
```

Run on 2026-11-14 with the pin above: all four as commented, `Server: nginx`
with no version, every request on the container's stdout and every error on
its stderr.

**Air gap:** mirror it by digest, every architecture
(`skopeo copy --all docker://registry.access.redhat.com/ubi9/nginx-124:9.8@sha256:… docker://<mirror>/ubi9/nginx-124:9.8`),
and point the chart at the mirror (the chart README's "Images"), or let an
`ImageDigestMirrorSet` redirect the digest on OpenShift.

## Read-only root

The chart runs every container with `readOnlyRootFilesystem: true` (the chart
README's "Security context"). The paths a process writes, each an `emptyDir`:

| Image | Writable | Why |
|---|---|---|
| nginx | `/tmp` | its pid and temp files (`nginx.conf` puts them there) |
| `wingman-web` | `/app/apps/web/.next/cache` | Next.js's runtime cache: the pages never write it, its image optimizer (`/_next/image`) does |
| `wingman-day1`, `wingman-day2` | nothing | GitLab's archives are read in memory; no temp file, no form upload, no bytecode (`PYTHONDONTWRITEBYTECODE`) |

Checked on 2026-11-14 on the released 3.30.0 images (amd64, emulated on an
arm64 laptop) and the nginx check's image, in one podman pod, each container
with the flags above and only its own paths writable, and the fake backend
(`WINGMAN_ENVIRONMENT=development WINGMAN_GIT_BACKEND=fake`,
`DAY1_FAKE_FLEET=true`, dev login; the repository's `dev/` mounted read-only at
`/opt/dev`, where the fakes look for their fixtures). day1 and day2 became
ready with nothing writable. Through nginx: a dev login, the cluster list, the
flavors, the sites, a cluster and its nodes, day2's teams and add-ons (both
services counted `read_archive` ok), gzip, the live-status stream unbuffered,
the web's pages and its static files. No EROFS, EACCES or traceback in any
log. The web without its `emptyDir` renders every page, but a request to
`/_next/image` logs `unhandledRejection: ENOENT ... mkdir '/app/apps/web/.next/cache'`.

A new write (a temp file, a cache directory) needs an `emptyDir` in the chart
and its path in the writable table of `tests/repo/test_chart_hardening.py`.
