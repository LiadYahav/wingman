import { Layers } from "lucide-react";
import { Callout, CodeBlock, InlineCode, SectionHeader, Step, TermCard } from "./docs-parts";

/** The docs page's "Flavors" section, `#specs`. */
export function FlavorsSection() {
  return (
    <section>
      <SectionHeader id="specs" icon={Layers} title="Flavors" subtitle="What every cluster of a kind gets, and what it may change" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        A flavor is a reusable class of cluster (the API and the specs repo call it a spec). It sets how many
        nodepools a cluster starts with, gives each value it sets either as a <strong>preset</strong> or{" "}
        <strong>locked</strong>, and lists the Day2 add-ons its clusters should have. Every flavor fills the same
        shared template, <InlineCode>cluster-template.j2</InlineCode> in the specs repo, so flavors differ in
        values, not in templates.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
        {[
          { title: "Preset", desc: "Prefilled in the create form; a cluster may change it. A preset never drifts." },
          { title: "Locked", desc: "Fixed: every cluster gets exactly this value, the create form shows it read-only and day1 refuses another, and a later edit of the file shows as drift. Lockable: the owner numbers, the platform, and per nodepool its replicas, machine configs and node labels." },
        ].map(({ title, desc }) => (
          <TermCard key={title} title={title} desc={desc} />
        ))}
      </div>

      <h3 className="text-base font-semibold mb-4">Creating a flavor — worked example</h3>
      <p className="text-sm text-muted-foreground mb-4">
        We will walk through <InlineCode>agent-baseline</InlineCode>: every nodepool of its clusters gets the
        team&apos;s machine configs, and every cluster gets the redbull team&apos;s cluster-roles add-on. Go to{" "}
        <strong>Flavors</strong> → <strong>New Flavor</strong>; the editor has four parts, listed in the bar at
        the top, which also counts the problems in each.
      </p>
      <div className="space-y-4 mb-6">
        <Step n={1} title="Basics">
          The name <InlineCode>agent-baseline</InlineCode> (a lowercase DNS label; a flavor keeps its name), a
          version and a description. Under <strong>Owner and platform</strong>, the owner numbers (digits only)
          and the platform. Each has a <strong>Preset | Locked</strong> switch: leave a preset empty and each
          cluster fills it in. Other template inputs can be preset too, in the collapsed group below.
        </Step>
        <Step n={2} title="Nodepools">
          Add nodepools: each starts with the team&apos;s defaults (<InlineCode>nodepool-defaults.yaml</InlineCode>{" "}
          in the specs repo). Then choose how machine configs work: <strong>Each nodepool its own</strong> (a list
          per nodepool, preset or locked by position), or <strong>The same on every nodepool</strong>: one list,
          locked as a rule, so every nodepool of every cluster has exactly these configs, whatever its number or
          order. Configs come from the picker: a file of <InlineCode>mc-files/</InlineCode> by name, or{" "}
          <InlineCode>nm-conf</InlineCode>, the cluster&apos;s own network config, with a hardware type (under
          the rule, each nodepool picks its own). The type starts at <strong>generic</strong> when the day1 repo has
          the generic template (<InlineCode>nm-conf-template.bu</InlineCode>, for any hardware, written as plain{" "}
          <InlineCode>nm-conf</InlineCode>). Replicas and node labels are preset or locked per nodepool.
        </Step>
        <Step n={3} title="Add-ons">
          Pick charts from the catalog and put them in order. The gear opens{" "}
          <strong>Configure overrideable fields</strong>: the values a cluster&apos;s creator may set for that
          add-on. Everything else comes from the chart&apos;s defaults.
        </Step>
        <Step n={4} title="Review">
          Lists what every cluster gets (<strong>Locked</strong>) and what it starts from (<strong>Presets</strong>),
          and shows the flavor file. On an existing flavor&apos;s edit page it also previews the cluster file the
          flavor produces, on an MCE and release you choose. <strong>Review &amp; Create</strong> runs day1&apos;s
          checks and <strong>Confirm — Create Flavor MR</strong> opens the MR in the specs repo; the flavor can be
          used once it is merged. Every refusal shows at its field.
        </Step>
      </div>

      <CodeBlock language="The flavor file — specs/agent-baseline.yaml">
{`apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: agent-baseline
  description: Every nodepool gets the team's machine configs
  version: "1.0.0"
spec:
  day1:
    structure:                 # clusters start with one nodepool
      nodepools:
        - configs: [{}, {}, {}]
    locked_paths:              # fixed; every other value is a preset
      - nodepools[*].configs   # the rule: every nodepool, exactly these
    values:
      nodepools:
        - configs:
            - name: nm-conf    # the cluster's own network config,
              hardware: dell   #   written as nm-conf-<clusterName>-dell
            - name: workers-chrony-configuration
            - name: nic-ring-buffer
  day2:
    addons:
      - team: redbull
        name: cluster-roles
        version: main
        overrideable: []       # the values a creator may set`}
      </CodeBlock>

      <h3 className="text-base font-semibold mt-6 mb-3">Adding existing clusters to a flavor</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        Clusters written before Wingman, or created from another flavor, can join one from the flavor&apos;s
        page: <strong>Add existing clusters</strong> (admins).
      </p>
      <div className="space-y-3 mb-5">
        <Step n={1} title="Pick">
          Search by name and filter by site, MCE and owner numbers; pick up to 50.
        </Step>
        <Step n={2} title="Preview">
          Each cluster shows whether it can join (<strong>Ready</strong>; on another flavor, which needs{" "}
          <strong>Move to this flavor</strong>; already on it; or can&apos;t be imported, and why) and what will
          show as drift once it has: the configs a sync would add and remove per nodepool, and the missing add-ons.
        </Step>
        <Step n={3} title="Import">
          One Day1 MR per cluster writes only the flavor link (<InlineCode># specName</InlineCode>,{" "}
          <InlineCode># specVersion</InlineCode>) into its file&apos;s header, so each cluster is approved, merged
          or rejected on its own. Every pick is checked first: if one can&apos;t be imported, none opens. Nothing
          changes on the clusters. The last step lists each MR, and each cluster whose MR did not open and why.
          Once a cluster&apos;s MR merges it shows its differences as drift, and <strong>Sync to flavor</strong> on
          its page fixes them (see Drift Detection).
        </Step>
      </div>

      <div className="mt-5 space-y-4">
        <Callout type="tip" title="Example comments in the template">
          A <InlineCode># Example: value</InlineCode> or <InlineCode>{"{# Example: value #}"}</InlineCode> comment
          on a line just before an input in <InlineCode>cluster-template.j2</InlineCode> becomes that field&apos;s
          hint in the create form.
          <div className="mt-2">
            <CodeBlock language="cluster-template.j2 snippet">
{`  {# Example: dell-r660-site1-128c-1024gb-5tb #}
  - infraEnvName: {{ np.infra_env }}`}
            </CodeBlock>
          </div>
        </Callout>
        <Callout type="warning" title="An edit is a new version, and reaches each cluster through its own MR">
          Saving an edit needs a new version: a version, once saved, never changes, because each cluster is
          compared with the version it is on. Merging the flavor&apos;s MR rewrites no cluster file. Instead Wingman
          opens one Day1 MR per cluster that follows the flavor on an older version, and each customer merges
          theirs when ready (see Rolling out a new version, under Drift Detection). Until then the cluster shows{" "}
          <strong>Update MR open</strong>, not drift. A flavor that clusters follow cannot be deleted; delete or
          move them first.
        </Callout>
      </div>
    </section>
  );
}
