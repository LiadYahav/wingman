import type { FieldValue } from "@/components/clusters/dynamic-variable-form";

/** A nodepool's replicas under the flavor's ratio (ADR-0040): its part times the size, read-only. */
export function SizedReplicas({ index, value, part, size }: { index: number; value: FieldValue; part: number; size: number | null }) {
  return (
    <p data-testid={`nodepool-${index}-replicas-sized`} className="text-sm">
      <span className="font-mono font-medium">{size !== null ? String(value) : "—"}</span>
      <span className="ml-2 text-xs text-muted-foreground">ratio {part} × size {size ?? "?"}</span>
    </p>
  );
}
