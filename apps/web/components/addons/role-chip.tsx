"use client";

import { roleStyle } from "@/lib/day2";
import { cn } from "@/lib/utils";

/** Which layer set a value, as a small chip; `path` (the layer's file) goes in its title. */
export function RoleChip({ role, path, className }: { role?: string; path?: string; className?: string }) {
  const style = roleStyle(role);
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center rounded-md border px-1.5 py-px text-[10px] font-medium leading-4 whitespace-nowrap",
        style.chip,
        !role && "border-dashed",
        className,
      )}
      title={path ? `${style.description}\n${path}` : style.description}
    >
      <span className="truncate">{style.label}</span>
    </span>
  );
}
