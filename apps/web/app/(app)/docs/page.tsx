"use client";

import { useState, useEffect } from "react";
import {
  BookOpen,
  Layers,
  Server,
  Package,
  GitPullRequest,
  ClipboardList,
  Shield,
  ShieldAlert,
  AlertTriangle,
  CheckCircle,
  ChevronRight,
  GitMerge,
  Eye,
  Lock,
  Zap,
  RefreshCw,
  ExternalLink,
  Terminal,
  ArrowRight,
  Info,
  Boxes,
  Network,
  FileCode2,
  GitBranch,
  Settings2,
  Pin,
  Pencil,
  XCircle,
} from "lucide-react";

// ── Low-level primitives ──────────────────────────────────────────────────────

function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-mono text-foreground break-words">{children}</code>
  );
}

function CodeBlock({ language, children }: { language?: string; children: string }) {
  return (
    <div className="rounded-xl border bg-[#0d1117] dark:bg-zinc-900 overflow-hidden text-xs">
      {language && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-white/10 bg-white/5">
          <Terminal className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground font-mono text-[10px] uppercase tracking-wider">{language}</span>
        </div>
      )}
      <pre className="px-4 py-3.5 overflow-x-auto leading-relaxed">
        <code className="text-[#e6edf3] font-mono whitespace-pre">{children}</code>
      </pre>
    </div>
  );
}

function Callout({ type, title, children }: { type: "info" | "warning" | "tip" | "danger"; title?: string; children: React.ReactNode }) {
  const map = {
    info: { bg: "bg-blue-500/5 border-blue-500/25", text: "text-blue-600 dark:text-blue-400", Icon: Info },
    tip: { bg: "bg-emerald-500/5 border-emerald-500/25", text: "text-emerald-600 dark:text-emerald-400", Icon: CheckCircle },
    warning: { bg: "bg-amber-500/5 border-amber-500/25", text: "text-amber-600 dark:text-amber-400", Icon: AlertTriangle },
    danger: { bg: "bg-red-500/5 border-red-500/25", text: "text-red-600 dark:text-red-400", Icon: AlertTriangle },
  };
  const { bg, text, Icon } = map[type];
  return (
    <div className={`rounded-xl border p-4 ${bg}`}>
      <div className={`flex items-center gap-2 mb-1.5 ${text}`}>
        <Icon className="h-4 w-4 shrink-0" />
        {title && <p className="text-sm font-semibold">{title}</p>}
      </div>
      <div className="text-sm text-muted-foreground leading-relaxed pl-6">{children}</div>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title?: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 items-start">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-bold text-primary-foreground mt-0.5">
        {n}
      </div>
      <div className="flex-1 min-w-0">
        {title && <p className="text-sm font-semibold mb-0.5">{title}</p>}
        <div className="text-sm text-muted-foreground leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

function NavLink({ href, label, active }: { href: string; label: string; active?: boolean }) {
  return (
    <a
      href={href}
      className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition-colors group ${
        active ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      <ChevronRight className={`h-3 w-3 shrink-0 transition-colors ${active ? "text-primary" : "group-hover:text-primary"}`} />
      {label}
    </a>
  );
}

function SectionHeader({ id, icon: Icon, title, subtitle, badge }: {
  id: string;
  icon: React.ElementType;
  title: string;
  subtitle?: string;
  badge?: string;
}) {
  return (
    <div id={id} className="scroll-mt-8 flex items-start gap-4 pb-4 border-b mb-6">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 border border-primary/20">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="text-xl font-bold">{title}</h2>
          {badge && (
            <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold bg-muted text-muted-foreground">{badge}</span>
          )}
        </div>
        {subtitle && <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
    </div>
  );
}

/** A term and what it means, in a grid of them. */
function TermCard({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-sm font-semibold mb-1">{title}</p>
      <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
    </div>
  );
}

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

/** A titled card in the "Special features" list. */
function FeaturePanel({ icon: Icon, tint, title, where, children }: {
  icon: React.ElementType;
  tint: string;
  title: string;
  where: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border bg-card overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-3.5 border-b bg-muted/30">
        <div className={`flex h-7 w-7 items-center justify-center rounded-lg shrink-0 ${tint}`}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs text-muted-foreground">{where}</p>
        </div>
      </div>
      <div className="px-5 py-4 text-sm text-muted-foreground leading-relaxed space-y-2">{children}</div>
    </div>
  );
}

/** One file in the "File Locations" lists. */
function FileRow({ file, where, desc }: { file: string; where: string; desc: string }) {
  return (
    <div className="px-5 py-3 space-y-1">
      <p className="text-xs font-mono text-foreground font-semibold break-all">{file}</p>
      <p className="text-[10px] text-muted-foreground/60">{where}</p>
      <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const NAV_SECTIONS = [
  { id: "overview", label: "Platform Overview" },
  { id: "concepts", label: "Core Concepts" },
  { id: "roles", label: "Roles & Access" },
  { id: "gitops", label: "GitOps Workflow" },
  { id: "specs", label: "Flavors" },
  { id: "clusters", label: "Clusters" },
  { id: "addons", label: "Day2 Addons" },
  { id: "drift", label: "Drift Detection" },
  { id: "approvals", label: "Approvals" },
  { id: "audit", label: "Audit Log" },
  { id: "errors", label: "When a Change Is Refused" },
  { id: "special-features", label: "Special Features" },
  { id: "filelocations", label: "File Locations" },
  { id: "troubleshooting", label: "Troubleshooting" },
] as const;

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

export default function DocsPage() {
  const [activeSection, setActiveSection] = useState<string>("overview");

  useEffect(() => {
    const observers = NAV_SECTIONS.map(({ id }) => {
      const el = document.getElementById(id);
      if (!el) return null;
      const obs = new IntersectionObserver(
        ([entry]) => { if (entry.isIntersecting) setActiveSection(id); },
        { rootMargin: "-10% 0px -80% 0px", threshold: 0 }
      );
      obs.observe(el);
      return obs;
    });
    return () => observers.forEach((obs) => obs?.disconnect());
  }, []);

  return (
    <div className="flex gap-10 max-w-7xl mx-auto px-4 sm:px-6 py-8">

      {/* Left sticky nav */}
      <aside className="hidden xl:block w-56 shrink-0">
        <div className="sticky top-6">
          <div className="rounded-xl border bg-card p-3 shadow-sm">
            <p className="px-2 mb-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Contents</p>
            <div className="space-y-0.5">
              {NAV_SECTIONS.map(({ id, label }) => (
                <NavLink key={id} href={`#${id}`} label={label} active={activeSection === id} />
              ))}
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 min-w-0 space-y-14">

        {/* Hero */}
        <div className="relative rounded-2xl border bg-gradient-to-br from-primary/5 via-primary/3 to-transparent p-6 sm:p-8 overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none" />
          <div className="relative">
            <div className="flex items-center gap-2 text-primary text-sm font-medium mb-3">
              <BookOpen className="h-4 w-4" />
              Platform Documentation
            </div>
            <h1 className="text-3xl font-bold mb-3">Wingman Platform</h1>
            <p className="text-muted-foreground max-w-2xl leading-relaxed mb-5">
              The team&apos;s self-service portal for OpenShift hosted clusters. GitLab is Wingman&apos;s only
              store: every action you take in the UI opens a merge request, and nothing changes until another
              admin approves it and it is merged. ArgoCD applies what is merged.
            </p>
            <div className="flex flex-wrap gap-3">
              {[
                { icon: GitBranch, label: "GitOps-native" },
                { icon: Shield, label: "Role-based access" },
                { icon: RefreshCw, label: "Drift detection" },
                { icon: Boxes, label: "Multi-cluster" },
              ].map(({ icon: Icon, label }) => (
                <div key={label} className="flex items-center gap-1.5 rounded-full border bg-background/60 px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  <Icon className="h-3 w-3 text-primary" />
                  {label}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Platform Overview */}
        <section>
          <SectionHeader id="overview" icon={BookOpen} title="Platform Overview" subtitle="What Wingman does and how it fits into your workflow" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-6">
            Wingman covers <strong>Day1</strong>, creating, editing and deleting a hosted cluster, and{" "}
            <strong>Day2</strong>, installing and configuring teams&apos; charts on the hub, the MCEs and the
            clusters. There is no application database: all state lives in Git repositories on GitLab.
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

          <Callout type="info" title="Provisioning today, and what is planned">
            Today Wingman provisions a cluster by merge request: it opens the MR, the day1 CI runs the
            allocate-segment workflow on the MR branch, and a person&apos;s merge is the approval. The team
            plans a <InlineCode>create-cluster</InlineCode> workflow (on Temporal) to take this over. It does
            not exist yet; when it does, Wingman will start that workflow instead of committing the file itself.
          </Callout>
        </section>

        {/* Core Concepts */}
        <section>
          <SectionHeader id="concepts" icon={Boxes} title="Core Concepts" subtitle="The mental model behind Wingman" />
          <div className="space-y-4">
            {[
              {
                term: "Flavor",
                color: "bg-purple-500/10 text-purple-500",
                description: "A class of cluster (a spec, in the API and the specs repo). It sets the shape the create form starts with (how many nodepools), presets some template inputs and locks others (a locked value is fixed, and an edit that changes it is drift), and lists the day2 add-ons its clusters should have, with the values a creator may set for each. Every flavor fills the same shared template. Clusters are created from a flavor, and existing ones can join one.",
                example: "agent-standard — two nodepools on the Agent platform, with the redbull team's cluster-roles addon",
              },
              {
                term: "Cluster",
                color: "bg-blue-500/10 text-blue-500",
                description: "A hosted cluster: one values file in the day1 repo, at sites/{site}/mces/{mce}/hostedClusters/{cluster}.yaml. Its name, site and MCE come from that path, so a cluster cannot be renamed or moved: that would be a delete and a create.",
                example: "ocp4-prod-herzi-site1 — sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-herzi-site1.yaml",
              },
              {
                term: "Site",
                color: "bg-amber-500/10 text-amber-500",
                description: "A location: a folder under sites/ in the day1 repo. Wingman lists sites and never creates them.",
                example: "site1 — its MCEs are at sites/site1/mces/",
              },
              {
                term: "MCE",
                color: "bg-emerald-500/10 text-emerald-500",
                description: "A multicluster engine hub that runs hosted clusters' control planes: a folder at sites/{site}/mces/{mce}/. Its values.yaml holds the default mastertag for new clusters. MCE names follow ocp4-{env}-mce-{site}-{letter}. Read-only in Wingman: MCE onboarding happens elsewhere.",
                example: "ocp4-prod-mce-site1-a — a prod MCE on site1",
              },
              {
                term: "Destination",
                color: "bg-cyan-500/10 text-cyan-500",
                description: "Anywhere Day2 deploys charts: the hub, an MCE, a hosted cluster or a UPI cluster. Each has an id that says where it is. A hosted cluster's charts are on its page (Addons); an add-on's page lists each destination its defaults reach, each name a link to its charts.",
                example: "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1 — a hosted cluster's id",
              },
              {
                term: "Merge Request",
                color: "bg-pink-500/10 text-pink-500",
                description: "Every create, edit and delete in Wingman opens a GitLab MR from a platform/{you}/… branch. Nothing changes until another admin approves it, which merges it. The MR and its commit name the person who asked for the change.",
                example: "Creating ocp4-prod-herzi-site1 opens “[Wingman/Day1] Create cluster ocp4-prod-herzi-site1 from spec agent-standard”",
              },
            ].map(({ term, color, description, example }) => (
              <div key={term} className="rounded-xl border bg-card p-5">
                <div className="flex flex-col sm:flex-row items-start gap-3 sm:gap-4">
                  <span className={`inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-bold font-mono mt-0.5 ${color}`}>{term}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-muted-foreground leading-relaxed mb-2">{description}</p>
                    <div className="flex items-start gap-2 rounded-lg bg-muted/40 px-3 py-2">
                      <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mt-0.5 shrink-0">Example</span>
                      <p className="text-xs text-muted-foreground min-w-0 break-words">{example}</p>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Roles */}
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

        {/* GitOps workflow */}
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

        {/* Flavors */}
        <section>
          <SectionHeader id="specs" icon={Layers} title="Flavors" subtitle="What every cluster of a kind gets, and what it may change" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            A flavor is a reusable class of cluster (the API and the specs repo call it a spec). It sets how many
            nodepools a cluster starts with, gives each value it sets either as a <strong>preset</strong> or{" "}
            <strong>locked</strong>, and lists the Day2 add-ons its clusters should have. Every flavor fills the same
            shared template, <InlineCode>cluster-template.j2</InlineCode> in the specs repo, so flavors differ in
            values, not in templates.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
            {[
              { title: "Preset", desc: "Prefilled in the create form; a cluster may change it. A preset never drifts." },
              { title: "Locked", desc: "Fixed: every cluster gets exactly this value, the create form shows it read-only and day1 refuses another, and a later edit of the file shows as drift. Lockable: the owner numbers, the platform, and per nodepool its replicas, machine configs and node labels." },
            ].map(({ title, desc }) => (
              <TermCard key={title} title={title} desc={desc} />
            ))}
          </div>

          <h3 className="text-base font-semibold mb-4">Creating a flavor — worked example</h3>
          <p className="text-sm text-muted-foreground mb-4">
            We will walk through <InlineCode>agent-baseline</InlineCode>: every nodepool of its clusters gets the
            team&apos;s machine configs, and every cluster gets the redbull team&apos;s cluster-roles add-on. Go to{" "}
            <strong>Flavors</strong> → <strong>New Flavor</strong>; the editor has four parts, listed in the bar at
            the top, which also counts the problems in each.
          </p>
          <div className="space-y-4 mb-6">
            <Step n={1} title="Basics">
              The name <InlineCode>agent-baseline</InlineCode> (a lowercase DNS label; a flavor keeps its name), a
              version and a description. Under <strong>Owner and platform</strong>, the owner numbers (digits only)
              and the platform. Each has a <strong>Preset | Locked</strong> switch: leave a preset empty and each
              cluster fills it in. Other template inputs can be preset too, in the collapsed group below.
            </Step>
            <Step n={2} title="Nodepools">
              Add nodepools: each starts with the team&apos;s defaults (<InlineCode>nodepool-defaults.yaml</InlineCode>{" "}
              in the specs repo). Then choose how machine configs work: <strong>Each nodepool its own</strong> (a list
              per nodepool, preset or locked by position), or <strong>The same on every nodepool</strong>: one list,
              locked as a rule, so every nodepool of every cluster has exactly these configs, whatever its number or
              order. Configs come from the picker: a file of <InlineCode>mc-files/</InlineCode> by name, or{" "}
              <InlineCode>nm-conf</InlineCode>, the cluster&apos;s own network config, with a hardware type (under
              the rule, each nodepool picks its own). The type starts at <strong>generic</strong> when the day1 repo has
              the generic template (<InlineCode>nm-conf-template.bu</InlineCode>, for any hardware, written as plain{" "}
              <InlineCode>nm-conf</InlineCode>). Replicas and node labels are preset or locked per nodepool.
            </Step>
            <Step n={3} title="Add-ons">
              Pick charts from the catalog and put them in order. The gear opens{" "}
              <strong>Configure overrideable fields</strong>: the values a cluster&apos;s creator may set for that
              add-on. Everything else comes from the chart&apos;s defaults.
            </Step>
            <Step n={4} title="Review">
              Lists what every cluster gets (<strong>Locked</strong>) and what it starts from (<strong>Presets</strong>),
              and shows the flavor file. On an existing flavor&apos;s edit page it also previews the cluster file the
              flavor produces, on an MCE and release you choose. <strong>Review &amp; Create</strong> runs day1&apos;s
              checks and <strong>Confirm — Create Flavor MR</strong> opens the MR in the specs repo; the flavor can be
              used once it is merged. Every refusal shows at its field.
            </Step>
          </div>

          <CodeBlock language="The flavor file — specs/agent-baseline.yaml">
{`apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: agent-baseline
  description: Every nodepool gets the team's machine configs
  version: "1.0.0"
spec:
  day1:
    structure:                 # clusters start with one nodepool
      nodepools:
        - configs: [{}, {}, {}]
    locked_paths:              # fixed; every other value is a preset
      - nodepools[*].configs   # the rule: every nodepool, exactly these
    values:
      nodepools:
        - configs:
            - name: nm-conf    # the cluster's own network config,
              hardware: dell   #   written as nm-conf-<clusterName>-dell
            - name: workers-chrony-configuration
            - name: nic-ring-buffer
  day2:
    addons:
      - team: redbull
        name: cluster-roles
        version: main
        overrideable: []       # the values a creator may set`}
          </CodeBlock>

          <h3 className="text-base font-semibold mt-6 mb-3">Adding existing clusters to a flavor</h3>
          <p className="text-sm text-muted-foreground leading-relaxed mb-4">
            Clusters written before Wingman, or created from another flavor, can join one from the flavor&apos;s
            page: <strong>Add existing clusters</strong> (admins).
          </p>
          <div className="space-y-3 mb-5">
            <Step n={1} title="Pick">
              Search by name and filter by site, MCE and owner numbers; pick up to 50.
            </Step>
            <Step n={2} title="Preview">
              Each cluster shows whether it can join (<strong>Ready</strong>; on another flavor, which needs{" "}
              <strong>Move to this flavor</strong>; already on it; or can&apos;t be imported, and why) and what will
              show as drift once it has: the configs a sync would add and remove per nodepool, and the missing add-ons.
            </Step>
            <Step n={3} title="Import">
              One Day1 MR per cluster writes only the flavor link (<InlineCode># specName</InlineCode>,{" "}
              <InlineCode># specVersion</InlineCode>) into its file&apos;s header, so each cluster is approved, merged
              or rejected on its own. Every pick is checked first: if one can&apos;t be imported, none opens. Nothing
              changes on the clusters. The last step lists each MR, and each cluster whose MR did not open and why.
              Once a cluster&apos;s MR merges it shows its differences as drift, and <strong>Sync to flavor</strong> on
              its page fixes them (see Drift Detection).
            </Step>
          </div>

          <div className="mt-5 space-y-4">
            <Callout type="tip" title="Example comments in the template">
              A <InlineCode># Example: value</InlineCode> or <InlineCode>{"{# Example: value #}"}</InlineCode> comment
              on a line just before an input in <InlineCode>cluster-template.j2</InlineCode> becomes that field&apos;s
              hint in the create form.
              <div className="mt-2">
                <CodeBlock language="cluster-template.j2 snippet">
{`  {# Example: dell-r660-site1-128c-1024gb-5tb #}
  - infraEnvName: {{ np.infra_env }}`}
                </CodeBlock>
              </div>
            </Callout>
            <Callout type="warning" title="An edit is a new version, and reaches each cluster through its own MR">
              Saving an edit needs a new version: a version, once saved, never changes, because each cluster is
              compared with the version it is on. Merging the flavor&apos;s MR rewrites no cluster file. Instead Wingman
              opens one Day1 MR per cluster that follows the flavor on an older version, and each customer merges
              theirs when ready (see Rolling out a new version, under Drift Detection). Until then the cluster shows{" "}
              <strong>Update MR open</strong>, not drift. A flavor that clusters follow cannot be deleted; delete or
              move them first.
            </Callout>
          </div>
        </section>

        {/* Clusters */}
        <section>
          <SectionHeader id="clusters" icon={Server} title="Clusters" subtitle="Create a hosted cluster from a flavor, then edit or delete it by MR" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            Creating a cluster is a two-step form: choose a flavor, then fill in the values. The flavor sets the
            shape (how many nodepools it starts with), presets values and locks others.
          </p>

          <h3 className="text-base font-semibold mb-4">Worked example — ocp4-prod-herzi-site1</h3>
          <div className="space-y-4 mb-6">
            <Step n={1} title="Choose the flavor">
              Go to <strong>Clusters</strong> → <strong>New Cluster</strong> and pick{" "}
              <InlineCode>agent-standard</InlineCode>. A flavor is required; a flavor file that does not parse is
              shown but cannot be picked.
            </Step>
            <Step n={2} title="Cluster details">
              <ul className="mt-2 space-y-1 list-none">
                <li><InlineCode>Site</InlineCode> → <InlineCode>site1</InlineCode></li>
                <li><InlineCode>Environment</InlineCode> → <InlineCode>prod</InlineCode></li>
                <li><InlineCode>OpenShift Version</InlineCode> → <InlineCode>4.18.56</InlineCode></li>
                <li><InlineCode>MCE</InlineCode> → Wingman&apos;s pick, here <InlineCode>ocp4-prod-mce-site1-a</InlineCode></li>
                <li><InlineCode>Cluster Name</InlineCode> → <InlineCode>ocp4-prod-herzi-site1</InlineCode></li>
              </ul>
              <p className="mt-2">
                You choose the site, <InlineCode>prod</InlineCode> or <InlineCode>prep</InlineCode>, and the version;
                <strong> Wingman picks the MCE</strong>, which runs the cluster&apos;s control plane. The version list is
                what the site&apos;s MCEs of that environment can host (the releases of the day1 repo&apos;s upgrade
                ladder in each MCE&apos;s minors), so it offers only what some MCE there can run; it defaults to the
                flavor&apos;s preset when one of them hosts it. The release becomes the file&apos;s{" "}
                <InlineCode>mastertag</InlineCode>.
              </p>
              <p className="mt-2">
                As soon as those three are chosen, the MCE section lists every candidate, one row each with its
                numbers, and the pick&apos;s row is marked <strong>Wingman&apos;s pick</strong> and chosen. The details
                wait in tooltips, which open on hover, on keyboard focus or on a tap: the ⓘ beside MCE gives the rule,
                the pick&apos;s mark says why it won, each row&apos;s check mark (passes, fails, or passes with some
                checks not made) gives its reasons and numbers, and a dash says why a number is missing. A candidate
                must host the version, have enough free pods for a control plane on its workers, have enough healthy
                free servers of each node type (InfraEnv) the nodepools use, and answer Wingman; among those, the pick
                has the fewest clusters of this owner, then the fewest clusters, then the most usable spare servers.
                The owner&apos;s mador and the nodepools below refine the pick; they are not needed to see one. Where
                this deployment does not read the MCEs live, one line under the table says free pods and servers were
                not checked, and the pick rests on the rest. An MCE that fails a check says why in a few words
                (<InlineCode>no 4.18.56</InlineCode>) and cannot be chosen. An admin may choose another MCE that
                passes, with a reason; the merge request records the numbers, the pick and the reason.
              </p>
              <p className="mt-2">
                Sites and MCEs are the day1 repo&apos;s folders and are read-only: Wingman never creates them, and an
                MCE whose name is off its convention is never a candidate. New names must follow{" "}
                <InlineCode>{"ocp4-<env>-<name>-<site>[-<seq>]"}</InlineCode>, with the environment and the site you
                chose, and a sequence of one letter, <InlineCode>a</InlineCode> to <InlineCode>z</InlineCode>, never a
                number. Once Wingman picks the MCE, the form suggests{" "}
                <InlineCode>{"ocp4-<env>-<flavor>-<site>-<letter>"}</InlineCode> with the first letter no cluster has
                (marked <strong>Suggested</strong>); type over it to use your own. The form lists every problem with a
                name as you type, and fills in the site and the environment when it can read them from the name.
              </p>
            </Step>
            <Step n={3} title="Cluster configuration">
              The fields are the inputs of the shared template. With the default template: the owner numbers
              (merkaz, anaf, mador: digits only) and, per nodepool, its InfraEnv, replicas, machine configs, node
              labels and tuning config. InfraEnvs are picked from the MCE&apos;s list when this deployment reads the
              MCE. A flavor that sizes its nodepools by a ratio (<InlineCode>1:2:1</InlineCode>) asks for one size
              instead, and each sized nodepool gets its part times that size. A field the flavor <strong>presets</strong> is filled in and can be changed;
              a field it <strong>locks</strong> is shown read-only with the flavor&apos;s value. Machine configs come
              from a picker of the day1 repo&apos;s <InlineCode>mc-files/</InlineCode>: a static config by name, or{" "}
              <InlineCode>nm-conf</InlineCode> with a hardware type, the cluster&apos;s own network config, written as{" "}
              <InlineCode>{"nm-conf-<clusterName>-<hardware>"}</InlineCode>, or <strong>generic</strong> (the
              default when the day1 repo has <InlineCode>nm-conf-template.bu</InlineCode>), written as plain{" "}
              <InlineCode>nm-conf</InlineCode>. A nodepool you add starts with the
              team&apos;s defaults (<InlineCode>nodepool-defaults.yaml</InlineCode> in the specs repo), unless the
              flavor locks its configs. Every refusal shows at its field.
            </Step>
            <Step n={4} title="Addon configuration">
              If the flavor lists add-ons, set the values it lets you set for each (or switch to{" "}
              <strong>Full Values</strong> for YAML). They are recorded in the cluster file&apos;s header and used
              when the addons are installed: installing them is a Day2 change, from the cluster&apos;s Drift tab.
            </Step>
            <Step n={5} title="Review and open the MR">
              <strong>Review &amp; Create</strong> runs every check a create runs and opens{" "}
              <strong>Review: Create Cluster</strong>, which shows the exact file the MR adds.{" "}
              <strong>Confirm — Create Cluster MR</strong> opens it and takes you to its approval page.
            </Step>
          </div>

          <CodeBlock language="The file the MR adds — ocp4-prod-herzi-site1.yaml">
{`# specName: "agent-standard"
# specVersion: "1.0.0"
# wingmanAddons: [{"name": "cluster-roles", "override_values": {}, "team": "redbull", "version": "main"}]
owner:
  merkaz: "1234"
  anaf: "56"
  mador: "7"

mastertag: 4.16.27-x86_64

nodepool:
  - infraEnvName: dell-r660-site1-128c-1024gb-5tb
    replicas: 3
    labels:
      allowDeletion: false
    configs:
      - name: worker-kubeletconfig-reserved
  - infraEnvName: dell-r660-site1-64c-512gb
    replicas: 2
    labels:
      allowDeletion: false`}
          </CodeBlock>

          <h3 className="text-base font-semibold mt-6 mb-3">Who writes which key</h3>
          <p className="text-sm text-muted-foreground leading-relaxed mb-4">
            The cluster file is the values file of the hostedclusters-setup chart. People and automation own
            separate keys, and both commit to the MR branch before it is approved:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
            {[
              {
                who: "You, through Wingman",
                keys: "owner, mastertag, nodepool[] (infraEnvName, replicas, labels.allowDeletion, configs, name, nodeLabels, tuningConfig), and optional keys such as platform: kubevirt",
              },
              {
                who: "Automation, on the MR branch",
                keys: "vlanId and dhcp_values (the allocate-segment workflow); mcConfigMap and mcFiles (the day1 CI). Wingman never writes them, and an edit that changes or removes one is refused.",
              },
              {
                who: "The file's path",
                keys: "clusterName, site and mce come from where the file is. Wingman writes none of them; the comment header (# specName, …) is Wingman's own bookkeeping, which Helm ignores.",
              },
            ].map(({ who, keys }) => (
              <div key={who} className="rounded-xl border bg-card p-4">
                <p className="text-sm font-semibold mb-1">{who}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{keys}</p>
              </div>
            ))}
          </div>
          <Callout type="info" title="VLAN and DHCP show as pending">
            The cluster page shows <strong>VLAN</strong> and <strong>DHCP network</strong> as{" "}
            <strong>pending</strong> until the allocate-segment workflow has written them. Approve a create MR once
            the workflow and CI have committed to its branch: the review dialog says so too.
          </Callout>

          <h3 className="text-base font-semibold mt-6 mb-3">The cluster page</h3>
          <p className="text-sm text-muted-foreground leading-relaxed mb-4">
            The tabs are <strong>Overview</strong> (the cluster, its HostedCluster and network, nodepools, flavor and,
            when it is on, live status), <strong>Nodes</strong> (below), <strong>YAML</strong>, <strong>Drift</strong> and <strong>History</strong>{" "}
            (the cluster file&apos;s commits in the day1 repo, and its chart values&apos; commits in the team repos).
            The header has <strong>GitLab</strong> (the file), <strong>Addons</strong> (its charts) and, for admins,{" "}
            <strong>Edit</strong> and <strong>Delete</strong>. A name off the naming convention is flagged{" "}
            <strong>Off the naming convention</strong>, here and in the list, never hidden: existing clusters keep
            working, and only new names are refused. When segments-manager is configured
            (<InlineCode>SEGMENTS_MANAGER_UI_URL</InlineCode>), the <strong>HostedCluster &amp; network</strong> card
            links to it. Its UI opens no single cluster, so the card names the cluster to search for there, with a
            copy button, and <strong>this cluster&apos;s segment (JSON)</strong> opens its search for the
            cluster&apos;s segment.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex gap-4 rounded-xl border bg-card p-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <Pencil className="h-4 w-4 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold mb-1">Edit</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Edit the file as YAML, then <strong>Review &amp; Submit</strong> shows the diff and opens a modify MR.
                  Keep the automation keys as they are. If the file changed since you opened it (CI or the workflow
                  committed), the MR is refused and nothing is overwritten: <strong>Reload</strong> and edit again.
                </p>
              </div>
            </div>
            <div className="flex gap-4 rounded-xl border bg-card p-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500/10">
                <XCircle className="h-4 w-4 text-red-500" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold mb-1">Delete</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  <strong>Confirm — Delete Cluster MR</strong> opens an MR that removes the cluster file. Once it is
                  merged, the file and with it the cluster&apos;s ArgoCD Application are gone.
                </p>
              </div>
            </div>
          </div>

          <h3 className="text-base font-semibold mt-6 mb-3">Nodes</h3>
          <p className="text-sm text-muted-foreground leading-relaxed mb-3">
            The cluster page&apos;s <strong>Nodes</strong> tab shows each NodePool as the cluster&apos;s MCE reports it.
            Its header sums it up: how many nodes are ready of how many it wants (or the range it autoscales in), the
            version it last finished updating to, whether an update reboots its nodes in place (<strong>InPlace</strong>)
            or replaces them (<strong>Replace</strong>), and which Agents it takes. Under it is one row per Machine: the
            server behind it, linked to its page in server-scan, with its serial, hardware, Machine, Agent, state and
            health, and flags for a server in maintenance, stale, unreachable or contested (claimed by two clusters).
            Health server-scan could not determine shows as <strong>Unknown</strong>, never as healthy. Ready, healthy
            rows stay quiet, so what needs a look stands out.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
            {[
              {
                title: "An update in progress",
                desc: "A banner says what is being updated (the version or the config), how many nodes are done when an in-place update counts them, and the NodePool's own message. The node the update is working on now is marked, with what is happening to it: “Rebooting for the update”, “Draining”. A failed update is shown in red.",
              },
              {
                title: "The missing piece",
                desc: "A Machine that waits for a server, or a node the NodePool wants and has no Machine for, is a dashed placeholder that says why: usually that no free Agent matches the NodePool. The header then counts the matching Agents and how many are free.",
              },
              {
                title: "In no NodePool",
                desc: "Servers server-scan still places in the cluster that no Machine has are listed apart, under the NodePools. That is usual for a few minutes after an uninstall.",
              },
            ].map(({ title, desc }) => (
              <TermCard key={title} title={title} desc={desc} />
            ))}
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed mb-3">
            The tab reads the MCE as live status does, so it needs <InlineCode>CLUSTER_STATUS_ENABLED</InlineCode>; without
            it, the tab says so (<InlineCode>501 FEATURE_DISABLED</InlineCode>). When server-scan does not answer, the
            Machines are still listed, without links or health.
          </p>

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
        </section>

        {/* Addons */}
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
        </section>

        {/* Drift */}
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

        {/* Approvals */}
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

        {/* Audit */}
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

        {/* Errors */}
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

        {/* Special Features */}
        <section>
          <SectionHeader id="special-features" icon={Zap} title="Special Features" subtitle="Capabilities that are easy to miss" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-6">
            These features exist throughout the UI but are not always obvious at first glance.
          </p>

          <div className="space-y-5">

            <FeaturePanel icon={RefreshCw} tint="bg-emerald-500/10 text-emerald-500" title="Live cluster status" where="Cluster page, Clusters list, Dashboard — only when the deployment turns it on">
              <p>
                When the deployment reads HostedClusters from the MCE hubs (<InlineCode>CLUSTER_STATUS_ENABLED</InlineCode>),
                the cluster page&apos;s <strong>Live Status</strong> card shows the HostedCluster&apos;s phase, OCP
                version and problems, and each node pool&apos;s ready replicas. It updates itself (every 30 seconds
                by default) and reconnects after a network blip, up to 5 times. The Clusters list shows each
                cluster&apos;s health, and the Dashboard counts them.
              </p>
              <p>
                The HostedCluster of <InlineCode>ocp4-prod-herzi-site1</InlineCode> is{" "}
                <InlineCode>openshift-prod-herzi-site1</InlineCode> in <InlineCode>hcp-prod-herzi-site1</InlineCode>:
                the file name minus the deployment&apos;s <InlineCode>DAY1_CLUSTER_NAME_STRIP_PREFIX</InlineCode>{" "}
                (<InlineCode>ocp4-</InlineCode> by default).
              </p>
              <Callout type="tip">
                When live status is off, the Dashboard says <strong>Live status is off</strong>, the list shows a dash
                (&quot;Live status is off in this deployment&quot;), and the cluster page has no Live Status card.
                That is a deployment choice, not an error.
              </Callout>
            </FeaturePanel>

            <FeaturePanel icon={Eye} tint="bg-blue-500/10 text-blue-500" title="Preview the cluster file a flavor produces" where="A flavor's edit page → Review">
              <p>
                The <strong>Review</strong> part of a saved flavor&apos;s edit page renders the cluster file the
                flavor produces, as you edit, on an MCE, release and example name you choose: the same render a
                create runs, through day1. A new flavor has no preview until it is merged.
              </p>
            </FeaturePanel>

            <FeaturePanel icon={GitBranch} tint="bg-purple-500/10 text-purple-500" title="Flavor history & time travel" where="Flavor page → History tab">
              <p>
                Every flavor has a <strong>History</strong> tab listing every commit that touched it. Selecting a commit
                shows the flavor <em>at that exact commit</em>, without affecting the current one. This is useful for:
              </p>
              <ul className="space-y-1 pl-4 list-disc marker:text-muted-foreground/40">
                <li>Auditing what changed between two flavor versions</li>
                <li>Recovering a previous value that was overwritten</li>
                <li>Understanding what a cluster created at a particular time got</li>
              </ul>
            </FeaturePanel>

            <FeaturePanel icon={FileCode2} tint="bg-amber-500/10 text-amber-500" title="Form ↔ YAML toggle for chart values" where="A chart's values editor">
              <p>A chart&apos;s values editor has two views:</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 my-2">
                <div className="rounded-lg border bg-muted/30 p-3">
                  <p className="text-xs font-semibold mb-1">Form</p>
                  <p className="text-xs leading-relaxed">
                    Every merged value with the layer that set it. Numbers stay numbers, booleans are switches, lists
                    and maps are YAML. It edits keys the merge already has.
                  </p>
                </div>
                <div className="rounded-lg border bg-muted/30 p-3">
                  <p className="text-xs font-semibold mb-1">YAML</p>
                  <p className="text-xs leading-relaxed">
                    The values the change writes into the file, and nothing inherited. Needed for new keys or a{" "}
                    <InlineCode>null</InlineCode> that deletes a default. Comments in the file are not kept.
                  </p>
                </div>
              </div>
              <p>
                Edits in one view show in the other. While the YAML does not parse, the Form view is unavailable.
              </p>
            </FeaturePanel>

            <FeaturePanel icon={Layers} tint="bg-pink-500/10 text-pink-500" title="Chart value layers view" where="A destination's charts page → a chart → Layers tab">
              <p>Every value in a chart&apos;s values table carries the layer that set it:</p>
              <CodeBlock language="Value provenance example">
{`replicas:   2              ← cluster    (this cluster's values.yaml)
retention:  30d            ← team       (operators/{chart}/values.yaml)
namespace:  cert-manager   ← chart      (the chart's own values.yaml)`}
              </CodeBlock>
              <p>
                The <strong>Layers</strong> tab lists the whole stack in merge order, starting with the chart&apos;s own
                defaults. Files that do not exist are dimmed (<strong>no file</strong>), and the file an edit writes is
                tagged. The stack (which files, in which order) is the platform&apos;s own, checked against the
                platform&apos;s <InlineCode>render_chain.py</InlineCode> simulation.
              </p>
            </FeaturePanel>

            <FeaturePanel icon={AlertTriangle} tint="bg-red-500/10 text-red-500" title="MR conflict detection" where="Approvals page">
              <p>
                The Approvals page shows a <strong>Conflicted</strong> badge on any MR whose branch conflicts with its
                target. This happens when two changes touch the same file, for example two edits of one cluster.
              </p>
              <p>A conflicted MR cannot be merged until the conflict is resolved. Options:</p>
              <ul className="space-y-1 pl-4 list-disc marker:text-muted-foreground/40">
                <li>Reject the conflicted MR and make the change again from the Wingman UI (recommended)</li>
                <li>Resolve the conflict directly in GitLab if you are comfortable with the raw YAML</li>
              </ul>
            </FeaturePanel>

            <FeaturePanel icon={ExternalLink} tint="bg-primary/10 text-primary" title="Open in GitLab — everywhere" where="Clusters, specs, charts, approvals and the audit log">
              <p className="mb-1">These links open in a new tab and are available to all users, including Viewers:</p>
              <div className="space-y-2">
                {[
                  { where: "Cluster page → GitLab", what: "The cluster's values file in the day1 repo" },
                  { where: "Spec page → History", what: "Each commit of the spec in the specs repo" },
                  { where: "Chart → ⋮ menu", what: "Open folder in GitLab: the chart's folder in the team repo" },
                  { where: "Approvals → MR", what: "The MR in GitLab" },
                  { where: "Audit Log → row", what: "The exact commit or MR in GitLab" },
                ].map(({ where, what }) => (
                  <div key={where} className="flex flex-col sm:flex-row gap-1 sm:gap-3 rounded-lg bg-muted/30 px-3 py-2.5">
                    <p className="text-xs font-medium text-foreground sm:w-44 sm:shrink-0">{where}</p>
                    <p className="text-xs text-muted-foreground min-w-0">{what}</p>
                  </div>
                ))}
              </div>
            </FeaturePanel>

            <FeaturePanel icon={Settings2} tint="bg-indigo-500/10 text-indigo-500" title="OpenShift versions come from the upgrade ladder, per MCE" where="New Cluster → OpenShift Version">
              <p>
                Not every MCE can host every OpenShift release, so the list depends on the site and the environment
                you choose, and the picker stays disabled until you choose both. It offers every release some MCE of
                that site and environment can host: the releases in the day1 repo&apos;s{" "}
                <InlineCode>upgrade/ladder.yaml</InlineCode> whose minor is in the MCE&apos;s{" "}
                <InlineCode>upgrade/mces/&lt;mce&gt;.yaml</InlineCode>, newest first. Wingman then picks an MCE that
                hosts the one you chose. These are the same files the cluster-upgrade workflow reads. The release goes
                into the cluster file&apos;s <InlineCode>mastertag</InlineCode>, and the chart adds{" "}
                <InlineCode>-x86_64</InlineCode> to it.
              </p>
              <CodeBlock language="upgrade/mces/ocp4-prod-mce-site1-a.yaml">
{`mce:
  version: 2.8.2
  supportedHostedVersions: ["4.18", "4.17", "4.16"]   # quoted: 4.20 unquoted is a number
maxConcurrentControlPlanes: 1`}
              </CodeBlock>
              <p>
                An MCE with no file, or every MCE while the ladder is missing or broken, hosts no version: it is not
                offered for any, and its version check says why. Wingman never falls back to every release. A
                flavor&apos;s preset version prefills only when some MCE of the site and environment hosts it. Create
                refuses a release the chosen MCE can&apos;t host. To offer
                another release, add a rung to the ladder or a minor to the MCE&apos;s file, through a merge request
                in the day1 repo.
              </p>
            </FeaturePanel>

            <FeaturePanel icon={Network} tint="bg-emerald-500/10 text-emerald-500" title="InfraEnv dropdown" where="New Cluster → nodepool fields">
              <p>
                A template input named <InlineCode>infra_env</InlineCode> becomes a dropdown of the InfraEnvs on the
                chosen MCE&apos;s hub, which prevents typos in the field that decides which bare-metal hosts the
                nodepool gets:
              </p>
              <CodeBlock language="cluster-template.j2 snippet">
{`nodepool:
{% for np in nodepools %}
  - infraEnvName: {{ np.infra_env }}   # picked from the dropdown`}
              </CodeBlock>
              <p>
                It needs live status to be on and the MCE to have a hub token configured. Otherwise the field is plain
                text; if listing fails, the form says why and you type the names.
              </p>
              <Callout type="tip" title="Which namespace is listed">
                By default, InfraEnvs are listed across the whole hub. The day1 service&apos;s{" "}
                <InlineCode>MCE_INFRAENV_NAMESPACE</InlineCode> restricts the list to one namespace; the Helm chart does
                not set it yet.
              </Callout>
            </FeaturePanel>

          </div>
        </section>

        {/* File Locations */}
        <section>
          <SectionHeader id="filelocations" icon={FileCode2} title="File Locations" subtitle="Where every important file lives in GitLab" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            All platform state is stored as plain files in GitLab. Which repository is which is set by the
            deployment (Helm values, passed to the services as environment variables); the layout inside each is
            the platform&apos;s.
          </p>

          <div className="space-y-4 mb-6">
            <div className="rounded-xl border bg-card overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-3 border-b bg-muted/30">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-500/10 shrink-0">
                  <Layers className="h-3.5 w-3.5 text-purple-500" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">Specs repository</p>
                  <p className="text-xs text-muted-foreground break-words">
                    Helm: <InlineCode>gitlab.specsProjectId</InlineCode> → env: <InlineCode>SPECS_GITLAB_PROJECT_ID</InlineCode>
                  </p>
                </div>
              </div>
              <div className="divide-y">
                <FileRow file="cluster-template.j2" where="repository root" desc="The shared template every cluster file is rendered from (sandboxed). Its inputs are the create form's fields." />
                <FileRow file="specs/{name}.yaml" where="Helm gitlab.specsRoot → SPECS_ROOT_PATH (default: specs)" desc="One file per spec: nodepool structure, preset values, locked-field hints and the Day2 addons." />
              </div>
            </div>

            <div className="rounded-xl border bg-card overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-3 border-b bg-muted/30">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/10 shrink-0">
                  <Server className="h-3.5 w-3.5 text-blue-500" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">Day1 repository</p>
                  <p className="text-xs text-muted-foreground break-words">
                    Helm: <InlineCode>gitlab.day1ProjectId</InlineCode> → env: <InlineCode>DAY1_GITLAB_PROJECT_ID</InlineCode>
                  </p>
                </div>
              </div>
              <div className="divide-y">
                <FileRow file="sites/{site}/mces/{mce}/hostedClusters/{cluster}.yaml" where="fixed by the MCE's ApplicationSet" desc="One values file per hosted cluster, the only file Wingman writes here. Every file in hostedClusters/ becomes an ArgoCD Application, so anything else there is flagged as a stray file." />
                <FileRow file="sites/{site}/mces/{mce}/values.yaml" where="read only" desc="The MCE's values: its mastertag is the default OpenShift version for new clusters, when the MCE offers it." />
                <FileRow file="sites/{site}/mces/{mce}/version.yaml" where="read only" desc="The MCE hub's own version." />
                <FileRow file="upgrade/ladder.yaml" where="read only" desc="The verified releases, at least one per minor. The create form offers them." />
                <FileRow file="upgrade/mces/{mce}.yaml" where="read only" desc="The OpenShift minors the MCE can host. Without this file the MCE offers no version." />
              </div>
            </div>

            <div className="rounded-xl border bg-card overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-3 border-b bg-muted/30">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 shrink-0">
                  <Package className="h-3.5 w-3.5 text-emerald-500" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">Day2 team repositories</p>
                  <p className="text-xs text-muted-foreground break-words">
                    Helm: <InlineCode>gitlab.day2SigsGroupPath</InlineCode> → env: <InlineCode>DAY2_SIGS_GROUP_PATH</InlineCode>
                    {" "}— one GitLab project per team under this group
                  </p>
                </div>
              </div>
              <div className="divide-y">
                <FileRow file="operators/{chart}/{chart}.yaml, values.yaml" where="per-team project root" desc="The add-on: where the chart comes from (repourl, targetRevision, path) and its Sig values (values.yaml). Maintained by the owning team; operators/{chart}/ocp-versions/{ocp}/ holds per-OCP-version pins." />
                <FileRow file="sites/{site}/{env}/mces/{mce}/{cluster}/{chart}/values.yaml" where="per-team project root" desc="A hosted cluster's values for the chart, written by Wingman on install and update. MCEs use …/mces/{mce}/in-cluster/{chart}/, UPI clusters sites/{site}/{env}/upi/{cluster}/{chart}/, the hub defaults/hub/{chart}/." />
                <FileRow file="…/{chart}/{chart}.yaml" where="per-team project root" desc="Written only when the destination needs a deploy-config key it does not inherit: a repourl (when no layer sets a lowercase one) or an emergency targetRevision pin. Choosing the inherited revision again removes the pin, and deletes the file if nothing else is left in it." />
                <FileRow file="defaults/{scope}/{chart}/values-{cluster}.yaml" where="per-team project root" desc="A fleet default's values for one cluster, written when you edit a fleet default there." />
              </div>
            </div>
          </div>

          <Callout type="info" title="The layouts are the platform's contract">
            The paths inside each repository are fixed by the platform&apos;s ApplicationSets, not by Wingman&apos;s
            settings. A deployment chooses only which projects to use, the specs folder and the branch Day2 targets.
          </Callout>
        </section>

        {/* Troubleshooting */}
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

      </div>
    </div>
  );
}
