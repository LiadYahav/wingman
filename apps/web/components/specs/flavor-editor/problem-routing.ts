/**
 * Day1's problems at their fields. Every problem day1 refuses a flavor with
 * starts with its path (docs/notes/2026-11-08-flavors-v2-api-changes.md §1),
 * so the editor shows each one at the field it is about.
 */

/** A problem's subject (`owner_anaf`, `nodepools[1].configs[0]`) and the rest of it. */
export function problemSubject(problem: string): { path: string; message: string } | null {
  const lock = /^locked_paths: '?([^\s']+)'?\s(.*)$/.exec(problem);
  if (lock) return { path: lock[1], message: `${lock[1]} ${lock[2]}` };
  const at = problem.indexOf(": ");
  if (at <= 0) return null;
  const head = problem.slice(0, at);
  if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]+\])*$/.test(head)) return null;
  return { path: head, message: problem.slice(at + 2) };
}

export interface RoutedProblem {
  /** The field it is shown at. */
  field: string;
  /** The problem's own path: the field's, or one inside it (`nodepools[0].configs[2]`). */
  path: string;
  message: string;
  /** The problem as day1 wrote it. */
  raw: string;
}

/**
 * Attach each problem to the deepest field whose path is the problem's or
 * contains it; the rest have no field and are listed at the top.
 */
export function routeProblems(problems: string[], fields: string[]): { routed: RoutedProblem[]; unmatched: string[] } {
  const routed: RoutedProblem[] = [];
  const unmatched: string[] = [];
  for (const raw of problems) {
    const subject = problemSubject(raw);
    const field = subject
      ? fields
          .filter((f) => subject.path === f || subject.path.startsWith(`${f}.`) || subject.path.startsWith(`${f}[`))
          .sort((a, b) => b.length - a.length)[0]
      : undefined;
    if (subject && field) routed.push({ field, path: subject.path, message: subject.message, raw });
    else unmatched.push(raw);
  }
  return { routed, unmatched };
}
