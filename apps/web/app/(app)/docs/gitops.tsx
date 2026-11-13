import { ClipboardList, GitBranch, GitPullRequest, RefreshCw, Shield } from "lucide-react";
import { Callout, SectionHeader } from "./docs-parts";

/** The docs page's "GitOps Workflow" section, `#gitops`. */
export function GitOpsSection() {
  return (
    <section>
      <SectionHeader id="gitops" icon={GitBranch} title="GitOps Workflow" subtitle="Every action in Wingman is a Git commit" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        Wingman never applies changes directly. Every create, edit or delete writes files as one commit on a
        new branch and opens a merge request. This means:
      </p>
      <div className="space-y-3 mb-5">
        {[
          { icon: GitPullRequest, text: "Peer review is built in: another admin reviews the diff and approves it. Nobody approves their own change." },
          { icon: ClipboardList, text: "Full audit trail: every change is a commit that names the person who asked for it." },
          { icon: RefreshCw, text: "Rollback is a revert: revert the merge in GitLab, and ArgoCD applies the revert like any other change." },
          { icon: Shield, text: "Other writers are respected: the allocate-segment workflow and the day1 CI commit to cluster MR branches. A Wingman edit or approval based on an older read is refused instead of overwriting them." },
        ].map(({ icon: Icon, text }) => (
          <div key={text} className="flex items-start gap-3 rounded-lg border bg-card px-4 py-3">
            <Icon className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <p className="text-sm text-muted-foreground min-w-0">{text}</p>
          </div>
        ))}
      </div>
      <Callout type="warning" title="Changes are not immediate">
        Merging an MR changes Git only. For Day1, the ApplicationSet on the MCE turns each cluster file into an
        ArgoCD Application and HyperShift brings the cluster up. For Day2, ArgoCD generates the chart&apos;s
        app; most of these apps are manual-sync and deploy nothing until someone syncs them. Wingman has no
        ArgoCD access, so it never shows sync or health: use the ArgoCD UI, where you can also sync by hand.
      </Callout>
    </section>
  );
}
