# ADR-0060: A team's charts sit in `<team>/helm-charts`; Wingman suggests that address for a new add-on and never enforces it

Date: 2026-11-14
Status: Accepted

## Context

A deploy config's `repourl` names the chart repo, and day2 resolves any
project path on its own GitLab (ADR-0024), so where a chart repo sits has
never mattered to Wingman's reads.

Until now the fixtures, the seed and the docs modelled one shared top-level
group, `helm-charts/<chart>`. The New add-on form's suggested address
(`repourl_prefix` of `GET /teams/{team}/addon-template`, ADR-0043) was the
folder most of the team's existing add-ons' chart repos sit in, or none: a
team with no add-on yet got no suggestion, and a team whose add-ons point at
a shared group kept being steered there.

The user's decision (2026-11-14): each team's charts sit in its own GitLab
group at the root of the GitLab, `<team>/helm-charts/<chart>`
(`orca/helm-charts/<chart>.git`, `redbull/helm-charts/<chart>.git`). The
team is the day2 team, the name of its `sigs/<team>` project. Wingman only
suggests the address.

## Decision

- **The address.** A new add-on `<name>` of team `<team>` is suggested at
  `<GITLAB_URL>/<team>/helm-charts/<name>.git`, built from the GitLab URL
  day2 is configured with; a URL with a sub-path keeps it
  (`https://host/gitlab` gives `https://host/gitlab/<team>/helm-charts/`).
  The add-on template answers the folder as `repourl_prefix`, whatever the
  team's existing add-ons use. The field keeps its name, and is now always
  set.
- **Only a suggestion.** The New add-on form fills the address in as
  `<prefix><name>.git` while the name is typed, until the person edits the
  address; from then on their text stays. A tooltip says where a team's
  charts sit and that the address can be changed. An install that must give
  a `repourl` (an add-on with only the miscased `repoUrl`) shows the team's
  address as its placeholder.
- **Never enforced.** Wingman does not refuse, warn about or lint a
  `repourl` elsewhere on its GitLab. ADR-0043's existing checks are
  unchanged: a `repourl` on this GitLab must name a project Wingman can
  read, and one on another host is accepted with a warning. Add-ons already
  in Git are untouched: nothing compares their address with the layout.
- **Fixed in code, not a setting.** The group is `<team>/helm-charts`, in
  `wingman_day2.domain.teams.charts_group`. If an environment ever nests it
  (`<top>/<team>/helm-charts`), change that function and its test; make it a
  setting then, with its chart value and schema entry (ADR-0059), only if two
  environments need different layouts. Nothing else reads it.
- **The fixtures model it.** `dev/gitlab-fixtures/<team>/helm-charts/<chart>`
  for each team's charts, every fixture `repourl` on its own team's group,
  and `scripts/dev/seed_gitlab.py` creates the nested groups.

## Alternatives rejected

- **Refuse an address elsewhere.** Teams whose charts sit elsewhere today (a
  shared group, a mirror, another team's chart) could no longer create or
  edit those add-ons, and the platform renders any `repourl`: the refusal
  would protect nothing that breaks.
- **Warn about an address elsewhere.** Every existing add-on would carry the
  warning until its team moves its charts, a warning people learn to skip;
  the lints (ADR-0023) are for what breaks a render, and this does not.
- **Keep the most common folder of the team's add-ons.** It steers new
  charts to wherever the old ones happen to be, and a team with no add-on
  yet gets no suggestion.
- **A setting for the group (a template such as `{team}/helm-charts`).**
  Every environment has the same layout, and a setting is one more chart
  value, schema entry and variable to keep in step for a suggestion (keep
  extras thin).

## Consequences

- A team with no add-on yet gets a suggestion too.
- A team whose add-ons point at the shared `helm-charts/` group is now
  suggested its own group. The group and its repos are the team's to create:
  Wingman creates no group or project, and a suggested repo that does not
  exist yet is refused as before (`chart-repo-missing`), so the person
  creates it or types another address.
- Wingman's account reads each team's chart repos, so it needs Reporter (or
  more) on each `<team>/helm-charts` group, as it had on the shared group.
- A local GitLab seeded before keeps its `helm-charts/*` projects (the seed
  deletes nothing) and gains the per-team groups on the next seed.

## Verification

- `apps/day2-service/tests/unit/application/test_authoring.py`: the prefix
  is the team's group for every team, with or without add-ons, and whatever
  folder its add-ons use; `tests/api/test_authoring_api.py` over HTTP;
  `tests/unit/infrastructure/test_chart_repository.py`: the folder's URL on a
  GitLab with a sub-path, read back to the project path.
- `apps/day2-service/tests/unit/domain/test_teams.py`: `charts_group`.
- `apps/web/e2e/tests/addon-chart-address.spec.ts` (mocked): the prefill
  follows the name, an edited address is kept, each team gets its own
  folder, and an install's placeholder is the team's address.
- `packages/wingman-core/tests/unit/testing/test_fixtures.py`: the fixtures
  load nested groups, and every fixture `repourl` names its team's group.
