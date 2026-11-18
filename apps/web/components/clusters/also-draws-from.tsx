"use client";

import { useState, type ReactNode } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { addable, MAX_ADDITIONAL, nameProblem } from "@/lib/infra-envs";
import { cn } from "@/lib/utils";

const inputCls =
  "h-8 w-56 rounded-md border border-input bg-background px-2.5 font-mono text-xs placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50";

/** Typing a name, when the MCE's InfraEnvs are not listed (live status off, or the flavor editor). */
function TypedName({ own, value, onAdd, label, testId }: { own?: string; value: string[]; onAdd: (name: string) => void; label: string; testId: string }) {
  const [text, setText] = useState("");
  const name = text.trim();
  const problem = name ? nameProblem(name, own, value) : null;
  const add = () => {
    if (!name || problem) return;
    onAdd(name);
    setText("");
  };
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5">
        <input
          className={inputCls}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder="Type an InfraEnv…"
          aria-label={`${label}: add an InfraEnv`}
          aria-invalid={Boolean(problem)}
          spellCheck={false}
          autoComplete="off"
          data-testid={`${testId}-type`}
        />
        <Button type="button" variant="outline" size="sm" onClick={add} disabled={!name || Boolean(problem)}>
          <Plus /> Add
        </Button>
      </div>
      {problem && <p className="text-xs text-destructive">{problem}</p>}
    </div>
  );
}

/**
 * The InfraEnvs a nodepool draws Agents from beside its own (ADR-0064), as
 * removable chips and one control that adds another: the MCE's InfraEnvs when
 * they are listed, else a typed name. The nodepool's own InfraEnv stays where
 * it is chosen and names the NodePool; `note` says so where it helps.
 */
export function AlsoDrawsFrom({
  value,
  onChange,
  own,
  options,
  loading = false,
  readOnly = false,
  label,
  note,
  testId,
}: {
  value: string[];
  onChange: (names: string[]) => void;
  /** The nodepool's own InfraEnv: never offered here. */
  own?: string;
  /** The MCE's InfraEnvs; `undefined` when they are not listed (then the name is typed). */
  options?: string[];
  loading?: boolean;
  readOnly?: boolean;
  label: string;
  note?: ReactNode;
  testId: string;
}) {
  const rest = options ? addable(options, own, value) : [];
  const full = value.length >= MAX_ADDITIONAL;
  return (
    <div className="space-y-2" data-testid={testId}>
      {value.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label={label}>
          {value.map((name) => (
            <li
              key={name}
              className="inline-flex max-w-full items-center gap-0.5 rounded-md border bg-muted/40 py-0.5 pl-2 pr-0.5 font-mono text-xs"
              data-testid={`${testId}-${name}`}
            >
              <span className="break-all">{name}</span>
              {!readOnly && (
                <button
                  type="button"
                  onClick={() => onChange(value.filter((n) => n !== name))}
                  aria-label={`Stop drawing from ${name}`}
                  className="rounded p-1 text-muted-foreground outline-none transition-colors duration-100 hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
                >
                  <X className="h-3 w-3" aria-hidden />
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">Only its own InfraEnv.</p>
      )}
      {!readOnly && !full && (options || loading ? (
        <Combobox
          className="w-64"
          size="sm"
          options={rest.map((name) => ({ value: name, label: name }))}
          value={null}
          onValueChange={(name) => name && onChange([...value, name])}
          disabled={loading || rest.length === 0}
          placeholder={loading ? "Loading InfraEnvs…" : rest.length === 0 ? "No other InfraEnv on this MCE" : "Add an InfraEnv…"}
          searchPlaceholder="Search InfraEnvs…"
          emptyMessage="No InfraEnv matches."
          aria-label={`${label}: add an InfraEnv`}
          data-testid={`${testId}-add`}
        />
      ) : (
        <TypedName own={own} value={value} onAdd={(name) => onChange([...value, name])} label={label} testId={testId} />
      ))}
      {note && <p className={cn("text-xs text-muted-foreground", readOnly && "flex items-center gap-1")}>{note}</p>}
    </div>
  );
}
