# ADR-0058: nginx stays the one entry point, behind one Route or Ingress

Date: 2026-11-14
Status: Accepted

## Context

Wingman is three services behind one hostname: day1 and day2 (FastAPI) and
the web (Next.js). The chart's one Route (or, off OpenShift, one Ingress)
sends every request to nginx (`wingman-nginx`, port 8080), and nginx splits
them by path (`templates/nginx-configmap.yaml`):

| Path | Goes to |
|---|---|
| `/api/auth/`, `/api/day1/`, `/api/webhooks/` (GitLab's) | day1 |
| `/api/day2/` | day2 |
| everything else | the web |

nginx also does the work no service does for itself:

- **gzip** (ADR-0041): JSON, problem JSON, JavaScript, CSS, text and SVG,
  level 5, above 1 KiB, never `text/event-stream`. The cluster list went from
  188 KiB to 6 KiB on the wire, and day1's conditional reads use weak `ETag`s
  because nginx gzips their bytes (`wingman_day1.api.conditional`).
- **Timeouts:** 10 s to connect, 60 s to read, and 130 s for one path,
  `/api/day1/clusters/<name>/upgrade-targets`, which waits on the
  orchestrator (ADR-0055; the Route gets the same 130 s when upgrades are on).
- **Body size:** 10 MiB (`client_max_body_size`), for the large YAML edits,
  with 16 KiB proxy buffers.
- **Streams:** day1's live status is server-sent events; day1 sends
  `X-Accel-Buffering: no`, so nginx passes each event through as it comes.
- The forwarded headers (`Host`, `X-Real-IP`, `X-Forwarded-For`,
  `X-Forwarded-Proto`), and no route to `/metrics`, which stays on each
  service's own port (ADR-0010).

The quality bar's chart gaps (`docs/notes/2026-11-07-quality-bar-repo.md`
§5 and §7.5) put nginx itself in question: it ran `nginx:latest` from Docker
Hub, its liveness probe asked the web through it, and when day1 or day2 did
not answer, its 502 and 504 were HTML pages where the web expects an RFC 9457
problem (ADR-0004; ADR-0054 met them in a GitLab outage). The question was
whether to keep it at all.

server-scan, the quality bar (convention 1), answered it for itself. Its
`deploy/README.md` ("The frontend"): exactly one Route exists, and the
frontend's nginx forwards `/api/` and `/health/` to the API Service in
the cluster. That one Route "replaced a set of five path-scoped API Routes on
2026-09-12, at the operator's request". Its nginx is Red Hat's
`registry.access.redhat.com/ubi9/nginx-124` (`deploy/air-gapped-images.txt`),
which the air gap already mirrors.

## Decision

- **nginx stays the one entry point**, behind one Route (OpenShift) or one
  Ingress, as today. The path table, gzip, the timeouts, the body size and the
  streams stay in nginx, in one file.
- **It runs Red Hat's UBI nginx**, `registry.access.redhat.com/ubi9/nginx-124`,
  pinned by tag and by the digest of its manifest list, like the UBI base
  images (`docs/ops/images.md`). The image's own command prints a usage note
  (it is an S2I builder), so the chart starts `nginx` itself.
- **nginx answers its own health**, `/healthz`, for its liveness and
  readiness probes. It no longer asks the web: a web that is down no longer
  restarts nginx, and the API paths keep working.
- **nginx's own errors on `/api/` are problems.** When day1 or day2 cannot be
  reached (502), is unavailable (503) or does not answer in time (504), nginx
  answers `application/problem+json`, code `DEPENDENCY_UNAVAILABLE`, with the
  status it met and a detail naming the service. A service's own answers,
  errors included, pass through untouched (`proxy_intercept_errors` stays off),
  so Wingman's `GIT_UNAVAILABLE` still reaches the page as Wingman wrote it.
  Pages (`/`) keep nginx's HTML error page.
- **It logs to the container**: errors to stderr, requests to stdout; no
  version in its `Server` header or error pages (`server_tokens off`); it
  writes nothing but `/tmp`.

## Alternatives rejected

- **One path-scoped Route per service** (`/api/day1` to day1, `/api/day2` to
  day2, `/` to the web). The operator asked server-scan for the opposite. gzip
  would move into each service, and the timeouts into each Route's annotations
  and each Ingress controller's own; the path table would exist twice, once
  for the Route and once for the Ingress, each in its own syntax.
- **Next.js proxies the APIs** (rewrites or route handlers in production).
  Node, with the web's 200m of CPU, would sit on the path of every API call,
  of every live-status stream for as long as a page is open, and of GitLab's
  webhooks, which would then fail whenever the web does.

## Consequences

- **Route stickiness does not reach day1.** The Route's cookie pins a person
  to an nginx pod, and nginx proxies to the day1 Service's one ClusterIP, so
  with more than one day1 replica a person's requests spread over them, each
  with its own cache. Accepted: the default is one replica, and
  [shared-cache.md](../ideas/shared-cache.md) has the two ways to add per-person
  affinity if that changes.
- nginx is one more image to mirror, by digest (`docs/ops/images.md`).
- The path table has a second copy for development only: `next dev`'s
  rewrites (`apps/web/next.config.ts`) mirror it when the services run
  locally. A new API prefix goes in both.
- The web's API client reads nginx's 502 and 504 like any problem: the person
  sees which service did not answer instead of "API error 502" and an HTML
  page.

## Verification

- `tests/repo/test_chart_nginx.py` renders the chart and checks the
  configuration: each path to its service, the 130 s path, gzip without
  `text/event-stream`, no `/metrics` location, `/healthz` and the probes on
  it, the `/api/` problem for 502, 503 and 504 and none on `/`, the logs and
  `server_tokens off`, and the image by tag and digest.
- The image under OpenShift's restricted settings, with podman
  (`docs/ops/images.md`, "The nginx image"): `nginx -t` passes on the rendered
  configuration; `/healthz` answers 200; `/api/day1/…` with no day1 answers 502
  and `/api/day2/…` with an unreachable day2 answers 504, both
  `application/problem+json`.
