import { Boxes } from "lucide-react";
import { Callout, InlineCode, SectionHeader, Step, TermCard } from "./docs-parts";

/** A pool row's four numbers, as the column headers' tooltips say them. */
const COLUMNS = [
  {
    title: "Available",
    desc: "Agents already in this MCE's inventory and in no cluster. A NodePool on this InfraEnv that is short of nodes takes one.",
  },
  {
    title: "Ready",
    desc: "Free servers in server-scan named for this pool that a pool draw could pick today: healthy and reachable, unlocked, out of maintenance. The workflow still checks each one itself, so a run may still refuse one.",
  },
  {
    title: "Needs fix",
    desc: "Free servers named for this pool that a pool draw never picks: server-scan does not call them healthy, or cannot reach their BMC.",
  },
  {
    title: "Total",
    desc: "Available + Ready + Needs fix: what the pool reaches once every free server named for it is fixed and installed. Locked, in-maintenance and contested servers are not counted.",
  },
] as const;

/** The docs page's "Inventory Management" section, `#inventory` (ADR-0057 and its amendments). */
export function InventorySection() {
  return (
    <section>
      <SectionHeader id="inventory" icon={Boxes} title="Inventory Management" subtitle="Each MCE's server pools, the add-server runs, and installing servers" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        A server reaches a hosted cluster in two steps. The platform&apos;s <InlineCode>add-server-to-mce</InlineCode>{" "}
        workflow makes it an Agent in one of an MCE&apos;s InfraEnv pools (the inventory); then any NodePool on that
        InfraEnv that is short of nodes takes a free Agent, whatever its cluster. herzi, one per MCE hub, starts the same
        workflow by itself to keep the pools topped up. <strong>Inventory Management</strong>, in the sidebar, shows both:
        everyone signed in reads it, and only admins install.
      </p>

      <h3 className="text-base font-semibold mb-3">The pools</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        One card per MCE, with its servers <strong>available</strong>, <strong>in clusters</strong> and its{" "}
        <strong>total</strong>, then a row per InfraEnv pool. Click an MCE&apos;s name to fold its pools away; this
        browser remembers it. The counts are server-scan&apos;s: an MCE it names no server on says{" "}
        <strong>not in server-scan</strong>, never zero, and an available server whose name starts with no InfraEnv of
        the MCE is counted under <strong>No InfraEnv</strong>, not guessed. Each number&apos;s header explains it in a
        tooltip:
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {COLUMNS.map(({ title, desc }) => (
          <TermCard key={title} title={title} desc={desc} />
        ))}
      </div>
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        Where this deployment does not read the MCE&apos;s own InfraEnv list (live status off), the pools are the
        InfraEnvs its cluster files name, and the card says so in one quiet line.
      </p>

      <h3 className="text-base font-semibold mb-3">The runs</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-5">
        <strong>Runs</strong> lists the platform&apos;s add-server runs, herzi&apos;s and people&apos;s, newest first: when
        each started, who, its pool, its server, its status and its error, in the workflow&apos;s words. A run that named
        its server is a <strong>Person</strong>&apos;s; a pool draw is <strong>herzi or a person</strong>, since the
        orchestrator does not record who. A run installed with its health checks waived says <strong>checks waived</strong>, with which in a tooltip.
      </p>

      <h3 className="text-base font-semibold mb-3">Install servers</h3>
      <div className="space-y-4 mb-5">
        <Step n={1} title="Open the dialog">
          An admin&apos;s <strong>Install servers</strong> beside the title, or <strong>Install</strong> on a pool row,
          which opens it on that MCE and pool.
        </Step>
        <Step n={2} title="Choose the MCE and the pool">
          Pick the MCE and its InfraEnv, or type another InfraEnv name: the workflow first checks the MCE has it.
        </Step>
        <Step n={3} title="Let the pool pick, or choose servers">
          <strong>Let the pool pick</strong> takes a number (up to 20) and leaves the choice to the workflow.{" "}
          <strong>Choose servers</strong> lists the free servers named for the pool (up to 20 at once). A locked,
          in-maintenance or contested server is listed with why and cannot be chosen.
        </Step>
        <Step n={4} title="Install">
          Before anything is sent the dialog says what an install does: the server <strong>joins the MCE&apos;s pool,
          not one cluster</strong>; there is <strong>one run per server</strong>; and <strong>sending again installs
          more</strong>. The runs appear under Runs.
        </Step>
      </div>
      <div className="space-y-3">
        <Callout type="warning" title="Installing a server that needs a fix">
          Under <strong>Choose servers</strong>, an admin may also check a <strong>Needs fix</strong> server.{" "}
          <strong>Install</strong> then asks first, in <strong>Install with health checks waived?</strong>: it lists each
          such server with what server-scan shows wrong, and says the workflow waives its health checks for every server
          of the request while its safety checks still apply. Only <strong>Install with checks waived</strong> sends it;
          Back and Cancel send nothing. A pool draw never waives a check.
        </Callout>
        <Callout type="info" title="When Install servers is greyed out">
          Installing needs <InlineCode>DAY1_ADD_SERVERS</InlineCode> on (the chart&apos;s{" "}
          <InlineCode>day1.addServers.enabled</InlineCode>, off by default) and the workflows orchestrator. Without them
          an admin sees the button greyed out with the reason in its tooltip; a viewer sees no button. The page itself
          needs server-scan (<InlineCode>SERVER_SCAN_URL</InlineCode>), or it says{" "}
          <strong>Inventory Management is not set up</strong>.
        </Callout>
        <Callout type="danger" title="A start is never retried">
          If Wingman sent a start and got no answer, some servers may have started: look at the runs before you send
          again, since sending again installs more.
        </Callout>
      </div>
    </section>
  );
}
