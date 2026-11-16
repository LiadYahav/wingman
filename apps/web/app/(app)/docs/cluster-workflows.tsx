import { Workflow } from "lucide-react";
import { Callout, InlineCode, SectionHeader } from "./docs-parts";

/**
 * The docs page's "Cluster Workflows" section, `#cluster-workflows`: the
 * changes that start one of the platform's workflows instead of a merge
 * request (ADR-0042 create, ADR-0038 uninstall, ADR-0055 upgrade, ADR-0062 scale).
 */
export function ClusterWorkflowsSection() {
  return (
    <section>
      <SectionHeader id="cluster-workflows" icon={Workflow} title="Cluster Workflows" subtitle="Create, uninstall, upgrade and scale through the platform's workflows" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        Some changes are not Wingman&apos;s merge requests: an admin starts one of the platform&apos;s workflows, and the
        workflow does the work and its own checks. Wingman starts the run and shows it in the workflow&apos;s own words,
        and never retries a start. Each is something your operator turns on; until then a create opens Wingman&apos;s
        own merge request, and the other buttons are greyed out with why, or not there. Installing servers into an MCE
        is the same kind of run, on{" "}
        <a href="#inventory" className="text-primary hover:underline">Inventory Management</a>.
      </p>
      <ProvisionDocs />
      <UninstallDocs />
      <UpgradeDocs />
      <ScaleDocs />
    </section>
  );
}

/** Create through provision-cluster (ADR-0042), behind DAY1_PROVISIONER. */
function ProvisionDocs() {
  return (
    <>
      <h3 className="text-base font-semibold mb-3">Create through provision-cluster</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        By default a create opens Wingman&apos;s own merge request. With <InlineCode>DAY1_PROVISIONER=workflow</InlineCode>{" "}
        (the chart&apos;s <InlineCode>day1.provisioner</InlineCode>), it starts the platform&apos;s{" "}
        <InlineCode>provision-cluster</InlineCode> workflow instead. The form and its checks stay the same; the review
        dialog says the file goes to the workflow, and its button is <strong>Confirm — Start provision-cluster</strong>.
        The workflow reserves the segment, adds <InlineCode>vlanId</InlineCode> and <InlineCode>dhcp_values</InlineCode>,
        pushes the file on its own branch and opens the merge request; a person merges it.
      </p>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        The form then shows the run, <strong>Provisioning</strong> the cluster: its status, its phase, the merge request
        once the workflow has opened one (<strong>Review it</strong>), and its error in the workflow&apos;s words. That
        merge request is listed in Approvals with a badge. Only creates go through the workflow: edit, delete, sync and
        import still open Wingman&apos;s merge requests.
      </p>
    </>
  );
}

/** A server's uninstall (ADR-0038). */
function UninstallDocs() {
  return (
    <>
      <h3 className="text-base font-semibold mt-6 mb-3">Uninstall a server</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        An admin&apos;s <strong>Uninstall</strong> beside a server on the Nodes tab starts the platform&apos;s{" "}
        <InlineCode>uninstall-server-from-hc</InlineCode> workflow on it, once the server&apos;s name is typed again.
        Wingman starts the workflow and shows its run beside the server, with the step it is on, and the workflow
        does the work and its own checks. In short, it drains the node and deletes its Machine, then takes the
        server out of the hosted cluster and out of the MCE (powered off, its BareMetalHost and Agent removed), after
        which server-scan shows it free.
      </p>
      <Callout type="warning" title="A replacement, not a shrink">
        The NodePool keeps its size, so it binds a replacement node in the server&apos;s place: watch for it as the
        missing piece. Nothing is undone if the run fails, and running it again resumes. A server the workflow
        refuses (a contested one, say) fails its run, and the error shows beside the server.
      </Callout>
      <p className="text-sm text-muted-foreground leading-relaxed mt-3">
        Without the workflows orchestrator or server-scan, the servers are listed with no Uninstall button.
      </p>
    </>
  );
}

/** A cluster's upgrade (ADR-0055), behind DAY1_UPGRADES. */
function UpgradeDocs() {
  return (
    <>
      <h3 className="text-base font-semibold mt-6 mb-3">Upgrade a cluster</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        With <InlineCode>DAY1_UPGRADES</InlineCode> on, an admin&apos;s <strong>Upgrade</strong> on the cluster&apos;s
        Overview tab, in its Mastertag row, starts the platform&apos;s <InlineCode>upgrade-cluster</InlineCode> workflow toward a target it
        offers (reading them can take a minute). Start plans and checks, then waits for approval: nothing is committed
        before <strong>Approve</strong>. The <strong>Upgrade</strong> panel on that tab shows the run in the
        workflow&apos;s words: its phase, what it waits for, its plan step by step, the upgrade agent&apos;s proposals
        and its log. Admins press what it waits for (<strong>Approve</strong>, <strong>Day2 is ready</strong>,{" "}
        <strong>Continue</strong> before each NodePool, <strong>Retry</strong>), and <strong>Pause</strong> or{" "}
        <strong>Abort</strong> (with a reason) while it is open; the run judges each, and a refusal is shown in its
        words. The workflow commits each step to day1 itself, so the History tab shows its commits. A finished
        run&apos;s panel can be dismissed (×) in this browser; the next upgrade shows again.
      </p>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        The clusters list shows each cluster&apos;s upgrade under its mastertag. <strong>Upgrading</strong> names the
        run&apos;s phase, says what it waits for in its tooltip, and opens the cluster, where the decisions are.{" "}
        <strong>Upgrade available → 4.18.56</strong> means the cluster&apos;s MCE offers a newer OpenShift than its
        mastertag (the versions a new cluster there may use); it is only a suggestion, since the workflow plans the
        path when the dialog opens and may offer other targets, or none. An admin&apos;s <strong>Upgrade</strong> beside
        it opens the same dialog without leaving the list. An up to date cluster shows nothing. The{" "}
        <strong>Upgrades</strong> filter (<InlineCode>?upgrade=available</InlineCode> or{" "}
        <InlineCode>?upgrade=upgrading</InlineCode>) shows only those clusters.
      </p>
      <Callout type="info" title="Versions change through Upgrade">
        While upgrades are on, an edit (or an MR review edit) that changes <InlineCode>mastertag</InlineCode> or a{" "}
        <InlineCode>workertag</InlineCode>, or adds <InlineCode>pausedUntil</InlineCode>, is refused. Removing{" "}
        <InlineCode>pausedUntil</InlineCode> after an aborted upgrade is a normal edit. Off, an admin sees{" "}
        <strong>Upgrade</strong> greyed out with why, and nothing else mentions upgrades.
      </Callout>
    </>
  );
}

/** Scale through update-nodepool (ADR-0062): off by default, so only what turning it on brings. */
function ScaleDocs() {
  return (
    <>
      <h3 className="text-base font-semibold mt-6 mb-3">Scale a NodePool</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        Scale appears on the Nodes tab when your operator turns it on (<InlineCode>DAY1_SCALE_NODEPOOLS</InlineCode>,
        the chart&apos;s <InlineCode>day1.scaleNodepools.enabled</InlineCode>; off by default). An admin then sets a
        NodePool&apos;s replicas with the <strong>− N +</strong> on its card, one change at a time and after a short
        confirmation, and the platform&apos;s <InlineCode>update-nodepool</InlineCode> workflow does it: one commit to
        day1, no merge request. The run shows under <strong>NodePool sizes</strong> for everyone.
      </p>
      <Callout type="info" title="With Scale on, replicas change only through it">
        An edit that changes an existing NodePool&apos;s <InlineCode>replicas</InlineCode> is refused and points to
        Scale; a new cluster and a new NodePool still set their first replicas. A NodePool whose replicas its flavor
        locks is not scaled, and a flavor sync leaves replicas out and offers <strong>Restore</strong> instead.
        Off, replicas change by editing the cluster or syncing it to its flavor, as everything else.
      </Callout>
    </>
  );
}
