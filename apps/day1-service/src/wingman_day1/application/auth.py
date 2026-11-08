"""Login: OpenShift OAuth for real users, a secret-guarded dev login for local use.

After OpenShift says who someone is, their groups decide their role (admin
wins over viewer); someone in no Wingman group is refused, never let in
read-only. Wingman then issues its own session token, which day1 and day2
both accept.

Dev login exists only when ``DEV_AUTH_ENABLED=true`` and a strong
``DEV_AUTH_SECRET`` is set (settings refuse to start otherwise, ADR-0009).
The secret is compared in constant time.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from wingman_core.domain.users import Role, User, resolve_role
from wingman_day1.domain.errors import (
    IdentityError,
    InvalidInputError,
    LoginRefusedError,
    ResourceNotFoundError,
)
from wingman_day1.ports import IdentityProvider, SessionIssuer

DEV_ADMIN_GROUP: Final = "wingman-dev-admins"
DEV_VIEWER_GROUP: Final = "wingman-dev-viewers"
_DEV_USERNAME = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class LoginConfig:
    """What the login page needs."""

    authorize_url: str
    dev_auth_enabled: bool


@dataclass(frozen=True, slots=True)
class Session:
    """A logged-in user and their token."""

    token: str
    user: User


class AuthService:
    """Logins and the session tokens they produce."""

    def __init__(
        self,
        issuer: SessionIssuer,
        *,
        identity: IdentityProvider | None,
        admin_groups: Sequence[str],
        viewer_groups: Sequence[str],
        dev_secret: str | None,
    ) -> None:
        """``identity`` is ``None`` when OAuth is not configured; ``dev_secret`` when dev is off."""
        self._issuer = issuer
        self._identity = identity
        self._admin_groups = tuple(admin_groups)
        self._viewer_groups = tuple(viewer_groups)
        self._dev_secret = dev_secret

    @property
    def dev_enabled(self) -> bool:
        """Whether dev login is on."""
        return self._dev_secret is not None

    async def config(self) -> LoginConfig:
        """Where to log in. With dev login on, there is no OAuth redirect."""
        if self.dev_enabled or self._identity is None:
            return LoginConfig(authorize_url="", dev_auth_enabled=self.dev_enabled)
        return LoginConfig(
            authorize_url=await self._identity.authorize_url(), dev_auth_enabled=False
        )

    async def oauth_login(self, code: str) -> Session:
        """Exchange an OAuth code; the person's groups decide their role."""
        if self._identity is None:
            raise IdentityError("OpenShift OAuth is not configured in this deployment")
        identity = await self._identity.identify(code)
        role = resolve_role(
            identity.groups, admin_groups=self._admin_groups, viewer_groups=self._viewer_groups
        )
        if role is None:
            raise LoginRefusedError(
                f"{identity.username} is in none of the groups that grant access to Wingman; "
                "ask an administrator"
            )
        user = User(
            username=identity.username,
            role=role,
            groups=identity.groups,
            uid=identity.uid,
            full_name=identity.full_name,
        )
        return Session(self._issuer.issue(user), user)

    def dev_login(self, *, username: str, role: str, secret: str) -> Session:
        """A session without OpenShift, for local development only."""
        if self._dev_secret is None:
            raise ResourceNotFoundError("dev login is not enabled")
        if not hmac.compare_digest(secret.encode(), self._dev_secret.encode()):
            raise IdentityError("the dev login secret is wrong")
        if not _DEV_USERNAME.match(username):
            raise InvalidInputError(
                "invalid dev username", ["lowercase letters, digits, '.', '_' and '-' only"]
            )
        try:
            resolved = Role(role)
        except ValueError as exc:
            raise InvalidInputError("invalid role", ["role must be admin or viewer"]) from exc
        group = DEV_ADMIN_GROUP if resolved is Role.ADMIN else DEV_VIEWER_GROUP
        user = User(
            username=username,
            role=resolved,
            groups=(group,),
            uid=f"dev-{username}",
            full_name=f"Dev User ({username})",
        )
        return Session(self._issuer.issue(user), user)
