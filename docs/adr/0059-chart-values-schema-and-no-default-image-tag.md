# ADR-0059: The chart checks its values against a schema, and has no default image tag

Date: 2026-11-14
Status: Accepted

## Context

The chart had no `values.schema.json`, so a values file was never checked:

- **A misspelt key rendered silently**, and the setting it meant kept its
  default: `serverScan.tokenSecert` gave day1 no server-scan token, and
  nothing said why.
- **A wrong type rendered wrong.** `--set serverScan.sslVerify=false` is a
  boolean, and the template's `default "true"` turned it into `"true"`.
  `devAuth.enabled: "false"`, a string, is true in the templates' `if`: the
  `OAuthClient` was left out while day1 was told dev login is off.
- **The image tags defaulted to `latest`**, against the chart's own comment.
  herzi and server-scan default an empty tag to the chart's `appVersion`, but
  Wingman's is `0.1.0` and never stamped: a release publishes images and a git
  tag, and the chart is deployed from the repository at that tag.

herzi, the quality bar (convention 1), checks its values with a schema that
refuses any key it does not know (`additionalProperties: false` at the root
and on every object) and tests that a typo, a wrong type and a value out of
range each fail with the key named (`hack/test-chart.sh`). The quality-bar
study planned the same for Wingman (`docs/notes/2026-11-07-quality-bar-repo.md`
§7.5). One difference matters: Wingman's upgrades reuse the release's values
(`helm upgrade --reset-then-reuse-values`, `docs/upgrade/README.md`), and those
hold keys older releases documented and then dropped, which the chart still
accepts and ignores (ADR-0052's amendment).

## Decision

- **`deploy/helm/wingman/values.schema.json`** (JSON Schema draft-07, which
  Helm 3 and 4 both read) describes every key the chart reads.
  `additionalProperties: false` at the root and on every object: a key not in
  it fails `helm template`, `install`, `upgrade` and `lint`, naming its path
  (`at '/serverScan': additional properties 'tokenSecert' not allowed`).
- **Types follow what the templates do with a value.** A switch the templates
  test with `if` is a boolean only; the project ids a string or an integer
  (`--set gitlab.day1ProjectId=42`).
- **The five `sslVerify` keys take a boolean or a non-empty string**
  (`"true"`, `"false"` or a CA path), and one helper renders all five
  (`wingman.tlsVerify`): a boolean as `"true"` or `"false"`, a string as given,
  unset or empty as `"true"`. `--set serverScan.sslVerify=false` now means
  false; each key's default in `values.yaml` is unchanged.
- **Enums** where the templates take only a few values: `environment`,
  `day1.provisioner`, the Route's TLS `termination` and
  `insecureEdgeTerminationPolicy`, `pullPolicy`. **Ranges** where the services
  have bounds: the cache TTLs and timeouts at most 60 s, the upgrade targets'
  at most 120 s, `auth.jwtExpiryHours` 1 to 24, `day1.placementMinFreePods`
  0 to 100,000, a Quick Links section's `columns` 1 to 6. **Patterns** on the
  strings that must have a shape: URLs (http(s), or empty where optional),
  DNS names, Kubernetes names and Secret keys, image tags and digests,
  Prometheus durations, and the OpenShift hosts without a scheme.
- **Keys an older release dropped stay allowed, with any value, and are
  ignored.** Each says `Deprecated: …; delete it` in its description:
  `quickLinks.status`, `quickLinks.sslVerify`, `quickLinks.argocdTokensSecret`
  and a link's `ping` and `argocd` (3.13.1); `cache`, `paths`,
  `gitlab.defaultBranch`, `gitlab.sslVerify` and
  `clusterStatus.clusterNamePrefix` (the legacy chart, before 3.0.0).
- **No default Wingman image tag.** `image.{day1,day2,web}.tag` is `""` in
  `values.yaml`, and an empty one fails the render, naming the key with an
  example: `image.day1.tag is empty: set it to the release to deploy, for
  example --set image.day1.tag=3.33.0`. `values.minikube.yaml` names its local
  builds (`latest`); the `ci/` fixtures set a release.
- **nginx's tag and digest change together** (ADR-0058). Nodes pull the digest,
  so a tag kept from earlier values beside the chart's digest fails the render
  instead of pulling nothing.

## Alternatives rejected

- **An empty tag meaning `appVersion`**, as herzi and server-scan do. Every
  release would have to stamp `Chart.yaml`, or publish a packaged chart, and
  Wingman does neither; `0.1.0` names no image.
- **Refusing the dropped keys**, as herzi refuses its removed ones with a
  message. An upgrade that reuses values would fail on keys a release told
  operators were ignored. A major release can drop them later.
- **`required` keys in the schema.** Values kept from a release before a key
  existed do not have it, and the templates give it its default (the
  `--reuse-values` cases in `tests/repo/test_chart_env_contract.py`). Only the
  tags are required, by the template, with the message above.
- **Checking a Quick Links link's URL and icon in the schema.** day1 checks
  them on every page load, and a bad link is a line on the page, not a failed
  page (ADR-0052). The schema checks the file's keys and types only.

## Consequences

- A typo, a wrong type or a value out of range fails before anything changes,
  naming the key. A values file in use today can fail on its next upgrade: the
  3.33 upgrade guide checks it first (`docs/upgrade/3.32-to-3.33.md`).
- A new key needs its entry in the schema in the same commit, or the chart
  refuses its own `values.yaml`; the tests render it.
- An install that names no release fails. Every documented install and upgrade
  already set the three tags.
- A boolean `false` in the `sslVerify` of `serverScan`, `workflows` or
  `segmentsManager` now turns verification off, as written; before 3.33 it was
  silently on. The upgrade guide has the release's values checked for one.
- `helm lint` reports a template's `fail` only as information, so it passes a
  chart that cannot render without tags. The gate and CI lint the chart with
  each `ci/` fixture instead, as herzi does, and `helm template` renders each.

## Verification

`tests/repo/test_chart_schema.py`: `values.yaml`, `values.minikube.yaml` and
every `ci/` fixture render; every object in the schema refuses unknown keys;
a typo at the root and in each nested object, a wrong type, a bad enum, a value
out of range and an empty `sslVerify` each fail `helm template` and
`helm lint --strict` with the key named; every deprecated key is accepted and
changes nothing; an empty Wingman tag fails naming it.
`tests/repo/test_chart_env_contract.py`: each of the five `sslVerify` keys
given `false`, `"false"`, `true`, a CA path or nothing sets its variable to
`"false"`, `"false"`, `"true"`, the path or `"true"`.
`tests/repo/test_chart_nginx.py`: an nginx tag kept beside the chart's digest
fails, and an empty digest pulls that image by its tag.
`tests/repo/test_web_docs_contract.py` lets the docs name a deprecated key.
