"""Users and roles.

A user's role comes from their OpenShift groups: admin if they are in any
admin group, viewer if in any viewer group, and no access otherwise. Admin
wins when both match.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """What a user may do. Admins change things; viewers only read."""

    ADMIN = "admin"
    VIEWER = "viewer"


@dataclass(frozen=True, slots=True)
class User:
    """An authenticated user, as carried in the session token."""

    username: str
    role: Role
    groups: tuple[str, ...] = ()
    uid: str = ""
    full_name: str = ""

    @property
    def is_admin(self) -> bool:
        """Whether this user may make changes."""
        return self.role is Role.ADMIN


def resolve_role(
    groups: Iterable[str], *, admin_groups: Iterable[str], viewer_groups: Iterable[str]
) -> Role | None:
    """The role ``groups`` grant, or ``None`` if they grant no access."""
    member_of = set(groups)
    if member_of & set(admin_groups):
        return Role.ADMIN
    if member_of & set(viewer_groups):
        return Role.VIEWER
    return None
