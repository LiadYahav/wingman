import { Callout, InlineCode } from "./docs-parts";

/**
 * The cluster page's actions that start one of the platform's workflows:
 * a server's uninstall (ADR-0038) and the cluster's upgrade (ADR-0055).
 */
export function ClusterWorkflowsDocs() {
  return (
    <>
      <h3 className="text-base font-semibold mt-6 mb-3">Uninstall a server</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        An admin&apos;s <strong>Uninstall</strong> beside a server starts the platform&apos;s{" "}
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

      <h3 className="text-base font-semibold mt-6 mb-3">Upgrade a cluster</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        With <InlineCode>DAY1_UPGRADES</InlineCode> on, an admin&apos;s <strong>Upgrade</strong> on the Overview&apos;s
        Mastertag row starts the platform&apos;s <InlineCode>upgrade-cluster</InlineCode> workflow toward a target it
        offers (reading them can take a minute). Start plans and checks, then waits for approval: nothing is committed
        before <strong>Approve</strong>. The <strong>Upgrade</strong> panel on the Overview shows the run in the
        workflow&apos;s words: its phase, what it waits for, its plan step by step, the upgrade agent&apos;s proposals
        and its log. Admins press what it waits for (<strong>Approve</strong>, <strong>Day2 is ready</strong>,{" "}
        <strong>Continue</strong> before each NodePool, <strong>Retry</strong>), and <strong>Pause</strong> or{" "}
        <strong>Abort</strong> (with a reason) while it is open; the run judges each, and a refusal is shown in its
        words. The workflow commits each step to day1 itself, so the History tab shows its commits. A finished
        run&apos;s panel can be dismissed (×) in this browser; the next upgrade shows again.
      </p>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        The Clusters page&apos;s <strong>Upgrades</strong> view (<InlineCode>/clusters#upgrades</InlineCode>) lists
        every cluster&apos;s newest run, open ones first: its status, its phase, what it waits for and when it
        started. Each row opens its cluster, where the decisions are. The list marks each cluster being upgraded with{" "}
        <strong>Upgrading</strong>.
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
