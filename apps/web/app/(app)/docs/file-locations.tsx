import { FileCode2, Layers, Package, Server } from "lucide-react";
import { Callout, InlineCode, SectionHeader } from "./docs-parts";

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

/** The docs page's "File Locations" section, `#filelocations`. */
export function FileLocationsSection() {
  return (
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
  );
}
