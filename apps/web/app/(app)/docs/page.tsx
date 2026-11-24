"use client";

import { useEffect, useMemo, useState } from "react";
import { BookOpen, Boxes, ChevronRight, GitBranch, RefreshCw, Shield } from "lucide-react";
import { AddonsSection } from "./addons";
import { ApprovalsSection } from "./approvals";
import { AuditSection } from "./audit";
import { ClusterWorkflowsSection } from "./cluster-workflows";
import { ClustersSection } from "./clusters";
import { ConceptsSection } from "./concepts";
import { DriftSection } from "./drift";
import { FileLocationsSection } from "./file-locations";
import { FlavorsSection } from "./flavors";
import { GitOpsSection } from "./gitops";
import { HomeSection } from "./home";
import { InventorySection } from "./inventory";
import { OverviewSection } from "./overview";
import { QuickLinksSection } from "./quick-links";
import { RefusalsSection } from "./refusals";
import { RolesSection } from "./roles";
import { SpecialFeaturesSection } from "./special-features";
import { TroubleshootingSection } from "./troubleshooting";
import { WorkspacesSection } from "./workspaces";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";

// ── Low-level primitives ──────────────────────────────────────────────────────

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

// ── Page ──────────────────────────────────────────────────────────────────────

/**
 * Every section, in order. `admin`: about the infrastructure (the workspaces,
 * the server workflows, Inventory, Quick Links, the MCEs' upgrade rules, the
 * repo's folders), so not a viewer's: a customer never learns of it (ADR-0068).
 */
const NAV_SECTIONS: { id: string; label: string; Section: () => React.ReactNode; admin?: true }[] = [
  { id: "overview", label: "Platform Overview", Section: OverviewSection },
  { id: "concepts", label: "Core Concepts", Section: ConceptsSection },
  { id: "roles", label: "Roles & Access", Section: RolesSection },
  { id: "workspaces", label: "Workspaces", Section: WorkspacesSection, admin: true },
  { id: "gitops", label: "GitOps Workflow", Section: GitOpsSection },
  { id: "home", label: "The Overview Page", Section: HomeSection },
  { id: "specs", label: "Flavors", Section: FlavorsSection },
  { id: "clusters", label: "Clusters", Section: ClustersSection },
  { id: "cluster-workflows", label: "Cluster Workflows", Section: ClusterWorkflowsSection, admin: true },
  { id: "inventory", label: "Inventory Management", Section: InventorySection, admin: true },
  { id: "addons", label: "Day2 Addons", Section: AddonsSection },
  { id: "drift", label: "Drift Detection", Section: DriftSection },
  { id: "approvals", label: "Approvals", Section: ApprovalsSection },
  { id: "audit", label: "Audit Log", Section: AuditSection },
  { id: "quick-links", label: "Quick Links", Section: QuickLinksSection, admin: true },
  { id: "errors", label: "When a Change Is Refused", Section: RefusalsSection },
  { id: "special-features", label: "Special Features", Section: SpecialFeaturesSection, admin: true },
  { id: "filelocations", label: "File Locations", Section: FileLocationsSection, admin: true },
  { id: "troubleshooting", label: "Troubleshooting", Section: TroubleshootingSection },
];

/** The nav, the hero and the sections in order; each section is a file beside this one. */
export default function DocsPage() {
  const [activeSection, setActiveSection] = useState<string>("overview");
  // The role is known once mounted (the persisted auth store): until then the sections everyone reads
  const mounted = useMounted();
  const isAdmin = useIsAdmin() && mounted;
  const sections = useMemo(() => NAV_SECTIONS.filter((s) => isAdmin || !s.admin), [isAdmin]);

  useEffect(() => {
    const observers = sections.map(({ id }) => {
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
  }, [sections]);

  return (
    <div className="flex gap-10 max-w-7xl mx-auto px-4 sm:px-6 py-8">

      {/* Left sticky nav */}
      <aside className="hidden xl:block w-56 shrink-0">
        <div className="sticky top-6">
          <div className="rounded-xl border bg-card p-3 shadow-sm max-h-[calc(100vh-3rem)] overflow-y-auto">
            <p className="px-2 mb-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Contents</p>
            <nav aria-label="Contents" className="space-y-0.5">
              {sections.map(({ id, label }) => (
                <NavLink key={id} href={`#${id}`} label={label} active={activeSection === id} />
              ))}
            </nav>
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
              store: a change you make opens a merge request, and nothing changes until another admin approves it
              and it is merged. ArgoCD applies what is merged. A few actions start one of the platform&apos;s
              workflows instead, which does the work and its own checks.
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

        {sections.map(({ id, Section }) => <Section key={id} />)}

      </div>
    </div>
  );
}
