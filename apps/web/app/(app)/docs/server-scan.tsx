import { ScanSearch } from "lucide-react";
import { Callout, InlineCode, SectionHeader, TermCard } from "./docs-parts";

/** The area's pages, in its sidebar's order (Fleet, Activity, Configuration, Reference). */
const PAGES = [
  {
    title: "Sites",
    desc: "The fleet at a glance: a card for all sites, each installation type (UPI, Hosted cluster, MCE), Available and Installed, then one per site. Each counts its critical, major, warning, in-maintenance and unknown servers, or says all healthy, a bar of its servers by health, and its physical servers, VMs and servers per vendor; every count opens Servers filtered to it.",
  },
  {
    title: "Servers",
    desc: "The fleet's table, read again every 30 seconds: search by name, serial or BMC, filter by vendor, source, type (physical or VM), site, classification, installation and health, toggle stale, duplicate, name-mismatch and donor servers, or pick a cluster in the side panel; a row's BMC opens its console or copies its address. The table scrolls in its own box, its header pinned. A ticked health leaves out servers in maintenance unless Maintenance is ticked too, as the Sites cards count them. Export as Excel or CSV.",
  },
  {
    title: "A server's page",
    desc: "Opened from a name on Servers, in Inventory Management or on a cluster's Nodes tab. Tabs: Overview (health and why, the install lock, maintenance, and a collection error with its cause), Hardware, Network, Connectivity and History. A BMC button opens its console; Fetch now reads the server from its vendor manager now.",
  },
  {
    title: "Confs",
    desc: "The hardware catalog, read only: one row per server configuration (part number, model, CPU, RAM, storage, GPUs, adapters). Click a row for the full spec.",
  },
  {
    title: "Events",
    desc: "The fleet's audit trail, newest first, in Israel time. Filter by event type, server (name, serial or BMC), user and time range; each event's details name the server's serial and BMC.",
  },
  {
    title: "Jobs",
    desc: "server-scan's collector and prune CronJobs: each one's schedule, its recent runs and each run's log, read again every 5 seconds while a run goes on.",
  },
  {
    title: "Rules & Policies",
    desc: "What server-scan runs, read only: its classification rules in the order it tries them, and its health policies with their severity and condition.",
  },
  {
    title: "Claude and Architecture",
    desc: "Claude sets up server-scan's Claude Code skill: its zip, four setup steps, or an MCP server. Architecture shows server-scan's diagrams, the full flow and one per collector, a tab each.",
  },
] as const;

/** The docs page's "Server Scan" section, `#server-scan` (ADR-0048 and its amendments, up to 2026-11-16). */
export function ServerScanSection() {
  return (
    <section>
      <SectionHeader id="server-scan" icon={ScanSearch} title="Server Scan" subtitle="server-scan's pages, inside Wingman" badge="Admins" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        The top bar&apos;s <strong>Server Scan</strong> opens server-scan&apos;s pages inside Wingman, read through
        Wingman with no second sign-in. Its sidebar groups them: <strong>Fleet</strong> (Sites, Servers, Confs),{" "}
        <strong>Activity</strong> (Events, Jobs), <strong>Configuration</strong> (Rules &amp; Policies) and{" "}
        <strong>Reference</strong> (Claude, Architecture).
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {PAGES.map(({ title, desc }) => (
          <TermCard key={title} title={title} desc={desc} />
        ))}
      </div>
      <div className="space-y-3">
        <Callout type="warning" title="Three writes, each logged with your name">
          <strong>Maintenance</strong>, on Servers: turning a server&apos;s maintenance on asks why and, if you like, the
          expected end (<strong>Start maintenance</strong>); turning it off is one click. A server&apos;s page shows its
          maintenance and links to the switch on Servers. <strong>Run job</strong>, on Jobs: after{" "}
          <strong>Run this job now?</strong> it starts a real Job from the CronJob&apos;s template, sent once.{" "}
          <strong>Fetch now</strong>, on a server&apos;s page and first on every Servers row: server-scan reads that one
          server from its vendor manager now, which can take a minute or two, sent once; a server it cannot read so (a
          standalone Redfish BMC) says why. Everything else in the area is read only.
        </Callout>
        <Callout type="info" title="Who sees it, and what needs a token">
          Wingman&apos;s admins, for now, once server-scan is configured (<InlineCode>SERVER_SCAN_URL</InlineCode>, the
          chart&apos;s <InlineCode>serverScan.url</InlineCode>); a viewer who opens a page is told it is for admins.
          Where server-scan asks for tokens, Maintenance, Jobs and Fetch now need its admin token and History and Events its
          auditor token, from the Secret your operator names in <InlineCode>serverScan.tokenSecret.name</InlineCode>;
          without one, the page or the switch says which it needs. An older server-scan still works, without its newer
          details.
        </Callout>
      </div>
    </section>
  );
}
