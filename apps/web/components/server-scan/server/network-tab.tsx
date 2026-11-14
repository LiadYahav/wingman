import { CopyButton } from "@/components/data-table/copy-cell";
import { attachmentDetails, bmcAddress, describeLocation, fabricGroups, interconnectName, speedText, type FabricGroup } from "@/lib/server-scan/network";
import type { ConnectivityDetail, NetworkInfo } from "@/types/server-scan-record";
import { Empty, LinkState, Reported, SectionTitle } from "./fields";

/**
 * The Network and Connectivity tabs, as server-scan's `NetworkTab.tsx` and
 * `ConnectivityTab.tsx` (team-redbull/server-scan at 92146d3, decision 18;
 * docs/notes/2026-11-13-server-scan-area-api.md §9.1); the rules are
 * `lib/server-scan/network.ts`.
 */

/** The BMC and every interface in server-scan's order: where it is, its MAC's number, speed, link, OS name. */
export function NetworkTab({ network, osNames, unreadFields }: { network: NetworkInfo; osNames: Record<string, string>; unreadFields: string[] }) {
  const unread = new Set(unreadFields);
  const address = bmcAddress(network.bmc);
  const { interfaces } = network;
  return (
    <div className="space-y-8 rounded-xl border bg-card p-5" data-testid="ss-network">
      <section aria-label="BMC">
        <SectionTitle>BMC</SectionTitle>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted-foreground">Address</dt>
            <dd className="inline-flex items-center gap-1 font-medium">
              {address ?? "—"}
              {address && <CopyButton value={address} label="BMC address" />}
            </dd>
          </div>
          {network.bmc.mac && (
            <div>
              <dt className="text-xs text-muted-foreground">MAC</dt>
              <dd className="font-medium">
                <Reported unread={unread.has("network.bmc.mac")} empty={false} inline>
                  {network.bmc.mac}
                </Reported>
              </dd>
            </div>
          )}
        </dl>
      </section>
      <section aria-label="Interfaces">
        <SectionTitle>Interfaces</SectionTitle>
        <Reported unread={unread.has("identity.nic_macs") || unread.has("network.interfaces")} empty={interfaces.length === 0}>
          {interfaces.length > 0 ? (
            <ul className="mt-2 divide-y divide-border/60">
              {interfaces.map((iface, index) => (
                <li key={`${iface.name}-${iface.mac}`} className="py-3" data-testid="ss-interface">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                    <span className="font-medium">{iface.name}</span>
                    <span className="font-mono text-sm text-muted-foreground">{iface.mac ?? "—"}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
                    <span>{describeLocation(iface) ?? "—"}</span>
                    <span aria-hidden>·</span>
                    <span title="Its discovery order: tooling picks the bond pair by it">MAC #{index + 1}</span>
                    <span aria-hidden>·</span>
                    <span>{speedText(iface.speed_mbps)}</span>
                    <span aria-hidden>·</span>
                    <LinkState state={iface.link_state} />
                  </div>
                  {osNames[iface.name] && (
                    <p className="mt-1 text-sm text-muted-foreground" title="From server-scan's settings, not read from the server">
                      OS name (derived): <span className="font-mono text-foreground">{osNames[iface.name]}</span>
                    </p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No network interfaces.</Empty>
          )}
        </Reported>
      </section>
    </div>
  );
}

function FabricCard({ group }: { group: FabricGroup }) {
  return (
    <div className="rounded-lg border p-4" data-testid="ss-fabric">
      <h3 className="text-sm font-semibold">Fabric {group.fabric ?? "Other"}</h3>
      <ul className="mt-3 space-y-3">
        {group.attachments.map((a, index) => (
          <li key={`${a.fabric_id ?? a.fabric_name ?? "fi"}-${a.server_port ?? index}`} className="rounded-md border border-border/60 p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{interconnectName(a)}</span>
              <LinkState state={a.oper_state} />
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              {attachmentDetails(a).map(([label, value]) => (
                <div key={label} className="contents">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A Cisco server's physical fabric uplinks, a card per fabric. */
export function ConnectivityTab({ connectivity }: { connectivity: ConnectivityDetail }) {
  const groups = fabricGroups(connectivity.attachments);
  const box = "rounded-xl border bg-card p-5";
  if (connectivity.attachments.length === 0) {
    return (
      <div className={box} data-testid="ss-connectivity">
        <p className="text-sm text-muted-foreground">No connectivity data.</p>
      </div>
    );
  }
  if (groups.length === 0) {
    return (
      <div className={box} data-testid="ss-connectivity">
        <p className="text-sm text-muted-foreground">No physical fabric connections reported.</p>
      </div>
    );
  }
  const { fabric_paths_up: up, fabric_paths_total: total } = connectivity.facts;
  return (
    <div className={`${box} space-y-4`} data-testid="ss-connectivity">
      <p className="text-sm text-muted-foreground" data-testid="ss-fabric-paths">
        {up}/{total} fabric paths up
      </p>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {groups.map((group) => (
          <FabricCard key={group.fabric ?? "__other__"} group={group} />
        ))}
      </div>
    </div>
  );
}
