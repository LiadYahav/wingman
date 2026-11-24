import { LayoutDashboard } from "lucide-react";
import { Callout, InlineCode, SectionHeader, TermCard } from "./docs-parts";

/** The two overviews' cards below their numbers, in each page's order (ADR-0067). */
const CARDS = [
  {
    title: "OpenShift Versions (Customers)",
    desc: "The customers' clusters per mastertag, newest first. With upgrades on, how many have an upgrade available and how many are upgrading; each opens the Clusters list with that filter.",
  },
  {
    title: "Where Clusters Run (Infrastructure)",
    desc: "The customers' clusters per site, with each Customer MCE's count under its bar: the day1 repo's site and MCE folders. The five biggest sites are shown; the rest are summed in one line.",
  },
  {
    title: "Free Servers (Infrastructure)",
    desc: "Each MCE's free Agents by InfraEnv pool, as server-scan counts them: Inventory Management's numbers. Each MCE opens its own servers in Inventory Management.",
  },
] as const;

/** The docs page's "The Overview Page" section, `#home`: each workspace's home page (ADR-0057, ADR-0067). */
export function HomeSection() {
  return (
    <section>
      <SectionHeader id="home" icon={LayoutDashboard} title="The Overview Pages" subtitle="Each workspace's home: the customers' clusters, and what serves them, at a glance" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        <strong>Dashboard</strong>, the Customers workspace&apos;s home, opens with four numbers about the
        customers&apos; clusters: <strong>Total Clusters</strong>, <strong>Ready</strong> (from live status),{" "}
        <strong>Pending Approvals</strong> and <strong>Drifted</strong>, each a link to its page. Under them,{" "}
        <strong>Cluster Health</strong> counts the clusters by their live phase (Ready, Provisioning, Error,
        Unknown), and <strong>Pending Approvals</strong> lists the newest open merge requests, or says{" "}
        <strong>All caught up</strong>. Admins get <strong>New Cluster</strong> and <strong>New Flavor</strong>{" "}
        beside the title; everyone gets <strong>Browse Flavors</strong>. A KV cluster is never counted there.
      </p>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        <strong>Overview</strong>, the Infrastructure workspace&apos;s home (admins), counts the{" "}
        <strong>Customer MCEs</strong> and their sites, the <strong>Seeds</strong> and their zones, the{" "}
        <strong>KV Clusters</strong> and the <strong>Free Servers</strong>, each a link to its page.
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
        <strong>Live status is off</strong>). Free segments and the server fleet&apos;s health live in
        segments-manager&apos;s and server-scan&apos;s own UIs, apart from Wingman: the Infrastructure sidebar links to each.
      </Callout>
    </section>
  );
}
