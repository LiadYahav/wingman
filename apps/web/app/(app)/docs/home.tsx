import { LayoutDashboard } from "lucide-react";
import { Callout, InlineCode, SectionHeader, TermCard } from "./docs-parts";

/** The home page's cards below Cluster Health and Pending Approvals, in the page's order. */
const CARDS = [
  {
    title: "Where Clusters Run",
    desc: "Clusters per site, with each MCE's count under its bar: the day1 repo's site and MCE folders. The five biggest sites are shown; the rest are summed in one line.",
  },
  {
    title: "OpenShift Versions",
    desc: "Clusters per mastertag, newest first. With upgrades on, how many clusters have an upgrade available and how many are upgrading; each opens the Clusters list with that filter.",
  },
  {
    title: "Free Servers",
    desc: "Each MCE's free Agents by InfraEnv pool, as server-scan counts them: Inventory Management's numbers, for everyone. Each MCE opens Inventory Management.",
  },
  {
    title: "Free Segments",
    desc: "Each site's segments that are Available in segments-manager, out of all its segments. Shown only to people with the Segments area; each site opens its Available segments.",
  },
  {
    title: "Server Fleet Health",
    desc: "server-scan's servers per site by health (critical, major, warning, unknown) and those in maintenance. Shown only to people with the Server Scan area; each count opens the Servers page filtered to it.",
  },
] as const;

/** The docs page's "The Overview Page" section, `#home`: Wingman's home page (ADR-0047, ADR-0048, ADR-0057). */
export function HomeSection() {
  return (
    <section>
      <SectionHeader id="home" icon={LayoutDashboard} title="The Overview Page" subtitle="Wingman's home page, Dashboard in the sidebar: the platform at a glance" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        Four numbers open the page: <strong>Total Clusters</strong>, <strong>Ready</strong> (from live status),{" "}
        <strong>Pending Approvals</strong> and <strong>Drifted</strong>, each a link to its page. Under them,{" "}
        <strong>Cluster Health</strong> counts the clusters by their live phase (Ready, Provisioning, Error,
        Unknown), and <strong>Pending Approvals</strong> lists the newest open merge requests, or says{" "}
        <strong>All caught up</strong>. Admins get <strong>New Cluster</strong> and <strong>New Flavor</strong>{" "}
        beside the title; everyone gets <strong>Browse Flavors</strong>.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {CARDS.map(({ title, desc }) => (
          <TermCard key={title} title={title} desc={desc} />
        ))}
      </div>
      <Callout type="tip" title="Each card stands alone">
        Every card reads its own source, so one that fails or loads slowly leaves the others alone. A source this
        deployment does not have says so in one quiet line (Free Servers needs{" "}
        <InlineCode>SERVER_SCAN_URL</InlineCode>; with live status off, Ready and Cluster Health say{" "}
        <strong>Live status is off</strong>), or its card is not shown at all.
      </Callout>
    </section>
  );
}
