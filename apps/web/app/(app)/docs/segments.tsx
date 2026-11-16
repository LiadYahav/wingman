import { Network } from "lucide-react";
import { Callout, InlineCode, SectionHeader, TermCard } from "./docs-parts";

/** What the Segments page offers, in the page's order. */
const PARTS = [
  {
    title: "Site cards",
    desc: "One per site: how many of its segments are used, and the allocated ones per type. Click a card to show only that site; click it again to show all.",
  },
  {
    title: "The table",
    desc: "Type, Site, VLAN ID, EPG Name, Network Segment, DHCP, Cluster and Status. A cluster whose file is in the day1 repo opens its Wingman page.",
  },
  {
    title: "Filters",
    desc: "Search by cluster, EPG, VLAN ID or segment; Available or Allocated; a site; a filter on any column; hide columns you do not need. The filters are in the address, so a view can be shared.",
  },
  {
    title: "Disagrees with Git",
    desc: "A warning mark beside the VLAN ID where segments-manager disagrees with a cluster file: the segment is not Allocated, another cluster holds it, or the VLAN or segment differs. Its popup says which cluster and why.",
  },
] as const;

/** The docs page's "Segments" section, `#segments` (ADR-0047 and its amendment; ADR-0039 for the checks). */
export function SegmentsSection() {
  return (
    <section>
      <SectionHeader id="segments" icon={Network} title="Segments" subtitle="segments-manager's network segments, read in Wingman" badge="Admins" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        The top bar&apos;s <strong>Segments</strong> opens segments-manager&apos;s segments inside Wingman: every
        site&apos;s VLANs and network segments, which the allocate-segment workflow hands to new clusters. Its sidebar
        has the same views as the page (<strong>All</strong>, <strong>Available</strong>, <strong>Allocated</strong>,{" "}
        <strong>Disagrees with Git</strong>) and each site with its allocated and total segments.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {PARTS.map(({ title, desc }) => (
          <TermCard key={title} title={title} desc={desc} />
        ))}
      </div>
      <div className="space-y-3">
        <Callout type="info" title="Read-only">
          Wingman never writes to segments-manager. The page reads it again every 30 seconds, and a dot beside the time
          says whether the last read was answered. <strong>Refresh</strong> reads segments-manager&apos;s database now,
          and the rows shown download as CSV or Excel. Where segments-manager and a cluster file disagree, Git is the
          source of truth: the file is what the cluster runs with.
        </Callout>
        <Callout type="tip" title="Who sees it">
          Wingman&apos;s admins, for now, once segments-manager is configured (<InlineCode>SEGMENTS_MANAGER_URL</InlineCode>,
          the chart&apos;s <InlineCode>segmentsManager.url</InlineCode>). Without it the area is not in the top bar.
        </Callout>
      </div>
    </section>
  );
}
