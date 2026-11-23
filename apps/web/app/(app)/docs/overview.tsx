import { ArrowRight, BookOpen, GitPullRequest, Layers, Package, RefreshCw, Server, Workflow } from "lucide-react";
import { Callout, InlineCode, SectionHeader } from "./docs-parts";

function FeatureCard({ icon: Icon, title, description }: { icon: React.ElementType; title: string; description: string }) {
  return (
    <div className="rounded-xl border bg-card p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2.5 mb-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
          <Icon className="h-3.5 w-3.5 text-primary" />
        </div>
        <p className="text-sm font-semibold min-w-0">{title}</p>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}

/** The docs page's "Platform Overview" section, `#overview`. */
export function OverviewSection() {
  return (
    <section>
      <SectionHeader id="overview" icon={BookOpen} title="Platform Overview" subtitle="What Wingman does and how it fits into your workflow" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-6">
        Wingman covers <strong>Day1</strong>, creating, editing and deleting a hosted cluster, and{" "}
        <strong>Day2</strong>, installing and configuring teams&apos; charts on the hub, the MCEs and the
        clusters. There is no application database: all state lives in Git repositories on GitLab. Around them it
        shows the platform (each MCE&apos;s server pools, each cluster&apos;s servers and segment) and starts the
        platform&apos;s workflows for what a merge request does not do.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        <FeatureCard
          icon={Layers}
          title="Day1 — Hosted Clusters"
          description="Create, edit and delete hosted clusters. A cluster is one short values file for the hostedclusters-setup chart (owner, mastertag, nodepools), proposed as a merge request into the day1 repo."
        />
        <FeatureCard
          icon={Package}
          title="Day2 — Charts"
          description="Install, configure and remove teams' charts on the hub, MCEs, hosted and UPI clusters. Every value shows the layer that set it, and lints check every team repo before a change is proposed."
        />
        <FeatureCard
          icon={RefreshCw}
          title="Drift Detection"
          description="Checks that a cluster holds every value the version of its flavor it is on locks, and has every add-on it lists, and syncs it back in one MR. A new flavor version reaches each cluster through its own MR, which its customer merges when ready. An add-on at another version is reported, never changed. When Wingman cannot tell, it says unknown, never in sync."
        />
        <FeatureCard
          icon={GitPullRequest}
          title="Approval Workflow"
          description="The Approvals page lists the open merge requests of the day1, specs and team repos. Approving merges exactly the commit you reviewed, and nobody approves their own change."
        />
        <FeatureCard
          icon={Workflow}
          title="Platform Workflows"
          description="With the platform's workflows orchestrator: scale a NodePool and uninstall a server; where your operator turns them on, create through provision-cluster, upgrade a cluster, install servers into an MCE's pool. Wingman starts the platform's workflow and shows its run in the workflow's own words."
        />
        <FeatureCard
          icon={Server}
          title="Servers and Segments"
          description="Inventory Management counts each MCE's free servers, for everyone. segments-manager and server-scan live in their own UIs, apart from Wingman: an admin's top bar links to each, in a new tab."
        />
      </div>

      {/* Architecture diagram */}
      <div className="rounded-xl border bg-card overflow-hidden mb-5">
        <div className="px-5 py-3 border-b bg-muted/30">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">How it fits together</p>
        </div>
        <div className="p-5 font-mono text-xs text-muted-foreground leading-loose">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-foreground font-semibold">You</span>
              <ArrowRight className="h-3 w-3" />
              <span className="text-primary">Wingman UI</span>
              <ArrowRight className="h-3 w-3" />
              <span className="text-emerald-500">GitLab MR</span>
              <ArrowRight className="h-3 w-3" />
              <span className="text-blue-500">Approve &amp; merge</span>
              <ArrowRight className="h-3 w-3" />
              <span className="text-foreground">ArgoCD (Day1 + Day2)</span>
            </div>
            <div className="mt-3 pl-4 border-l-2 border-muted space-y-1">
              <p><span className="text-primary">Day1 repo</span>  — one values file per hosted cluster, and the upgrade ladder: the OpenShift versions each MCE offers</p>
              <p><span className="text-amber-500">Specs repo</span> — the shared cluster template and the specs</p>
              <p><span className="text-blue-500">Team repos</span> — one per team under the sigs group: chart defaults, fleet defaults, a folder per destination</p>
            </div>
          </div>
        </div>
      </div>

      <Callout type="info" title="How a new cluster is proposed">
        By default Wingman opens the merge request itself: the day1 CI runs the allocate-segment workflow on the MR
        branch, and a person&apos;s merge is the approval. Your operator can switch creates to the platform&apos;s{" "}
        <InlineCode>provision-cluster</InlineCode> workflow (<InlineCode>DAY1_PROVISIONER=workflow</InlineCode>): Wingman
        then hands it the same file, and the workflow reserves the segment and opens the merge request. Either way
        the cluster is built only once a person merges. See{" "}
        <a href="#cluster-workflows" className="text-primary hover:underline">Cluster Workflows</a>.
      </Callout>
    </section>
  );
}
