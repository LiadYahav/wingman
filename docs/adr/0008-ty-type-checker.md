# ADR-0008: ty is the type checker, as in server-scan

Date: 2026-11-07
Status: Accepted

## Context

The legacy services ran mypy with `disallow_untyped_defs=false` and
`--ignore-missing-imports`, and about 157 `Any`s passed through unchecked.
The rewrite needed a strict checker. The two candidates were mypy `--strict`
and Astral's ty, which server-scan adopted in its ADR-0019. The user chose ty
on 2026-11-07, so the team's repositories share one toolchain (uv, ruff, ty).

## Decision

- ty, pinned exactly in the root dev group (`ty==0.0.78`), configured in the
  root `pyproject.toml` (`[tool.ty]`): Python 3.13, `unused-awaitable` and
  `blanket-ignore-comment` as errors.
- Because ty does not reject unannotated functions by itself, ruff's
  annotation rules (`ANN001`..`ANN206`) are on for all new code.
- New packages pass `uv run ty check` with no suppressions. ty honours only a
  bare `# type: ignore` or `# ty: ignore[rule]`; a mypy-style
  `# type: ignore[code]` is not a suppression to it, so don't write one.

## Alternatives rejected

- **mypy `--strict`.** More mature, and it rejects unannotated defs on its own,
  but it would split the team's toolchain from server-scan's.

## Consequences

- ty is pre-1.0. A version bump can move diagnostics without any code change;
  read a new error after a bump as ty changing, and pin the bump in its own
  commit.
- Legacy packages are not type-checked by ty until they are rewritten.

## Verification

`uv run ty check packages/wingman-core` in CI and `scripts/gate.sh`.
