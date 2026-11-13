import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** `1 cluster`, `3 clusters`: a count with its noun, `many` for an irregular plural. */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}

/** A date as every page shows it, whatever the browser's locale: en-GB, "07/11/2026". */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB")
}

/** A date and time as every page shows them: en-GB, "07/11/2026, 10:00:00". */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB")
}
