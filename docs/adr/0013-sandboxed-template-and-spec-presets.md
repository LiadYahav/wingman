# ADR-0013: The cluster file is rendered from the shared template in a sandbox; specs are value presets

Date: 2026-11-07
Status: Superseded in part by ADR-0034 (the release list `openshift-versions.txt`)

## Context

The specs project (`wingman/cluster-specs`) holds one shared Jinja template,
`cluster-template.j2`, the release list `openshift-versions.txt` and the
specs `specs/<name>.yaml`. The legacy renderer used a plain Jinja
`Environment` (template code could reach Python objects), coerced numeric
strings, and pasted user input into YAML text unchecked: a value with a
newline could add keys such as `vlanId`. Specs held a list shape
(`structure`) for the form but no values, so "spec" meant little beyond a
name and its day2 addons.

## Decision

- Render with `jinja2.sandbox.SandboxedEnvironment` and `StrictUndefined`
  (no autoescape: the output is YAML). A sandbox violation, an undefined
  input or a syntax error is a 422 with the reason.
- Before rendering, every input value must be a plain JSON-like value; every
  string single-line, without quotes, backslashes or control characters, at
  most 253 characters; nesting and size are bounded. Node-label keys such as
  `topology.kubernetes.io/zone` stay allowed.
- Reserved inputs are set by Wingman from the request, never from the form:
  `cluster_name`, `site`, `mce`, `openshift_release_version`. A form value
  for one of them (or the legacy aliases `site_name`, `mce_name`) must agree.
- After rendering, the output must pass the values-file contract (ADR-0012)
  before anything is committed. Preview runs every check a create runs.
- A spec keeps the legacy document shape and gains `spec.day1.values`:
  preset inputs merged under what the user enters (dicts deep-merge, the
  user's lists and scalars win). `day1.template` is never stored; it is the
  shared template, filled in on read. Spec documents reject unknown keys.

## Alternatives rejected

- **Generating the values file in Python, no template**: the team edits the
  template in the specs repo today; the `create-cluster` workflow (ADR-0017)
  will own composition, and the template moves or retires with it.
- **Escaping values instead of refusing them**: YAML quoting rules differ by
  context; refusing is simpler to reason about and nothing legitimate needs
  multi-line values here.

## Consequences

- The template analyzer still turns the template into the form schema, so
  the web form keeps working; a few legacy analyzer quirks were fixed
  (`elif` blocks, literal defaults), listed in `domain/template.py`.
- No stored inputs means no re-render later: YAML drift and `sync-yaml` are
  gone (ADR-0016).

## Verification

- `apps/day1-service/tests/unit/domain/test_template.py`: the fixture
  template's schema, rendering, sandbox escape refused, input checks, and a
  property test that no accepted value changes the rendered key set.
- `apps/day1-service/tests/api/test_fixture_template_contract.py`: a create
  of the fixture template satisfies the values-file contract (and renders
  through the chart with `helm template` when a chart is configured).
