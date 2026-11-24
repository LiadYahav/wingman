"use client";

import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** The names shown one by one; past them, how many more (the picker lists them all). */
const MAX_SHOWN = 8;

function Token({ name, onRemove, absent = false }: { name: string; onRemove: () => void; absent?: boolean }) {
  return (
    <span
      data-testid="picked-infra-env"
      data-infra-env={name}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full border py-px pl-2 pr-0.5 font-mono text-[11px]",
        absent ? "border-dashed text-muted-foreground" : "bg-muted/50 text-foreground"
      )}
    >
      {name}
      <button
        type="button"
        aria-label={`Unpick ${name}`}
        onClick={onRemove}
        className="rounded-full p-1 text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <X aria-hidden className="h-3 w-3" />
      </button>
    </span>
  );
}

function Tokens({ names, onRemove, absent }: { names: string[]; onRemove: (name: string) => void; absent?: boolean }) {
  return (
    <>
      {names.slice(0, MAX_SHOWN).map((name) => (
        <Token key={name} name={name} absent={absent} onRemove={() => onRemove(name)} />
      ))}
      {names.length > MAX_SHOWN && <span className="text-muted-foreground">+{names.length - MAX_SHOWN} more</span>}
    </>
  );
}

/**
 * The InfraEnvs picked, each removable; those this MCE lacks quietly apart,
 * still picked for the MCEs that have them (a pool's name carries no hub).
 */
export function PickedInfraEnvs({
  mce,
  present,
  missing,
  onChange,
}: {
  mce: string;
  present: string[];
  missing: string[];
  onChange: (next: string[]) => void;
}) {
  if (present.length + missing.length === 0) return null;
  const all = [...present, ...missing];
  const remove = (name: string) => onChange(all.filter((n) => n !== name));
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs" data-testid="picked-infra-envs">
      {present.length > 0 && (
        <>
          <span className="text-muted-foreground">Picked:</span>
          <Tokens names={present} onRemove={remove} />
        </>
      )}
      {missing.length > 0 && (
        <span className="inline-flex flex-wrap items-center gap-1.5 text-muted-foreground" data-testid="infra-env-missing">
          <span>
            Not on <span className="font-mono">{mce}</span>, kept for the other MCEs:
          </span>
          <Tokens names={missing} onRemove={remove} absent />
        </span>
      )}
      <button
        type="button"
        onClick={() => onChange([])}
        className="rounded px-1 text-muted-foreground underline decoration-dotted underline-offset-4 outline-none hover:text-foreground hover:decoration-solid focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        Unpick all
      </button>
    </div>
  );
}
