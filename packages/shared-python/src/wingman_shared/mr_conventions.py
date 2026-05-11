"""Wingman MR/commit naming conventions.

All platform-generated MRs and commits follow a fixed, parseable format.
This allows the audit service to extract structured information without
additional API calls, and makes GitLab history human-readable.

── Branch format ──────────────────────────────────────────────────────────────
  platform/{username}/{action}-{resource}-{timestamp}

  Examples:
    platform/jane.doe/create-cluster-alpha-20260418T143022
    platform/jane.doe/install-cert-manager-alpha-20260418T143022
    platform/bob.smith/delete-spec-standard-ha-20260418T143022

── MR title format ────────────────────────────────────────────────────────────
  [Wingman/{repo}] {Verb} {resource_type} {resource_name}{extra}

  Where:
    repo          = Day1 | Day2 | Specs
    Verb          = Create | Modify | Delete | Install | Update | Remove
    resource_type = cluster | spec | addon
    resource_name = the actual resource name (e.g. "alpha", "cert-manager")
    extra         = optional suffix (e.g. "from spec standard-ha", "on cluster alpha")

  Examples:
    [Wingman/Day1] Create cluster alpha from spec standard-ha
    [Wingman/Day1] Delete cluster beta
    [Wingman/Specs] Update spec standard-ha to v1.1.0
    [Wingman/Day2] Install cert-manager v1.12.0 on alpha
    [Wingman/Day2] Remove monitoring-stack from gamma

── MR description format ──────────────────────────────────────────────────────
  {Human description}

  Author: {username}
  Action: {action}
  Resource: {resource_type}/{resource_name}
  Repo: {repo}

  The structured section at the bottom is machine-parseable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import MRDetail


# ── Branch name builder ────────────────────────────────────────────────────────


def make_branch_name(username: str, action: str, resource: str) -> str:
    """Build a canonical platform branch name.

    Args:
        username: The OpenShift username performing the action
        action: e.g. "create-cluster-alpha", "install-cert-manager-alpha"
        resource: Additional resource identifier string

    Returns:
        Branch name like "platform/jane.doe/create-cluster-alpha-20260418T143022"
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    # Sanitize: replace characters not valid in git branch names
    safe_user = re.sub(r"[^a-zA-Z0-9._-]", "-", username)
    safe_resource = re.sub(r"[^a-zA-Z0-9._-]", "-", resource)
    return f"platform/{safe_user}/{action}-{safe_resource}-{timestamp}"


# ── MR title builder ───────────────────────────────────────────────────────────


def make_mr_title(
    repo: str, verb: str, resource_type: str, resource_name: str, extra: str = ""
) -> str:
    """Build a structured MR title.

    Args:
        repo: "Day1", "Day2", or "Specs"
        verb: "Create", "Modify", "Delete", "Install", "Update", "Remove"
        resource_type: "cluster", "spec", "addon"
        resource_name: The name of the resource
        extra: Optional suffix (e.g. "from spec standard-ha", "on cluster alpha")

    Returns:
        "[Wingman/Day1] Create cluster alpha from spec standard-ha"
    """
    title = f"[Wingman/{repo}] {verb} {resource_type} {resource_name}"
    if extra:
        title += f" {extra}"
    return title


# ── MR description builder ─────────────────────────────────────────────────────


def make_mr_description(
    human_text: str,
    username: str,
    action: str,
    resource_type: str,
    resource_name: str,
    repo: str,
) -> str:
    """Build a structured MR description with machine-parseable metadata.

    The last section is parseable by the audit service using parse_mr_description().
    """
    return (
        f"{human_text}\n\n"
        f"---\n"
        f"Author: {username}\n"
        f"Action: {action}\n"
        f"Resource: {resource_type}/{resource_name}\n"
        f"Repo: {repo}\n"
    )


# ── MR description parser ──────────────────────────────────────────────────────


@dataclass
class ParsedMRDescription:
    author: str = ""
    action: str = ""
    resource_type: str = ""
    resource_name: str = ""
    repo: str = ""


def parse_mr_description(description: str) -> ParsedMRDescription:
    """Extract structured metadata from a Wingman MR description.

    Returns ParsedMRDescription with empty strings for missing fields.
    """
    result = ParsedMRDescription()
    if not description:
        return result

    for line in description.splitlines():
        if line.startswith("Author: "):
            result.author = line[len("Author: ") :].strip()
        elif line.startswith("Action: "):
            result.action = line[len("Action: ") :].strip()
        elif line.startswith("Resource: "):
            resource = line[len("Resource: ") :].strip()
            parts = resource.split("/", 1)
            if len(parts) == 2:
                result.resource_type, result.resource_name = parts
        elif line.startswith("Repo: "):
            result.repo = line[len("Repo: ") :].strip()

    return result


# ── MR title parser (for audit enrichment) ────────────────────────────────────

_TITLE_PATTERN = re.compile(
    r"\[Wingman/(?P<repo>[^\]]+)\]\s+(?P<verb>\w+)\s+(?P<resource_type>\w+)\s+(?P<resource_name>\S+)",
    re.IGNORECASE,
)


def parse_mr_title(title: str) -> dict[str, str]:
    """Extract structured fields from a Wingman MR title.

    Returns dict with keys: repo, verb, resource_type, resource_name
    Empty dict if title doesn't match the format.
    """
    m = _TITLE_PATTERN.match(title)
    if not m:
        return {}
    return {
        "repo": m.group("repo"),
        "verb": m.group("verb"),
        "resource_type": m.group("resource_type"),
        "resource_name": m.group("resource_name"),
    }


# ── MR dict to MRDetail converter ─────────────────────────────────────────────


def parse_mr_to_detail(raw: dict[str, Any], extract_platform_author: bool = True) -> MRDetail:
    """Convert a raw GitLab MR dict to an MRDetail model.

    This is the canonical function for parsing MR responses from GitLab.
    Use this instead of duplicating the parsing logic in each service.

    Args:
        raw: Raw dict from GitLab API (mr.attributes or list item)
        extract_platform_author: If True, extract the real platform username from
            the MR description (since GitLab shows the service account as author).
            Set to False for audit/history views where you want the raw GitLab author.

    Returns:
        MRDetail instance with all fields populated.
    """
    from .models import MRAuthor, MRDetail  # noqa: PLC0415 - avoid circular import

    author_raw = raw.get("author", {})
    description = raw.get("description", "") or ""

    # Determine the author to display
    if extract_platform_author:
        # Extract platform username from description "Author: {username}" line
        # since the GitLab API author is the service token, not the real user
        parsed = parse_mr_description(description)
        display_username = parsed.author or author_raw.get("username", "")
    else:
        display_username = author_raw.get("username", "")

    return MRDetail(
        iid=raw["iid"],
        title=raw.get("title", ""),
        description=description,
        author=MRAuthor(
            username=display_username,
            name=display_username,
            avatar_url=author_raw.get("avatar_url", ""),
        ),
        state=raw.get("state", "opened"),
        created_at=raw.get("created_at", ""),
        updated_at=raw.get("updated_at", ""),
        web_url=raw.get("web_url", ""),
        source_branch=raw.get("source_branch", ""),
        target_branch=raw.get("target_branch", ""),
        labels=raw.get("labels", []),
        has_conflicts=raw.get("has_conflicts"),
    )
