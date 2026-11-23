import { Link2 } from "lucide-react";
import { Callout, CodeBlock, InlineCode, SectionHeader } from "./docs-parts";

/** The docs page's "Quick Links" section, `#quick-links` (ADR-0052 and its amendment). */
export function QuickLinksSection() {
  return (
    <section>
      <SectionHeader id="quick-links" icon={Link2} title="Quick Links" subtitle="Every cluster's ArgoCD and console, and the team's own links, on one page" badge="Admins" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        <strong>Quick Links</strong>, in the Infrastructure workspace&apos;s sidebar, is a launcher for Wingman&apos;s admins. It starts with a card for
        the hub Wingman runs on, then one for every MCE of the day1 repo, a section per site: each opens that
        cluster&apos;s ArgoCD, with its console beside it. The team&apos;s own links follow, in the sections your
        operator writes. Search with the box at the top, or press <InlineCode>/</InlineCode> to jump to it.
      </p>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        Wingman only lists the links: it never calls them, so there are no status dots, and the page keeps working when
        what it links to does not. The icons ship with Wingman.
      </p>
      <CodeBlock language="The chart's quickLinks.sections — the team's links">
{`quickLinks:
  sections:
    - name: Core GitOps
      columns: 2                    # 1 to 6, default 4
      links:
        - name: GitLab GitOps Project
          url: https://gitlab.<domain>/platform/gitops
          description: Main GitOps repository
          icon: gitlab              # a key: argocd, gitlab, openshift, grafana, ...`}
      </CodeBlock>
      <div className="space-y-3 mt-4">
        <Callout type="info" title="Where the links come from">
          The cluster cards follow two URL templates with <InlineCode>{"{cluster}"}</InlineCode> and{" "}
          <InlineCode>{"{domain}"}</InlineCode> (<InlineCode>quickLinks.argocdUrlTemplate</InlineCode>,{" "}
          <InlineCode>quickLinks.consoleUrlTemplate</InlineCode>); a cluster that does not follow them gets its own
          addresses in <InlineCode>quickLinks.clusters</InlineCode>. The team&apos;s links are a ConfigMap the chart
          renders from <InlineCode>quickLinks.sections</InlineCode>, read again on every page load, so an edit shows
          without a restart. With nothing set the page says <strong>No links yet</strong> and names what to set.
        </Callout>
        <Callout type="tip" title="A bad links file never breaks the page">
          A link without a name or an http(s) address, or an unknown key, is skipped or ignored, and a line above the
          cards names the section and the link. The rest of the page still shows.
        </Callout>
      </div>
    </section>
  );
}
