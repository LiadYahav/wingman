"use client";

import { Fragment, useState, type ReactNode } from "react";
import {
  UNKNOWN, adapterText, driveCount, formatGhz, formatKb, formatTb, gpuEntries, hasVram, ramTypeText, ramUnread, totalStorageTb,
} from "@/lib/server-scan/confs";
import { cn } from "@/lib/utils";
import type { Conf } from "@/types/server-scan-confs";
import { pill } from "./server-badges";

/**
 * The Confs page's table, as server-scan's `ConfsPage.tsx` (team-redbull/server-scan
 * at 92146d3, decision 18; docs/notes/2026-11-13-server-scan-area-api.md
 * §10.1): one row per conf, its columns and words, and a row opened into the
 * full spec under it. Several rows may be open.
 */

const COLUMNS = ["Conf", "Part number", "Model", "CPU", "RAM", "Storage", "GPU", "Adapters"] as const;

/** Text the writer recorded as `"unknown"` renders muted, so it reads as a value, not a gap. */
function Value({ text }: { text: string }) {
  if (text === UNKNOWN) return <span className="italic text-muted-foreground">unknown</span>;
  return <>{text}</>;
}

function Secondary({ children }: { children: ReactNode }) {
  return <div className="text-xs text-muted-foreground">{children}</div>;
}

function None() {
  return <span className="text-muted-foreground">—</span>;
}

function Unread({ children }: { children: ReactNode }) {
  return <span className="italic text-muted-foreground">{children}</span>;
}

function CountedList({ entries }: { entries: { count: number; model: string }[] }) {
  if (entries.length === 0) return <None />;
  return (
    <ul className="space-y-0.5">
      {entries.map((entry) => (
        <li key={entry.model}>
          {entry.count}× <Value text={entry.model} />
        </li>
      ))}
    </ul>
  );
}

function AdapterList({ adapters }: { adapters: Conf["adapters"] }) {
  if (adapters.length === 0) return <None />;
  return (
    <ul className="space-y-0.5">
      {adapters.map((adapter, index) => (
        <li key={String(index)}>{adapterText(adapter)}</li>
      ))}
    </ul>
  );
}

/** No part number: no catalog entry matches the conf. */
function Unmapped() {
  return (
    <span
      className={cn(pill, "bg-status-warning/15 text-status-warning-fg")}
      title="No catalog entry matches this conf, so it has no part number"
      data-testid="ss-conf-unmapped"
    >
      Unmapped
    </span>
  );
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title}>
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h3>
      <div className="mt-1 space-y-0.5 text-sm">{children}</div>
    </section>
  );
}

function MemoryDetail({ conf }: { conf: Conf }) {
  const { ram } = conf;
  if (ramUnread(conf)) return <Unread>not read (scan failed)</Unread>;
  return (
    <>
      <div>{ram.total_gib} GiB</div>
      <div>
        {ram.dimms} × {ram.per_dimm_gb} GB DIMMs
      </div>
      <div>Type: {ram.type.length > 0 ? ram.type.join(", ") : <Unread>not read (DIMM read failed)</Unread>}</div>
    </>
  );
}

function PartsDetail({ conf }: { conf: Conf }) {
  const gpus = gpuEntries(conf);
  return (
    <>
      {conf.disks.length === 0 && <div>No disks</div>}
      {conf.disks.map((disk, index) => (
        <div key={String(index)}>
          {disk.count}× {formatTb(disk.capacity_tb)} <Value text={disk.type} />
        </div>
      ))}
      {gpus.length > 0 && (
        <>
          <div className="pt-1">GPUs ({conf.gpu_count}):</div>
          <CountedList entries={gpus} />
          {hasVram(conf) && <div>{conf.gpu_vram_gb} GB VRAM per GPU</div>}
        </>
      )}
      <div className="pt-1">Adapters ({conf.adapter_count}):</div>
      <AdapterList adapters={conf.adapters} />
    </>
  );
}

/** Everything the table row abbreviates, laid out under it. */
function ConfDetail({ conf }: { conf: Conf }) {
  const { cpu } = conf;
  return (
    <div className="grid gap-6 bg-muted/40 px-4 py-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="ss-conf-detail">
      <DetailSection title="Identity">
        <div>
          Conf ID: <span className="font-mono">{conf.conf_id}</span>
        </div>
        <div>Part number: {conf.part_number ? <span className="font-mono">{conf.part_number}</span> : <None />}</div>
        <div>Model: {conf.model}</div>
      </DetailSection>
      <DetailSection title="CPU">
        <div>{cpu.model}</div>
        <div>Vendor: {cpu.vendor ?? <None />}</div>
        <div>
          {cpu.sockets} socket{cpu.sockets === 1 ? "" : "s"} × {cpu.cores_per_cpu} cores
        </div>
        <div>{cpu.total_cores_ht} threads (HT)</div>
        <div>
          {formatGhz(cpu.clock_mhz)} base, {formatGhz(cpu.max_clock_mhz)} max
        </div>
        <div>
          Cache: L1 {formatKb(cpu.cache_kb.l1)} · L2 {formatKb(cpu.cache_kb.l2)} · L3 {formatKb(cpu.cache_kb.l3)}
        </div>
      </DetailSection>
      <DetailSection title="Memory">
        <MemoryDetail conf={conf} />
      </DetailSection>
      <DetailSection title="Storage, GPU and adapters">
        <PartsDetail conf={conf} />
      </DetailSection>
    </div>
  );
}

function RowCells({ conf }: { conf: Conf }) {
  const { cpu, ram } = conf;
  return (
    <>
      <td className="px-3 py-2">{conf.part_number ? <span className="font-mono">{conf.part_number}</span> : <Unmapped />}</td>
      <td className="whitespace-nowrap px-3 py-2">{conf.model}</td>
      <td className="px-3 py-2">
        <div>
          {cpu.sockets}× {cpu.model}
        </div>
        <Secondary>
          {cpu.sockets * cpu.cores_per_cpu} cores · {cpu.total_cores_ht} threads · {formatGhz(cpu.clock_mhz)}
        </Secondary>
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        {ramUnread(conf) ? (
          <Unread>not read (scan failed)</Unread>
        ) : (
          <>
            <div>{ram.total_gib} GiB</div>
            <Secondary>
              {ram.dimms} × {ram.per_dimm_gb} GB {ramTypeText(conf)}
            </Secondary>
          </>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        {conf.disks.length === 0 ? (
          <None />
        ) : (
          <>
            <div>{formatTb(totalStorageTb(conf))}</div>
            <Secondary>{driveCount(conf)} drives</Secondary>
          </>
        )}
      </td>
      <td className="px-3 py-2">
        <CountedList entries={gpuEntries(conf)} />
        {hasVram(conf) && <Secondary>{conf.gpu_vram_gb} GB each</Secondary>}
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        <AdapterList adapters={conf.adapters} />
      </td>
    </>
  );
}

function ConfRow({ conf, open, onToggle }: { conf: Conf; open: boolean; onToggle: () => void }) {
  return (
    <Fragment>
      <tr onClick={onToggle} className="cursor-pointer align-top transition-colors hover:bg-muted/40" data-testid="ss-conf-row" data-conf={conf.conf_id}>
        <td className="whitespace-nowrap px-3 py-2">
          <button
            type="button"
            aria-expanded={open}
            aria-label={`${open ? "Hide" : "Show"} details of ${conf.conf_id}`}
            onClick={(event) => {
              event.stopPropagation();
              onToggle();
            }}
            className="mr-1.5 inline-block w-3 text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-primary/50"
          >
            {open ? "▾" : "▸"}
          </button>
          <span className="font-mono font-medium">{conf.conf_id}</span>
        </td>
        <RowCells conf={conf} />
      </tr>
      {open && (
        <tr>
          <td colSpan={COLUMNS.length} className="p-0">
            <ConfDetail conf={conf} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/** The confs the search keeps, in server-scan's order; `empty` in place of the rows when it keeps none. */
export function ConfsTable({ rows, empty }: { rows: Conf[]; empty: ReactNode }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  return (
    <div className="overflow-x-auto rounded-xl border bg-card">
      <table aria-label="Confs" className="w-full border-collapse text-left text-sm">
        <thead className="bg-muted/60 text-xs text-muted-foreground">
          <tr className="border-b">
            {COLUMNS.map((column) => (
              <th key={column} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {rows.map((conf, index) => (
            <ConfRow key={`${conf.conf_id}#${String(index)}`} conf={conf} open={open.has(conf.conf_id)} onToggle={() => toggle(conf.conf_id)} />
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={COLUMNS.length} className="px-3 py-6 text-center text-muted-foreground">
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
