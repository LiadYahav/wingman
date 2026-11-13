import { ChevronDown, ChevronsUpDown, ChevronUp } from "lucide-react";
import type { SortDir, SortField } from "./model";

/** A sortable column's mark: muted while another column sorts, else the direction. */
export function SortIcon({ field, sortField, sortDir }: { field: SortField; sortField: SortField; sortDir: SortDir }) {
  if (sortField !== field) return <ChevronsUpDown className="h-3 w-3 text-muted-foreground/50" />;
  return sortDir === "asc"
    ? <ChevronUp className="h-3 w-3 text-primary" />
    : <ChevronDown className="h-3 w-3 text-primary" />;
}
