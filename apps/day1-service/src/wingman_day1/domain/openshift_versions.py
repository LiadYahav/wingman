"""The OpenShift releases a new hosted cluster on an MCE may use (ADR-0034).

The day1 repo's ``upgrade/`` folder says it, in two files the cluster-upgrade
workflow also reads:

- ``upgrade/ladder.yaml``: ``ladder[].version``, the verified releases (bare,
  ``4.20.44``), at least one per minor;
- ``upgrade/mces/<mce>.yaml``: ``mce.supportedHostedVersions``, the minors
  (``"4.22"``) that MCE's HyperShift operator can host.

A new cluster on an MCE may use a rung whose minor the MCE can host, newest
first. Their JSON schemas (``upgrade/schema/``) are the contract: this checks
the parts Wingman reads against them, and the day1 repo's
``scripts/validate_upgrade_rules.py`` checks the rest. ``schemaVersion`` is
part of the rest: production's ladder predates it, and a rung is checked on
its own shape whatever the file says its version is.

Nothing here raises. What a file gets wrong comes back as problems, in plain
words, and the entries that are wrong are left out. An MCE whose file is
missing or unreadable offers no version: unknown is never "everything".
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

import yaml

LADDER_PATH: Final = "upgrade/ladder.yaml"
README_PATH: Final = "upgrade/README.md"

_RELEASE: Final = re.compile(r"^4\.[0-9]+\.[0-9]+$")
"""``ladder.schema.json``, ``$defs.rung.version``."""
_MINOR: Final = re.compile(r"^4\.[0-9]+$")
"""``mce.schema.json``, ``mce.supportedHostedVersions`` items."""
_ARCH_SUFFIX: Final = "-x86_64"


def mce_rules_path(mce: str) -> str:
    """``upgrade/mces/<mce>.yaml``, as the problems name it."""
    return f"upgrade/mces/{mce}.yaml"


@dataclass(frozen=True, slots=True)
class Ladder:
    """The verified releases in ``upgrade/ladder.yaml``, and what is wrong with the file."""

    releases: tuple[str, ...]
    problems: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HostedMinors:
    """The minors an MCE can host, from ``upgrade/mces/<mce>.yaml``."""

    minors: tuple[str, ...]
    problems: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OpenShiftVersions:
    """What a new cluster on ``mce`` may run, newest first, and why the list may be short."""

    mce: str
    versions: tuple[str, ...]
    problems: tuple[str, ...] = ()


def bare_release(version: str) -> str:
    """``4.20.44-x86_64`` → ``4.20.44``, the form the ladder writes."""
    return version.strip().removesuffix(_ARCH_SUFFIX)


def is_release(version: str) -> bool:
    """Whether ``version`` (``-x86_64`` allowed) is a release, ``4.N.N``."""
    return _RELEASE.match(bare_release(version)) is not None


def newest_first(releases: Iterable[str]) -> tuple[str, ...]:
    """Distinct releases, newest first."""
    return tuple(sorted(set(releases), key=_order, reverse=True))


def _minor(release: str) -> str:
    major, minor, _ = release.split(".")
    return f"{major}.{minor}"


def _order(release: str) -> tuple[int, ...]:
    return tuple(int(part) for part in release.split("."))


def _load(text: str, path: str) -> tuple[Mapping[object, object] | None, list[str]]:
    """The file's mapping, or ``None`` and why there is none."""
    try:
        document = yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        return None, [f"{path} is not valid YAML{where}: {exc.problem or exc}"]
    except yaml.YAMLError as exc:
        return None, [f"{path} is not valid YAML: {exc}"]
    if not isinstance(document, dict):
        return None, [f"{path} is not a YAML mapping"]
    return document, []


# ── upgrade/ladder.yaml ──────────────────────────────────────────────────────


def missing_ladder() -> Ladder:
    """The day1 repo has no ``upgrade/ladder.yaml``."""
    return Ladder(
        (),
        (
            f"The day1 repo has no {LADDER_PATH}, so Wingman can't tell which OpenShift "
            f"versions are verified. Add it (see {README_PATH}).",
        ),
    )


def parse_ladder(text: str) -> Ladder:
    """The rungs of ``upgrade/ladder.yaml``; a rung that breaks the schema is left out."""
    document, problems = _load(text, LADDER_PATH)
    if document is None:
        return Ladder((), tuple(problems))
    rungs = document.get("ladder")
    if not isinstance(rungs, list) or not rungs:
        return Ladder((), (f"{LADDER_PATH} has no ladder: list of releases",))
    releases: list[str] = []
    for index, rung in enumerate(rungs):
        where = f"{LADDER_PATH} ladder[{index}]"
        version = rung.get("version") if isinstance(rung, dict) else None
        if version is None:
            problems.append(f"{where} has no version")
        elif not isinstance(version, str) or not _RELEASE.match(version):
            problems.append(
                f"{where}.version {version!r} is not a bare release like 4.20.44 (no -x86_64)"
            )
        elif version not in releases:
            releases.append(version)
    return Ladder(tuple(releases), tuple(problems))


# ── upgrade/mces/<mce>.yaml ──────────────────────────────────────────────────


def missing_mce_rules(mce: str) -> HostedMinors:
    """The day1 repo has no ``upgrade/mces/<mce>.yaml``."""
    return HostedMinors(
        (),
        (
            f"MCE {mce} has no {mce_rules_path(mce)} in the day1 repo, so Wingman can't tell "
            f"which OpenShift versions it can host. Add it (see {README_PATH}).",
        ),
    )


def parse_mce_rules(mce: str, text: str) -> HostedMinors:
    """``mce.supportedHostedVersions``; an entry that breaks the schema is left out."""
    path = mce_rules_path(mce)
    document, problems = _load(text, path)
    if document is None:
        return HostedMinors((), tuple(problems))
    block = document.get("mce")
    supported = block.get("supportedHostedVersions") if isinstance(block, dict) else None
    if not isinstance(supported, list) or not supported:
        return HostedMinors((), (f"{path} has no mce.supportedHostedVersions list",))
    minors: list[str] = []
    for index, entry in enumerate(supported):
        where = f"{path} mce.supportedHostedVersions[{index}]"
        if isinstance(entry, float):
            # An unquoted 4.20 is the float 4.2: which minor was meant is lost.
            problems.append(f'{where} is the number {entry!r}; quote it, as in "4.20"')
        elif not isinstance(entry, str) or not _MINOR.match(entry):
            problems.append(f'{where} {entry!r} is not a minor like "4.22"')
        elif entry not in minors:
            minors.append(entry)
    return HostedMinors(tuple(minors), tuple(problems))


# ── Together ─────────────────────────────────────────────────────────────────


def versions_for(mce: str, ladder: Ladder, hosted: HostedMinors) -> OpenShiftVersions:
    """The rungs whose minor ``mce`` can host, newest first, with both files' problems."""
    problems = [*ladder.problems, *hosted.problems]
    minors = set(hosted.minors)
    versions = sorted((r for r in ladder.releases if _minor(r) in minors), key=_order, reverse=True)
    if not versions and ladder.releases and hosted.minors:
        problems.append(
            f"No release in {LADDER_PATH} is in a minor MCE {mce} can host "
            f"({', '.join(hosted.minors)}). Add a rung for one of them."
        )
    return OpenShiftVersions(mce, tuple(versions), tuple(problems))


def upgrade_hint(mastertag: str | None, offered: OpenShiftVersions) -> str | None:
    """The clusters list's "Upgrade available → <version>" (ADR-0055's 3.20.0 amendment).

    The newest release ``offered`` (what a new cluster on the MCE may use)
    that is newer than ``mastertag``; ``None`` when there is none, or when
    ``mastertag`` is missing or not a release. A suggestion only: it says a
    newer version is offered on this MCE, nothing about the path. The
    upgrade-cluster workflow plans that, and may offer other targets or none.
    """
    if mastertag is None or not is_release(mastertag):
        return None
    current = _order(bare_release(mastertag))
    newer = [release for release in offered.versions if _order(release) > current]
    return max(newer, key=_order) if newer else None


def unhostable_problems(version: str, offered: OpenShiftVersions) -> list[str]:
    """Why ``version`` cannot be a new cluster's release on ``offered.mce``; empty when it can."""
    if bare_release(version) in offered.versions:
        return []
    if not offered.versions:
        return [f"MCE {offered.mce} offers no OpenShift version", *offered.problems]
    return [
        f"MCE {offered.mce} can host {', '.join(offered.versions)}; "
        f"{bare_release(version)} is not one of them"
    ]
