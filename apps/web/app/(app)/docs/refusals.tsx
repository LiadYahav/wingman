import { XCircle } from "lucide-react";
import { SectionHeader } from "./docs-parts";

/** What a refusal looks like, why it happens and what to do (ADR-0004: match on `code`). */
const REFUSALS = [
  {
    code: "409 REVISION_CONFLICT",
    see: "“… changed since you opened it”, or “The branch moved since you loaded this MR”: most pages offer Reload, and a chart's values editor reloads itself and says so",
    why: "Someone committed to the file or the MR branch after you loaded it: another person, the day1 CI or the allocate-segment workflow. Nothing was written or merged.",
    fix: "Reload if the page has not, look at what changed, and make your change (or review) again.",
  },
  {
    code: "409 ALREADY_EXISTS",
    see: "“This cluster name is taken”, “A spec named … already exists”, or a chart that is already on the destination",
    why: "The name is used by a cluster anywhere in the day1 repo or by an open create MR; the spec exists; the chart is already installed there, or is a fleet default of that kind.",
    fix: "Pick another name, or edit what exists. For a fleet default, edit its values for this cluster instead.",
  },
  {
    code: "422 VALIDATION_ERROR",
    see: "A red box headed “… fix the following” (or “The change was refused”) listing every problem",
    why: "The change breaks one or more rules: the naming convention, an automation-owned key, an unconfirmed emergency pin, a lint error the change would add. All of them are listed at once.",
    fix: "Fix every listed problem, then submit again.",
  },
  {
    code: "403 FORBIDDEN",
    see: "“This needs the admin role.”, or at sign-in “You are not in a Wingman group. Ask an admin for access.”",
    why: "You are a Viewer. At sign-in, the same code means you are in no Wingman group. (A Viewer who opens a create page is shown “Insufficient permissions” without any request being made.)",
    fix: "Ask your platform team to add you to an admin group, then sign in again.",
  },
  {
    code: "403 SELF_APPROVAL",
    see: "“You requested this change, so another admin must approve it.”",
    why: "Nobody approves their own change. The Review & Approve button is disabled on your own MRs.",
    fix: "Ask another admin to review it.",
  },
  {
    code: "409 NOT_MERGEABLE",
    see: "“GitLab cannot merge this MR right now”",
    why: "The branch conflicts with the target (the Conflicted badge), or GitLab refused the merge.",
    fix: "Open the MR in GitLab to see why; for a conflict, Reject it and make the change again.",
  },
  {
    code: "501 FEATURE_DISABLED",
    see: "“Live status is off”, “Live status is off in this deployment”, or “Nodes need live status from the MCE”",
    why: "This deployment does not read HostedClusters from the MCE hubs. It is not an error.",
    fix: "Nothing to fix. InfraEnv names are typed instead of picked, and the Nodes tab lists no NodePools.",
  },
  {
    code: "504 AMBIGUOUS_WRITE",
    see: "A message that GitLab did not confirm the change, so it may or may not have been made; or that an uninstall's start was not confirmed",
    why: "GitLab (for an uninstall, the workflows orchestrator) timed out after receiving the write, so it may or may not have happened. Wingman never retries a write.",
    fix: "Check the Approvals page (or the repo in GitLab) for the MR, or the node's run for an uninstall, before trying again.",
  },
] as const;

/** The docs page's "When a Change Is Refused" section, `#errors`. */
export function RefusalsSection() {
  return (
    <section>
      <SectionHeader id="errors" icon={XCircle} title="When a Change Is Refused" subtitle="What Wingman tells you, why, and what to do" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        A refused change writes nothing. Wingman says why on the page you are on; the code below is what the
        service returned, and the <strong>request</strong> id under an error ties it to the service&apos;s log:
        quote it when you report a problem.
      </p>
      <div className="space-y-3">
        {REFUSALS.map(({ code, see, why, fix }) => (
          <div key={code} className="rounded-xl border bg-card p-4">
            <div className="flex flex-col sm:flex-row sm:items-start gap-2 sm:gap-4">
              <span className="inline-flex shrink-0 items-center rounded-md bg-muted px-2 py-0.5 text-[11px] font-mono font-semibold text-foreground sm:w-48">{code}</span>
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium text-foreground">{see}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{why}</p>
                <p className="text-xs text-muted-foreground leading-relaxed"><strong>What to do:</strong> {fix}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
