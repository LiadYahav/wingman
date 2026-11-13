# ADR-0056: Files and functions stay small

Date: 2026-11-13
Status: Accepted

## Context

A code-organisation audit of main (2026-11-13) counted 341 source files and
72,142 lines (Python and TS/TSX under `apps/`, `packages/` and `scripts/`,
tests left out). 50 files were over 400 lines and 5 over 1,000. The two
languages had different problems:

- **Python: a few modules are too big, but their functions are small.** Two
  schema modules (day1 2,070 lines, day2 1,433), three application services
  and a few adapters hold the weight; ruff's `C901` at complexity 12 flags 8
  of 1,868 functions.
- **Web: whole features are written as one component.** 9 of the 21 files
  over 400 code lines were route `page.tsx` files. `NewClusterPage` was one
  function of 1,193 code lines with complexity 202; 17 functions had over
  200 code lines and 18 a complexity over 30.

Nothing stopped a file or a function from growing, and every feature PR
added to the same few files (three branches in flight edited the docs page
at once). server-scan and herzi enforce no file length; herzi gates
cyclomatic complexity (gocyclo, 30) and server-scan keeps a baseline that
may only shrink for comment density. Wingman's npm audit allowlist
(ADR-0032) already works that way.

## Decision

### The limits, and baselines that only shrink

| Guard | Limit | Where | Exemptions today |
|---|---|---|---|
| File size, Python and TS/TSX | **500** physical lines (`wc -l`); **800** for tests (a path through a `tests/` or `e2e/` folder) | `scripts/check-file-size.py`, in `scripts/gate.sh python` and CI's Python job; it checks both languages | 42 files in `scripts/file-size-baseline.txt` (21 Python, 19 TS/TSX, 1 test; day2's schemas.py was split first, 3.14.1) |
| Python complexity | ruff `C901`, max-complexity **12** | `ruff check` | 8 functions, `# noqa: C901 - baseline: <why>` |
| Python statements | ruff `PLR0915`, ruff's default **50** | `ruff check` | 3 functions (two in `scripts/dev/day1_live_e2e.py`, one test) |
| Web function length | ESLint `max-lines-per-function` **200**, blank lines and comments not counted | `npm run lint` | 17 functions |
| Web complexity | ESLint `complexity` **30** | `npm run lint` | 18 functions (25 functions in all carry an exemption) |

- **The baseline only shrinks.** A listed file has a ceiling, its line count
  when it was listed. It may shrink and never grow past it; a ceiling is
  never raised and no file is added. An entry whose file is back within the
  limit, or gone, fails the check, so the change that splits a file removes
  its line. When a listed file shrinks, lower its ceiling (the check prints a
  note). `--list` prints the offenders as baseline lines.
- **Exemptions only shrink too.** Each existing offender is exempted on the
  function itself: `# noqa: C901 - baseline: <why>`, or
  `// eslint-disable-next-line <rule> -- size baseline (ADR-0056)` on the line
  above it. ruff's `RUF100` and ESLint's
  `reportUnusedDisableDirectives: "error"` fail an exemption that no longer
  suppresses anything, so splitting a function forces its comment out.
  **Never add an exemption or a baseline entry: split the code.** A case
  that truly cannot be split amends this ADR first.
- **Not checked**: shadcn's generated `apps/web/components/ui/`, the vendored
  `apps/day2-service/tests/oracle/render_chain.py`, `*.d.ts`, and
  `dev/gitlab-fixtures/`. The ESLint function rules skip `e2e/` (a
  `describe` block is long by nature; the file limit covers tests).

### Where code goes

New code follows these; existing code moves to them one refactor PR at a
time.

**Python (all three packages)**
1. `api/v1/<resource>.py` is one router per URL resource; its request and
   response models are in `api/v1/<resource>_schemas.py`. `api/v1/schemas.py`
   keeps only the models two or more routers use. A router past ~15 routes
   splits by sub-resource (`cluster_nodes.py`, `cluster_sync.py`).
2. `application/<area>.py` holds one area's use cases. Past ~15 public methods
   or 500 lines, split by use case: separate services, or a package
   `application/<area>/` with a module per use case and shared module
   functions. Don't grow a base class.
3. `infrastructure/<system>/` is a sub-package once a system has more than one
   module: `adapter.py` (the real one), `parse.py` (wire to domain),
   `cached.py` (the cache decorator). Fakes go in `infrastructure/fakes/`.
4. The composition root is `main.py`, plus at most a `composition/` package.
   Nothing else wires adapters.
5. API dependencies go in `api/deps.py` and errors in `api/errors.py`, the
   same place in every service.

**Web (`apps/web`)**
1. `app/**/page.tsx` and `layout.tsx` are route entries only: read params
   and search params, guard roles, render one feature component (aim for
   ≤ 150 lines). No `useQuery`, `useMutation` or `api.*` in a route file,
   and no file in `app/` other than Next's file conventions.
2. API paths and query keys are named in one module per service:
   `lib/day2.ts` (`day2Api`, `day2Keys`) and `lib/api/day1/` (`day1Api`,
   `day1Keys`, one file per area; since 3.18.5). The review and audit routes
   of both services are in the day1 module, since their keys share one
   namespace.
   Query and mutation hooks sit beside it or in the feature folder;
   components never call `api.get` themselves.
3. `components/<area>/` holds the UI. A flow over ~300 lines gets a folder,
   `components/<area>/<flow>/`, like `specs/flavor-editor/` and
   `specs/import-clusters/`: a file per section, step, tab or dialog,
   `use-<flow>.ts` for its state, `model.ts` for its pure logic.
4. A `.tsx` file exports components and their props types only. A helper
   another file imports goes in a `.ts` file: the flow's `model.ts`, or
   `lib/<topic>.ts` when two areas use it.
5. Types are mirrored in `types/<service>/<area>.ts` and imported from
   `@/types` only.

### The numbers

- **500 / 800 lines.** At 500, 85% of the files are already under 400;
  herzi's largest is 501. Docstrings are 10-15% of Wingman's Python, so 500
  physical lines are about 400 of code. Physical lines are what `wc -l` and
  every editor show. Tests read top to bottom and repeat their setup, so
  they get 800 (one test file is over it).
- **C901 at 12.** At 15 it flags one function and guards nothing; at 10 it
  flags 16. 12 holds the line where the code already is.
- **PLR0915 at 50.** The audit measured 0 offenders in `src`; the rule runs on
  everything ruff checks, so the dev script and one end-to-end test are
  exempted. PLR0913 (77 hits, keyword-only constructors) and PLR0911/0912
  (they overlap C901) are not selected.
- **200 lines, complexity 30 per web function.** A component over 200 code
  lines always holds a section, tab or dialog that could be its own file; 150
  would flag 33. JSX's `&&`, `?:` and `??` count as branches, so 20 is
  ordinary in TSX and 30 is where the tangles start (herzi's gocyclo default
  too).
- **Changed from the audit's proposal**: ESLint offenders are exempted per
  function, not by one comment at the top of each file, so an exemption
  excuses only the function it names and not the next one added to the file.

## Alternatives rejected

- **No file-length guard** (server-scan, herzi). The problem is at the top:
  the biggest files are the ones every feature edits, and they kept growing.
- **400 or 600 lines.** 400 would list 50 files; 600 would let the type
  mirrors and nine pages stay as they are.
- **Code lines instead of physical lines.** Another number to explain, and a
  docstring-heavy module would pass at 700 lines on screen.
- **A ruff or ESLint rule for file length.** ruff has none (pylint's C0302 is
  not implemented); ESLint's `max-lines` would cover only TypeScript, and the
  baseline would be per-file disables. One stdlib script covers both.
- **Split everything first, then guard.** The splits take many PRs; the
  guard lands first so nothing grows meanwhile.
- **`react-refresh/only-export-components`** (server-scan's rule) now. It needs
  a new dev dependency (ADR-0003) and flags 20 files today; it lands after
  the helpers move out of `.tsx` files, with no offender left.

## Consequences

- A change that grows a listed file past its ceiling fails: it moves code
  out first. A branch begun before this ADR that adds to a listed file has to
  do the same when it rebases.
- Every split PR deletes its baseline lines and exemptions, so the ratchet
  shows in the diff.
- The web ceilings include each file's one-line exemption comment.
- CI only: the services and the web behave as before; the code gains only
  comments.

## Verification

- `tests/repo/test_ci_scripts.py::TestFileSize`: the limits per kind, what is
  not checked, the line count, a new file over the limit, a listed file that
  grows, shrinks or is back within the limit, a stale entry, the baseline's
  format, and that every committed entry is over its limit.
- 2026-11-13: `python3 scripts/check-file-size.py` passes with 41 entries;
  `scripts/gate.sh ci`, `python` and `web` pass. A probe `# noqa: C901` on a
  simple function fails with `RUF100`, and a probe
  `// eslint-disable-next-line complexity` above one fails with "Unused
  eslint-disable directive".
