# ADR-0052: Quick Links is a launcher page: every cluster's ArgoCD and console, generated, and the team's links from a ConfigMap, checked by day1

Date: 2026-11-12
Status: Accepted; amended 2026-11-13 (no status dots and no ArgoCD counts: Wingman lists the links and never calls them)

## Context

Wingman runs on the hub cluster, and the hub and every MCE have their own
OpenShift GitOps (ArgoCD), each at
`https://openshift-gitops-server-openshift-gitops.apps.<cluster>.<domain>`.
The team keeps a homepage dashboard (gethomepage) with those links by hand,
next to its other links (GitLab, Confluence, Grafana, DC systems): sections
of cards with an icon, a description, a status dot and, for an ArgoCD, its
applications' counts. The user asked for the same inside Wingman
(decision 20 of the single-pane plan), as a sidebar entry; first called
"GitOps", renamed **Quick Links** the same day (the generated ArgoCD cards
are only part of it).

What has to hold: the environment is disconnected (no CDN, so no remote
icons); the browser cannot ping dozens of origins (CORS, and it should not
hold ArgoCD tokens); the links change more often than Wingman is released;
and the page must keep working when what it links to does not, since that
is when it is needed.

## Decision

- **A page, `/quick-links`, admins only** (decision 13: like the other new
  areas, until RBAC). Both routes take `AdminUser` (one route since 2026-11-13: see Amendments); the sidebar hides the
  entry from viewers. The API is `docs/notes/2026-11-12-quick-links-api.md`.
- **Generated cards.** One per cluster: the hub Wingman runs on
  (`QUICK_LINKS_HUB_NAME`; none when empty), then every MCE folder of the
  day1 repo, one section per site. A card opens the cluster's ArgoCD and has
  its console beside it, each with its own dot (the dots: *Superseded 2026-11-13: see Amendments.*). The addresses come from two
  URL templates with `{cluster}` and `{domain}`
  (`QUICK_LINKS_ARGOCD_URL_TEMPLATE`, `QUICK_LINKS_CONSOLE_URL_TEMPLATE`,
  checked at start-up); the domain is `QUICK_LINKS_DOMAIN`, else
  `MCE_API_DOMAIN` (the MCE's API is `api.<mce>.<domain>`, so its routes are
  `apps.<mce>.<domain>`), and the hub's `QUICK_LINKS_HUB_DOMAIN`, else that.
  A cluster that does not follow the templates gets its own addresses in the
  links file's `clusters` map. Quick Links builds no per-MCE API address of
  its own: that is the MCE placement work's (ADR-0050, in progress).
- **The team's links are a file the chart renders.** `quickLinks.sections`
  and `quickLinks.clusters` become the ConfigMap `wingman-quick-links`,
  mounted in day1 as a directory (never `subPath`). day1 re-reads it on every
  page load, so an edit (`helm upgrade`, `oc edit`) shows within the
  kubelet's sync with no restart, and it is in no checksum annotation. Each
  link has a name, a URL, a description, an icon key, an optional `ping`
  URL (or `false`) and an optional `argocd` token key (those two: *Superseded 2026-11-13: see Amendments.*); a section has a name,
  a description and its columns (1 to 6).
- **A bad file is a problem on the page, never a failure.** Not YAML or not a
  mapping: no team links, and the page says why. A link without a name or an
  http(s) URL is skipped, a section without a name or links too, an unknown
  key (`href`) is named and ignored, a bad icon or `ping` falls back (`ping`: *Superseded 2026-11-13: see Amendments.*); every
  one is a line naming the section and the link. GitLab down drops the MCE
  cards with a problem and keeps the rest.
- *Superseded 2026-11-13: see Amendments.* **day1 checks the links; the browser never does.** A port (`LinkProbe`),
  an httpx adapter and a fake (ADR-0001). `HEAD`, then `GET` without its
  body when `HEAD` answers 405 or 501; redirects not followed; no credential
  sent; one deadline (`QUICK_LINKS_TIMEOUT_SECONDS`, 3) per check; at most
  `QUICK_LINKS_CONCURRENCY` (8) at once; TLS verified per
  `QUICK_LINKS_SSL_VERIFY` as the other adapters do. Up: 2xx, 3xx, 401, 403.
  Down: any other answer, no answer, no connection. Unknown: TLS could not
  be verified. The reason is always given and shown on hover.
- *Superseded 2026-11-13: see Amendments.* **On read, cached, shared.** Checks run when the page reads
  `GET /quick-links/status`, not on a timer: nothing is called while nobody
  looks. Each URL's reading is kept `QUICK_LINKS_STATUS_TTL_SECONDS` (60) in
  the per-replica cache, and for as long again it is answered while one
  check refreshes it in the background; concurrent reads share one check
  (the cache's single flight). A failed check is a reading and is kept like
  one. This is not GitLab data, so ADR-0011's minute does not bound it: a dot
  is at most two TTLs old and carries `checked_at`.
- *Superseded 2026-11-13: see Amendments.* **ArgoCD counts where a token exists.** A Secret (`quickLinks.argocdTokensSecret`,
  key `tokens`, a YAML map of instance to read-only token) is mounted like the
  MCE tokens; an instance is a cluster name for the generated cards or the
  file's `argocd:` key. Only an instance with a token gets counts:
  `GET /api/v1/applications?fields=items.status.sync.status,items.status.health.status`,
  counted by sync (Synced, OutOfSync) and health (Healthy, Progressing,
  Degraded, Missing, Suspended), cached like the checks. A token never
  reaches the browser, an error or a log line. Another port (`ArgoCdApi`),
  adapter and fake.
- *Superseded 2026-11-13: see Amendments.* **Metrics** (ADR-0010): `dependency="link_check"`, `operation="check_link"`
  and `dependency="argocd"`, `operation="list_applications"`, with outcomes
  from the fixed set. Never a URL or an instance as a label.
- **Icons ship with the web.** Brand icons are vendored from simple-icons
  16.36.0 (CC0-1.0; the marks stay their owners' trademarks), 31 of them,
  leaving out those under their own licences (Jenkins, Harbor, Keycloak);
  generic ones are lucide's, already a dependency. A card names its icon by
  key; an unknown key shows a link icon.
- **`DAY1_FAKE_FLEET`** (development): fake checks and counts from
  `dev/fleet-fixtures/quick-links.yaml` (*Superseded 2026-11-13: see Amendments.*), and the demo links file when
  `QUICK_LINKS_FILE` does not exist.

## Alternatives rejected

- **The browser pings each link.** CORS blocks reading most answers, an
  `<img>` or `no-cors` trick tells "reachable from this laptop" at best, and
  ArgoCD's counts need a token the browser must not hold.
- *Superseded 2026-11-13: see Amendments.* **A background timer in day1.** It would call every link of every
  deployment forever, also when nobody has the page open, and on every
  replica. On read with a shared cache costs one check per link per TTL
  while the page is open, and nothing otherwise.
- **The links in Wingman's settings (environment variables) or in Git.** A
  setting per link does not scale and needs a restart; Git would make
  every link change a merge request in a repo the links have nothing to do
  with. A ConfigMap is what operators already edit.
- **The homepage's own `services.yaml` shape** (a list of single-key maps).
  It cannot be checked with clear messages, and its `href`/`widget` fields
  carry secrets inline; the file here is explicit, and names its token by key.
- **One card per link for the generated ones** (an ArgoCD card and a console
  card per MCE, as the homepage has). Twice the cards with the same name; a
  cluster card with both links, each with its own dot, reads better.
- **Icons from a CDN or the simple-icons package.** No CDN in the air gap; the
  package is thousands of icons (and an npm dependency to keep current) for
  the thirty used.
- *Superseded 2026-11-13: see Amendments.* **Counting applications with `?selector=` or the full application list.** The
  full list is megabytes on a large hub; `fields` asks only for the two
  statuses counted.

## Consequences

- Admins get one page with every cluster's ArgoCD and console without
  anyone keeping a list, and the team's other links beside them.
- Turning it on needs nothing: with `MCE_API_DOMAIN` (or `quickLinks.domain`)
  set, every MCE has its card. The hub card needs `quickLinks.hubName`; the
  counts need the tokens Secret (*Superseded 2026-11-13: see Amendments.*); team links need `quickLinks.sections`
  (`docs/upgrade/3.8-to-3.9.md`).
- *Superseded 2026-11-13: see Amendments.* day1 makes outbound requests to every link while the page is open, with
  its own timeout and concurrency; `QUICK_LINKS_STATUS_ENABLED=false` turns
  the dots, and those requests, off.
- A viewer does not see the page until RBAC (the plan's workstream 8,
  ADR-0051 when it is built) says who may.
- Adding a brand icon is a web change (vendored data), not a setting.

## Amendments

**2026-11-13, 3.13.1: no status dots and no ArgoCD counts; Wingman lists the
links and never calls them.** The user, on 2026-11-13: Wingman carries too
much weight, and Quick Links is a launcher page that had grown to about
5,200 lines of code, tests and docs. Two parts of it go, superseding the
decision's checks, cache, counts and their metrics above:

- **The status dots.** day1 called every link on the page with `HEAD`, then
  `GET`, for as long as someone had it open, with its own timeout,
  concurrency and TLS settings and a cache in front. That is outbound
  traffic to dozens of systems, and settings and failure modes of its own,
  for a dot the system it links to shows itself the moment the link is
  opened.
- **The ArgoCD counts.** They needed a read-only token per ArgoCD, in a
  Secret operators had to create, rotate and mount, for numbers each ArgoCD
  shows itself one click away.

Removed: `GET /api/day1/quick-links/status`; the `LinkProbe` and `ArgoCdApi`
ports, their adapters and fakes, the status cache and `count_applications`;
the settings `QUICK_LINKS_STATUS_ENABLED`, `QUICK_LINKS_STATUS_TTL_SECONDS`,
`QUICK_LINKS_TIMEOUT_SECONDS`, `QUICK_LINKS_CONCURRENCY`,
`QUICK_LINKS_SSL_VERIFY` and `QUICK_LINKS_ARGOCD_TOKENS_FILE`; the chart's
`quickLinks.status.*`, `quickLinks.sslVerify` and
`quickLinks.argocdTokensSecret` and the tokens Secret's mount (values that
still set them render, and are ignored: there is no values schema); the
metric values `link_check`/`check_link` and `argocd`/`list_applications`
(`docs/ops/metrics.md`); the fake fleet's `dev/fleet-fixtures/quick-links.yaml`.
A card's links lose `ping` and a card loses `argocd` in
`GET /api/day1/quick-links`. In the links file, `ping` and `argocd` are no
longer read: like any unknown key, each is named on the page and ignored.

Kept as decided: the page and its route, admins only; the generated cards
(the hub, every MCE by site, each with its ArgoCD and console, from the two
URL templates and the domains, and the file's `clusters`); the team's links
file, re-read on every page load; the problems panel; search and `/`; the
vendored icons; the fake fleet's demo links file. The context's "the browser
cannot ping dozens of origins" still holds: now nothing pings them.

## Verification

The 2026-11-13 amendment: `apps/day1-service/tests/unit/domain/test_quick_links.py`
(`ping` and `argocd` named as unknown keys),
`apps/day1-service/tests/api/test_quick_links_api.py` (the cards are links
only; no `/status` route), `tests/repo/test_chart_quick_links.py` (values that
still set the removed keys render and change nothing) and
`apps/web/e2e/tests/quick-links.spec.ts` (plain links; the page asks day1 for
nothing but the cards).


- `apps/day1-service/tests/unit/domain/test_quick_links.py`: the templates,
  the generated sections and overrides, every links-file rule and message,
  the counts, the states (the counts and the states: *Superseded 2026-11-13: see Amendments.*).
- *Superseded 2026-11-13: see Amendments.* `apps/day1-service/tests/unit/infrastructure/test_link_probe.py`: up, down
  and unknown answers, HEAD then GET, no redirects, no credentials, the
  deadline, the concurrency bound, the metrics without a URL label.
- *Superseded 2026-11-13: see Amendments.* `apps/day1-service/tests/unit/infrastructure/test_argocd_api.py`: the one
  call and its fields, the counts, refusals and failures, the token kept
  out of errors, the tokens file.
- `apps/day1-service/tests/unit/infrastructure/test_quick_links_adapters.py`:
  the cache (kept, shared, answered stale while refreshing), the links file,
  the fakes and the demo fixtures (the cache and the fakes: *Superseded 2026-11-13: see Amendments.*).
- `apps/day1-service/tests/unit/application/test_quick_links.py` and
  `apps/day1-service/tests/api/test_quick_links_api.py`: admins only, the
  shapes, GitLab down, a broken file, checks off (checks off: *Superseded 2026-11-13: see Amendments.*).
- `apps/day1-service/tests/unit/test_quick_links_settings.py`: the fallbacks
  and the start-up checks.
- `tests/repo/test_chart_quick_links.py` and `tests/repo/test_chart_env_contract.py`:
  the chart's settings and defaults, values kept from 3.7, the ConfigMap day1
  parses, the mounts, no restart on a links edit.
- `apps/web/e2e/tests/quick-links.spec.ts`: the page (sections, search, `/`,
  dots and reasons, counts, problems, admins only; the dots and the counts:
  *Superseded 2026-11-13: see Amendments.*)
