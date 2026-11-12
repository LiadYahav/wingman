# ADR-0023: day2 lints are render_chain.py's rules as errors plus Wingman's own; a change that adds an error is refused

Date: 2026-11-07
Status: Accepted

## Context

The platform's failure modes are mostly silent: a misspelled exclusion keeps
deploying, `repoUrl` renders an empty `repoURL`, a stray folder becomes a
phantom app, an OCP upgrade without `ocp-versions/<new>/` falls back to the
team default. The team's CI gate for this, `render_chain.py`, may not exist
in the air-gapped GitLab yet (`docs/ecosystem/README.md`). Wingman is the
natural place to check before an MR, for every team at once.

## Decision

- One vocabulary, `wingman_day2.domain.findings.Rule`, with stable string
  values. Rules `render_chain.py` fails a snapshot on are errors with the
  same meaning: env allow-list, day1 version parity, mastertag format, UPI
  name and version-file rules, the legacy layout, exclusions rules 0-3, and
  duplicate apps (the XOR rule). Its migration-window checks of the legacy
  marker files are left out.
- Wingman's own rules: `repourl-miscased` and `repourl-missing`,
  `yaml-invalid`, `ocp-version-pin-missing` (a pinned chart with no folder for
  the cluster's version), `fleet-pin-overrides-ocp-versions`, `emergency-pin`
  (info), `cluster-position-conflict`, `env-unknown`; and (2026-11-12)
  `sync-policy-invalid`: a leaf's merged `syncPolicy`, `automated` or
  `automated.enabled` is not of the type ArgoCD's Application CRD takes
  (`automated: true`), so the leaf is refused; reported on the highest layer
  that sets it.
- Chart repos (2026-11-08): every file that sets a `repourl` (a catalog
  entry's team default, or any layer an app's `repourl` comes from) is
  checked against GitLab once per distinct URL. `repourl-moved` (warning): the
  URL names a project GitLab renamed or transferred; it still redirects, but
  only until a new project takes the old path, and the finding gives the URL
  to write. `chart-repo-unreadable` (error): GitLab refused the chart repo
  (no access, or an answer Wingman does not expect). Both belong to that
  chart: the catalog and the other charts still load. GitLab being
  unreachable is still the whole page's error (ADR-0004).
- Findings appear where they apply: on clusters, installed charts, catalog
  entries and previews, and all of them at `GET /api/day2/lints`.
  `GET /clusters/{id}/upgrade-check?to=<version>` lists the pinned charts a
  cluster would silently unpin at a new version.
- A change is linted on the tree it would produce; an error it adds refuses
  it (422 or 409 with `details.rule`).

## Alternatives rejected

- **Running render_chain.py itself.** It needs helm and the platform
  checkout; the rules are pure and small, and the oracle test keeps them
  equal (ADR-0021).
- **Warnings only.** An install that makes ArgoCD generate a duplicate app
  breaks every app of that name; it must not be one click away.

## Consequences

- Existing errors in a team repo do not block unrelated changes; only new
  ones do.

## Verification

The oracle's broken-tree scenarios require the same set of failing rules
from both implementations; `tests/unit/application/test_changes.py` covers a
change refused for an error it would add (`upi-name-reused`).
