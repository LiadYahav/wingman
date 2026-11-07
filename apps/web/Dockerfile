# The Wingman web image. Built from the repository root, so `npm ci` installs
# exactly what the root package-lock.json names (one lockfile, ADR-0003):
#
#   podman build -f apps/web/Dockerfile -t wingman-web:$(git rev-parse --short HEAD) .
#
# The context is filtered by apps/web/Dockerfile.dockerignore (an allowlist).
# Base images are Red Hat UBI, which the air-gapped mirror carries (as in
# server-scan), pinned by tag and by multi-arch digest; docs/ops/images.md
# says how to bump them.

FROM registry.access.redhat.com/ubi9/nodejs-24:9.8@sha256:8783eefc2f87113865eb24478fdd9351dd34c3928827895f319d57a3165fff09 AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /opt/app-root/src

# The manifests first, so the dependency layer is cached until they change.
# --ignore-scripts: no package's install script runs; the native pieces Next
# needs (SWC, sharp, lightningcss) are prebuilt optional dependencies.
COPY --chown=1001:0 package.json package-lock.json ./
COPY --chown=1001:0 apps/web/package.json apps/web/
RUN npm ci --ignore-scripts --no-audit --no-fund

COPY --chown=1001:0 apps/web/ apps/web/
RUN npm run build --workspace=web

FROM registry.access.redhat.com/ubi9/nodejs-24-minimal:9.8@sha256:da724df0db4baceb0b89ebdc160dfe330fe3b215925742ee9e65efdfc6038850 AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app

# The standalone server traces from the repository root, so it lives at
# apps/web/server.js; static assets and public/ are not traced and are copied.
COPY --from=build --chown=1001:0 /opt/app-root/src/apps/web/.next/standalone/ ./
COPY --from=build --chown=1001:0 /opt/app-root/src/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=1001:0 /opt/app-root/src/apps/web/public ./apps/web/public

# OpenShift runs the container as an arbitrary UID in group 0: give the group
# the owner's permissions, or Next cannot write its cache (server-scan's
# "arbitrary UID trap").
USER 0
RUN chgrp -R 0 /app && chmod -R g=u /app
USER 1001

EXPOSE 3000

# Last, so a new version or commit rebuilds only this layer. CI's
# docker/metadata-action adds the source, url and created labels.
ARG VERSION=dev
ARG COMMIT=unknown
LABEL org.opencontainers.image.title="wingman-web" \
      org.opencontainers.image.description="Wingman web app" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${COMMIT}"

CMD ["node", "apps/web/server.js"]
