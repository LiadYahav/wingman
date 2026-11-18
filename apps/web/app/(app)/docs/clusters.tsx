import { Pencil, Server, XCircle } from "lucide-react";
import { Callout, CodeBlock, InlineCode, SectionHeader, Step, TermCard } from "./docs-parts";

/** The docs page's "Clusters" section, `#clusters`. */
export function ClustersSection() {
  return (
    <section>
      <SectionHeader id="clusters" icon={Server} title="Clusters" subtitle="Create a hosted cluster from a flavor, then edit or delete it by MR" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        Creating a cluster is a two-step form: choose a flavor, then fill in the values. The flavor sets the
        shape (how many nodepools it starts with), presets values and locks others.
      </p>

      <h3 className="text-base font-semibold mb-4">Worked example — ocp4-prod-herzi-site1</h3>
      <div className="space-y-4 mb-6">
        <Step n={1} title="Choose the flavor">
          Go to <strong>Clusters</strong> → <strong>New Cluster</strong> and pick{" "}
          <InlineCode>agent-standard</InlineCode>. A flavor is required; a flavor file that does not parse is
          shown but cannot be picked.
        </Step>
        <Step n={2} title="Cluster details">
          <ul className="mt-2 space-y-1 list-none">
            <li><InlineCode>Site</InlineCode> → <InlineCode>site1</InlineCode></li>
            <li><InlineCode>Environment</InlineCode> → <InlineCode>prod</InlineCode></li>
            <li><InlineCode>OpenShift Version</InlineCode> → <InlineCode>4.18.56</InlineCode></li>
            <li><InlineCode>MCE</InlineCode> → Wingman&apos;s pick, here <InlineCode>ocp4-prod-mce-site1-a</InlineCode></li>
            <li><InlineCode>Cluster Name</InlineCode> → <InlineCode>ocp4-prod-herzi-site1</InlineCode></li>
          </ul>
          <p className="mt-2">
            You choose the site, <InlineCode>prod</InlineCode> or <InlineCode>prep</InlineCode>, and the version;
            <strong> Wingman picks the MCE</strong>, which runs the cluster&apos;s control plane. The version list is
            what the site&apos;s MCEs of that environment can host (the releases of the day1 repo&apos;s upgrade
            ladder in each MCE&apos;s minors), so it offers only what some MCE there can run; it defaults to the
            flavor&apos;s preset when one of them hosts it. The release becomes the file&apos;s{" "}
            <InlineCode>mastertag</InlineCode>.
          </p>
          <p className="mt-2">
            As soon as those three are chosen, the MCE section lists every candidate, one row each with its
            numbers, and the pick&apos;s row is marked <strong>Wingman&apos;s pick</strong> and chosen. The details
            wait in tooltips, which open on hover, on keyboard focus or on a tap: the ⓘ beside MCE gives the rule,
            the pick&apos;s mark says why it won, each row&apos;s check mark (passes, fails, or passes with some
            checks not made) gives its reasons and numbers, and a dash says why a number is missing. A candidate
            must host the version, have enough free pods for a control plane on its workers, have enough healthy
            free servers of each node type (InfraEnv) the nodepools use, and answer Wingman; among those, the pick
            has the fewest clusters of this owner, then the fewest clusters, then the most usable spare servers.
            The owner&apos;s mador and the nodepools below refine the pick; they are not needed to see one. Where
            this deployment does not read the MCEs live, one line under the table says free pods and servers were
            not checked, and the pick rests on the rest. An MCE that fails a check says why in a few words
            (<InlineCode>no 4.18.56</InlineCode>) and cannot be chosen. An admin may choose another MCE that
            passes, with a reason; the merge request records the numbers, the pick and the reason.
          </p>
          <p className="mt-2">
            Sites and MCEs are the day1 repo&apos;s folders and are read-only: Wingman never creates them, and an
            MCE whose name is off its convention is never a candidate. New names must follow{" "}
            <InlineCode>{"ocp4-<env>-<name>-<site>[-<seq>]"}</InlineCode>, with the environment and the site you
            chose, and a sequence of one letter, <InlineCode>a</InlineCode> to <InlineCode>z</InlineCode>, never a
            number. Once Wingman picks the MCE, the form suggests{" "}
            <InlineCode>{"ocp4-<env>-<flavor>-<site>-<letter>"}</InlineCode> with the first letter no cluster has
            (marked <strong>Suggested</strong>); type over it to use your own. The form lists every problem with a
            name as you type, and fills in the site and the environment when it can read them from the name.
          </p>
        </Step>
        <Step n={3} title="Cluster configuration">
          The fields are the inputs of the shared template. With the default template: the owner numbers
          (merkaz, anaf, mador: digits only) and, per nodepool, its InfraEnv, replicas, machine configs, node
          labels and tuning profiles (picked from <InlineCode>tuning/</InlineCode> in the day1 repo, each with its
          kind and summary; read-only when the flavor locks them). InfraEnvs are picked from the MCE&apos;s list when this deployment reads the
          MCE. Where your operator turns it on, a nodepool may also <strong>draw from</strong> other InfraEnvs: its
          own InfraEnv still names its NodePool, and a new node takes the first free Agent of any of them; Wingman
          counts its free servers over all of them, and never one server twice. Where the specs project&apos;s
          template writes it, each nodepool has a <strong>Scale-down policy</strong>: which nodes leave first when it
          scales down (<InlineCode>fewest-pods</InlineCode>, <InlineCode>least-requested</InlineCode>,{" "}
          <InlineCode>least-utilized</InlineCode>, which needs the hosted cluster&apos;s metrics API), written as its{" "}
          <InlineCode>redbull.io/scale-down-policy</InlineCode> annotation; the <strong>platform default</strong> writes
          nothing, and CAPI picks at random. A flavor that sizes its nodepools by a ratio (<InlineCode>1:2:1</InlineCode>) asks for one size
          instead, and each sized nodepool gets its part times that size. A field the flavor <strong>presets</strong> is filled in and can be changed;
          a field it <strong>locks</strong> is shown read-only with the flavor&apos;s value. Machine configs come
          from a picker of the day1 repo&apos;s <InlineCode>mc-files/</InlineCode>: a static config by name, or{" "}
          <InlineCode>nm-conf</InlineCode> with a hardware type, the cluster&apos;s own network config, written as{" "}
          <InlineCode>{"nm-conf-<clusterName>-<hardware>"}</InlineCode>, or <strong>generic</strong> (the
          default when the day1 repo has <InlineCode>nm-conf-template.bu</InlineCode>), written as plain{" "}
          <InlineCode>nm-conf</InlineCode>. A nodepool you add starts with the
          team&apos;s defaults (<InlineCode>nodepool-defaults.yaml</InlineCode> in the specs repo), unless the
          flavor locks its configs. Every refusal shows at its field.
        </Step>
        <Step n={4} title="Addon configuration">
          If the flavor lists add-ons, set the values it lets you set for each (or switch to{" "}
          <strong>Full Values</strong> for YAML). They are recorded in the cluster file&apos;s header and used
          when the addons are installed: installing them is a Day2 change, from the cluster&apos;s Drift tab.
        </Step>
        <Step n={5} title="Review and open the MR">
          <strong>Review &amp; Create</strong> runs every check a create runs and opens{" "}
          <strong>Review: Create Cluster</strong>, which shows the exact file the MR adds.{" "}
          <strong>Confirm — Create Cluster MR</strong> opens it and takes you to its approval page. Where your operator
          sends creates through the platform&apos;s workflow, the button starts it instead:{" "}
          <a href="#cluster-workflows" className="text-primary hover:underline">Create through provision-cluster</a>.
        </Step>
      </div>

      <CodeBlock language="The file the MR adds — ocp4-prod-herzi-site1.yaml">
{`# specName: "agent-standard"
# specVersion: "1.0.0"
# wingmanAddons: [{"name": "cluster-roles", "override_values": {}, "team": "redbull", "version": "main"}]
owner:
  merkaz: "1234"
  anaf: "56"
  mador: "7"

mastertag: 4.18.56

nodepool:
  - infraEnvName: dell-r660-site1-128c-1024gb-5tb
    replicas: 3
    labels:
      allowDeletion: false
    configs:
      - name: worker-kubeletconfig-reserved
  - infraEnvName: dell-r660-site1-64c-512gb
    replicas: 2
    labels:
      allowDeletion: false`}
      </CodeBlock>

      <h3 className="text-base font-semibold mt-6 mb-3">Who writes which key</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        The cluster file is the values file of the hostedclusters-setup chart. People and automation own
        separate keys, and both commit to the MR branch before it is approved:
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
        {[
          {
            who: "You, through Wingman",
            keys: "owner, mastertag, nodepool[] (infraEnvName, replicas, labels.allowDeletion, configs, name, nodeLabels, tuningConfig), and optional keys such as platform: kubevirt",
          },
          {
            who: "Automation, on the MR branch",
            keys: "vlanId and dhcp_values (the allocate-segment workflow); mcConfigMap, mcFiles and tuningConfigmap (the day1 CI, from mc-files/ and tuning/). Wingman never writes them, and an edit that changes or removes one is refused.",
          },
          {
            who: "The file's path",
            keys: "clusterName, site and mce come from where the file is. Wingman writes none of them; the comment header (# specName, …) is Wingman's own bookkeeping, which Helm ignores.",
          },
        ].map(({ who, keys }) => (
          <div key={who} className="rounded-xl border bg-card p-4">
            <p className="text-sm font-semibold mb-1">{who}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{keys}</p>
          </div>
        ))}
      </div>
      <Callout type="info" title="VLAN and DHCP show as pending">
        The cluster page shows <strong>VLAN</strong> and <strong>DHCP network</strong> as{" "}
        <strong>pending</strong> until the allocate-segment workflow has written them. Approve a create MR once
        the workflow and CI have committed to its branch: the review dialog says so too.
      </Callout>

      <ClusterPageDocs />
    </section>
  );
}

/** The cluster page: its tabs and header, and the Nodes tab. */
function ClusterPageDocs() {
  return (
    <>
      <h3 className="text-base font-semibold mt-6 mb-3">The cluster page</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        The tabs are <strong>Overview</strong> (the cluster, its HostedCluster and network, nodepools, flavor and,
        when it is on, live status), <strong>Nodes</strong> (below), <strong>YAML</strong>, <strong>Drift</strong> and <strong>History</strong>{" "}
        (the cluster file&apos;s commits in the day1 repo, and its chart values&apos; commits in the team repos).
        The header has <strong>GitLab</strong> (the file), <strong>Addons</strong> (its charts) and, for admins,{" "}
        <strong>Edit</strong> and <strong>Delete</strong>. A name off the naming convention is flagged{" "}
        <strong>Off the naming convention</strong>, here and in the list, never hidden: existing clusters keep
        working, and only new names are refused.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="flex gap-4 rounded-xl border bg-card p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Pencil className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold mb-1">Edit</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Edit the file as YAML, then <strong>Review &amp; Submit</strong> shows the diff and opens a modify MR.
              Keep the automation keys as they are. If the file changed since you opened it (CI or the workflow
              committed), the MR is refused and nothing is overwritten: <strong>Reload</strong> and edit again.
              Where nodepools may draw from several InfraEnvs, <strong>InfraEnvs per nodepool</strong> above the
              file adds and removes the others; a nodepool&apos;s own InfraEnv names its NodePool and stays, and
              a <strong>Replace</strong> NodePool&apos;s stay as they are, since a change would replace every node.
              Where the template writes it, or a nodepool already has one, <strong>Scale-down policy per
              nodepool</strong> sets each one&apos;s annotation in the file; it rolls no node.
            </p>
          </div>
        </div>
        <div className="flex gap-4 rounded-xl border bg-card p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500/10">
            <XCircle className="h-4 w-4 text-red-500" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold mb-1">Delete</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              <strong>Confirm — Delete Cluster MR</strong> opens an MR that removes the cluster file. Once it is
              merged, the file and with it the cluster&apos;s ArgoCD Application are gone.
            </p>
          </div>
        </div>
      </div>

      <h3 className="text-base font-semibold mt-6 mb-3">The network and its EPG</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        The Overview tab&apos;s <strong>HostedCluster &amp; network</strong> card shows the HostedCluster&apos;s name and
        namespace, the <InlineCode>clusterName</InlineCode>, and the file&apos;s <strong>VLAN</strong> and{" "}
        <strong>Segment</strong>, which are pending until the allocate-segment workflow writes them. When segments-manager
        is configured (<InlineCode>SEGMENTS_MANAGER_URL</InlineCode>), the card adds the segment&apos;s{" "}
        <strong>EPG</strong> from segments-manager and checks its record against the file. Each disagreement is a warning
        line under the rows: segments-manager has no such segment, or does not mark it Allocated, or gives it to
        another cluster, or has another VLAN for it. The file is what the cluster runs with, so the warnings are for
        you to look into; nothing is written to either side. The EPG shows a dash when there is none, and{" "}
        <strong>unknown</strong>, with why in its tooltip, when segments-manager did not answer.
      </p>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        Under the card, an admin with the Segments area gets <strong>This cluster&apos;s segments</strong>, the{" "}
        <a href="#segments" className="text-primary hover:underline">Segments</a> page filtered to this cluster. Anyone
        else gets a link to segments-manager&apos;s own UI (<InlineCode>SEGMENTS_MANAGER_UI_URL</InlineCode>), which opens
        no single cluster: the card names the cluster to search for, with a copy button, and{" "}
        <strong>this cluster&apos;s segment (JSON)</strong>.
      </p>

      <h3 className="text-base font-semibold mt-6 mb-3">Nodes</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        The cluster page&apos;s <strong>Nodes</strong> tab shows each NodePool as the cluster&apos;s MCE reports it.
        Its header sums it up: how many nodes are ready of how many it wants (or the range it autoscales in), the
        version it last finished updating to, whether an update reboots its nodes in place (<strong>InPlace</strong>)
        or replaces them (<strong>Replace</strong>), and which Agents it takes. Under it is one row per Machine: the
        server behind it, with its serial, hardware, Machine, Agent, state and health, and flags for a server in
        maintenance, stale, unreachable or contested (claimed by two clusters). The server&apos;s name opens its page:
        for an admin with the Server Scan area, its page in <a href="#server-scan" className="text-primary hover:underline">Server Scan</a>,
        here in Wingman; for everyone else, its page in server-scan&apos;s own UI, in a new tab.
        Health server-scan could not determine shows as <strong>Unknown</strong>, never as healthy. Ready, healthy
        rows stay quiet, so what needs a look stands out.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        {[
          {
            title: "An update in progress",
            desc: "A banner says what is being updated (the version or the config), how many nodes are done when an in-place update counts them, and the NodePool's own message. The node the update is working on now is marked, with what is happening to it: “Rebooting for the update”, “Draining”. A failed update is shown in red.",
          },
          {
            title: "The missing piece",
            desc: "A Machine that waits for a server, or a node the NodePool wants and has no Machine for, is a dashed placeholder that says why: usually that no free Agent matches the NodePool. The header then counts the matching Agents and how many are free.",
          },
          {
            title: "In no NodePool",
            desc: "Servers server-scan still places in the cluster that no Machine has are listed apart, under the NodePools. That is usual for a few minutes after an uninstall.",
          },
        ].map(({ title, desc }) => (
          <TermCard key={title} title={title} desc={desc} />
        ))}
      </div>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        The tab reads the MCE as live status does, so it needs <InlineCode>CLUSTER_STATUS_ENABLED</InlineCode>; without
        it, the tab says so (<InlineCode>501 FEATURE_DISABLED</InlineCode>). When server-scan does not answer, the
        Machines are still listed, without links or health. An admin&apos;s <strong>Uninstall</strong> beside a server,
        and <strong>Scale</strong> when it is on, are under{" "}
        <a href="#cluster-workflows" className="text-primary hover:underline">Cluster Workflows</a>.
      </p>
    </>
  );
}
