import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** A date as every page shows it, whatever the browser's locale: en-GB, "07/11/2026". */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB")
}

/** A date and time as every page shows them: en-GB, "07/11/2026, 10:00:00". */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB")
}
