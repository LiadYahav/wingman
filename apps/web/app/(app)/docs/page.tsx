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
} from "lucide-react";

// ── Low-level primitives ──────────────────────────────────────────────────────

function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-mono text-foreground">{children}</code>
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
      <div className="flex-1">
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
      <div>
        <div className="flex items-center gap-2">
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

function FeatureCard({ icon: Icon, title, description }: { icon: React.ElementType; title: string; description: string }) {
  return (
    <div className="rounded-xl border bg-card p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2.5 mb-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
          <Icon className="h-3.5 w-3.5 text-primary" />
        </div>
        <p className="text-sm font-semibold">{title}</p>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const NAV_SECTIONS = [
  { id: "overview", label: "Platform Overview" },
  { id: "concepts", label: "Core Concepts" },
  { id: "roles", label: "Roles & Access" },
  { id: "gitops", label: "GitOps Workflow" },
  { id: "specs", label: "Specs" },
  { id: "clusters", label: "Creating a Cluster" },
  { id: "addons", label: "Day2 Addons" },
  { id: "drift", label: "Drift Detection" },
  { id: "approvals", label: "Approvals" },
  { id: "audit", label: "Audit Log" },
  { id: "troubleshooting", label: "Troubleshooting" },
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
    <div className="flex gap-10 max-w-7xl mx-auto px-6 py-8">

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
        <div className="relative rounded-2xl border bg-gradient-to-br from-primary/5 via-primary/3 to-transparent p-8 overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none" />
          <div className="relative">
            <div className="flex items-center gap-2 text-primary text-sm font-medium mb-3">
              <BookOpen className="h-4 w-4" />
              Platform Documentation
            </div>
            <h1 className="text-3xl font-bold mb-3">Wingman Platform</h1>
            <p className="text-muted-foreground max-w-2xl leading-relaxed mb-5">
              A GitOps-based Internal Developer Platform for provisioning and managing OpenShift clusters.
              Wingman uses GitLab as its single source of truth — every action you take in the UI creates
              a Merge Request that must be reviewed and merged before any change takes effect.
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
            Wingman manages the full lifecycle of OpenShift clusters — from templating and provisioning
            (Day1) to operator installation and configuration (Day2). There is no application database:
            all state lives in Git repositories hosted on GitLab.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            <FeatureCard
              icon={Layers}
              title="Day1 — Cluster Provisioning"
              description="Create new OpenShift clusters from spec templates. Wingman generates the AgentCluster, NodePool, and MachineConfig manifests and commits them to GitLab for the provisioner to consume."
            />
            <FeatureCard
              icon={Package}
              title="Day2 — Addon Management"
              description="Install, configure, and remove operators on existing clusters via ArgoCD. Addon defaults are owned by teams; per-cluster values are layered on top."
            />
            <FeatureCard
              icon={RefreshCw}
              title="Drift Detection"
              description="Automatically detects when a running cluster's actual state diverges from its spec. Drifted clusters are highlighted in red with a unified diff."
            />
            <FeatureCard
              icon={GitPullRequest}
              title="Approval Workflow"
              description="Every mutation opens a GitLab Merge Request. The Approvals page aggregates open MRs from all repositories so admins can review in one place."
            />
          </div>

          {/* Architecture diagram */}
          <div className="rounded-xl border bg-card overflow-hidden">
            <div className="px-5 py-3 border-b bg-muted/30">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">How it fits together</p>
            </div>
            <div className="p-5 font-mono text-xs text-muted-foreground leading-loose">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="text-foreground font-semibold">User (Admin)</span>
                  <ArrowRight className="h-3 w-3" />
                  <span className="text-primary">Wingman UI</span>
                  <ArrowRight className="h-3 w-3" />
                  <span className="text-emerald-500">GitLab MR</span>
                  <ArrowRight className="h-3 w-3" />
                  <span className="text-blue-500">Merge</span>
                  <ArrowRight className="h-3 w-3" />
                  <span className="text-foreground">ArgoCD (Day1 + Day2)</span>
                </div>
                <div className="mt-3 pl-4 border-l-2 border-muted space-y-1">
                  <p><span className="text-primary">Day1 repo</span>  — cluster manifests (AgentCluster, NodePool, MachineConfig)</p>
                  <p><span className="text-blue-500">Day2 repos</span> — per-team operator defaults + per-cluster overrides</p>
                  <p><span className="text-amber-500">Specs repo</span> — Jinja2 templates + openshift-versions.txt</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Core Concepts */}
        <section>
          <SectionHeader id="concepts" icon={Boxes} title="Core Concepts" subtitle="The mental model behind Wingman" />
          <div className="space-y-4">
            {[
              {
                term: "Spec",
                color: "bg-purple-500/10 text-purple-500",
                description: "A Jinja2 template (cluster-template.j2) combined with a YAML config that defines the structure of clusters: number of nodepools, which MachineConfigs apply, which Day2 addons are pre-configured, and which fields become immutable after a cluster is created. Multiple clusters share one spec.",
                example: 'prod-dok-ha — 2 nodepools, high-availability hardware profile, monitoring addons pre-configured',
              },
              {
                term: "Cluster",
                color: "bg-blue-500/10 text-blue-500",
                description: "A running OpenShift cluster created from a spec. Its identity (cluster name, site, MCE) is set once at creation time and is permanently immutable — a cluster cannot be renamed or moved.",
                example: 'prod-dok-nova — built from prod-dok-ha spec, zone-a and zone-b nodepools, 9 total replicas',
              },
              {
                term: "Site",
                color: "bg-amber-500/10 text-amber-500",
                description: "A physical location — a datacenter, room, or zone. Sites are the top-level geographic grouping; one site can host multiple MCEs. In the Day1 repository, sites live under site/{site}/.",
                example: 'nova — a physical datacenter; its clusters are at site/nova/mces/.../hostedClusters/',
              },
              {
                term: "MCE",
                color: "bg-emerald-500/10 text-emerald-500",
                description: "Multi-Cluster Engine — a logical management plane that lives within a Site. Groups clusters sharing the same management infrastructure. In the Day1 repository: site/{site}/mces/{mce}/hostedClusters/{cluster}.yaml.",
                example: 'prod-dok — a logical MCE inside the nova site, at site/nova/mces/prod-dok/',
              },
              {
                term: "Merge Request",
                color: "bg-pink-500/10 text-pink-500",
                description: "Every create / edit / delete operation in Wingman produces a GitLab MR. The change is not applied until the MR is merged by an approver. This gives you a full audit trail and allows peer review of infrastructure changes.",
                example: 'Creating prod-dok-nova opens MR #47 in the day1 repo',
              },
            ].map(({ term, color, description, example }) => (
              <div key={term} className="rounded-xl border bg-card p-5">
                <div className="flex items-start gap-4">
                  <span className={`inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-bold font-mono mt-0.5 ${color}`}>{term}</span>
                  <div className="flex-1">
                    <p className="text-sm text-muted-foreground leading-relaxed mb-2">{description}</p>
                    <div className="flex items-start gap-2 rounded-lg bg-muted/40 px-3 py-2">
                      <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mt-0.5">Example</span>
                      <p className="text-xs text-muted-foreground">{example}</p>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Roles */}
        <section>
          <SectionHeader id="roles" icon={Shield} title="Roles & Access" subtitle="Access is controlled by OpenShift group membership" />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
            <div className="rounded-xl border bg-card p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                  <Lock className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-bold">Admin</p>
                  <p className="text-xs text-muted-foreground">Full read-write access</p>
                </div>
              </div>
              <ul className="space-y-2">
                {[
                  "Create / edit / delete specs",
                  "Create clusters from specs",
                  "Install and remove addons",
                  "Approve and merge GitLab MRs",
                  "Access all audit and drift views",
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
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
                  <Eye className="h-4 w-4 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-sm font-bold">Viewer</p>
                  <p className="text-xs text-muted-foreground">Read-only access</p>
                </div>
              </div>
              <ul className="space-y-2">
                {[
                  "Browse clusters, specs, and addons",
                  "View drift reports",
                  "Read audit history",
                  "Open-in-GitLab links on any resource",
                  "View addon configurations",
                ].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <CheckCircle className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <Callout type="info" title="How roles are assigned">
            Your role is derived from your <strong>OpenShift group membership</strong> and embedded in
            your login session at authentication time. If you need admin access, ask your platform team
            to add you to the appropriate OpenShift group. Your role updates on your next login.
          </Callout>
        </section>

        {/* GitOps workflow */}
        <section>
          <SectionHeader id="gitops" icon={GitBranch} title="GitOps Workflow" subtitle="Every action in Wingman is a Git commit" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            Wingman never applies changes directly. Every create, update, or delete operation renders
            YAML manifests and commits them to GitLab as a Merge Request branch. This means:
          </p>
          <div className="space-y-3 mb-5">
            {[
              { icon: GitPullRequest, text: "Peer review is built in — a second admin can review the manifest diff before merging." },
              { icon: ClipboardList, text: "Full audit trail — every change is a git commit with author and timestamp." },
              { icon: RefreshCw, text: "Rollback is trivial — revert the commit in GitLab and ArgoCD reconciles automatically on its next sync." },
              { icon: Shield, text: "No shadow changes — if something changed in your cluster and it is not in Git, Wingman will flag it as drift." },
            ].map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-start gap-3 rounded-lg border bg-card px-4 py-3">
                <Icon className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                <p className="text-sm text-muted-foreground">{text}</p>
              </div>
            ))}
          </div>
          <Callout type="warning" title="Changes are not immediate">
            Merging an MR commits manifests to Git. Actual cluster provisioning and addon sync both
            happen asynchronously — ArgoCD handles both Day1 and Day2, picking up changes on its next
            reconcile loop. You can trigger a manual sync from the ArgoCD dashboard if needed.
          </Callout>
        </section>

        {/* Specs */}
        <section>
          <SectionHeader id="specs" icon={Layers} title="Specs" subtitle="Define the shape of your clusters before you build them" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            A Spec is a reusable cluster template. It defines the nodepool structure, hardware profiles,
            MachineConfigs, and which Day2 addons are pre-configured. Think of it as a &quot;cluster class&quot; —
            you create one spec for &quot;high-availability bare metal Dell nodes&quot; and then create multiple
            clusters from it.
          </p>

          <h3 className="text-base font-semibold mb-4">Creating a spec — worked example</h3>
          <p className="text-sm text-muted-foreground mb-4">
            We will walk through creating the <InlineCode>prod-dok-ha</InlineCode> spec used by the
            <InlineCode>prod-dok-nova</InlineCode> cluster.
          </p>
          <div className="space-y-4 mb-6">
            <Step n={1} title="Name the spec">
              Navigate to <strong>Specs</strong> → <strong>New Spec</strong>. Enter the spec name{" "}
              <InlineCode>prod-dok-ha</InlineCode>. This names the template — not a cluster. Cluster-specific
              fields like cluster name, site, MCE, and OpenShift version are set later when creating
              a cluster from this spec.
            </Step>
            <Step n={2} title="Define the cluster structure">
              In the <strong>Cluster Structure</strong> section, add <strong>2 nodepools</strong> by clicking
              the + button. For each nodepool you can expand and configure sub-fields
              (labels, nodeLabels, agentLabelSelector, configs, tuningConfig, workerTag).
              The count you set here is locked — clusters built from this spec will always have exactly 2 nodepools.
            </Step>
            <Step n={3} title="Mark fields as immutable">
              Click the <Lock className="inline h-3 w-3" /> toggle next to any field to mark it immutable.
              Immutable fields cannot be edited after a cluster is created from this spec. Cluster identity
              fields (<InlineCode>clusterName</InlineCode>, <InlineCode>site</InlineCode>,{" "}
              <InlineCode>MCE</InlineCode>) are always immutable — they never appear here. For{" "}
              <InlineCode>prod-dok-ha</InlineCode> we additionally lock:{" "}
              <InlineCode>platform</InlineCode> and <InlineCode>masterTag</InlineCode>.
            </Step>
            <Step n={4} title="Pre-configure Day2 addons">
              In the <strong>Day2 Addons</strong> section, browse the marketplace and select addons.
              For each addon, click <strong>Configure</strong> to choose which fields cluster operators
              can override at cluster-creation time.
            </Step>
            <Step n={5} title="Review and submit">
              Click <strong>Create Spec</strong>. Wingman renders the spec YAML and opens a GitLab MR.
              Merge it to activate the spec.
            </Step>
          </div>

          <CodeBlock language="Rendered spec YAML — prod-dok-ha">
{`name: prod-dok-ha
spec:
  day1:
    immutable_paths:
      - platform
      - masterTag
    structure:
      nodepool:
        - {}
        - {}

  day2:
    addons:
      - team: monitoring
        name: prometheus-stack
        overrideable_fields:
          - retention
          - storageClass
      - team: networking
        name: cert-manager
        overrideable_fields: []`}
          </CodeBlock>

          <div className="mt-5">
            <Callout type="warning" title="Editing a spec affects future clusters only">
              Changing the nodepool count in a spec does not update clusters that already exist — those
              will show as drifted. You must explicitly re-render each existing cluster if you want them
              to follow the new structure.
            </Callout>
          </div>
        </section>

        {/* Creating a cluster */}
        <section>
          <SectionHeader id="clusters" icon={Server} title="Creating a Cluster" subtitle="Pick a spec, fill in the values, open the MR" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            Creating a cluster is a two-phase form. Phase one locks in the shape (from the spec);
            phase two fills in the values. No field can be added or removed at cluster-creation time —
            only the values change.
          </p>

          <h3 className="text-base font-semibold mb-4">Worked example — prod-dok-nova</h3>
          <div className="space-y-4 mb-6">
            <Step n={1} title="Pick the spec">
              Navigate to <strong>Clusters</strong> → <strong>New Cluster</strong>. Select{" "}
              <InlineCode>prod-dok-ha</InlineCode> from the spec dropdown. The form immediately shows
              exactly 2 nodepool cards — locked to the spec structure.
            </Step>
            <Step n={2} title="Fill in cluster identity">
              These three fields are set once, forever:
              <ul className="mt-2 space-y-1 list-none">
                <li><InlineCode>Cluster name</InlineCode> → <InlineCode>prod-dok-nova</InlineCode></li>
                <li><InlineCode>Site</InlineCode> → select <InlineCode>nova</InlineCode> (or type to create)</li>
                <li><InlineCode>MCE</InlineCode> → select <InlineCode>prod-dok</InlineCode> (or type to create)</li>
              </ul>
              Site and MCE are selected from existing GitLab folder paths. The cluster will be stored at{" "}
              <InlineCode>site/nova/mces/prod-dok/hostedClusters/prod-dok-nova.yaml</InlineCode> in the
              Day1 repository. If the site or MCE folder does not exist yet, type the new name and
              Wingman creates it automatically.
            </Step>
            <Step n={3} title="Fill in global fields">
              <ul className="mt-1 space-y-1 list-none">
                <li><InlineCode>platform</InlineCode> → <InlineCode>agent</InlineCode></li>
                <li><InlineCode>hostInventory</InlineCode> → <InlineCode>inventory</InlineCode></li>
                <li><InlineCode>masterTag</InlineCode> → <InlineCode>4.14.0-x86_64</InlineCode></li>
                <li><InlineCode>openshift_release_version</InlineCode> → <InlineCode>4.14.0-x86_64</InlineCode></li>
              </ul>
            </Step>
            <Step n={4} title="Fill in nodepool details">
              Each nodepool card corresponds to one nodepool in the spec structure. For nodepool 1:
            </Step>
          </div>

          <CodeBlock language="Nodepool 1 — zone-a values">
{`name: prod-dok-nova-prod-dok-nova-a-dell-r660-128c-1024gb-10tb-nodepool-zone-a
replicas: 6

labels:
  minReplicas: "5"
  maxReplicas: "6"
  allowDeletion: "false"

nodeLabels:
  node-role.kubernetes.io/worker: ""
  topology.kubernetes.io/zone: zone-a

agentLabelSelector:
  nodeLabelKey: infraenvs.agent-install.openshift.io
  nodeLabelValue: prod-dok-nova-a-dell-r660-128c-1024gb-10tb

configs:
  - name: nm-conf-prod-dok-nova-a-dell-r660-128c-1024gb-10tb
  - name: worker-chrony-configuration
  - name: worker-kubeletconfig-high-mem
  - name: special-nic-config
  - name: audit-policy-config

tuningConfig: high-perf-tuned       # bare scalar — typed directly, no JSON braces needed
workerTag: 4.14.0-x86_64`}
          </CodeBlock>

          <div className="mt-4 mb-4">
            <Callout type="tip" title="YAML fields accept any YAML">
              Object/map fields like <InlineCode>agentLabelSelector</InlineCode> accept plain YAML — no
              JSON required. A bare scalar like <InlineCode>high-perf-tuned</InlineCode> is perfectly valid.
              A multiline map is also valid:
              <div className="mt-2">
                <InlineCode>name: high-perf-tuned{"\n"}level: aggressive</InlineCode>
              </div>
            </Callout>
          </div>

          <p className="text-sm text-muted-foreground mb-3">And the full rendered cluster manifest that goes into the Day1 repository:</p>

          <CodeBlock language="Rendered cluster manifest — prod-dok-nova">
{`clusterName: prod-dok-nova
platform: agent

hostInventory: inventory

masterTag: 4.14.0-x86_64

nodepool:
  - name: prod-dok-nova-prod-dok-nova-a-dell-r660-128c-1024gb-10tb-nodepool-zone-a
    replicas: 6
    labels:
      minReplicas: "5"
      maxReplicas: "6"
      allowDeletion: "false"
    nodeLabels:
      node-role.kubernetes.io/worker: ""
      topology.kubernetes.io/zone: zone-a
    agentLabelSelector:
      nodeLabelKey: infraenvs.agent-install.openshift.io
      nodeLabelValue: prod-dok-nova-a-dell-r660-128c-1024gb-10tb
    configs:
      - name: nm-conf-prod-dok-nova-a-dell-r660-128c-1024gb-10tb
      - name: worker-chrony-configuration
      - name: worker-kubeletconfig-high-mem
      - name: special-nic-config      # ← from extra_configs
      - name: audit-policy-config     # ← from additional_configs (all nodepools)
    tuningConfig: high-perf-tuned
    workerTag: 4.14.0-x86_64

  - name: prod-dok-nova-prod-dok-nova-b-dell-r660-128c-1024gb-nodepool-zone-b
    replicas: 3
    labels:
      minReplicas: "2"
      maxReplicas: "3"
      allowDeletion: "false"
    nodeLabels:
    agentLabelSelector:
      nodeLabelKey: infraenvs.agent-install.openshift.io
      nodeLabelValue: prod-dok-nova-b-dell-r660-128c-1024gb
    configs:
      - name: nm-conf-prod-dok-nova-b-dell-r660-128c-1024gb
      - name: worker-chrony-configuration
      - name: worker-kubeletconfig-reserved
      - name: custom-bond-interface   # ← from extra_configs
      - name: audit-policy-config     # ← from additional_configs (all nodepools)
    tuningConfig:
    workerTag: 4.14.0-x86_64

mcFiles:
  - nm-conf-prod-dok-nova-a-dell-r660-128c-1024gb-10tb
  - worker-chrony-configuration
  - worker-kubeletconfig-high-mem
  - special-nic-config
  - audit-policy-config
  - nm-conf-prod-dok-nova-b-dell-r660-128c-1024gb
  - worker-kubeletconfig-reserved
  - custom-bond-interface`}
          </CodeBlock>

          <div className="mt-5">
            <Callout type="info" title="Review before submitting">
              Click <strong>Review</strong> to open a dialog showing the full rendered YAML and all GitLab
              file paths that will be created. Verify everything looks correct before clicking
              <strong> Create Cluster</strong>.
            </Callout>
          </div>
        </section>

        {/* Addons */}
        <section>
          <SectionHeader id="addons" icon={Package} title="Day2 Addons" subtitle="Install, configure, and manage operators on running clusters" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            Addons are Kubernetes operators deployed via ArgoCD. Each addon belongs to a <strong>team</strong>{" "}
            (e.g. <InlineCode>networking</InlineCode>, <InlineCode>storage</InlineCode>, <InlineCode>monitoring</InlineCode>).
            Teams maintain default values; per-cluster overrides are layered on top.
          </p>

          <h3 className="text-base font-semibold mb-3">Value layering</h3>
          <CodeBlock language="Addon value priority (lowest → highest)">
{`1. Helm chart defaults       (shipped with the operator)
2. Team defaults              operators/{addon}/values.yaml
3. Cluster overrides          mces/{mce}/{cluster}/{addon}/values.yaml
                              ↑ this is what Wingman writes when you fill the addon form`}
          </CodeBlock>

          <h3 className="text-base font-semibold mt-6 mb-4">Installing an addon</h3>
          <div className="space-y-3 mb-5">
            <Step n={1} title="Open the cluster's Addons tab">
              Navigate to the cluster (<InlineCode>prod-dok-nova</InlineCode>) → <strong>Addons</strong> tab.
            </Step>
            <Step n={2} title="Browse the catalog">
              Click <strong>Add Addon</strong>. The catalog is organized by team. Select the addon you need.
            </Step>
            <Step n={3} title="Configure override values">
              Only fields the spec author marked as <em>overrideable</em> are shown. You can use the
              <strong> Form</strong> mode for simple key-value edits or switch to <strong>YAML</strong> mode
              for multi-level structures.
            </Step>
            <Step n={4} title="Submit">
              Click <strong>Install</strong>. Wingman commits an override <InlineCode>values.yaml</InlineCode>{" "}
              to the team&apos;s Day2 repository and opens a GitLab MR. Merge it to trigger ArgoCD sync.
            </Step>
          </div>

          <h3 className="text-base font-semibold mb-3">The addon kebab menu</h3>
          <p className="text-sm text-muted-foreground mb-3">
            Each installed addon row has a <strong>⋮</strong> menu with two options:
          </p>
          <div className="space-y-3 mb-5">
            <div className="flex gap-4 rounded-xl border bg-card p-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <ExternalLink className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-sm font-semibold mb-1">Open in GitLab</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Opens the per-cluster override directory directly in GitLab. Path:{" "}
                  <InlineCode>mces/{"{mce}"}/{"{cluster}"}/{"{addon}"}</InlineCode>. Visible to all users,
                  including Viewers — useful for auditing or emergency direct-Git edits.
                </p>
              </div>
            </div>
            <div className="flex gap-4 rounded-xl border bg-card p-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500/10">
                <AlertTriangle className="h-4 w-4 text-red-500" />
              </div>
              <div>
                <p className="text-sm font-semibold mb-1">Remove Addon</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Opens a confirmation dialog then commits a removal MR — deletes the cluster override
                  files and removes the ArgoCD Application. Admin-only.
                </p>
              </div>
            </div>
          </div>

          <Callout type="tip" title="Addon override example">
            Say the <InlineCode>monitoring/prometheus-stack</InlineCode> addon has a team default of{" "}
            <InlineCode>retention: 30d</InlineCode>. For <InlineCode>prod-dok-nova</InlineCode> you
            override to <InlineCode>retention: 90d</InlineCode> and{" "}
            <InlineCode>storageClass: fast-ssd</InlineCode>. These two values are written to{" "}
            <InlineCode>mces/prod-dok/prod-dok-nova/prometheus-stack/values.yaml</InlineCode> in the
            monitoring team&apos;s repository — the team default is unaffected.
          </Callout>
        </section>

        {/* Drift */}
        <section>
          <SectionHeader id="drift" icon={RefreshCw} title="Drift Detection" subtitle="Know when your clusters diverge from their spec" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            A cluster is <strong>drifted</strong> when its committed manifest no longer matches what the
            current spec would render. Common causes:
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
            {[
              { title: "Spec updated", desc: "Someone edited the spec after you created the cluster. The cluster still runs old config." },
              { title: "Direct Git edit", desc: "Someone edited the cluster's manifest directly in GitLab, bypassing Wingman." },
              { title: "Addon drift", desc: "An addon's team defaults changed and the cluster overrides no longer produce the expected result." },
              { title: "Version skew", desc: "The spec's OpenShift version was bumped but the cluster was not re-rendered." },
            ].map(({ title, desc }) => (
              <div key={title} className="rounded-xl border bg-card p-4">
                <p className="text-sm font-semibold mb-1">{title}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>

          <h3 className="text-base font-semibold mb-3">Viewing and resolving drift</h3>
          <div className="space-y-3">
            <Step n={1} title="Find drifted clusters">
              Drifted clusters are highlighted on the <strong>Clusters</strong> list page with a red
              indicator. The spec detail page also lists which of its clusters are drifted.
            </Step>
            <Step n={2} title="Review the diff">
              Open the cluster → <strong>Drift</strong> tab to see a unified diff of what changed
              (similar to <InlineCode>git diff</InlineCode>).
            </Step>
            <Step n={3} title="Resolve">
              Either re-render the cluster (apply the current spec) or edit specific values to reconcile.
              Both paths open a GitLab MR.
            </Step>
          </div>
        </section>

        {/* Approvals */}
        <section>
          <SectionHeader id="approvals" icon={GitPullRequest} title="Approvals" subtitle="Review and merge platform Merge Requests" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-5">
            The <strong>Approvals</strong> page aggregates all open MRs from all platform repositories
            (Day1 cluster repo + all Day2 team repos) in a single view. Admins use this page to:
          </p>
          <div className="space-y-2 mb-5">
            {[
              "Review the manifest diff before merging a cluster creation",
              "Approve addon installs from multiple teams without switching between GitLab projects",
              "Identify and close stale or abandoned MRs",
            ].map((item) => (
              <div key={item} className="flex items-start gap-3 rounded-lg border bg-card px-4 py-3">
                <GitMerge className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                <p className="text-sm text-muted-foreground">{item}</p>
              </div>
            ))}
          </div>
          <Callout type="danger" title="MRs expire">
            Wingman does not auto-merge MRs. If an MR sits unmerged for a long time, the branch may
            conflict with subsequent changes. Close stale MRs and re-create them from the Wingman UI.
          </Callout>
        </section>

        {/* Audit */}
        <section>
          <SectionHeader id="audit" icon={ClipboardList} title="Audit Log" subtitle="Track every platform action to its author" />
          <p className="text-sm text-muted-foreground leading-relaxed mb-4">
            The <strong>Audit</strong> page shows recent Git commits and merged MRs across all platform
            repositories. Every action Wingman takes on your behalf appears here with author, timestamp,
            and a link to the exact commit in GitLab.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="rounded-xl border bg-card p-4">
              <p className="text-sm font-semibold mb-2 flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-emerald-500" />
                Captured
              </p>
              <ul className="space-y-1 text-xs text-muted-foreground">
                {["Spec create / edit / delete", "Cluster creation", "Addon install / remove", "MR merge events", "Value override changes"].map((i) => (
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
                {["Direct GitLab edits outside Wingman", "ArgoCD sync events", "Cluster controller logs", "GitLab CI/CD pipeline runs"].map((i) => (
                  <li key={i} className="flex items-center gap-1.5"><ArrowRight className="h-2.5 w-2.5 text-muted-foreground/50" />{i}</li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* Troubleshooting */}
        <section>
          <SectionHeader id="troubleshooting" icon={AlertTriangle} title="Troubleshooting" subtitle="Common issues and how to fix them" />
          <div className="space-y-4">
            {[
              {
                q: 'Template rendering fails with "undefined variable"',
                a: (
                  <>
                    The Jinja2 template uses <InlineCode>StrictUndefined</InlineCode> — every variable
                    referenced in the template must have a value. Check the preview error message for the
                    exact variable name and ensure it is filled in the cluster form.
                  </>
                ),
              },
              {
                q: "Cluster shows as drifted immediately after creation",
                a: "The spec was edited between when you opened the creation form and when the MR was merged. Re-render the cluster from the current spec.",
              },
              {
                q: "MR was merged but cluster is still not provisioned",
                a: (
                  <>
                    Day1 provisioning is asynchronous. The MR commits manifests to Git; ArgoCD picks them up on
                    its next reconcile loop. Check the ArgoCD Application for the cluster and look for sync errors
                    in the ArgoCD UI. You can also trigger a manual sync if you need the change applied immediately.
                  </>
                ),
              },
              {
                q: "Addon installed but not appearing in the cluster",
                a: (
                  <>
                    ArgoCD syncs on a schedule (or manually via the ArgoCD UI). Use{" "}
                    <strong>Open in GitLab</strong> from the addon menu to confirm the{" "}
                    <InlineCode>values.yaml</InlineCode> is committed, then check the ArgoCD Application
                    health in the ArgoCD dashboard.
                  </>
                ),
              },
              {
                q: 'Site / MCE dropdown shows "No options"',
                a: "Wingman reads existing sites and MCEs from the Day1 GitLab repository folder structure. If no clusters have been deployed yet, the list is empty — type a new name to create the first one.",
              },
              {
                q: "I cannot see Create / Install / Remove buttons",
                a: (
                  <>
                    You have <strong>Viewer</strong> role. Write operations require <strong>Admin</strong>{" "}
                    role. Contact your platform team to request access.
                  </>
                ),
              },
              {
                q: "tuningConfig shows as {name: value} instead of plain value",
                a: (
                  <>
                    This happened with an older version of the form that required JSON syntax. The form
                    now accepts bare YAML scalars — type <InlineCode>high-perf-tuned</InlineCode> without
                    any braces. If you see this in an existing cluster, edit the cluster and re-enter the
                    field as a plain value to clean it up.
                  </>
                ),
              },
            ].map(({ q, a }) => (
              <div key={q} className="rounded-xl border bg-card overflow-hidden">
                <div className="flex items-start gap-3 px-5 py-4 border-b bg-muted/20">
                  <Zap className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  <p className="text-sm font-semibold">{q}</p>
                </div>
                <div className="px-5 py-4 pl-12">
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
              The platform is fully transparent — every resource is a plain YAML or Jinja2 file in GitLab.
              Open the relevant repository directly (<strong>Open in GitLab</strong> links are on every
              cluster, spec, and addon) and inspect or edit the files manually as a last resort.
              The platform team is also reachable via your organisation&apos;s internal channels.
            </p>
          </div>

          <div className="mt-4 rounded-xl border bg-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <FileCode2 className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-semibold">For platform operators — key file locations</p>
            </div>
            <div className="font-mono text-xs text-muted-foreground space-y-1 pl-6 mt-2">
              <p><span className="text-foreground">Day1 repo</span>               — <InlineCode>site/{'{site}'}/mces/{'{mce}'}/hostedClusters/{'{cluster}'}.yaml</InlineCode></p>
              <p><span className="text-foreground">Specs repo root</span>         — cluster-template.j2, openshift-versions.txt</p>
              <p><span className="text-foreground">Day2 repo / operators/</span>  — per-addon team defaults (values.yaml)</p>
              <p><span className="text-foreground">Day2 repo / mces/</span>       — per-cluster addon overrides</p>
              <p><span className="text-foreground">Settings → About</span>        — displays connected GitLab URLs for your instance</p>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
