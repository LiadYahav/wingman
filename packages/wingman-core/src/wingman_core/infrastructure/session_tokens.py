"""Wingman's own session tokens: short-lived HS256 JWTs issued after login.

OpenShift OAuth returns an opaque token that is used once, at login, to read
the user's identity and groups. Wingman then issues its own token carrying
the username, groups and resolved role, so each request is checked without
calling OpenShift. Day1 and day2 share the secret, so a token from either
works on both.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

import jwt

from wingman_core.domain.users import Role, User
from wingman_core.ports.clock import Clock, system_clock

ALGORITHM: Final = "HS256"


class InvalidSessionError(Exception):
    """The token is missing, malformed, tampered with or expired."""


class SessionTokens:
    """Issue and verify session tokens."""

    def __init__(self, secret: str, *, ttl: timedelta, clock: Clock = system_clock) -> None:
        """``secret`` is validated by ``AuthSettings``; ``ttl`` is the session length."""
        self._secret = secret
        self._ttl = ttl
        self._clock = clock

    def issue(self, user: User) -> str:
        """A signed token for ``user``."""
        now = self._clock()
        payload = {
            "sub": user.username,
            "groups": list(user.groups),
            "uid": user.uid,
            "name": user.full_name,
            "role": str(user.role),
            "iat": now,
            "exp": now + self._ttl,
        }
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def verify(self, token: str) -> User:
        """The user a valid token was issued for. Raises ``InvalidSessionError``."""
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],
                options={"require": ["sub", "exp", "iat", "role"]},
            )
            role = Role(payload["role"])
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise InvalidSessionError(type(exc).__name__) from exc
        username = payload["sub"]
        if not isinstance(username, str) or not username:
            raise InvalidSessionError("empty subject")
        return User(
            username=username,
            role=role,
            groups=tuple(str(g) for g in payload.get("groups", ())),
            uid=str(payload.get("uid", "")),
            full_name=str(payload.get("name", "")),
        )
