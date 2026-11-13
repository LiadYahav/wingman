"use client";

import { Download, Search, X } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import type { FacetCounts } from "@/lib/server-scan/rows";
import {
  FLAG_KEYS,
  setFlag,
  setValues,
  toggleValue,
  withChange,
  type FilterChip,
  type FlagKey,
  type ServersView,
} from "@/lib/server-scan/servers-view";
import { HEALTH_SEVERITIES, INSTALLATION_TYPES, OPENSHIFT_STATES, SOURCE_PROVIDERS, VENDORS } from "@/lib/server-scan/vocabulary";
import { cn } from "@/lib/utils";
import { MultiSelect } from "./multi-select";

/**
 * The Servers page's filters, as server-scan's page has them
 * (team-redbull/server-scan at 92146d3, `InventoryPage.tsx`, decision 18):
 * the search, six dropdowns with their counts, five toggles, the "Filtered
 * by:" chips, and the exports. Each control changes the URL's view.
 */

const SEARCH_HELP =
  'Plain text matches anywhere. "10.0.0.1" in quotes must equal the whole value. /10\\.0\\.0\\.(1|13)$/ between slashes is a regular expression.';

/** server-scan's search box: name, serial, BMC… with its three syntaxes in the tooltip, and a bad regex under it. */
export function ServerSearch({
  value,
  error,
  onChange,
  onCommit,
}: {
  value: string;
  error: string | null;
  onChange: (q: string) => void;
  onCommit: () => void;
}) {
  return (
    <div className="flex w-full flex-col gap-1 text-xs font-medium text-muted-foreground sm:w-96">
      <span>Search</span>
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2" />
        <input
          type="search"
          aria-label="Search servers"
          placeholder="Name, serial, BMC…"
          title={SEARCH_HELP}
          value={value}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error !== null}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onCommit();
            if (e.key === "Escape" && value) onChange("");
          }}
          className="h-8 w-full rounded-lg border bg-card pl-8 pr-2 text-sm font-normal text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 aria-invalid:border-destructive [&::-webkit-search-cancel-button]:hidden"
        />
      </div>
      {error && (
        <span role="alert" data-testid="ss-search-error" className="font-normal text-destructive">
          {error}
        </span>
      )}
    </div>
  );
}

/** The Health dropdown's last entry: Maintenance, which keeps only servers in maintenance. */
const MAINTENANCE_OPTION = "MAINTENANCE";

/** The six dropdowns, each option counted over what every other filter keeps. */
export function ServerDropdowns({
  view,
  setView,
  facets,
  sites,
}: {
  view: ServersView;
  setView: (next: ServersView) => void;
  facets: FacetCounts;
  /** The Site options: server-scan's sites in its order, with their names. */
  sites: { value: string; label: string }[];
}) {
  const all = (word = "All") => `${word} (${facets.total.toLocaleString()})`;
  const count = (counts: Record<string, number>, value: string) => counts[value] ?? 0;
  const multi = (key: "vendor" | "source_provider" | "site_id" | "installation_type" | "openshift_state") => ({
    selected: view.multi[key],
    onToggle: (value: string) => setView(toggleValue(view, key, value)),
    onClear: () => setView(setValues(view, key, [])),
  });
  const only = view.maintenance === "only";
  return (
    <>
      <MultiSelect
        label="Vendor"
        allLabel={all()}
        options={VENDORS.map((v) => ({ value: v, label: v, count: count(facets.vendor, v) }))}
        {...multi("vendor")}
      />
      <MultiSelect
        label="Source"
        allLabel={all()}
        options={SOURCE_PROVIDERS.map((s) => ({ ...s, count: count(facets.source_provider, s.value) }))}
        {...multi("source_provider")}
      />
      <MultiSelect
        label="Site"
        allLabel={all("All sites")}
        options={sites.map((s) => ({ ...s, count: count(facets.site_id, s.value) }))}
        {...multi("site_id")}
      />
      <MultiSelect
        label="Classification"
        allLabel={all()}
        options={INSTALLATION_TYPES.map((t) => ({ value: t, label: t, count: count(facets.installation_type, t) }))}
        {...multi("installation_type")}
      />
      <MultiSelect
        label="Installation"
        allLabel={all()}
        options={OPENSHIFT_STATES.map((s) => ({ ...s, count: count(facets.openshift_state, s.value) }))}
        {...multi("openshift_state")}
      />
      <MultiSelect
        label="Health"
        allLabel={all()}
        selected={only ? [...view.multi.health_overall, MAINTENANCE_OPTION] : view.multi.health_overall}
        options={[
          ...HEALTH_SEVERITIES.map((h) => ({ value: h, label: h, count: count(facets.health, h) })),
          { value: MAINTENANCE_OPTION, label: "Maintenance", count: count(facets.maintenance, "true") },
        ]}
        onToggle={(value) =>
          setView(value === MAINTENANCE_OPTION ? withChange(view, { maintenance: only ? "include" : "only" }) : toggleValue(view, "health_overall", value))
        }
        onClear={() => setView(withChange(view, { multi: { ...view.multi, health_overall: [] }, maintenance: "include" }))}
      />
    </>
  );
}

/** server-scan's toggles, their words and tooltips. */
const TOGGLES: Record<FlagKey, { label: string; title: string }> = {
  stale: { label: "Stale", title: "Not collected within server-scan's staleness window, or never" },
  duplicate: {
    label: "Duplicate Name",
    title: "Shares its name with another server: a real platform bug (one machine, two documents) or two different machines with the same profile name",
  },
  contested: { label: "Duplicate Server", title: "Claimed by two OpenShift clusters at once: one physical server in two memberships" },
  name_mismatch: { label: "Name mismatch", title: "Installed in OpenShift under a hostname the vendor manager no longer reports: a rename after install" },
  donor: { label: "Donor", title: "In maintenance with “donor” in the reason: kept only for its parts" },
};

/** The five toggles; one that is on shows how many servers it keeps. */
export function ServerToggles({ view, setView, total }: { view: ServersView; setView: (next: ServersView) => void; total: number }) {
  return (
    <div role="group" aria-label="Toggles" className="flex flex-wrap items-center gap-x-5 gap-y-2">
      {FLAG_KEYS.map((key) => (
        <label key={key} title={TOGGLES[key].title} className="flex cursor-pointer items-center gap-2 text-xs font-medium text-muted-foreground">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 accent-primary"
            checked={view.flags[key]}
            onChange={(e) => setView(setFlag(view, key, e.target.checked))}
          />
          {TOGGLES[key].label}
          {view.flags[key] && <span className="tabular-nums">({total.toLocaleString()})</span>}
        </label>
      ))}
    </div>
  );
}

/** "Filtered by:" and a chip per active filter that removes it, then Clear filters. */
export function ActiveFilters({
  chips,
  view,
  setView,
  onClear,
}: {
  chips: FilterChip[];
  view: ServersView;
  setView: (next: ServersView) => void;
  onClear: () => void;
}) {
  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground" data-testid="ss-active-filters">
      <span>Filtered by:</span>
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          title="Remove this filter"
          onClick={() => setView(chip.remove(view))}
          className="inline-flex items-center gap-1 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-0.5 font-medium text-primary transition-colors hover:bg-primary/20"
        >
          {chip.label}
          <X aria-hidden className="h-3 w-3" />
        </button>
      ))}
      <button type="button" onClick={onClear} className="font-medium text-primary hover:underline">
        Clear filters
      </button>
    </div>
  );
}

/** The exports of every server the filters keep (not only the page): server-scan's Excel file, and the same as CSV. */
export function ServerExports({ shown, exporting, onCsv, onExcel }: { shown: number; exporting: boolean; onCsv: () => void; onExcel: () => void }) {
  const what = `the ${shown.toLocaleString()} server${shown === 1 ? "" : "s"} the filters keep, every page`;
  const joined = (side: "left" | "right") =>
    cn(buttonVariants({ variant: "outline", size: "sm" }), side === "left" ? "gap-1.5 rounded-r-none" : "-ml-px rounded-l-none");
  return (
    <div role="group" aria-label={`Download ${what}`} className="inline-flex">
      <button type="button" onClick={onExcel} disabled={shown === 0 || exporting} title={`Download ${what}, as an Excel file (.xlsx)`} className={joined("left")}>
        <Download aria-hidden className="h-3.5 w-3.5" />
        Export Excel
      </button>
      <button type="button" onClick={onCsv} disabled={shown === 0} title={`Download ${what}, as CSV`} className={joined("right")}>
        CSV
      </button>
    </div>
  );
}
