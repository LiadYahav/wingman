"use client";

import { Check, Columns3 } from "lucide-react";
import type { Table } from "@tanstack/react-table";
import { buttonVariants } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/** Show or hide a table's columns; the last shown one stays, so the table never empties. */
export function ColumnPicker<T>({ table }: { table: Table<T> }) {
  const columns = table.getAllLeafColumns().filter((column) => column.getCanHide());
  const shown = columns.filter((column) => column.getIsVisible()).length;
  return (
    <Popover>
      <PopoverTrigger
        aria-label="Show or hide columns"
        title="Columns"
        className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
      >
        <Columns3 className="h-3.5 w-3.5" aria-hidden />
        Columns
      </PopoverTrigger>
      <PopoverContent align="end" className="w-52 gap-0.5 p-1.5" aria-label="Columns">
        {columns.map((column) => {
          const visible = column.getIsVisible();
          return (
            <button
              key={column.id}
              type="button"
              role="checkbox"
              aria-checked={visible}
              disabled={visible && shown === 1}
              onClick={() => column.toggleVisibility(!visible)}
              className="flex items-center gap-2 rounded-md px-2 py-1 text-left text-sm outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span
                aria-hidden
                className={cn(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                  visible ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"
                )}
              >
                {visible && <Check className="h-3 w-3" strokeWidth={3} />}
              </span>
              {column.columnDef.meta?.label ?? column.id}
            </button>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}
