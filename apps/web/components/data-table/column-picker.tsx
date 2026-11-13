"use client";

import { Columns3 } from "lucide-react";
import type { Table } from "@tanstack/react-table";
import { buttonVariants } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { CheckItem } from "./check-item";

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
            <CheckItem key={column.id} checked={visible} disabled={visible && shown === 1} onToggle={() => column.toggleVisibility(!visible)}>
              {column.columnDef.meta?.label ?? column.id}
            </CheckItem>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}
