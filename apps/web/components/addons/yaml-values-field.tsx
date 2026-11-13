"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { parseValuesYaml, toYaml, type Values } from "@/lib/values";

/**
 * A values file edited as YAML, as the values editor's YAML view does: the
 * text is the file, checked as it is typed. Used where there is no merged
 * stack to show (Sig values, a fleet default, a new add-on): the file is
 * the whole story. `onChange` gets the values while the text parses, and
 * `null` while it does not, so the form can hold its submit.
 */
export function YamlValuesField({
  label,
  path,
  initial,
  onChange,
  placeholder = "# Empty: the chart's own values apply.\nreplicas: 2",
  disabled = false,
}: {
  label: string;
  /** The file the values are written to. */
  path: string;
  initial: Values;
  onChange: (values: Values | null) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [text, setText] = useState(() => toYaml(initial));
  const [error, setError] = useState("");

  function edit(next: string) {
    setText(next);
    const parsed = parseValuesYaml(next);
    if (parsed.ok) {
      setError("");
      onChange(parsed.values);
    } else {
      setError(parsed.error);
      onChange(null);
    }
  }

  return (
    <div className="space-y-1">
      <p className="text-xs">
        <span className="font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>{" "}
        <code className="break-all rounded bg-muted px-1 py-px font-mono text-[11px]">{path}</code>
      </p>
      <textarea
        aria-label={`Contents of ${path}`}
        className={cn(
          "min-h-28 w-full resize-y rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/50",
          error && "border-destructive/60",
        )}
        rows={Math.min(18, Math.max(5, text.split("\n").length + 1))}
        value={text}
        placeholder={placeholder}
        onChange={(e) => edit(e.target.value)}
        spellCheck={false}
        disabled={disabled}
      />
      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
