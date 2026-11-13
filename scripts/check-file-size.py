#!/usr/bin/env python3
"""Files stay small: a line limit per file, and a baseline that may only shrink.

    python3 scripts/check-file-size.py          # fail on a file over its limit, or a stale entry
    python3 scripts/check-file-size.py --list   # print today's offenders as baseline lines

Every Python, TypeScript and TSX file git tracks (or would track: new files
count before they are added) has at most 500 physical lines, as ``wc -l``
counts them, or 800 for a test (a path through a ``tests`` or ``e2e`` folder);
ADR-0056. A file over its limit must be listed in scripts/file-size-baseline.txt
with a ceiling: it may shrink, never grow past it, and no new file joins the
list. An entry whose file is back under the limit, or gone, fails too, so the
change that splits a file removes its line and the list can only shrink (the
npm audit allowlist's rule, ADR-0032). Standard library only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "file-size-baseline.txt"
SOURCE_LIMIT = 500
TEST_LIMIT = 800
SUFFIXES = (".py", ".ts", ".tsx")
TEST_DIRS = frozenset({"tests", "e2e"})
# Not ours to size: generated or vendored, and fixture trees.
EXCLUDED_DIRS = ("apps/web/components/ui/", "dev/gitlab-fixtures/")
EXCLUDED_FILES = frozenset({"apps/day2-service/tests/oracle/render_chain.py"})


def limit_for(path: str) -> int | None:
    """The line limit for ``path`` (repository-relative, POSIX), or ``None`` if unchecked."""
    if not path.endswith(SUFFIXES) or path.endswith(".d.ts"):
        return None
    if path in EXCLUDED_FILES or path.startswith(EXCLUDED_DIRS):
        return None
    folders = PurePosixPath(path).parts[:-1]
    return TEST_LIMIT if TEST_DIRS.intersection(folders) else SOURCE_LIMIT


def count_lines(data: bytes) -> int:
    """Physical lines, as ``wc -l`` counts them, plus a last line with no newline."""
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def parse_baseline(text: str) -> dict[str, int]:
    """``{path: ceiling}`` from baseline lines ``<ceiling>  <path>``; ``#`` starts a comment."""
    ceilings: dict[str, int] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        ceiling, _, path = entry.partition(" ")
        path = path.strip()
        if not ceiling.isdigit() or not path:
            raise SystemExit(f"{BASELINE.name}:{number}: not '<ceiling>  <path>': {line!r}")
        if path in ceilings:
            raise SystemExit(f"{BASELINE.name}:{number}: {path} is listed twice")
        ceilings[path] = int(ceiling)
    return ceilings


def compare(sizes: dict[str, int], ceilings: dict[str, int]) -> tuple[list[str], list[str]]:
    """``(errors, notes)`` for the files' line counts against the baseline's ceilings."""
    errors: list[str] = []
    notes: list[str] = []
    for path, lines in sorted(sizes.items()):
        limit = limit_for(path)
        if limit is None:
            continue
        ceiling = ceilings.get(path)
        if ceiling is None:
            if lines > limit:
                errors.append(
                    f"{path}: {lines} lines, over the {limit}-line limit: split it (ADR-0056); "
                    "the baseline takes no new files"
                )
        elif lines <= limit:
            errors.append(
                f"{path}: {lines} lines, within the {limit}-line limit now: "
                f"remove it from {BASELINE.name}"
            )
        elif lines > ceiling:
            errors.append(
                f"{path}: {lines} lines, past its ceiling of {ceiling}: move code out before "
                "adding to it (ADR-0056); a ceiling is never raised"
            )
        elif lines < ceiling:
            notes.append(f"{path}: {lines} lines, below its ceiling of {ceiling}: lower it")
    for path in sorted(ceilings.keys() - sizes.keys()):
        why = "is not a checked file" if limit_for(path) is None else "no longer exists"
        errors.append(f"{path}: listed in {BASELINE.name} but {why}: remove its line")
    return errors, notes


def repo_files() -> list[str]:
    """Every file git tracks or would track (untracked, not ignored), repository-relative."""
    result = subprocess.run(
        # git from PATH, fixed arguments
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"git ls-files failed:\n{result.stderr.decode(errors='replace')}")
    return sorted({name for name in result.stdout.decode().split("\0") if name})


def measure(paths: list[str]) -> dict[str, int]:
    """The line count of each checked file in ``paths`` that exists on disk."""
    sizes: dict[str, int] = {}
    for path in paths:
        file = ROOT / path
        if limit_for(path) is not None and file.is_file():
            sizes[path] = count_lines(file.read_bytes())
    return sizes


def main(argv: list[str] | None = None) -> int:
    """Check every file against its limit and the baseline, or print the offenders."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--list", action="store_true", help="print today's offenders as baseline lines"
    )
    args = parser.parse_args(argv)
    sizes = measure(repo_files())
    if args.list:
        for path, lines in sorted(sizes.items()):
            limit = limit_for(path)
            if limit is not None and lines > limit:
                print(f"{lines:>5}  {path}")
        return 0
    ceilings = parse_baseline(BASELINE.read_text(encoding="utf-8"))
    errors, notes = compare(sizes, ceilings)
    for note in notes:
        print(f"note: {note}")
    for error in errors:
        print(f"::error::file size: {error}")
    if errors:
        return 1
    print(
        f"file sizes: {len(sizes)} files within {SOURCE_LIMIT} lines ({TEST_LIMIT} for tests) "
        f"or their ceiling; {len(ceilings)} in the baseline"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
