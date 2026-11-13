import { GitMerge, GitPullRequest } from "lucide-react";
import { Callout, InlineCode, SectionHeader } from "./docs-parts";

/** The docs page's "Approvals" section, `#approvals`. */
export function ApprovalsSection() {
  return (
    <section>
      <SectionHeader id="approvals" icon={GitPullRequest} title="Approvals" subtitle="Review and merge platform Merge Requests" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        The <strong>Approvals</strong> page lists every open Wingman MR in the day1 repo, the specs repo and every
        team repo. Search by title or author, or filter by repo (day1, specs, day2). A <strong>you</strong> chip
        marks your own requests. Open an MR to see its author, branches, head commit, description and the diff of
        every changed file; admins then have three actions:
      </p>
      <div className="space-y-2 mb-5">
        {[
          { title: "Review & Approve", text: "Approves and merges exactly the commit you reviewed (the Head shown on the page)." },
          { title: "Edit Files", text: "Changes a file the MR adds. Your commit goes on top of the branch, never a force-push, and the MR needs a fresh review." },
          { title: "Reject", text: "Closes the MR without merging. The requester makes the change again to retry." },
        ].map(({ title, text }) => (
          <div key={title} className="flex items-start gap-3 rounded-lg border bg-card px-4 py-3">
            <GitMerge className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <p className="text-sm text-muted-foreground min-w-0"><strong>{title}</strong>: {text}</p>
          </div>
        ))}
      </div>
      <div className="space-y-3">
        <Callout type="info" title="You approve the commit you reviewed">
          If anything was pushed to the branch since you loaded it (the day1 CI and the allocate-segment workflow
          commit to cluster MRs), nothing is merged: <strong>Reload</strong> and review the new diff. Nobody
          approves a change they requested themselves; the button is disabled on your own MRs.
        </Callout>
        <Callout type="info" title="The provision-cluster workflow's MRs">
          The day1 MRs the <InlineCode>provision-cluster</InlineCode> workflow opens are listed too, with a{" "}
          <strong>provision-cluster workflow</strong> badge. They open in GitLab: review and merge them there, since
          the workflow records no requester for Wingman to check.
        </Callout>
        <Callout type="tip" title="Each MR has its own address">
          GitLab numbers MRs per repository, so every team&apos;s repo has its own !5. Wingman&apos;s links name
          the repo: <InlineCode>/approvals/day1-12</InlineCode>, <InlineCode>/approvals/specs-4</InlineCode>,{" "}
          <InlineCode>/approvals/day2-redbull-7</InlineCode>.
        </Callout>
        <Callout type="danger" title="MRs go stale">
          Wingman never merges on its own. An MR left open can conflict with later changes (the{" "}
          <strong>Conflicted</strong> badge): Reject it and make the change again from the Wingman UI.
        </Callout>
      </div>
    </section>
  );
}
