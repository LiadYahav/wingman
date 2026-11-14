/**
 * The Network and Connectivity tabs' rules, as server-scan's server page has
 * them (docs/notes/2026-11-13-server-scan-area-api.md §9.1): where a NIC is
 * in words, the BMC's address, and a Cisco server's physical fabric uplinks
 * grouped by fabric.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/features/servers/NetworkTab.tsx` and
 * `ConnectivityTab.tsx`.
 */

import type { BmcInfo, ConnectivityAttachment, NetworkInterface } from "@/types/server-scan-record";

const FQDD = /^NIC\.([A-Za-z]+)\.(\d+)-(\d+)-(\d+)$/;

/**
 * A Dell NIC FQDD in words: "Onboard · port 1" for an integrated NIC (the
 * distinction its OS name hangs off), "Slot 8 · port 1" for a card; any other
 * interface keeps the BMC's location.
 */
export function describeLocation(iface: Pick<NetworkInterface, "name" | "location">): string | null {
  const match = FQDD.exec(iface.name);
  if (!match) return iface.location;
  const [, kind, controller, port] = match;
  const where = kind === "Integrated" ? "Onboard" : `Slot ${controller}`;
  return `${where} · port ${port}`;
}

/** The BMC's host alone (the full URI is kept for Metal3), else what was read raw. */
export function bmcAddress(bmc: BmcInfo): string | null {
  return bmc.host ?? bmc.address_raw ?? null;
}

/** An interface's speed, or a dash: the collector looked and got nothing. */
export function speedText(speedMbps: number | null): string {
  return speedMbps != null ? `${speedMbps} Mbps` : "—";
}

export interface FabricGroup {
  /** `null`: the trailing "Other". */
  fabric: string | null;
  attachments: ConnectivityAttachment[];
}

/**
 * The cabled uplinks only (a port and its vNICs report the same fabric),
 * grouped by fabric in first-seen order, those with none last as "Other".
 */
export function fabricGroups(attachments: readonly ConnectivityAttachment[]): FabricGroup[] {
  const order: string[] = [];
  const groups = new Map<string, ConnectivityAttachment[]>();
  const other: ConnectivityAttachment[] = [];
  for (const attachment of attachments) {
    if (attachment.interface_kind !== "PHYSICAL") continue;
    if (attachment.fabric === null) {
      other.push(attachment);
      continue;
    }
    const existing = groups.get(attachment.fabric);
    if (existing) existing.push(attachment);
    else {
      groups.set(attachment.fabric, [attachment]);
      order.push(attachment.fabric);
    }
  }
  const result: FabricGroup[] = order.map((fabric) => ({ fabric, attachments: groups.get(fabric) ?? [] }));
  if (other.length > 0) result.push({ fabric: null, attachments: other });
  return result;
}

/** An uplink's details as server-scan lists them: only those read, Admin state always. */
export function attachmentDetails(a: ConnectivityAttachment): [label: string, value: string][] {
  const rows: [string, string | null][] = [
    ["Model", a.fabric_model],
    ["Serial", a.fabric_serial],
    ["Server interface", a.server_interface],
    ["Server port", a.server_port],
    ["Fabric port", a.fabric_port],
    ["Admin state", a.admin_state],
    ["Speed", a.speed_mbps != null ? `${a.speed_mbps} Mbps` : null],
  ];
  return rows.filter((row): row is [string, string] => Boolean(row[1]));
}

/** The interconnect's name, else its id, else "Unnamed interconnect". */
export function interconnectName(a: ConnectivityAttachment): string {
  return a.fabric_name ?? a.fabric_id ?? "Unnamed interconnect";
}
