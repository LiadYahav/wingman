"""Branch names, MR titles and MR descriptions Wingman writes, and their parsers.

These formats are a contract (ADR-0007): the audit view reads them back from
GitLab history, and approvals recover the real user from the description
because GitLab shows the service account as the author. Changing a format
breaks parsing of every MR already opened, so the parsers accept exactly
what the builders produce, and a round-trip test pins it.

Branch:       ``platform/{username}/{action}-{resource}-{YYYYmmddTHHMMSS}``
Rollout:      ``platform/rollout/{flavor}/v{version}/{cluster}``: one branch per
              flavor, version and cluster, with no timestamp, so a second run
              or a second pod finds it instead of opening another MR (ADR-0044).
              A user branch has three segments, a rollout branch five, so a
              user named ``rollout`` never makes one.
Title:        ``[Wingman/{repo}] {Verb} {resource_type} {resource_name}[ {extra}]``
Description:  the human text, then a ``---`` line, then ``Author:``,
              ``Action:``, ``Resource: {type}/{name}`` and ``Repo:`` lines.
Label:        ``wingman`` on every MR Wingman opens; approvals act only on MRs
              that carry it, and the lists filter on it. ``rollout`` also on
              each MR a flavor rollout opens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

WINGMAN_LABEL: Final = "wingman"
"""The label every Wingman MR carries."""

ROLLOUT_LABEL: Final = "rollout"
"""The label of each MR a flavor rollout opens (ADR-0044)."""

_ROLLOUT_PREFIX: Final = ("platform", "rollout")

_UNSAFE_BRANCH_CHARS = re.compile(r"[^a-zA-Z0-9._-]")
_DOTS = re.compile(r"\.{2,}")


class Repo(StrEnum):
    """Which Wingman-managed repository an MR targets."""

    DAY1 = "Day1"
    DAY2 = "Day2"
    SPECS = "Specs"


class Verb(StrEnum):
    """The action an MR title starts with."""

    CREATE = "Create"
    MODIFY = "Modify"
    DELETE = "Delete"
    INSTALL = "Install"
    UPDATE = "Update"
    REMOVE = "Remove"
    IMPORT = "Import"
    """Link existing clusters to a flavor (day1)."""
    SYNC = "Sync"
    """Set a cluster's drifted locked values to its flavor's (day1)."""
    PROMOTE = "Promote"
    """Make an add-on a fleet default (day2)."""
    EXCLUDE = "Exclude"
    """Keep a fleet default off named destinations, in ``exclusions.yaml`` (day2)."""
    INCLUDE = "Include"
    """Let a fleet default reach destinations ``exclusions.yaml`` kept it off (day2)."""
    OVERRIDE = "Override"
    """Give one destination of a fleet default its own values or deploy config (day2)."""


class ResourceType(StrEnum):
    """What an MR changes."""

    CLUSTER = "cluster"
    SPEC = "spec"
    ADDON = "addon"


def _branch_safe(text: str) -> str:
    """Make text safe inside a git ref name."""
    return _DOTS.sub(".", _UNSAFE_BRANCH_CHARS.sub("-", text)).strip(".-") or "x"


def branch_name(*, username: str, action: str, resource: str, at: datetime) -> str:
    """Build the branch for a platform change.

    Args:
        username: The user the change is made for.
        action: What is done, e.g. ``create-cluster``.
        resource: What it is done to, e.g. the cluster name.
        at: When; rendered in UTC so two replicas agree.

    Returns:
        For example ``platform/jane.doe/create-cluster-ocp4-prod-a-site1-20260418T143022``.
    """
    stamp = at.astimezone(UTC).strftime("%Y%m%dT%H%M%S")
    return (
        f"platform/{_branch_safe(username)}/{_branch_safe(action)}-{_branch_safe(resource)}-{stamp}"
    )


@dataclass(frozen=True, slots=True)
class RolloutBranch:
    """The parts of a rollout branch, in their branch-safe form."""

    flavor: str
    version: str
    cluster: str


def rollout_branch(*, flavor: str, version: str, cluster: str) -> str:
    """``platform/rollout/<flavor>/v<version>/<cluster>``: one per flavor, version and cluster.

    The same inputs always give the same branch (there is no timestamp), so
    a run that finds the branch knows an earlier run, or another pod, got
    there first. Each part goes through the branch-safe rewrite, so two
    names that differ only in unsafe characters (``1.0+a``, ``1.0-a``) share
    a branch: compare branches by building the expected one, not by parsing.

    Returns:
        For example ``platform/rollout/agent-baseline/v1.1.0/ocp4-prod-lark-site1``.
    """
    return "/".join(
        (
            *_ROLLOUT_PREFIX,
            _branch_safe(flavor),
            f"v{_branch_safe(version)}",
            _branch_safe(cluster),
        )
    )


def parse_rollout_branch(branch: str) -> RolloutBranch | None:
    """The parts of a branch :func:`rollout_branch` built; ``None`` for any other branch.

    Exactly five segments, ``platform/rollout/<flavor>/v<version>/<cluster>``,
    each already branch-safe: anything :func:`rollout_branch` cannot produce
    (a user branch, a version without its ``v``, an extra segment) is not one.
    """
    parts = branch.split("/")
    if len(parts) != 5 or tuple(parts[:2]) != _ROLLOUT_PREFIX:
        return None
    flavor, tagged, cluster = parts[2:]
    version = tagged.removeprefix("v")
    if version == tagged or any(_branch_safe(p) != p for p in (flavor, version, cluster)):
        return None
    return RolloutBranch(flavor=flavor, version=version, cluster=cluster)


def mr_title(
    repo: Repo, verb: Verb, resource_type: ResourceType, resource_name: str, extra: str = ""
) -> str:
    """Build an MR title, e.g. ``[Wingman/Day1] Create cluster ocp4-prod-a-site1 from spec x``."""
    if not resource_name or any(c.isspace() for c in resource_name):
        raise ValueError(f"resource name must be one non-empty word: {resource_name!r}")
    title = f"[Wingman/{repo}] {verb} {resource_type} {resource_name}"
    return f"{title} {extra}" if extra else title


@dataclass(frozen=True, slots=True)
class ParsedTitle:
    """The structured part of a Wingman MR title."""

    repo: Repo
    verb: Verb
    resource_type: ResourceType
    resource_name: str


_TITLE = re.compile(
    r"^\[Wingman/(?P<repo>[^\]]+)\] (?P<verb>\w+) (?P<resource_type>\w+) (?P<resource_name>\S+)"
)


def parse_mr_title(title: str) -> ParsedTitle | None:
    """Parse a title built by :func:`mr_title`; ``None`` for any other title."""
    match = _TITLE.match(title)
    if match is None:
        return None
    try:
        return ParsedTitle(
            repo=Repo(match["repo"]),
            verb=Verb(match["verb"]),
            resource_type=ResourceType(match["resource_type"]),
            resource_name=match["resource_name"],
        )
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class MRMetadata:
    """The machine-readable footer of a Wingman MR description."""

    author: str
    action: str
    resource_type: ResourceType
    resource_name: str
    repo: Repo


def mr_description(human_text: str, metadata: MRMetadata) -> str:
    """Build an MR description: the human text, then the parseable footer."""
    return (
        f"{human_text}\n\n"
        "---\n"
        f"Author: {metadata.author}\n"
        f"Action: {metadata.action}\n"
        f"Resource: {metadata.resource_type}/{metadata.resource_name}\n"
        f"Repo: {metadata.repo}\n"
    )


def parse_mr_description(description: str) -> MRMetadata | None:
    """Parse the footer :func:`mr_description` writes; ``None`` if it is absent or partial."""
    _, separator, footer = description.rpartition("\n---\n")
    if not separator:
        return None
    fields: dict[str, str] = {}
    for line in footer.splitlines():
        key, colon, value = line.partition(": ")
        if colon:
            fields[key] = value.strip()
    resource_type, slash, resource_name = fields.get("Resource", "").partition("/")
    try:
        return MRMetadata(
            author=fields["Author"],
            action=fields["Action"],
            resource_type=ResourceType(resource_type),
            resource_name=resource_name if slash else "",
            repo=Repo(fields["Repo"]),
        )
    except (KeyError, ValueError):
        return None
