/**
 * What herzi marked on a pool's InfraEnv (ADR-0057's 3.55.0 amendment; herzi's
 * `main`): ignored, paused, an order in flight, no hardware found. day1 reads
 * the marks with the InfraEnv list it already has; this is their words.
 */

import type { HerziMarks } from "@/types/inventory";

export interface HerziNote {
  /** The badge: the first mark that applies. */
  label: string;
  /** Every mark that applies, one sentence each. */
  hint: string;
}

const when = (iso: string) => new Date(iso).toLocaleString();

/** The pool's herzi badge and its tooltip, or `null` when herzi marked nothing (or only a past deadline). */
export function herziNote(marks: HerziMarks, now: Date = new Date()): HerziNote | null {
  const notes: [string, string][] = [];
  if (marks.ignored) {
    notes.push(["herzi ignores", "The InfraEnv carries herzi.redbull.io/ignore: herzi does not read this pool and orders nothing for it."]);
  }
  if (marks.paused) {
    notes.push([
      "herzi paused",
      'herzi.redbull.io/paused is "true": herzi watches this pool but orders nothing for it, and removes none of its used Agents, until the annotation is removed.',
    ]);
  }
  if (marks.blocked_until && new Date(marks.blocked_until) > now) {
    notes.push([
      "herzi ordering",
      `herzi sent an order for this pool and orders nothing more here until ${when(marks.blocked_until)} (herzi.redbull.io/blocked-until); the runs are under Runs.`,
    ]);
  }
  if (marks.no_hardware_since) {
    notes.push([
      "no hardware",
      `herzi's last order here found no hardware, at ${when(marks.no_hardware_since)}: it tries one server at a time until one arrives.`,
    ]);
  }
  if (notes.length === 0) return null;
  return { label: notes[0][0], hint: notes.map(([, sentence]) => sentence).join(" ") };
}
