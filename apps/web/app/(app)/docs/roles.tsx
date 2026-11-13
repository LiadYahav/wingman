import { CheckCircle, Eye, Lock, Shield } from "lucide-react";
import { Callout, InlineCode, SectionHeader } from "./docs-parts";

/** The docs page's "Roles & Access" section, `#roles`. */
export function RolesSection() {
  return (
    <section>
      <SectionHeader id="roles" icon={Shield} title="Roles & Access" subtitle="Sign in with OpenShift; your OpenShift groups decide your role" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
        <div className="rounded-xl border bg-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 shrink-0">
              <Lock className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold">Admin</p>
              <p className="text-xs text-muted-foreground">Proposes and approves changes</p>
            </div>
          </div>
          <ul className="space-y-2">
            {[
              "Create, edit and delete flavors and clusters; add existing clusters to a flavor and sync them",
              "Install, edit and remove charts",
              "Install a flavor's missing add-ons from a cluster's Drift tab",
              "Approve, edit or reject other people's MRs",
              "Everything a Viewer can do",
            ].map((item) => (
              <li key={item} className="flex items-center gap-2 text-xs text-muted-foreground">
                <CheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border bg-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted shrink-0">
              <Eye className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold">Viewer</p>
              <p className="text-xs text-muted-foreground">Read-only access</p>
            </div>
          </div>
          <ul className="space-y-2">
            {[
              "Browse clusters, flavors and add-ons",
              "See drift, lints and live status",
              "Read pending approvals and their diffs",
              "Read the audit log",
              "Open anything in GitLab",
            ].map((item) => (
              <li key={item} className="flex items-center gap-2 text-xs text-muted-foreground">
                <CheckCircle className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="space-y-3">
        <Callout type="info" title="Signing in and how roles are assigned">
          <strong>Log in via OpenShift</strong> sends you to your organisation&apos;s OpenShift OAuth server.
          Your role comes from your <strong>OpenShift groups</strong>: the deployment&apos;s admin groups
          (<InlineCode>WINGMAN_ADMIN_GROUPS</InlineCode>) make you an Admin, its viewer groups
          (<InlineCode>WINGMAN_VIEWER_GROUPS</InlineCode>) a Viewer; Admin wins if you are in both. Someone in
          neither is turned away: &quot;You are not in a Wingman group&quot;. The role is fixed when you sign
          in, so after a group change sign out and in again (a session lasts 8 hours by default).
        </Callout>
        <Callout type="warning" title="Dev login is for local development only">
          A local stack can run without OpenShift: the login page then shows a <strong>Dev mode</strong> banner,
          and you sign in with any lowercase username and the server&apos;s dev login secret. It exists only when
          the day1 service runs with <InlineCode>DEV_AUTH_ENABLED</InlineCode> and a{" "}
          <InlineCode>DEV_AUTH_SECRET</InlineCode> of at least 32 characters. A shared deployment uses OpenShift.
        </Callout>
      </div>
    </section>
  );
}
