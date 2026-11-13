import { AlertTriangle, FileCode2, Network, Zap } from "lucide-react";
import { SectionHeader } from "./docs-parts";

/** The docs page's "Troubleshooting" section, `#troubleshooting`. */
export function TroubleshootingSection() {
  return (
    <section>
      <SectionHeader id="troubleshooting" icon={AlertTriangle} title="Troubleshooting" subtitle="Common issues and how to fix them" />
      <div className="space-y-4">
        {[
          {
            q: "“The cluster file could not be rendered: fix the following”",
            a: (
              <>
                The template is rendered in a sandbox with strict undefined variables, and the result must be a valid
                cluster file. Every problem is listed: fill in each named field, and keep values on one line, at most
                253 characters, without double quotes or backslashes.
              </>
            ),
          },
          {
            q: "Cluster shows as drifted right after creation",
            a: "Drift compares the flavor's add-ons with what Day2 has installed. A new cluster's add-ons are not installed until someone installs them: once the cluster's MR is merged, install them from its Drift tab.",
          },
          {
            q: "MR was merged but cluster is still not provisioned",
            a: (
              <>
                Provisioning is asynchronous. The MCE&apos;s ApplicationSet makes an ArgoCD Application for the file,
                which may need a manual sync; HyperShift then brings up the control plane and the nodepools claim hosts
                from their InfraEnv. Look at the Application in ArgoCD for sync errors. When live status is on, the
                cluster page shows the HostedCluster and its node pools.
              </>
            ),
          },
          {
            q: "Addon installed but not appearing in the cluster",
            a: (
              <>
                Most leaf apps are manual-sync: after the merge ArgoCD generates the app, but nothing
                deploys until someone syncs it in ArgoCD (Wingman has no ArgoCD access). Use{" "}
                <strong>Open folder in GitLab</strong> from the chart&apos;s menu to confirm the folder is on{" "}
                the branch the platform reads (the one Day2 targets), then sync the app named on the chart&apos;s{" "}
                <strong>Deployment</strong> tab.
              </>
            ),
          },
          {
            q: "“No sites in the day1 repo”, “No MCEs on this site”, or an MCE I cannot pick",
            a: "Wingman reads sites and MCEs from the day1 repository's folders and never creates them: onboarding a site or MCE happens outside Wingman. An MCE marked off convention cannot host new clusters, because the env a new name must carry cannot be checked against it.",
          },
          {
            q: "An install asks me to confirm an emergency pin",
            a: "You chose a revision other than the inherited one. Pick the inherited revision to follow the add-on, or confirm the pin if this destination really must stay on that version.",
          },
          {
            q: "I cannot see Create / Install / Remove / Approve buttons",
            a: (
              <>
                You have the <strong>Viewer</strong> role. Write operations require the <strong>Admin</strong>{" "}
                role: ask your platform team, then sign in again. On your own MR, <strong>Review &amp; Approve</strong>{" "}
                is shown but disabled: another admin must approve it.
              </>
            ),
          },
        ].map(({ q, a }) => (
          <div key={q} className="rounded-xl border bg-card overflow-hidden">
            <div className="flex items-start gap-3 px-5 py-4 border-b bg-muted/20">
              <Zap className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              <p className="text-sm font-semibold min-w-0 break-words">{q}</p>
            </div>
            <div className="px-5 py-4 sm:pl-12">
              <p className="text-sm text-muted-foreground leading-relaxed">{a}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-xl border bg-gradient-to-br from-primary/5 to-transparent p-5">
        <div className="flex items-center gap-2 mb-2">
          <Network className="h-4 w-4 text-primary" />
          <p className="text-sm font-semibold">Still stuck?</p>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed">
          The platform is fully transparent: every resource is a plain YAML or Jinja2 file in GitLab, and
          clusters, specs, charts and MRs link to theirs. See{" "}
          <a href="#errors" className="text-primary underline underline-offset-2 hover:no-underline">When a Change Is Refused</a>{" "}
          for what each refusal means. The platform team is also reachable via your organisation&apos;s internal
          channels; quote the request id an error shows.
        </p>
      </div>

      <div className="mt-4 rounded-xl border bg-card p-4">
        <div className="flex items-center gap-2 mb-2">
          <FileCode2 className="h-4 w-4 text-muted-foreground" />
          <p className="text-sm font-semibold">For platform operators</p>
        </div>
        <p className="text-xs text-muted-foreground pl-6">
          See the <a href="#filelocations" className="text-primary underline underline-offset-2 hover:no-underline">File Locations</a> section above for
          the map of repositories and exact file paths.
        </p>
      </div>
    </section>
  );
}
