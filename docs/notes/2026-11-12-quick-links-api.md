# Quick Links: the API the web reads (2026-11-12; amended 2026-11-13)

The **Quick Links** page (`/quick-links`, in the sidebar) is a launcher in
the style of the team's homepage dashboard: sections of cards, each with an
icon and a description (ADR-0052). Wingman generates the cards it knows: the
hub it runs on and every MCE of the day1 repo, by site, each with its
ArgoCD and console. The team's other links come from a YAML file the chart
renders into a ConfigMap. Wingman only lists the links: neither day1 nor the
browser calls them.

**3.13.1 (ADR-0052's 2026-11-13 amendment)** removed the status dots and the
ArgoCD counts: `GET /api/day1/quick-links/status` is gone (§2), a link lost
`ping` and a card lost `argocd` (§1), and the links file's `ping` and
`argocd` keys are no longer read (§3).

The route is **admins only** for now (decision 13 of
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
          "links": [
            {
              "label": "ArgoCD",
              "url": "https://openshift-gitops-server-openshift-gitops.apps.hub-prod.example.internal"
            },
            {
              "label": "Console",
              "url": "https://console-openshift-console.apps.hub-prod.example.internal"
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
          "links": [
            {"label": "ArgoCD", "url": "https://openshift-gitops-server-openshift-gitops.apps.ocp4-prod-mce-site1-a.example.internal"},
            {"label": "Console", "url": "https://console-openshift-console.apps.ocp4-prod-mce-site1-a.example.internal"}
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
          "links": [{"label": null, "url": "https://gitlab.example.internal/platform/gitops"}]
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
| `card.links` | At least one. `links[0]` is the card's own link: its title opens it, in a new tab. A generated card has two, `ArgoCD` then `Console`. A file card has one, with `label: null` |
| `link.label`, `link.url` | All a link is. Until 3.13.1 a link also had `ping` (its status dot's URL) and a card `argocd` (the instance whose counts it showed) |
| `problems` | What Wingman could not generate, one sentence each, e.g. `Set QUICK_LINKS_DOMAIN (or MCE_API_DOMAIN) to list each MCE's ArgoCD and console.` |
| `links_file.state` | `loaded` (read; some parts may still have been skipped: see `problems`), `missing` (no file at the path: no team links, not an error) or `invalid` (unreadable, not YAML, or not a mapping: no team links) |
| `links_file.problems` | Every problem in the file, one line each, naming the section and link (`sections[0] "Core GitOps" links[1] "ArgoCD Main": url must be an http(s) URL`). A bad link is skipped, a bad section too; the rest is shown |

## 2. `GET /api/day1/quick-links/status`: removed in 3.13.1

3.9 to 3.13.0 served each link's check (`up`, `down` or `unknown`, with the
reason) and each ArgoCD's applications by sync and health here, checked by
day1 while the page was open and cached. 3.13.1 removed it (ADR-0052's
amendment): it answers `404 NOT_FOUND`, and the web no longer reads it.

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
      - name: ArgoCD Main
        url: https://argocd.example.internal
        icon: argocd
clusters:                             # optional: a cluster whose addresses don't follow the templates
  hub-prod:
    argocd: https://gitops.hub-prod.example.internal
    console: https://console.hub-prod.example.internal
```

Limits: 50 sections, 100 links a section, names of 80 characters,
descriptions of 200, URLs of 2048. An unknown key is reported (`href` is
not `url`) and otherwise ignored. So are `ping` and `argocd` since 3.13.1: a
file written for 3.9 to 3.13.0 still loads, and the page names each of them
until they are deleted.

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
