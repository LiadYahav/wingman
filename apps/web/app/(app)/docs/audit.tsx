import { AlertTriangle, ArrowRight, CheckCircle, ClipboardList } from "lucide-react";
import { InlineCode, SectionHeader } from "./docs-parts";

/** The docs page's "Audit Log" section, `#audit`. */
export function AuditSection() {
  return (
    <section>
      <SectionHeader id="audit" icon={ClipboardList} title="Audit Log" subtitle="Track every platform change to its author" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        The <strong>Audit Log</strong> page has two tabs. <strong>Commits</strong> lists the newest commits on the
        default branches of the day1, specs and team repos; <strong>Merge Requests</strong> lists the MRs Wingman
        opened on them (the ones labelled <InlineCode>wingman</InlineCode>), open, merged or closed. Click a row to see its diff; each row links to GitLab, and an open MR to its review page.
        Day1 and spec commits are authored by the person who asked for them; Day2 commits name them in the message
        (&quot;Requested by … via Wingman&quot;).
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="rounded-xl border bg-card p-4">
          <p className="text-sm font-semibold mb-2 flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-emerald-500" />
            Captured
          </p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {["Spec create / edit / delete", "Cluster create / edit / delete", "Chart install / update / remove", "Merges", "Commits made directly in GitLab on these repos"].map((i) => (
              <li key={i} className="flex items-center gap-1.5"><ArrowRight className="h-2.5 w-2.5 text-muted-foreground/50" />{i}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border bg-card p-4">
          <p className="text-sm font-semibold mb-2 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            Not captured here
          </p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {["ArgoCD syncs and health", "Events on the clusters and hubs", "GitLab CI/CD pipeline runs", "Other repositories, such as chart repos"].map((i) => (
              <li key={i} className="flex items-center gap-1.5"><ArrowRight className="h-2.5 w-2.5 text-muted-foreground/50" />{i}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
