# Quick Links: the API the web reads (2026-11-12)

The **Quick Links** page (`/quick-links`, in the sidebar) is a launcher in
the style of the team's homepage dashboard: sections of cards, each with an
icon, a description, a status dot and, for an ArgoCD with a token, its
applications' counts (ADR-0052). Wingman generates the cards it knows: the
hub it runs on and every MCE of the day1 repo, by site, each with its
ArgoCD and console. The team's other links come from a YAML file the chart
renders into a ConfigMap. day1 checks every link itself; the browser never
pings anything.

Both routes are **admins only** for now (decision 13 of
`docs/ideas/single-pane.md`, until RBAC): a viewer gets `403 FORBIDDEN`, and
the sidebar hides the entry from viewers.

## 1. `GET /api/day1/quick-links`: the sections and cards

Fast: it reads the day1 repo's tree (cached, ADR-0035) and the links file,
and calls nothing else.

```json
{
  "sections": [
    {
      "id": "hub",
      "name": "Hub",
      "description": "The cluster Wingman runs on",
      "columns": 4,
      "generated": true,
      "cards": [
        {
          "id": "hub:hub-prod",
          "name": "hub-prod",
          "description": null,
          "icon": "argocd",
          "argocd": "hub-prod",
          "links": [
            {
              "label": "ArgoCD",
              "url": "https://openshift-gitops-server-openshift-gitops.apps.hub-prod.example.internal",
              "ping": "https://openshift-gitops-server-openshift-gitops.apps.hub-prod.example.internal"
            },
            {
              "label": "Console",
              "url": "https://console-openshift-console.apps.hub-prod.example.internal",
              "ping": "https://console-openshift-console.apps.hub-prod.example.internal"
            }
          ]
        }
      ]
    },
    {
      "id": "site:site1",
      "name": "MCEs in site1",
      "description": "Each MCE's ArgoCD and console",
      "columns": 4,
      "generated": true,
      "cards": [
        {
          "id": "cluster:ocp4-prod-mce-site1-a",
          "name": "ocp4-prod-mce-site1-a",
          "description": "OpenShift 4.16.27 · 3 hosted clusters",
          "icon": "argocd",
          "argocd": null,
          "links": [
            {"label": "ArgoCD", "url": "https://openshift-gitops-server-openshift-gitops.apps.ocp4-prod-mce-site1-a.example.internal", "ping": "https://openshift-gitops-server-openshift-gitops.apps.ocp4-prod-mce-site1-a.example.internal"},
            {"label": "Console", "url": "https://console-openshift-console.apps.ocp4-prod-mce-site1-a.example.internal", "ping": "https://console-openshift-console.apps.ocp4-prod-mce-site1-a.example.internal"}
          ]
        }
      ]
    },
    {
      "id": "file:core-gitops",
      "name": "Core GitOps",
      "description": null,
      "columns": 2,
      "generated": false,
      "cards": [
        {
          "id": "file:core-gitops:gitlab-gitops-project",
          "name": "GitLab GitOps Project",
          "description": "Main GitOps repository",
          "icon": "gitlab",
          "argocd": null,
          "links": [{"label": null, "url": "https://gitlab.example.internal/platform/gitops", "ping": "https://gitlab.example.internal"}]
        }
      ]
    }
  ],
  "problems": [],
  "links_file": {"path": "/etc/wingman/quick-links/links.yaml", "state": "loaded", "problems": []}
}
```

| Field | Meaning |
|---|---|
| `sections` | In order: the hub (when `QUICK_LINKS_HUB_NAME` is set), one per site that has MCEs (sites sorted, MCEs sorted), then the links file's sections in the file's order |
| `section.id` | Stable: `hub`, `site:<site>`, `file:<slug of the name>` |
| `section.columns` | How many cards a row holds on a wide screen, 1 to 6 (the file's `columns`, default 4); narrower screens hold fewer |
| `section.generated` | `true` for what Wingman generated, `false` for the links file's |
| `card.id` | Stable: `hub:<name>` (the hub), `cluster:<name>` (an MCE), `file:<section slug>:<card slug>` |
| `card.description` | For an MCE, its hub's OpenShift version and how many hosted clusters its folder holds (either may be missing); the file's `description` otherwise |
| `card.icon` | An icon key (§4). Always set: the file's `icon`, else `link` |
| `card.argocd` | The ArgoCD instance whose applications' counts the status read carries for this card (§2): set only when that instance has a token. `null`: the card is a link and its status dots |
| `card.links` | At least one. `links[0]` is the card's own link: its title opens it, in a new tab. A generated card has two, `ArgoCD` then `Console`, each with its own dot. A file card has one, with `label: null` |
| `link.ping` | The URL whose answer is the link's status dot (the file's `ping`, else the link's `url`). `null`: no dot (the file's `ping: false`, or `QUICK_LINKS_STATUS_ENABLED=false`) |
| `problems` | What Wingman could not generate, one sentence each, e.g. `Set QUICK_LINKS_DOMAIN (or MCE_API_DOMAIN) to list each MCE's ArgoCD and console.` |
| `links_file.state` | `loaded` (read; some parts may still have been skipped: see `problems`), `missing` (no file at the path: no team links, not an error) or `invalid` (unreadable, not YAML, or not a mapping: no team links) |
| `links_file.problems` | Every problem in the file, one line each, naming the section and link (`sections[0] "Core GitOps" links[1] "ArgoCD Main": url must be an http(s) URL`). A bad link is skipped, a bad section too; the rest is shown |

## 2. `GET /api/day1/quick-links/status`: the dots and the ArgoCD counts

Slow the first time (each link is asked, at most `QUICK_LINKS_CONCURRENCY`
at once, each for at most `QUICK_LINKS_TIMEOUT_SECONDS`), then answered from
day1's cache: every answer is kept `QUICK_LINKS_STATUS_TTL_SECONDS` (60), and
for as long again it is answered while one check refreshes it in the
background. Every viewer shares the one cache, and two reads at once share one
check. Nothing is checked while nobody reads it. The web reads it once the
cards are shown and again every 60 s.

```json
{
  "checks": [
    {
      "url": "https://openshift-gitops-server-openshift-gitops.apps.hub-prod.example.internal",
      "state": "up",
      "reason": "answered 200",
      "http_status": 200,
      "latency_ms": 84,
      "checked_at": "2026-11-12T10:00:00Z"
    },
    {
      "url": "https://console-openshift-console.apps.ocp4-prep-mce-site2-a.example.internal",
      "state": "down",
      "reason": "no answer within 3 s",
      "http_status": null,
      "latency_ms": null,
      "checked_at": "2026-11-12T10:00:00Z"
    }
  ],
  "argocd": [
    {
      "instance": "hub-prod",
      "counts": {
        "applications": 45,
        "sync": {"synced": 42, "out_of_sync": 3, "unknown": 0},
        "health": {"healthy": 40, "progressing": 1, "degraded": 2, "missing": 1, "suspended": 0, "unknown": 1}
      },
      "error": null,
      "checked_at": "2026-11-12T10:00:00Z"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `checks` | One per distinct `ping` URL of §1, in no particular order: the web matches `link.ping` to `check.url` |
| `check.state` | `up`: it answered 2xx, 3xx (redirects are not followed: a login redirect is up), 401 or 403. `down`: any other answer (404, 5xx), no answer in time, or no connection. `unknown`: TLS could not be verified (an untrusted certificate), so whether it is up is not known |
| `check.reason` | Always set, short and lower-case: `answered 200`, `answered 503`, `no answer within 3 s`, `connection failed (ConnectError)`, `TLS certificate not trusted` |
| `check.http_status`, `check.latency_ms` | When it answered |
| `check.checked_at` | When day1 asked (UTC). Up to two TTLs old |
| `argocd` | One per instance named by a card's `argocd` |
| `argocd.counts` | Every application the token may see: by sync status (`Synced`, `OutOfSync`, else `unknown`) and by health (`Healthy`, `Progressing`, `Degraded`, `Missing`, `Suspended`, else `unknown`). `null` when the read failed |
| `argocd.error` | Why the counts could not be read, e.g. `ArgoCD refused the token (401)`, `ArgoCD did not answer within 3 s`; `null` when read |

A check is `HEAD <url>`, then `GET <url>` (its body not read) when `HEAD`
answers 405 or 501. No credential is ever sent to a checked URL. The ArgoCD
read is `GET <ArgoCD url>/api/v1/applications?fields=items.status.sync.status,items.status.health.status`
with `Authorization: Bearer <the instance's token>`; the token never leaves
day1.

## 3. The links file

The chart renders `quickLinks.sections` and `quickLinks.clusters` into the
ConfigMap `wingman-quick-links`, mounted in day1 at
`/etc/wingman/quick-links/links.yaml` (`QUICK_LINKS_FILE`). day1 reads it on
every `GET /quick-links`, so an edit (`helm upgrade`, or `oc edit cm`) shows
within the kubelet's sync, about a minute, without a restart.

```yaml
sections:
  - name: Core GitOps                 # required, unique
    description: The GitOps repos     # optional
    columns: 2                        # optional, 1 to 6 (default 4)
    links:
      - name: GitLab GitOps Project   # required, unique in its section
        url: https://gitlab.example.internal/platform/gitops   # required, http(s)
        description: Main GitOps repository                     # optional
        icon: gitlab                  # optional, a key (§4); default link
        ping: https://gitlab.example.internal   # optional: the URL to check; false: no dot
      - name: ArgoCD Main
        url: https://argocd.example.internal
        icon: argocd
        argocd: main                  # optional: the key of its token in the ArgoCD tokens Secret
clusters:                             # optional: a cluster whose addresses don't follow the templates
  hub-prod:
    argocd: https://gitops.hub-prod.example.internal
    console: https://console.hub-prod.example.internal
```

Limits: 50 sections, 100 links a section, names of 80 characters,
descriptions of 200, URLs of 2048. An unknown key is reported (`href` is
not `url`) and otherwise ignored.

## 4. Icons

A card names its icon by key; the web ships every icon (no CDN). Brand
icons (simple-icons 16.36.0, CC0-1.0, vendored): `argocd`, `gitlab`,
`openshift`, `redhat`, `grafana`, `confluence`, `jira`, `bitbucket`, `cisco`,
`dell`, `hp`, `lenovo`, `nutanix`, `vmware`, `f5`, `fortinet`, `paloalto`,
`kubernetes`, `prometheus`, `vault`, `ansible`, `helm`, `elastic`, `kibana`,
`opensearch`, `splunk`, `nexus`, `minio`, `mattermost`, `terraform`,
`docker`. Generic icons (lucide): `link`, `globe`, `book`, `docs`,
`network`, `compass`, `server`, `database`, `storage`, `shield`, `lock`,
`key`, `chart`, `dashboard`, `monitor`, `terminal`, `code`, `git`, `wrench`,
`settings`, `box`, `package`, `cloud`, `layers`, `cpu`, `router`, `wifi`,
`mail`, `chat`, `calendar`, `users`, `ticket`, `bell`, `activity`, `search`,
`home`. An unknown key shows `link`.
