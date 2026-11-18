"use client";

import { ArrowRight, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { mirrorEntryProblems, type MirrorEntry } from "@/lib/image-mirrors";
import { cn } from "@/lib/utils";

/**
 * The image mirrors of a flavor or a new cluster (ADR-0063), as the flavor
 * editor and the create form draw them: the entry list, the same list read
 * only, and the switch that keeps or drops the MCE's default mirrors.
 */

const EXAMPLE_SOURCE = "registry.example.com/team/operators";
const EXAMPLE_MIRROR = "mirror.example.com/team/operators";

/** The entries, editable: a source and its mirrors each; an empty one stays while it is typed. */
export function MirrorEntriesEditor({
  entries,
  onChange,
  inputClassName,
  label,
  invalid = false,
  describedBy,
  testId = "mirror-entries",
}: {
  entries: MirrorEntry[];
  onChange: (entries: MirrorEntry[]) => void;
  /** The text inputs' class, as the surrounding form draws its inputs. */
  inputClassName: string;
  /** What the list is, for screen readers: "Image mirrors". */
  label: string;
  invalid?: boolean;
  describedBy?: string;
  testId?: string;
}) {
  const problems = mirrorEntryProblems(entries);
  const sourceInvalid = (i: number) => problems.some((p) => p.entry === i && p.mirror === undefined && !p.message.startsWith("Give at least"));
  const mirrorInvalid = (i: number, j: number) => problems.some((p) => p.entry === i && p.mirror === j);
  const setEntry = (i: number, entry: MirrorEntry) => onChange(entries.map((e, k) => (k === i ? entry : e)));
  const input = cn(inputClassName, "font-mono text-xs");

  return (
    <div className="space-y-2" data-testid={testId} aria-describedby={describedBy}>
      {entries.length > 0 && (
        <ol className="space-y-2" aria-label={label}>
          {entries.map((entry, i) => (
            <li key={i} className="space-y-2 rounded-lg border bg-muted/20 p-3" data-testid={`${testId}-${i}`}>
              <p aria-hidden className="text-[11px] font-medium text-muted-foreground">Source, and the mirrors it is pulled from</p>
              <div className="flex items-center gap-1.5">
                <input
                  className={cn(input, "flex-1")}
                  aria-label={`${label} ${i + 1}: source`}
                  aria-invalid={sourceInvalid(i) || (invalid && !entry.source)}
                  placeholder={EXAMPLE_SOURCE}
                  autoComplete="off"
                  spellCheck={false}
                  value={entry.source}
                  onChange={(e) => setEntry(i, { ...entry, source: e.target.value.trim() })}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Remove ${entry.source || `entry ${i + 1}`}`}
                  onClick={() => onChange(entries.filter((_, k) => k !== i))}
                >
                  <X />
                </Button>
              </div>
              <ul className="space-y-1.5 border-l-2 border-border/70 pl-3" aria-label={`${label} ${i + 1}: mirrors`}>
                {entry.mirrors.map((mirror, j) => (
                  <li key={j} className="flex items-center gap-1.5">
                    <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                    <input
                      className={cn(input, "flex-1")}
                      aria-label={`${label} ${i + 1}: mirror ${j + 1}`}
                      aria-invalid={mirrorInvalid(i, j)}
                      placeholder={EXAMPLE_MIRROR}
                      autoComplete="off"
                      spellCheck={false}
                      value={mirror}
                      onChange={(e) => setEntry(i, { ...entry, mirrors: entry.mirrors.map((m, k) => (k === j ? e.target.value.trim() : m)) })}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Remove mirror ${j + 1} of ${entry.source || `entry ${i + 1}`}`}
                      onClick={() => setEntry(i, { ...entry, mirrors: entry.mirrors.filter((_, k) => k !== j) })}
                    >
                      <X />
                    </Button>
                  </li>
                ))}
                <li>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="-ml-2 text-muted-foreground"
                    onClick={() => setEntry(i, { ...entry, mirrors: [...entry.mirrors, ""] })}
                  >
                    <Plus /> Add mirror
                  </Button>
                </li>
              </ul>
            </li>
          ))}
        </ol>
      )}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        data-testid={`${testId}-add`}
        onClick={() => onChange([...entries, { source: "", mirrors: [""] }])}
      >
        <Plus /> Add image mirror
      </Button>
    </div>
  );
}

/** The entries, read only: `source → mirrors`, one per line. */
export function MirrorEntryList({ entries, empty = "None of its own", testId }: { entries: MirrorEntry[]; empty?: string; testId?: string }) {
  if (entries.length === 0) return <p className="text-xs text-muted-foreground" data-testid={testId}>{empty}</p>;
  return (
    <ul className="space-y-1" data-testid={testId}>
      {entries.map((entry, i) => (
        <li key={i} className="flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-1 text-xs">
          <span className="font-mono break-all">{entry.source || "—"}</span>
          <ArrowRight className="h-3 w-3 shrink-0 self-center text-muted-foreground" aria-label="mirrored to" />
          {entry.mirrors.map((mirror, j) => (
            <span key={j} className="rounded-md border bg-muted/40 px-1.5 py-0.5 font-mono break-all">
              {mirror}
            </span>
          ))}
        </li>
      ))}
    </ul>
  );
}

/**
 * "Keep the MCE's default mirrors": on, the template writes nothing and the
 * chart merges the MCE's mirrors with the cluster's own; off, the file gets
 * `disableIdmsMerge: true` and only the cluster's own mirrors are used.
 */
export function KeepMceMirrorsSwitch({
  keep,
  onChange,
  disabled = false,
  testId = "keep-mce-mirrors",
}: {
  keep: boolean;
  onChange: (keep: boolean) => void;
  disabled?: boolean;
  testId?: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <Switch
        checked={keep}
        disabled={disabled}
        onCheckedChange={(checked) => onChange(checked)}
        aria-label="Keep the MCE's default mirrors"
        className="mt-0.5"
        data-testid={testId}
      />
      <div className="min-w-0 text-xs">
        <p className="font-medium text-foreground/90">Keep the MCE&apos;s default mirrors</p>
        <p className="text-muted-foreground">
          {keep ? (
            <>On: the MCE&apos;s mirrors are merged with the cluster&apos;s own; nothing is written.</>
          ) : (
            <>
              Off: only the cluster&apos;s own mirrors; the file gets <code className="font-mono">disableIdmsMerge: true</code>.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
