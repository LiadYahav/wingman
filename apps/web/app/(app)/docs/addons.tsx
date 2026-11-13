import { AlertTriangle, ExternalLink, Package, Pin, ShieldAlert } from "lucide-react";
import { Callout, CodeBlock, InlineCode, SectionHeader, Step } from "./docs-parts";

/** The docs page's "Day2 Addons" section, `#addons`. */
export function AddonsSection() {
  return (
    <section>
      <SectionHeader id="addons" icon={Package} title="Day2 Addons" subtitle="Install, configure, and manage charts on the hub, MCEs, hosted and UPI clusters" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        Addons are Helm charts the platform&apos;s ArgoCD deploys. Each belongs to a <strong>team</strong>,
        whose GitLab project under the sigs group holds the add-on itself
        (<InlineCode>operators/{"{chart}"}/</InlineCode>: its deploy config and Sig values) and a folder per
        destination that gets it. A
        folder existing is the registration: Wingman installs a chart by opening an MR that adds the folder.
        There are four kinds of destination:
      </p>
      <CodeBlock language="Where a chart's folder lives, per destination kind">
{`hub      defaults/hub/{chart}/
mce      sites/{site}/{env}/mces/{mce}/in-cluster/{chart}/
hosted   sites/{site}/{env}/mces/{mce}/{cluster}/{chart}/
upi      sites/{site}/{env}/upi/{cluster}/{chart}/`}
      </CodeBlock>
      <p className="text-sm text-muted-foreground leading-relaxed mt-3 mb-5">
        The <strong>Addons</strong> page (<strong>Addon Catalog</strong>) lists every team&apos;s add-ons with their
        Sig values, deploy config, versions and fleet defaults; a hosted cluster&apos;s charts are on its page.
      </p>

      <h3 className="text-base font-semibold mt-6 mb-3">A team&apos;s add-ons and their defaults</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        An add-on is a chart in a team&apos;s catalog: <InlineCode>operators/{"{chart}"}/</InlineCode> in the team&apos;s
        repo, with its deploy config and Sig values, and the fleet defaults built from it
        (<InlineCode>defaults/{"{scope}"}/{"{chart}"}/</InlineCode>). Everything about it is on the{" "}
        <strong>Addons</strong> page:
      </p>
      <CodeBlock language="An add-on's values (lowest → highest)">
{`Chart values    the chart's own values.yaml
Sig values      operators/{chart}/values.yaml in the team's repo
Cluster values  what a cluster gets where the add-on is used: create, a flavor, its charts page`}
      </CodeBlock>
      <ul className="text-sm text-muted-foreground leading-relaxed mb-3 list-disc space-y-1 pl-5">
        <li>
          <strong>New add-on</strong>, on a team, adds one to the team&apos;s catalog; an add-on&apos;s{" "}
          <strong>Edit add-on</strong> (the same fields) changes its deploy config, sync options and Sig values.
        </li>
        <li>
          Its <strong>Defaults &amp; overrides</strong> page has one panel per scope (hosted clusters, MCEs, the hub,
          UPI clusters): make it a default there and edit that default; give one env (prod, prep or test) or one
          MCE, hosted cluster or UPI cluster its own values; and <strong>Deploy on specific MCEs</strong>, for an
          add-on wanted on some MCEs only. Which add-ons a hosted cluster has of its own comes from its flavor and
          the create form.
        </li>
        <li>
          Installing it on one cluster, and configuring or removing it there, is on that cluster&apos;s page (its{" "}
          <strong>Addons</strong> tab), as described below.
        </li>
      </ul>
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        Every change to an add-on is one merge request on the team&apos;s repo, previewed first. The preview lists each
        destination whose app changes, goes or comes, key by key; the ones that change or go must be confirmed, and
        the merge request is opened only for the plan you saw: if the repo changed in between, Wingman shows the new
        plan instead. A team that has not given Wingman write access is read-only.
      </p>

      <h3 className="text-base font-semibold mt-6 mb-3">Value layering</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-3">
        On top of the chart&apos;s own defaults, the platform merges up to ten files from the team&apos;s repo,
        as Helm does: a later layer wins, and <InlineCode>null</InlineCode> deletes a key, even a chart default.
        For a hosted cluster, with the names the UI shows:
      </p>
      <CodeBlock language="Hosted-cluster value stack (lowest → highest)">
{`chart                 the chart's own values.yaml, at the resolved revision
sig values            operators/{chart}/values.yaml
sig values · ocp      operators/{chart}/ocp-versions/{ocp}/values.yaml
site                  sites/{site}/values.yaml
site · env            sites/{site}/{env}/values.yaml
fleet                 defaults/hosted-clusters/{chart}/values.yaml
fleet · env           defaults/hosted-clusters/{chart}/values-{env}.yaml
fleet · this cluster  defaults/hosted-clusters/{chart}/values-{cluster}.yaml
mce                   sites/{site}/{env}/mces/{mce}/values.yaml
cluster-wide          …/{cluster}/values.yaml
cluster               …/{cluster}/{chart}/values.yaml
                      ↑ the file Wingman writes when you edit a chart's values`}
      </CodeBlock>
      <p className="text-sm text-muted-foreground leading-relaxed mt-3 mb-5">
        MCEs, UPI clusters (with an <InlineCode>upi-wide</InlineCode> layer) and the hub have stacks of their own.
        A chart&apos;s values table shows every merged value with the layer that set it (<strong>Set by</strong>);
        its <strong>Layers</strong> tab lists the stack file by file, and <strong>Deployment</strong> shows the
        ArgoCD app it generates. Editing a value writes it into the destination&apos;s file; <em>inherit</em>{" "}
        takes it out again.
      </p>

      <AddonChartsDocs />
    </section>
  );
}

/** A chart on a destination: installing, pinning, fleet defaults, its menu, and lints. */
function AddonChartsDocs() {
  return (
    <>
      <h3 className="text-base font-semibold mt-6 mb-4">Installing a chart</h3>
      <div className="space-y-3 mb-5">
        <Step n={1} title="Open the destination's charts">
          From a cluster&apos;s page (<strong>Addons</strong>), a destination&apos;s name on an add-on&apos;s page, or a
          destination a finding names on the <strong>Lints</strong> page. The charts page lists what is{" "}
          <strong>Installed</strong> and what is <strong>Available</strong>.
        </Step>
        <Step n={2} title="Pick a chart under Available">
          Click <strong>Install</strong>, or select several and use <strong>Install selected</strong>: one MR per
          team. Every chart is checked first, and if one is refused, none is opened. A chart that needs its own
          repourl is installed on its own.
        </Step>
        <Step n={3} title="Set only what differs">
          The form shows the values the chart would get; change only what this destination needs. The revision is
          inherited (the add-on&apos;s, its OCP-version pin, or a fleet default; else <InlineCode>HEAD</InlineCode>,
          the chart repo&apos;s default branch).
        </Step>
        <Step n={4} title="Review and open the MR">
          <strong>Review install</strong> shows the files the MR creates, with an optional note for the approver.
          After it is merged, ArgoCD generates the app; a manual-sync app deploys nothing until someone syncs it.
          Wingman has no ArgoCD access, so it never shows sync or health.
        </Step>
      </div>

      <h3 className="text-base font-semibold mb-3">Emergency pins</h3>
      <div className="flex gap-4 rounded-xl border bg-card p-4 mb-5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
          <Pin className="h-4 w-4 text-amber-500" />
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed min-w-0">
          Choosing a <strong>Revision</strong> other than the inherited one writes a{" "}
          <InlineCode>targetRevision</InlineCode> into the destination&apos;s folder: an{" "}
          <strong>emergency pin</strong>. The destination then stops following the add-on&apos;s revision and its
          OCP-version pins until someone removes the pin, so you must tick <strong>Pin … anyway</strong> first.
          On every destination but the hub, a pinned chart shows a <strong>pinned</strong> badge; choosing the
          inherited revision again removes the pin. This is the only way Wingman holds one cluster at a version.
        </p>
      </div>

      <h3 className="text-base font-semibold mb-3">Fleet defaults</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        A chart in a team&apos;s <InlineCode>defaults/{"{scope}"}/</InlineCode> (<InlineCode>mces</InlineCode>,{" "}
        <InlineCode>hosted-clusters</InlineCode> or <InlineCode>upi</InlineCode>) is deployed to every destination
        of that kind the team&apos;s repo has a folder for. It appears as <strong>fleet default</strong>; editing it
        writes <InlineCode>defaults/{"{scope}"}/{"{chart}"}/values-{"{cluster}"}.yaml</InlineCode>. It cannot be
        removed or pinned for one cluster from the cluster&apos;s page, nor installed into a cluster folder as well
        (that would generate the app twice). On the add-on&apos;s <strong>Defaults &amp; overrides</strong> page (from
        the Addons page), the MCE, hosted-cluster and UPI panels have values per env
        (<InlineCode>values-{"{env}"}.yaml</InlineCode>) and list every destination of the default with{" "}
        <strong>Override values</strong>: that destination&apos;s own values file, above the env&apos;s (the effective
        values before and after are shown, with the layer that sets each). Wingman does not exclude destinations from a default: an add-on wanted on some MCEs only
        is not a default, it is deployed on those MCEs (<strong>Deploy on specific MCEs</strong>: one install merge
        request per MCE, into its own <InlineCode>in-cluster/{"{chart}"}/</InlineCode>). A repo&apos;s existing{" "}
        <InlineCode>exclusions.yaml</InlineCode> is read and shown as it is.
      </p>

      <h3 className="text-base font-semibold mb-3">The chart&apos;s ⋮ menu</h3>
      <div className="space-y-3 mb-5">
        <div className="flex gap-4 rounded-xl border bg-card p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <ExternalLink className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold mb-1">Open folder in GitLab</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Opens the chart&apos;s folder in the team repository (for a fleet default, its{" "}
              <InlineCode>defaults/{"{scope}"}/{"{chart}"}</InlineCode> folder). Visible to all users, including Viewers.
            </p>
          </div>
        </div>
        <div className="flex gap-4 rounded-xl border bg-card p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500/10">
            <AlertTriangle className="h-4 w-4 text-red-500" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold mb-1">Remove from this cluster (on the hub: Remove from the hub)</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Opens an MR deleting the chart&apos;s folder (type the chart&apos;s name, then{" "}
              <strong>Open removal MR</strong>). That deletes its ArgoCD Application, but ArgoCD{" "}
              <strong>orphans the workload: it keeps running</strong>. A teardown needs{" "}
              <InlineCode>argocd app delete {"<app>"} --cascade</InlineCode> after the merge. Admin-only; a fleet
              default shows how to exclude it instead.
            </p>
          </div>
        </div>
      </div>

      <h3 className="text-base font-semibold mb-3">Lints</h3>
      <div className="flex gap-4 rounded-xl border bg-card p-4 mb-5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <ShieldAlert className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0 space-y-2 text-xs text-muted-foreground leading-relaxed">
          <p>
            The <strong>Lints</strong> page lists every finding in every team repo, by severity. Errors include
            every check the platform&apos;s own render check fails on: an env folder other than{" "}
            <InlineCode>prod</InlineCode>, <InlineCode>prep</InlineCode> or <InlineCode>test</InlineCode>, a cluster
            folder day1 has no version for, a malformed or misspelled <InlineCode>exclusions.yaml</InlineCode>, a
            chart that is both a fleet default and in a cluster&apos;s folder. Wingman adds checks of its own: errors
            for a deploy config with no lowercase <InlineCode>repourl</InlineCode> or a file that is not valid YAML,
            and warnings for a miscased <InlineCode>repoUrl</InlineCode>, a chart pinned per OCP version with no pin
            for a cluster&apos;s version, a fleet default&apos;s <InlineCode>targetRevision</InlineCode> that
            overrides the OCP-version pins, and a cluster name placed at more than one position across team repos.
            An emergency pin is listed as information. Every chart repo a <InlineCode>repourl</InlineCode> names is
            checked too: a repo GitLab renamed or moved is a warning that gives the URL to write, and a repo GitLab
            refuses is an error on that chart alone; the rest of the catalog still loads.
          </p>
          <p>
            Findings also appear on the charts pages and the catalog. Before any Day2 MR opens, the team repo
            is checked as it would be after the change: a change that adds an error is refused, while existing
            errors do not block unrelated changes. On every charts page but the hub&apos;s,{" "}
            <strong>Upgrade check</strong> lists the charts a new OCP version would leave without an OCP-version pin.
          </p>
        </div>
      </div>

      <Callout type="tip" title="Addon override example">
        Say the Sig values of the redbull team&apos;s <InlineCode>cluster-roles</InlineCode> chart set{" "}
        <InlineCode>aggregateToView: true</InlineCode>. For <InlineCode>ocp4-prod-herzi-site1</InlineCode> you set{" "}
        <InlineCode>aggregateToView: false</InlineCode>. Only that value is written, to{" "}
        <InlineCode>sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/cluster-roles/values.yaml</InlineCode>{" "}
        in the redbull repository; the Sig values are unaffected.
      </Callout>
    </>
  );
}
