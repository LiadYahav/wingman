"""Role-Based Access Control for Wingman.

Roles are derived from OpenShift group membership, stored in the platform JWT.

Two roles:
  - admin:  Full access — create, modify, delete, approve
  - viewer: Read-only — can see everything but cannot mutate

Group membership is configured via environment variables (not hardcoded):
  WINGMAN_ADMIN_GROUPS  — comma-separated list of groups that get admin role
  WINGMAN_VIEWER_GROUPS — comma-separated list of groups that get viewer role (optional)

A user must be in at least one allowed group to log in at all.
If a user is in both an admin group and a viewer group, admin wins.
"""

from __future__ import annotations

from enum import StrEnum

from ..models import UserInfo


class Role(StrEnum):
    ADMIN = "admin"
    VIEWER = "viewer"


def get_user_role(
    user: UserInfo,
    admin_groups: list[str],
    viewer_groups: list[str],
) -> Role | None:
    """Determine a user's role from their group membership.

    Args:
        user: The authenticated user (groups from JWT)
        admin_groups: Groups that grant admin access
        viewer_groups: Groups that grant viewer access

    Returns:
        Role.ADMIN if user is in any admin group,
        Role.VIEWER if user is in any viewer group (and no admin group),
        None if user is not in any allowed group (access denied).
    """
    user_groups = set(user.groups)

    # Admin takes precedence over viewer
    if any(g in user_groups for g in admin_groups):
        return Role.ADMIN

    if viewer_groups and any(g in user_groups for g in viewer_groups):
        return Role.VIEWER

    return None


def is_allowed(
    user: UserInfo,
    admin_groups: list[str],
    viewer_groups: list[str],
) -> bool:
    """Return True if the user is in any allowed group (admin or viewer)."""
    return get_user_role(user, admin_groups, viewer_groups) is not None


def parse_groups_env(value: str) -> list[str]:
    """Parse a comma-separated group list from an env var value.

    Example: "wingman-admins,platform-team" -> ["wingman-admins", "platform-team"]
    Empty string returns empty list.
    """
    return [g.strip() for g in value.split(",") if g.strip()]
