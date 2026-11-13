import { RefreshCw } from "lucide-react";
import { Callout, InlineCode, SectionHeader, Step, TermCard } from "./docs-parts";

/** The docs page's "Drift Detection" section, `#drift`. */
export function DriftSection() {
  return (
    <section>
      <SectionHeader id="drift" icon={RefreshCw} title="Drift Detection" subtitle="Know when a cluster differs from its flavor, and sync it back" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        A cluster&apos;s header names its flavor and the version it is on, and drift compares the cluster with{" "}
        <strong>that version</strong>. It is <strong>drifted</strong> when its file does not hold a value the
        version <strong>locks</strong> (someone edited it by hand, or the cluster was written before it joined
        the flavor), or when an add-on the version lists is not installed on it, as Day2 reports. Presets never
        drift: changing them is allowed. A newer version of the flavor is an <strong>update</strong>, never drift.
        An add-on installed at another version than the flavor names is not drift either: Wingman lists it as
        information and never changes it. The cluster list, the flavor&apos;s pages and the cluster&apos;s page show,
        in this order:
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
        {[
          { title: "Drifted", desc: "A value its version locks differs, or an add-on is missing. The Drift tab lists each one: Sync to flavor fixes the values, Install the add-ons." },
          { title: "Unknown", desc: "Drift could not be determined: Day2 did not answer, the cluster file does not parse, the flavor is gone or does not parse, or the header names no version (or one the specs repo never had). It is never shown as in sync." },
          { title: "Update MR open (v1.0.0 → v1.1.0)", desc: "In sync with its version, and the merge request that moves it to the newest is open. The badge opens its review page; its customer merges it when ready." },
          { title: "Update available (v1.0.0 → v1.1.0)", desc: "In sync with its version, and no open merge request moves it to the newest: the flavor's rollout says why (pending, needs a decision, or declined)." },
          { title: "In sync · v1.0.0", desc: "The file holds every value its version locks, every add-on it lists is installed, and it is the flavor's newest." },
          { title: "No flavor", desc: "The cluster follows no flavor. It can join one from that flavor's page (Add existing clusters)." },
        ].map(({ title, desc }) => (
          <TermCard key={title} title={title} desc={desc} />
        ))}
      </div>

      <h3 className="text-base font-semibold mb-3">Viewing and resolving drift</h3>
      <div className="space-y-3 mb-5">
        <Step n={1} title="Find drifted clusters">
          The <strong>Clusters</strong> list shows each cluster&apos;s state and filters by it; the dashboard counts
          drifted clusters, and beside them the unknown ones and those with an update. A flavor&apos;s{" "}
          <strong>Drift</strong> tab lists every cluster that follows it.
        </Step>
        <Step n={2} title="Review what differs">
          Open the cluster → <strong>Drift</strong> tab. <strong>Locked values that differ</strong> shows each one
          with the flavor&apos;s value beside the file&apos;s; for machine configs, the names a sync would add
          and remove. Where Wingman cannot tell a nodepool&apos;s network hardware (it has no network config, or
          two), it says so instead of guessing. Below are the missing add-ons, and add-ons installed at another
          version.
        </Step>
        <Step n={3} title="Sync to flavor">
          <strong>Sync to flavor</strong> (admins) previews one Day1 MR that sets every value the flavor&apos;s
          newest version locks that the file does not hold, and moves the header to that version. While the
          update MR to it is open, the Drift tab links that MR (<strong>Review the update MR !N</strong>) instead:
          it is the sync, and a second one is refused. The preview shows the change line by line,
          asks for the network hardware where a nodepool needs it, and lists every machine config it would
          remove: confirm each one before the sync can be opened. It never touches <InlineCode>vlanId</InlineCode>,{" "}
          <InlineCode>dhcp_values</InlineCode>, <InlineCode>mcFiles</InlineCode>, <InlineCode>mcConfigMap</InlineCode>,
          the CI&apos;s block or your comments.
        </Step>
        <Step n={4} title="Install what is missing">
          Each missing add-on has an <strong>Install</strong> button (admins), and the sync offers to install them
          after its MR. Each opens a Day2 MR that installs the chart at the team&apos;s default version, with the
          values requested when the cluster was created.
        </Step>
      </div>
      <h3 className="text-base font-semibold mb-3">Rolling out a new version</h3>
      <div className="space-y-3 mb-5">
        <Step n={1} title="Review the flavor's MR">
          The approve page of an MR that gives a flavor a new version says what merging it opens:{" "}
          <strong>Merging opens 12 cluster merge requests</strong>, out of the clusters that follow the flavor; the
          clusters whose nodes roll and how (replaced, or drained and rebooted in place); the ones that lose machine
          configs; the ones that need a decision, and why; and the add-ons the version adds. Merging it is the one
          confirmation.
        </Step>
        <Step n={2} title="One MR per cluster">
          Wingman then opens, for each cluster on an older version, one Day1 MR that syncs it to the new version,
          as Sync to flavor would. Its description repeats what it does to that cluster; where the version adds an
          add-on the cluster lacks, Day2&apos;s install MRs open first and are linked. An open MR to an older version
          is closed as superseded. Nothing changes on a cluster until its own MR merges, and each customer merges
          theirs when ready.
        </Step>
        <Step n={3} title="Follow it">
          The flavor&apos;s <strong>Clusters</strong> tab shows the rollout: a count per state, then the clusters,
          those that need a person first. <strong>Needs a decision</strong> (no MR opens; sync it by hand from its
          page), <strong>Failed</strong> (the next run tries again), <strong>Declined</strong> (its customer closed
          the MR: no new one opens for that version, though a person can still sync it by hand),{" "}
          <strong>Pending</strong>, <strong>MR open</strong> and <strong>On the version</strong>.{" "}
          <strong>Reconcile now</strong> (admins) opens what is due at once.
        </Step>
      </div>

      <Callout type="warning" title="Merging a sync that changes machine configs rolls nodes">
        OpenShift applies a nodepool&apos;s new machine configs to every node of it. With the chart&apos;s default
        (<InlineCode>upgradeType: InPlace</InlineCode>) each node is drained and rebooted, one at a time unless
        the nodepool sets <InlineCode>inPlace.maxUnavailable</InlineCode>; a nodepool with{" "}
        <InlineCode>upgradeType: Replace</InlineCode> gets new nodes instead. The sync dialog and the MR say which,
        per nodepool. Nothing happens until the MR is merged: merge it in a window the cluster&apos;s owners accept.
      </Callout>
      <div className="h-4" />
      <Callout type="info" title="Version differences are information only">
        Wingman never offers to move an installed add-on to the flavor&apos;s version: a cluster follows its
        team&apos;s default. To hold one cluster at a version on purpose, use an <strong>emergency pin</strong> on
        its charts page (see Day2 Addons).
      </Callout>
    </section>
  );
}
