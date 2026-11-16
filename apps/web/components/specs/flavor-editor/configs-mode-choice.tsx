"use client";

import { cn } from "@/lib/utils";
import type { ConfigsMode } from "./model";

/** The two ways a flavor sets machine configs and tuning profiles, as two cards to choose from. */
export function ConfigsModeChoice({ mode, onChange }: { mode: ConfigsMode; onChange: (mode: ConfigsMode) => void }) {
  const choices: { value: ConfigsMode; title: string; body: string }[] = [
    {
      value: "each",
      title: "Each nodepool its own",
      body: "Set machine configs and tuning profiles per nodepool, as presets or locked.",
    },
    {
      value: "rule",
      title: "The same on every nodepool",
      body: "One list of machine configs and, if you choose, tuning profiles for all nodepools, locked as a rule; each picks its own network hardware.",
    },
  ];
  return (
    <div role="radiogroup" aria-label="Machine configs and tuning profiles" className="grid gap-2 sm:grid-cols-2">
      {choices.map((choice) => {
        const selected = choice.value === mode;
        return (
          <button
            key={choice.value}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(choice.value)}
            onKeyDown={(e) => {
              if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
                e.preventDefault();
                onChange(mode === "each" ? "rule" : "each");
              }
            }}
            className={cn(
              "flex items-start gap-3 rounded-xl border p-3.5 text-left outline-none transition-[border-color,background-color,box-shadow] duration-150 focus-visible:ring-3 focus-visible:ring-ring/40",
              selected ? "border-primary/50 bg-primary/[0.06] shadow-sm" : "border-border hover:border-foreground/20 hover:bg-muted/40"
            )}
          >
            <span
              aria-hidden
              className={cn(
                "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors",
                selected ? "border-primary bg-primary" : "border-input"
              )}
            >
              {selected && <span className="h-1.5 w-1.5 rounded-full bg-primary-foreground" />}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium">{choice.title}</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">{choice.body}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
