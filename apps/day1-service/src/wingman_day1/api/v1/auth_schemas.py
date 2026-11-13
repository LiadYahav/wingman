"""The bodies of ``/api/auth``: the login page's config, the OAuth code, dev login."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from wingman_core.domain.users import User
from wingman_day1.api.v1.schemas import _In


class UserOut(BaseModel):
    """The legacy ``UserInfo``."""

    username: str
    groups: list[str]
    uid: str
    full_name: str
    role: Literal["admin", "viewer"]

    @classmethod
    def of(cls, user: User) -> UserOut:
        """From a session user."""
        return cls(
            username=user.username,
            groups=list(user.groups),
            uid=user.uid,
            full_name=user.full_name,
            role=user.role.value,
        )


class AuthConfigOut(BaseModel):
    """Where the login page sends the browser."""

    authorize_url: str
    dev_auth_enabled: bool = False


class CallbackIn(_In):
    """The OAuth code the login page received."""

    code: str = Field(min_length=1, max_length=4096)


class DevLoginIn(_In):
    """Dev login: the secret is required (``DEV_AUTH_SECRET``)."""

    username: str = Field(min_length=1, max_length=64)
    role: str = "admin"
    secret: str = Field(default="", max_length=1024)


class SessionOut(BaseModel):
    """A session token and its user."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - the OAuth token type, not a secret
    user: UserOut
