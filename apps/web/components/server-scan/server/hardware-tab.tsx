import { GPU_COLUMNS, NOT_READ_TITLE, STALE_TITLE, driveCells, formatMemory, formatStorage, gpuCells, psuLine, sortDrivesByCapacity } from "@/lib/server-scan/hardware";
import { cn } from "@/lib/utils";
import type { HardwareInfo } from "@/types/server-scan-record";
import { ComponentHealthValue, Empty, Reported, SectionTitle, Unconfirmed } from "./fields";

/**
 * The Hardware tab, as server-scan's `HardwareTab.tsx` (team-redbull/server-scan
 * at 92146d3, decision 18; docs/notes/2026-11-13-server-scan-area-api.md
 * §9.1): CPU, memory, storage with its drives, GPUs and PSUs. A field the
 * last collection could not read says so (`unread_fields`); the numbers and
 * words are `lib/server-scan/hardware.ts`.
 */

const TABLE = "min-w-full text-sm";
const HEAD = "py-1.5 pr-4 text-left text-xs font-medium text-muted-foreground";
const CELL = "py-1.5 pr-4 align-top";

/** One CPU figure; an unread one reads "Not reported", or its old value marked unconfirmed. */
function Stat({ label, value, unread }: { label: string; value: string | number | null; unread: boolean }) {
  // Falsy catches the 0 and "" server-scan writes for a field it never read
  const empty = !value;
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("font-medium", unread && (empty ? "text-muted-foreground" : "opacity-70"))} title={unread ? (empty ? NOT_READ_TITLE : STALE_TITLE) : undefined}>
        {unread && empty ? "Not reported" : (value ?? "—")}
        {unread && !empty && <Unconfirmed />}
      </dd>
    </div>
  );
}

function Drives({ hardware, unread }: { hardware: HardwareInfo; unread: Set<string> }) {
  const { drives } = hardware.storage;
  return (
    <Reported unread={unread.has("hardware.storage.drives")} empty={drives.length === 0}>
      {drives.length > 0 ? (
        <div className="mt-2 overflow-x-auto">
          <table className={TABLE} aria-label="Drives">
            <thead>
              <tr>
                {["Model", "Serial", "Media", "Capacity", "Health"].map((h) => (
                  <th key={h} className={HEAD}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {sortDrivesByCapacity(drives).map((drive) => (
                <tr key={drive.id} data-testid="ss-drive">
                  {driveCells(drive).map((cell, i) => (
                    <td key={i} className={CELL}>{cell}</td>
                  ))}
                  <td className={CELL}>
                    <ComponentHealthValue value={drive.health} detail={drive.health_detail} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>No per-drive detail.</Empty>
      )}
    </Reported>
  );
}

function Gpus({ hardware, unread }: { hardware: HardwareInfo; unread: Set<string> }) {
  const { gpus } = hardware;
  return (
    <Reported unread={unread.has("hardware.gpus")} empty={gpus.length === 0}>
      {gpus.length > 0 ? (
        <div className="mt-2 overflow-x-auto">
          <table className={TABLE} aria-label="GPUs">
            <thead>
              <tr>
                {GPU_COLUMNS.map((h) => (
                  <th key={h} className={HEAD}>{h}</th>
                ))}
                <th className={HEAD}>Health</th>
                <th className={HEAD}>Firmware</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {gpus.map((gpu, index) => {
                const { cells, firmware } = gpuCells(gpu);
                return (
                  <tr key={`${gpu.serial ?? gpu.model ?? "gpu"}-${index}`} data-testid="ss-gpu">
                    {cells.map((cell, i) => (
                      <td key={i} className={cn(CELL, "whitespace-nowrap")}>{cell}</td>
                    ))}
                    <td className={CELL}>
                      <ComponentHealthValue value={gpu.health} detail={gpu.health_detail} />
                    </td>
                    <td className={CELL}>{firmware}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>No GPUs.</Empty>
      )}
    </Reported>
  );
}

export function HardwareTab({ hardware, unreadFields }: { hardware: HardwareInfo; unreadFields: string[] }) {
  const unread = new Set(unreadFields);
  const { cpu, memory, storage, power } = hardware;
  const modules = memory.modules.length;
  return (
    <div className="space-y-8 rounded-xl border bg-card p-5" data-testid="ss-hardware">
      <section aria-label="CPU">
        <SectionTitle>CPU</SectionTitle>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <Stat label="Model" value={cpu.model} unread={unread.has("hardware.cpu.model")} />
          <Stat label="Sockets" value={cpu.sockets} unread={unread.has("hardware.cpu.sockets")} />
          <Stat label="Cores" value={cpu.cores} unread={unread.has("hardware.cpu.cores")} />
          <Stat label="Threads" value={cpu.threads} unread={unread.has("hardware.cpu.threads")} />
        </dl>
      </section>
      <section aria-label="Memory">
        <SectionTitle>Memory</SectionTitle>
        <Reported unread={unread.has("hardware.memory.total_bytes")} empty={memory.total_bytes <= 0}>
          <p className="mt-2 text-sm">
            {formatMemory(memory.total_bytes)} total ({modules} module{modules === 1 ? "" : "s"})
          </p>
        </Reported>
      </section>
      <section aria-label="Storage">
        <SectionTitle>Storage</SectionTitle>
        <Reported unread={unread.has("hardware.storage.total_bytes")} empty={storage.total_bytes <= 0}>
          <p className="mt-2 text-sm">{formatStorage(storage.total_bytes)} total</p>
        </Reported>
        <Drives hardware={hardware} unread={unread} />
      </section>
      <section aria-label="GPU">
        <SectionTitle>GPU</SectionTitle>
        <Gpus hardware={hardware} unread={unread} />
      </section>
      <section aria-label="Power">
        <SectionTitle>Power</SectionTitle>
        <Reported unread={unread.has("hardware.power.psus")} empty={power.psus.length === 0}>
          {power.psus.length > 0 ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {power.psus.map((psu, index) => (
                <li key={psu.id || `psu-${index}`} data-testid="ss-psu">
                  {psuLine(psu)} <ComponentHealthValue value={psu.health} detail={psu.health_detail} />
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No power supply data.</Empty>
          )}
        </Reported>
      </section>
    </div>
  );
}
