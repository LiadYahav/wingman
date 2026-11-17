#!/usr/bin/env python3
"""What changed upstream that a Wingman integration follows: its map, between two upstream refs.

    uv run python scripts/upstream_diff.py server-scan              # synced_at -> the newest tag
    uv run python scripts/upstream_diff.py server-scan v6.2.0 --patch
    uv run python scripts/upstream_diff.py segments-manager --repo ~/src/segments-manager
    uv run python scripts/upstream_diff.py server-scan v6.1.0 --from 92146d3   # an older range

``docs/integrations/<system>.yaml`` maps every Wingman file that follows an
upstream system to the upstream files it follows, and names the upstream
version Wingman matches (``synced_at``), the upstream folders whose changes
matter even when no Wingman file maps them (``watch``) and what under them
Wingman decided not to follow (``not_followed``, each with why). Between
``synced_at`` (or ``--from``) and the target (by default the newest tag, or
the map's ``default_target`` branch) this prints the upstream commits, then
three lists:

1. each Wingman file whose upstream files changed, with ``git diff --name-status``;
2. changes under ``watch`` that no entry follows and ``not_followed`` does not
   name (a new upstream file, or one Wingman never mapped);
3. upstream files the map names that no longer exist at the target.

``--patch`` adds the upstream diff under each Wingman file. An upstream path
that ends in ``/`` is a folder: it covers everything under it.

The upstream is a clone kept under
``${XDG_CACHE_HOME:-~/.cache}/wingman/upstreams/<owner>/<repo>`` (made with
``--filter=blob:none``, so file contents are fetched only when a diff needs
them), whose tags and branches are fetched on every run. ``--repo`` uses a
clone you already have, as it is, with no network. The script reports and
exits 0; the person decides what Wingman follows. A usage error, a bad map or
a git failure exits 2. Standard library and PyYAML (a dependency of every
workspace member: run it with ``uv run``). Each system's guide,
``docs/integrations/<system>.md``, has the checklist that follows a run.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MAPS = ROOT / "docs" / "integrations"
COMMITS_SHOWN = 40


class UpstreamError(Exception):
    """A map that cannot be read, a ref that does not resolve, or git failing."""


@dataclass(frozen=True)
class Entry:
    """One Wingman file and the upstream files (or ``dir/`` folders) it follows."""

    wingman: str
    upstream: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class UpstreamMap:
    """A system's map: ``docs/integrations/<system>.yaml``."""

    upstream: str
    synced_at: str
    default_target: str | None
    watch: tuple[str, ...]
    files: tuple[Entry, ...]
    not_followed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Change:
    """One line of ``git diff --name-status``; ``old_path`` is set for a rename or copy."""

    status: str
    path: str
    old_path: str | None = None

    def paths(self) -> tuple[str, ...]:
        """Every path the change touches: the new one, and the old one if it moved."""
        return (self.path,) if self.old_path is None else (self.old_path, self.path)

    def line(self) -> str:
        """The change as ``git diff --name-status`` prints it."""
        moved = f"{self.old_path} -> " if self.old_path else ""
        return f"{self.status:<4} {moved}{self.path}"


# ── The map ──────────────────────────────────────────────────────────────────


def _strings(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise UpstreamError(f"{what} must be a list of paths")
    return tuple(value)


def _entry(raw: object) -> Entry:
    if not isinstance(raw, dict) or not isinstance(raw.get("wingman"), str):
        raise UpstreamError(f"a files entry needs a wingman path: {raw!r}")
    upstream = _strings(raw.get("upstream"), f"{raw['wingman']}'s upstream")
    if not upstream:
        raise UpstreamError(f"{raw['wingman']} follows no upstream file")
    return Entry(raw["wingman"], upstream, str(raw.get("note", "")))


def _not_followed(raw: object) -> tuple[str, ...]:
    """The upstream paths under ``watch`` that Wingman decided not to follow, each with why."""
    if not isinstance(raw, list):
        raise UpstreamError("not_followed must be a list")
    paths: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("why"), str):
            raise UpstreamError(f"a not_followed entry needs a why: {item!r}")
        paths += _strings(item.get("upstream"), "a not_followed entry's upstream")
    return tuple(paths)


def parse_map(text: str) -> UpstreamMap:
    """Read a map's YAML; ``UpstreamError`` says what is wrong with it."""
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise UpstreamError("a map is a mapping")
    for key in ("upstream", "synced_at"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise UpstreamError(f"the map has no {key}")
    target = raw.get("default_target")
    if target is not None and not isinstance(target, str):
        raise UpstreamError("default_target is a branch name")
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        raise UpstreamError("the map has no files")
    return UpstreamMap(
        upstream=raw["upstream"],
        synced_at=str(raw["synced_at"]),
        default_target=target,
        watch=_strings(raw.get("watch", []), "watch"),
        files=tuple(_entry(item) for item in files),
        not_followed=_not_followed(raw.get("not_followed", [])),
    )


def load_map(path: Path) -> UpstreamMap:
    """The map at ``path``."""
    try:
        return parse_map(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise UpstreamError(f"{path}: {error}") from error


# ── Comparing ────────────────────────────────────────────────────────────────


def covers(pattern: str, path: str) -> bool:
    """Whether a map path covers an upstream path: the same file, or under a ``dir/``."""
    return path.startswith(pattern) if pattern.endswith("/") else path == pattern


def _touches(patterns: tuple[str, ...], change: Change) -> bool:
    return any(covers(p, path) for p in patterns for path in change.paths())


def entry_changes(entry: Entry, changes: list[Change]) -> list[Change]:
    """The changes to the upstream files ``entry`` follows."""
    return [change for change in changes if _touches(entry.upstream, change)]


def unmapped_watched(umap: UpstreamMap, changes: list[Change]) -> list[Change]:
    """Changes under ``watch`` that no entry follows and ``not_followed`` does not name."""
    mapped = (*(p for entry in umap.files for p in entry.upstream), *umap.not_followed)
    return [c for c in changes if _touches(umap.watch, c) and not _touches(mapped, c)]


def missing_upstream(umap: UpstreamMap, tree: frozenset[str]) -> list[tuple[str, str]]:
    """``(wingman, upstream)`` for each mapped upstream path the target does not have."""
    return [
        (entry.wingman, path)
        for entry in umap.files
        for path in entry.upstream
        if not any(covers(path, name) for name in tree)
    ]


def parse_name_status(output: str) -> list[Change]:
    """``git diff --name-status -z`` output, as changes."""
    fields = output.split("\0")
    changes: list[Change] = []
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        if status[0] in "RC":
            changes.append(Change(status, fields[i + 2], fields[i + 1]))
            i += 3
        else:
            changes.append(Change(status, fields[i + 1]))
            i += 2
    return changes


# ── git ──────────────────────────────────────────────────────────────────────


def git(repo: Path | None, *args: str) -> str:
    """Run git (in ``repo``) and return its output; ``UpstreamError`` when it fails."""
    where = ["-C", str(repo)] if repo else []
    result = subprocess.run(  # noqa: S603
        ["git", *where, *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise UpstreamError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def cached_clone(upstream: str, cache: Path) -> Path:
    """The clone of ``upstream`` under ``cache``, made if missing, with its refs fetched."""
    clone = cache / upstream
    if not clone.exists():
        clone.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/{upstream}.git"
        print(f"cloning {url} into {clone} ...", file=sys.stderr)
        git(None, "clone", "--quiet", "--filter=blob:none", "--no-checkout", url, str(clone))
    git(clone, "fetch", "--quiet", "--tags", "--force", "--prune", "origin")
    return clone


def resolve(repo: Path, ref: str) -> str | None:
    """The commit ``ref`` names, or ``None`` if it names none."""
    try:
        return git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()
    except UpstreamError:
        return None


def newest_tag(repo: Path) -> str | None:
    """The highest version tag, or ``None`` without tags."""
    tags = git(repo, "tag", "--list", "--sort=-v:refname").split()
    return tags[0] if tags else None


def default_target(repo: Path, umap: UpstreamMap) -> str:
    """The map's ``default_target`` branch (its remote one first), else the newest tag."""
    if umap.default_target:
        for ref in (f"refs/remotes/origin/{umap.default_target}", umap.default_target):
            if resolve(repo, ref):
                return ref.removeprefix("refs/remotes/")
        raise UpstreamError(f"no branch {umap.default_target} in {repo}")
    tag = newest_tag(repo)
    if tag is None:
        raise UpstreamError(f"{repo} has no tags: name a target")
    return tag


def tree(repo: Path, ref: str) -> frozenset[str]:
    """Every file at ``ref``."""
    return frozenset(git(repo, "ls-tree", "-r", "-z", "--name-only", ref).split("\0")) - {""}


def changes_between(repo: Path, base: str, target: str) -> list[Change]:
    """What changed from ``base`` to ``target``, renames found."""
    out = git(repo, "diff", "--no-ext-diff", "--name-status", "-z", "-M", base, target)
    return parse_name_status(out)


def is_ancestor(repo: Path, base: str, target: str) -> bool:
    """Whether ``target`` contains ``base``."""
    try:
        git(repo, "merge-base", "--is-ancestor", base, target)
    except UpstreamError:
        return False
    return True


# ── The report ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Run:
    """One comparison: the map, the clone and the two commits."""

    umap: UpstreamMap
    repo: Path
    base: str
    target: str
    base_sha: str
    target_sha: str


def label(ref: str, sha: str) -> str:
    """A ref and its short commit, or the short commit alone when the ref is one."""
    return sha[:7] if sha.startswith(ref) else f"{ref} ({sha[:7]})"


def header(run: Run) -> list[str]:
    """Which upstream, from where to where, and its commits between."""
    since = label(run.base, run.base_sha)
    if run.base == run.umap.synced_at:
        since = f"synced_at {since}"
    lines = [f"{run.umap.upstream}: {since} -> {label(run.target, run.target_sha)}"]
    if not is_ancestor(run.repo, run.base_sha, run.target_sha):
        lines.append(
            f"note: {run.target} does not contain {run.base}; the lists compare the two trees"
        )
    return lines + commits_section(run)


def commits_section(run: Run) -> list[str]:
    """The upstream commits from the base to the target, newest first."""
    span = f"{run.base_sha}..{run.target_sha}"
    commits = git(run.repo, "log", "--oneline", "--no-decorate", span).splitlines()
    if not commits:
        return [f"\nNo upstream commit since {run.base}: Wingman matches {run.target}."]
    lines = [f"\n{len(commits)} upstream commit(s) since {run.base}:"]
    lines += [f"  {commit}" for commit in commits[:COMMITS_SHOWN]]
    if len(commits) > COMMITS_SHOWN:
        lines.append(f"  ... and {len(commits) - COMMITS_SHOWN} more")
    return lines


def mapped_section(run: Run, changes: list[Change], *, patch: bool) -> list[str]:
    """List 1: each Wingman file whose upstream files changed."""
    hits = [(e, found) for e in run.umap.files if (found := entry_changes(e, changes))]
    lines = [f"\n1. Wingman files whose upstream changed ({len(hits)} of {len(run.umap.files)}):"]
    for entry, found in hits:
        lines.append(f"\n  {entry.wingman}" + (f"  ({entry.note})" if entry.note else ""))
        lines += [f"      {change.line()}" for change in found]
        if patch:
            lines += [f"      | {line}" for line in upstream_patch(run, entry).splitlines()]
    if not hits:
        lines.append("      none")
    return lines


def upstream_patch(run: Run, entry: Entry) -> str:
    """The upstream diff of the files ``entry`` follows."""
    span = (run.base_sha, run.target_sha)
    return git(run.repo, "diff", "--no-ext-diff", "--no-color", "-M", *span, "--", *entry.upstream)


def watched_section(run: Run, changes: list[Change]) -> list[str]:
    """List 2: changes under ``watch`` that no entry covers."""
    found = unmapped_watched(run.umap, changes)
    lines = [f"\n2. Upstream changes under watch that no map entry covers ({len(found)}):"]
    lines += [f"      {change.line()}" for change in found]
    if not found:
        lines.append("      none")
    return lines


def missing_section(run: Run) -> list[str]:
    """List 3: mapped upstream files the target does not have."""
    found = missing_upstream(run.umap, tree(run.repo, run.target_sha))
    lines = [f"\n3. Upstream files the map names that {run.target} does not have ({len(found)}):"]
    lines += [f"      {path}  (followed by {wingman})" for wingman, path in found]
    if not found:
        lines.append("      none")
    return lines


def report(run: Run, *, patch: bool) -> str:
    """The whole report, as text."""
    changes = changes_between(run.repo, run.base_sha, run.target_sha)
    lines = header(run)
    lines += mapped_section(run, changes, patch=patch)
    lines += watched_section(run, changes)
    lines += missing_section(run)
    return "\n".join(lines) + "\n"


# ── Command line ─────────────────────────────────────────────────────────────


def cache_root() -> Path:
    """``${XDG_CACHE_HOME:-~/.cache}/wingman/upstreams``."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "wingman" / "upstreams"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """The command line."""
    parser = argparse.ArgumentParser(
        description="What changed upstream that a Wingman integration follows.",
    )
    parser.add_argument("system", help="a map in docs/integrations/: server-scan, segments-manager")
    parser.add_argument("target", nargs="?", help="an upstream tag, branch or commit")
    parser.add_argument("--patch", action="store_true", help="the upstream diff per Wingman file")
    parser.add_argument("--from", dest="base", help="compare from this ref instead of synced_at")
    parser.add_argument("--repo", type=Path, help="an existing clone, used as it is (no network)")
    parser.add_argument("--map", type=Path, help="a map file instead of the system's")
    return parser.parse_args(argv)


def prepare(args: argparse.Namespace) -> Run:
    """The map, the clone and the two commits the arguments name."""
    path = args.map or MAPS / f"{args.system}.yaml"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in MAPS.glob("*.yaml"))) or "none"
        raise UpstreamError(f"no map {path} (the maps: {known})")
    umap = load_map(path)
    repo = args.repo or cached_clone(umap.upstream, cache_root())
    target = args.target or default_target(repo, umap)
    base = args.base or umap.synced_at
    base_sha = resolve(repo, base)
    target_sha = resolve(repo, target)
    if not base_sha or not target_sha:
        raise UpstreamError(f"{repo} has no commit {base if not base_sha else target}")
    return Run(umap, repo, base, target, base_sha, target_sha)


def main(argv: list[str] | None = None) -> int:
    """Print the report; 2 on a usage error, a bad map or git failing."""
    args = parse_args(argv)
    try:
        run = prepare(args)
        text = report(run, patch=args.patch)
    except UpstreamError as error:
        print(f"upstream_diff: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
