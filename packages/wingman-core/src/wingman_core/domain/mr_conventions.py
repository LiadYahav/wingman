"""Branch names, MR titles and MR descriptions Wingman writes, and their parsers.

These formats are a contract (ADR-0007): the audit view reads them back from
GitLab history, and approvals recover the real user from the description
because GitLab shows the service account as the author. Changing a format
breaks parsing of every MR already opened, so the parsers accept exactly
what the builders produce, and a round-trip test pins it.

Branch:       ``platform/{username}/{action}-{resource}-{YYYYmmddTHHMMSS}``
Title:        ``[Wingman/{repo}] {Verb} {resource_type} {resource_name}[ {extra}]``
Description:  the human text, then a ``---`` line, then ``Author:``,
              ``Action:``, ``Resource: {type}/{name}`` and ``Repo:`` lines.
Label:        ``wingman`` on every MR Wingman opens; approvals act only on MRs
              that carry it, and the lists filter on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

WINGMAN_LABEL: Final = "wingman"
"""The label every Wingman MR carries."""

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
