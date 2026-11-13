import { Boxes } from "lucide-react";
import { SectionHeader } from "./docs-parts";

/** The docs page's "Core Concepts" section, `#concepts`. */
export function ConceptsSection() {
  return (
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
  );
}
