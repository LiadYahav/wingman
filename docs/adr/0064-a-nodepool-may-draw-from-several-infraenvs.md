# ADR-0064: A nodepool may draw from several InfraEnvs: `infraEnvName` stays and names it, the others are `additionalInfraEnvNames`, behind a setting

Date: 2026-11-18
Status: Parked 2026-11-23 (the team runs no such NodePool for now: the chart and the specs template don't carry `additionalInfraEnvNames`, and the setting stays off); Accepted, amended 2026-11-19 (the chart change the owner approved: `In [infraEnvName, ...others]`, unsorted, and no checks in the chart)

## Context

A nodepool takes its nodes from one InfraEnv today: the chart renders its
NodePool's `agentLabelSelector` as the one label
`infraenvs.agent-install.openshift.io: <infraEnvName>`. The user's words
(2026-11-18):

> "each nodepool can pull nodes from multiple infraenv ... the customer
> doesn't care about the nodes spec (yes for CPU cores and Memory but not for
> CPU Hz / Memory speed / NIC speed). Don't make it complicated."

What the NodePool should get:

```yaml
agentLabelSelector:
  matchExpressions:
  - key: infraenvs.agent-install.openshift.io
    operator: In
    values: [infraenv-1, infraenv-2, infraenv-3, infraenv-4]
```

What HyperShift, cluster-api and cluster-api-provider-agent do with it:

- On an `upgradeType: InPlace` NodePool, the chart's default, a changed
  selector never drains, reboots or replaces a running node. It is applied
  only when a new Machine claims an Agent.
- A new Machine takes the first free valid Agent of any listed InfraEnv,
  with no preference and no spreading. Every InfraEnv must be in the
  HostedCluster's agent namespace.
- On a `Replace` NodePool the same change rolls every node.

What else reads a nodepool's InfraEnv:

- The chart derives the NodePool's name, `<clusterName>-<infraEnvName>`.
  A different name is a different NodePool: the old one and its nodes go.
- The team's workflows parse `infraEnvName`: update-nodepool and
  upgrade-cluster refuse a file whose nodepool lacks it.
- herzi counts a NodePool's demand only from a selector that is exactly
  that one label (`internal/pipeline/attribute.go`). It skips any other
  selector as "not tied to an InfraEnv".
- The hostedclusters-setup chart does not know a list yet, so a file
  carrying one would silently get the single-InfraEnv selector.

## Decision

1. **The file keeps `infraEnvName`.**
   - The first InfraEnv stays `infraEnvName` on every agent nodepool. It
     names the NodePool and is what the workflows read.
   - The others go in a new list, `additionalInfraEnvNames: [b, c]`.
   - With no others the file is exactly as today. With others, the chart
     renders the `In` selector over `infraEnvName` and the list, sorted and
     unique (*amended 2026-11-19, below: in the given order*).
   - The chart change is drafted for team-redbull/helm-charts-hostedclusters-setup
     and not merged. It fails the render on KubeVirt and with the legacy
     `agentLabelSelector.nodeLabelKey` (*amended 2026-11-19: the approved
     change does not; Wingman's rules still refuse both*).
   - No server classes: the person picks the InfraEnvs. How a nodepool's
     network hardware (`nm-conf`) is chosen does not change.

2. **`DAY1_MULTI_INFRAENV_NODEPOOLS`** turns it on. It is off by default;
   the chart value is `day1.multiInfraEnvNodepools.enabled`, in
   `values.schema.json`. Off, Wingman never offers or writes the list:
   - the form schema (`GET /specs/template/schema`) leaves the input out;
   - a create, a preview or a flavor save that sets it is a 422;
   - an edit that changes a nodepool's `additionalInfraEnvNames`, or adds a
     nodepool with it, is a 422.

   A file that already has the list still reads. Its list is shown, every
   edit, sync and rollout keeps it byte for byte, and Inventory Management
   and placement count it.

3. **The template input is `nodepools[].additional_infra_envs`**, a list of
   InfraEnv names. The shared template writes it only when it is not empty:

   ```jinja
   {% if np.additional_infra_envs | default([]) %}
       additionalInfraEnvNames: {{ np.additional_infra_envs | tojson }}
   {% endif %}
   ```

   At a create and a flavor save, each name must be:
   - a DNS label;
   - given once, and not the nodepool's own;
   - one of at most 16;
   - on an agent nodepool, never a KubeVirt one.

   It is not lockable: InfraEnvs never were (ADR-0026).

4. **A template that does not read the input is refused**, as for image
   mirrors (ADR-0063), so an older specs-project template never drops it
   silently:
   - At a flavor save, a nodepool that gives the input is refused while the
     template does not read it. The check uses the create form's own
     analysis of the template.
   - At a create, the rendered file must hold each nodepool's list exactly
     as given, and no list where none was given.

   The checks of a rendered file, tuning profiles and image mirrors
   included, are in one place, `domain/rendered_file.py`.
   `docs/upgrade/3.46-to-3.47.md` has the template lines.

5. **A NodePool is never renamed: removing or replacing the first InfraEnv
   is refused.** On every edit, whatever the setting, nodepools are matched
   with the file before the edit by `name`, else `infraEnvName`, as the
   replicas and version rules match them. The edit is refused when both of
   these hold:
   - an unnamed nodepool's NodePool disappears, and a new one appears whose
     first InfraEnv is different but shares an InfraEnv with it;
   - one of the two draws from more than one InfraEnv.

   That edit would replace the NodePool and every node. The problem says to
   keep the old first InfraEnv, or to remove the old nodepool in a merge
   request of its own.

   The other choice, writing an explicit `name:` equal to the old derived
   name and promoting the next InfraEnv, was rejected:
   - It leaves a NodePool whose name no longer says its InfraEnv.
   - A later edit that drops the "redundant" `name:` replaces every node.
   - Wingman's own rules key a nodepool by `name` before `infraEnvName`,
     so the NodePool would look new to them.

   A nodepool that already has its own `name` may change its first
   InfraEnv: the name stays. Changing the InfraEnv of a nodepool that draws
   from one InfraEnv, before and after, is today's edit and still allowed.

6. **A Replace NodePool keeps its InfraEnvs.** An edit is refused when it
   changes the InfraEnvs of an existing nodepool whose `upgradeType` is
   `Replace` (before or after) and which draws from more than one InfraEnv
   before or after. Adding or removing one would replace every node. A new
   nodepool may be Replace with several InfraEnvs: nothing runs yet. New
   clusters are InPlace by default.

7. **Free servers are counted across all of a nodepool's InfraEnvs, and
   never twice.**
   - **Placement** (ADR-0050). A nodepool that draws from several InfraEnvs
     is one node type, `a + b`. Its free Agents are those of all its
     InfraEnvs.
     - Node types that share an InfraEnv are judged together, in one row:
       all their InfraEnvs against all their replicas.
     - Every part of the row must also hold (Hall's condition, checked part
       by part up to 10 node types). So a nodepool that draws only on `a` is
       short when `a` is, however many free servers `b` has. The row's
       detail then names that part.
     - Every Agent is in one InfraEnv, so a sum over InfraEnvs counts a
       server once.
     - The form sends such a need as `need=a,b:<replicas>`. The API's
       node-type rows gain `infra_envs`.
   - **Inventory Management** (ADR-0057). Its pools are InfraEnvs, each
     server counted in one, so nothing double counts. Without the MCE's own
     list, the day1 files' InfraEnvs include every nodepool's others.
   - **The Nodes tab** (ADR-0038) applies the live NodePool's selector with
     Kubernetes' rules, `In` included. Each NodePool shows the free Agents
     it could take; NodePools that share an InfraEnv may list the same free
     Agent, which either could claim. Nothing sums them.

8. **The web** reads the template schema as the switch: when day1 offers
   the input, a nodepool shows **Also draws from**. It sits under its own
   InfraEnv, which the note says names the NodePool:
   - On the create form the others are picked from the MCE's InfraEnvs, the
     list the single picker offers, or typed without live status.
   - In the flavor editor they are a typed preset.
   - In Edit cluster, **InfraEnvs per nodepool** sits above the YAML. It edits
     only the list, in the file's text, every other line kept, as the
     template writes it. It never changes a nodepool's own InfraEnv, and
     shows a Replace NodePool's InfraEnvs read only.
   - The cluster page names the others under each nodepool.

9. **Unchanged**:
   - A flavor's nodepool ratio (ADR-0040) sizes nodepools, not InfraEnvs.
   - Drift compares locked values only.
   - Scale (ADR-0062) names one NodePool, by the chart's rule (`name`, else
     `<clusterName>-<infraEnvName>`), so a NodePool that draws from several
     InfraEnvs scales like any other.

## Alternatives rejected

- **Server classes** (a named set of InfraEnvs a nodepool picks): the user
  asked for InfraEnvs picked directly, and for nothing complicated.
- **One list `infraEnvNames` instead of `infraEnvName`**: the NodePool's name
  and the workflows both read `infraEnvName`.
- **Writing an explicit `name:` when the first InfraEnv goes**: point 5.
- **Counting each node type alone in placement**: two nodepools that share
  `a` would each count `a`'s free servers, and pass on servers there are
  not.
- **Merging overlapping node types without checking their parts**: it lets
  a nodepool that draws only on an empty InfraEnv pass on its neighbour's
  servers.
- **Writing the list with the setting off** and leaving it to the chart:
  today's chart ignores it, and the cluster would draw from its first
  InfraEnv without a word.

## Consequences

- **The chart must render the key before the setting is turned on.** The
  change is drafted for the connected chart and waits for its owners. The
  air-gapped chart needs the same change.
- **herzi orders no servers for a multi-InfraEnv NodePool's demand.** It
  sees a selector that is not its one label. Its InfraEnvs are still topped
  up for their single-InfraEnv NodePools. For a multi-InfraEnv one, it
  needs a rule for whose demand is whose.
- The specs project's own template needs the one block above. Until it has
  it, the form does not offer the input and a flavor that sets it is
  refused.
- New features land in the air-gap off: this one changes nothing there
  until the chart, the template and the setting are in place.

## Verification

- `apps/day1-service/tests/unit/domain/test_nodepool_infra_envs.py`:
  - reading the key;
  - the input rules on and off;
  - the schema without the input;
  - the template checks at save and create;
  - the edit rules: off, the rename, an explicit name, Replace.
- `apps/day1-service/tests/unit/domain/test_mce_capacity_infra_envs.py`:
  - node types;
  - groups that share an InfraEnv;
  - no server counted twice;
  - a short part decides;
  - unknown health.
- `apps/day1-service/tests/api/test_nodepool_infra_envs_api.py`:
  - the schema on and off;
  - a create and a flavor save, on and off;
  - a stale template;
  - edits off and on;
  - `need=a,b:n`.
- `apps/day1-service/tests/api/test_inventory_install_api.py` (the day1
  files fallback) and `tests/unit/domain/test_cluster_text.py` (a sync keeps
  the list).
- `tests/repo/test_chart_env_contract.py`: the chart value.
- `apps/web/lib/infra-envs.test.ts` (the file text edit) and
  `apps/web/e2e/tests/nodepool-infra-envs.spec.ts` (the create form, the
  flavor editor, Edit cluster and the cluster page, on and off).
- The chart draft's `tests/test_nodepool_infra_envs.py`, and a `helm
  template` of a two-InfraEnv nodepool.

## Amendment (2026-11-19): the chart change the owner approved

The hostedclusters-setup change the chart's owner approved is simpler than
the draft decision 1 describes. It is in this repository as patch 0002 in
`docs/upgrade/patches/hostedclusters-setup/`, on the public port of the
chart; the air-gapped chart gets the same change from a separate package.

- With `additionalInfraEnvNames`, the NodePool's `agentLabelSelector` has no
  `matchLabels`, and one `matchExpressions` requirement:
  `{key: infraenvs.agent-install.openshift.io, operator: In, values:
  [infraEnvName, ...additionalInfraEnvNames]}`, in that order, not sorted.
  Without the key, `matchLabels` as before.
- The chart checks nothing about the key: not KubeVirt, not the legacy
  `agentLabelSelector.nodeLabelKey`, not duplicates. Wingman's own rules
  (decision 3, `nodepool_infra_envs.input_problems` and `file_problems`)
  still refuse each of them in what it writes.
- With `excludeAgentLabels` (ADR-0065) too, the same requirement is followed
  by one `DoesNotExist` per key.

Nothing in Wingman changes: it reads the live NodePool's selector with
Kubernetes' rules (ADR-0038), and compares InfraEnvs as sets.

## Amendment (2026-11-23): parked

The team decided that no NodePool draws Agents from more than one InfraEnv
for now; they will add it later. So the feature is parked, not removed:

- Wingman keeps it as decided above, behind `DAY1_MULTI_INFRAENV_NODEPOOLS`
  (`day1.multiInfraEnvNodepools.enabled`), off by default. Its code and
  tests stay; the reference template in `dev/gitlab-fixtures` keeps the
  input block, which the tests use.
- The hostedclusters-setup chart and the specs project's
  `cluster-template.j2` don't carry `additionalInfraEnvNames`. The chart
  patch for it (patch 0002 of the 2026-11-19 amendment) is dropped from
  `docs/upgrade/patches/hostedclusters-setup/`; `excludeAgentLabels`
  (ADR-0065) is now patch 0002, made on the annotations patch alone, and
  keeps `matchLabels` beside its `DoesNotExist` requirements.
- **The setting must stay off until the team adds such NodePools.** On, a
  file could carry the list and a chart without the change would give the
  NodePool its first InfraEnv alone, without a word (Alternatives rejected,
  the last point).

To bring it back: the chart change (the 2026-11-19 amendment's shape, made
again on the current patches), the template block of decision 3 in the
specs project, a herzi rule for such a NodePool's demand, then the setting.
