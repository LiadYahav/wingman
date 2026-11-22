# ADR-0065: Every NodePool excludes the Agent labels the deployment names, written into each cluster file

Date: 2026-11-19
Status: Accepted

## Context

herzi keeps each MCE's inventory of free servers, and it also collects used
Agents. An uninstall or a scale-down does not return a used Agent to the
inventory cleanly, so herzi labels every Agent installed in a cluster ("used,
delete when free"), and deletes a free Agent that carries the label. Between
the moment such an Agent is freed and the moment herzi deletes it, a
NodePool that needs a node may bind it again: a used server, about to be
deleted under the new node. It has nothing to do with ranking InfraEnvs or
with kinds of servers.

The user (2026-11-19): "Excluded Agent labels: this should be a default for
all of the nodepools, but selected by an environment variable of Wingman /
inside the j2 / maybe inside hostedclusters-setup."

What the NodePool needs is `{key: <label>, operator: DoesNotExist}` in its
`agentLabelSelector.matchExpressions`. The hostedclusters-setup change the
chart's owner approved (patch 0003 in `docs/upgrade/patches/hostedclusters-setup/`,
on the public port; the air-gapped chart gets the same change from a
separate package) renders it from a nodepool entry's `excludeAgentLabels`:
the selector keeps `matchLabels` when the nodepool draws from one InfraEnv
and gains `matchExpressions`, the InfraEnvs' `In` requirement
(`[infraEnvName, ...additionalInfraEnvNames]`, ADR-0064) then one
`DoesNotExist` per key. It has no chart-wide list. The label's name is not
final: herzi's design names it (`redbull.io/claimed` is proposed).

What Kubernetes does with it: on an `InPlace` NodePool, the chart's default,
a changed selector touches no running node; it is read only when a new
Machine claims an Agent. On a `Replace` NodePool the same change replaces
every node (as in ADR-0064).

## Decision

1. **`DAY1_EXCLUDED_AGENT_LABELS`**: comma-separated Agent label keys, empty
   by default and shipped empty, the air-gap included (the chart's
   `day1.excludedAgentLabels: []`, in `values.schema.json`). Each is a Kubernetes label key (`[prefix/]name`),
   at most 16; day1 refuses to start otherwise (ADR-0009). Empty, nothing
   changes anywhere. A generic list, not one name: herzi names the label.
2. **It is the deployment's default, not a per-cluster choice.** Day1 sets
   the template input `excluded_agent_labels` itself on every create, after
   the request and the flavor (`rendered_file.with_agent_labels`): the form
   schema leaves it out, it is not lockable, and a request or a flavor that
   gives it is refused. A KubeVirt cluster takes no Agents and gets `[]`
   (Wingman's rule; the chart does not check). The
   create preview shows the rendered file, the key included.
3. **The shared template writes it on every nodepool entry**, only when the
   list is not empty:

   ```jinja
   {% if excluded_agent_labels | default([]) %}
       excludeAgentLabels: {{ excluded_agent_labels | tojson }}
   {% endif %}
   ```

4. **The stale-template guard** (ADR-0063, ADR-0064): a create whose rendered
   file does not hold the list on every nodepool, or holds one when the
   setting is empty, is refused (`rendered_file`), naming the upgrade guide.
   With the setting on and an older template, every create is refused: no
   cluster is created whose NodePools would bind used Agents.
5. **An existing cluster takes it through its own merge request, never all
   at once.**
   - `GET /api/day1/clusters/{name}/excluded-agent-labels` (anyone signed in)
     lists each nodepool by its NodePool's name, as the MCE shows it (the
     entry's `name`, else `<clusterName>-<infraEnvName>`), what it excludes
     now, and whether the merge request changes it, with why; `POST` (admin,
     `{last_commit_id}` from the read)
     opens that one merge request (201): the deployment's keys on each
     nodepool that lacks exactly them, in the file's text, every other line
     byte for byte (ADR-0037), through the cluster's modify. Nothing to
     change is a 422 with the reasons. Empty setting: both answer 501.
   - One at a time, as a sync's and a create's: while an open Wingman merge
     request that modifies the cluster already has the keys wherever the
     plan would write them (its branch's file plans no change, whoever wrote
     them there), the plan names it (`open_merge_request`) and the `POST`
     answers 409 `ALREADY_EXISTS` naming it, opening nothing. The plan's
     `change` still says what `main` lacks.
   - A person's edit may add or change a nodepool's list (each a label key).
   - A flavor's sync and rollout write only locked values: they keep the key
     byte for byte and never add it.
6. **A Replace NodePool keeps its list.** An edit that changes the list of a
   NodePool that already exists and is `upgradeType: Replace` (before or
   after) is refused: every node would be replaced. The per-cluster merge
   request leaves such a NodePool out (skips it) and says why, in the plan
   and in its own text, which lists each NodePool it leaves out ("upgradeType
   Replace: the change would replace every node"). A new NodePool
   may be Replace with the list: nothing runs yet. Whatever the setting. So
   Wingman never adds `excludeAgentLabels` to a running Replace NodePool, and,
   by ADR-0064's rule 6, never changes its `additionalInfraEnvNames` either:
   nothing in Wingman adds them by itself.
7. **Where the list lives, and why there.** Wingman's setting → the template
   input → each cluster file's nodepools → the chart. Written into each file,
   a change reaches a cluster only through that cluster's own merge request,
   reviewed and merged on its own: a small blast radius (one MR per cluster),
   and each NodePool's selector is what its file says. The alternative, a
   chart-wide list in the values layers (`sites/configValues.yaml`, a site's
   or an MCE's `values.yaml`), would change the selector of every Agent
   NodePool below that layer at its next sync, Replace NodePools included,
   with no per-cluster review; the approved chart change reads the key per
   nodepool only.
8. **herzi must accept it first.** herzi's current `main` treats a NodePool
   with `matchLabels` plus any `matchExpressions` as a problem of its
   InfraEnv's pool, and orders no servers for that InfraEnv for any cluster.
   The setting is turned on only with the herzi release that labels used
   Agents and accepts the exclusion.

## Alternatives rejected

- **A chart-wide list**: every cluster at once, Replace NodePools included,
  with no per-cluster review. The approved chart change has none.
- **A flavor input**: the exclusion is the platform's rule for herzi's
  collector, not a flavor's choice; a flavor that left it out would create
  clusters that bind used Agents.
- **Adding the key in every sync and rollout merge request**: a flavor's
  merge request would carry a selector change it is not about, and a
  Replace NodePool would roll with it.
- **One fixed label name**: herzi's design names it; a list of keys needs no
  Wingman release when it does.

## Consequences

- Before the setting is set: chart patch 0003, the specs project's template
  block above, and a herzi that accepts the exclusion
  (`docs/upgrade/3.48-to-3.49.md`, its excluded Agent labels section).
- Placement and Inventory Management count free Agents as before: a freed
  used Agent counts as free until herzi deletes it. The Nodes tab already
  applies a NodePool's live selector with Kubernetes' rules, `DoesNotExist`
  included (ADR-0038).
- `WorkflowKeys` carries the keys (`Day1Settings.workflow_keys()`), so the
  create, the edit rules and the merge request read one value.
- New problem texts only; no new problem code, metric or Secret.

## Verification

- `apps/day1-service/tests/unit/domain/test_excluded_agent_labels.py`: the
  keys, the setting, a create's input (KubeVirt none, another list or a
  flavor's refused), the rendered check, the edit rules (a Replace NodePool,
  a new one, the keys), the plan, the merge request's text.
- `apps/day1-service/tests/api/test_excluded_agent_labels_api.py`: a create
  with and without the setting, the schema, a request and a flavor that set
  the input, a stale template, 501 when empty, the plan and the per-cluster
  merge request (every other line kept, 403 for a viewer, NodePools by
  name), a second one refused while the first is open (another open edit
  carries nothing), a Replace NodePool left out, in the plan and the merge
  request's text, and its edit refused.
- `apps/day1-service/tests/unit/test_settings.py` (the setting refused when
  not label keys) and `tests/repo/test_chart_env_contract.py` (the chart
  value joined with commas, refused by the schema when not label keys).
