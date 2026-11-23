# hostedclusters-setup chart patches

Two keys of a nodepool entry that Wingman writes and the hostedclusters-setup
chart's `main` does not render yet. The change the chart's owner approved, as
`git format-patch` output on the public GitHub port of the chart
(team-redbull/helm-charts-hostedclusters-setup, `main` at `1820ce0`), with
its tests (`tests/test_nodepool_entry_keys.py`). Apply them in order: each is
made on top of the one before. The air-gapped chart gets the same change from
a separate package, not from these files.

| Patch | Key | Renders | Needed for |
|---|---|---|---|
| `0001-feat-a-nodepool-s-annotations-…` | `nodepool[].annotations` | The map onto the NodePool's `metadata.annotations`, as written (`toYaml`), after the chart's own `argocd.argoproj.io/sync-wave: "4"` | A NodePool's scale-down policy ([3.48-to-3.49.md](../../3.48-to-3.49.md) step 4, ADR-0062) |
| `0002-feat-keep-Agents-carrying-a-label-…` | `nodepool[].excludeAgentLabels` | `matchLabels` with the InfraEnv as before, then `matchExpressions` with one `{key: <label>, operator: DoesNotExist}` per key | Excluded Agent labels, herzi's collector of used Agents ([3.48-to-3.49.md](../../3.48-to-3.49.md) step 9, ADR-0065) |

Without the keys, every cluster file renders byte for byte as before. On an
`InPlace` NodePool (the default) a changed selector touches no running node;
on a `Replace` NodePool it replaces every node.

**2026-11-23: no `additionalInfraEnvNames`.** Until then this folder held
three patches, the second for a nodepool that draws Agents from several
InfraEnvs. The team runs no such NodePool for now, so that patch is gone and
the old 0003 is now 0002, made on 0001 alone (ADR-0064 is parked; keep
`day1.multiInfraEnvNodepools.enabled` off). A chart that already has the
three old patches may keep them: without `additionalInfraEnvNames` the old
second patch renders nothing, and the old third selects the same Agents
(its `In [<infraEnvName>]` beside `matchLabels` adds nothing).

## Apply, through the chart repo's own review

`<chart repo>` is the copy the hosted-cluster ApplicationSet reads.

1. **Render every cluster file before the change** (read-only), from a clone
   of the day1 values repo at `main`, the way the ApplicationSet does: the
   value files that exist, in its order, and its parameters (the connected
   copy also passes `site` and `mce`: add them to `--set-string`). With
   production's `clusterName` only:

   ```bash
   render_all() {  # <chart dir> <output dir>; from the day1 repo's root
     local chart=$1 out=$2 f site mce stem name layer
     mkdir -p "$out"
     for f in sites/*/mces/*/hostedClusters/*; do
       site=$(echo "$f" | cut -d/ -f2); mce=$(echo "$f" | cut -d/ -f4)
       stem=$(basename "$f" .yaml)
       name=$(sed -n 's/^clusterName: *//p' "$f" | tr -d "\"' ")
       [ -n "$name" ] || name=${stem#ocp4-}
       files=()
       for layer in sites/configValues.yaml "sites/$site/values.yaml" \
           "sites/$site/mces/$mce/values.yaml" "$f"; do
         [ -f "$layer" ] && files+=(-f "$layer")
       done
       helm template "$stem" "$chart" "${files[@]}" --set-string "clusterName=$name" \
         >"$out/$site.$mce.$stem.yaml" 2>"$out/$site.$mce.$stem.err"
       echo "exit $?" >>"$out/$site.$mce.$stem.err"
     done
     ls "$out"/*.yaml | wc -l
   }
   git -C <chart repo> checkout main
   render_all <chart repo> /tmp/render-before
   ```

   Record the number of files. A `.err` file that does not end in `exit 0`
   fails today too: record it, it is not this change's.
2. **Apply** on a branch. Leave out a patch whose key the chart's
   `templates/nodepool.yaml` already renders:

   ```bash
   cd <chart repo>
   git checkout -b feat/nodepool-selectors main
   git am -3 <patches>/0001-*.patch <patches>/0002-*.patch
   ```

   On a copy that is not the public port, `git am` may stop on a hunk that
   does not match (`git am --show-current-patch=diff` shows it). A hunk of
   `README.md` or `tests/` the copy lacks: write the lines where they fit,
   or leave them out (the tests need the port's
   `tests/fixtures/hostedcluster/`). A hunk of `templates/nodepool.yaml`:
   apply it by hand, it is a few lines. Then `git add` and
   `git am --continue`.
3. **Nothing existing changes.** Render again with the branch and compare:

   ```bash
   render_all <chart repo> /tmp/render-after
   diff -r /tmp/render-before /tmp/render-after && echo IDENTICAL
   ```

   Expect `IDENTICAL` and the same number of files. Anything else: **STOP**,
   and report the files that differ. Where the copy has them, run the
   chart's own tests too: `pytest -q` and `helm lint .`.
4. **The new shapes.** Copy one cluster file outside the day1 repo (never
   commit it: a file on `main` creates a cluster), give its first nodepool
   `annotations: {redbull.io/scale-down-policy: fewest-pods}` and its second
   `excludeAgentLabels: [example.com/used]`, and render it as in step 1 with
   `--show-only templates/nodepool.yaml`. Expect:

   ```yaml
   # the first: the annotation after the chart's own sync-wave
     annotations:
       argocd.argoproj.io/sync-wave: "4"
       redbull.io/scale-down-policy: fewest-pods
   # the second: its InfraEnv label as before, then the label kept out
         agentLabelSelector:
           matchLabels:
             infraenvs.agent-install.openshift.io: <its InfraEnv>
           matchExpressions:
             - key: example.com/used
               operator: DoesNotExist
   ```

   Every NodePool keeps its name. Anything else: **STOP**.

Then the chart repo's review merges the MR. Since every render is the same,
the hosted-cluster Applications stay Synced and Healthy after Argo CD reads
the new chart: check that they do.
