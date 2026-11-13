"use client";

import { useState, useEffect } from "react";
import { BookOpen, Boxes, ChevronRight, GitBranch, RefreshCw, Shield } from "lucide-react";
import { AddonsSection } from "./addons";
import { ApprovalsSection } from "./approvals";
import { AuditSection } from "./audit";
import { ClustersSection } from "./clusters";
import { ConceptsSection } from "./concepts";
import { DriftSection } from "./drift";
import { FileLocationsSection } from "./file-locations";
import { FlavorsSection } from "./flavors";
import { GitOpsSection } from "./gitops";
import { OverviewSection } from "./overview";
import { RefusalsSection } from "./refusals";
import { RolesSection } from "./roles";
import { SpecialFeaturesSection } from "./special-features";
import { TroubleshootingSection } from "./troubleshooting";

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

/** The nav, the hero and the sections in order; each section is a file beside this one. */
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

        <OverviewSection />
        <ConceptsSection />
        <RolesSection />
        <GitOpsSection />
        <FlavorsSection />
        <ClustersSection />
        <AddonsSection />
        <DriftSection />
        <ApprovalsSection />
        <AuditSection />
        <RefusalsSection />
        <SpecialFeaturesSection />
        <FileLocationsSection />
        <TroubleshootingSection />

      </div>
    </div>
  );
}
