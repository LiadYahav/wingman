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
# Day1 and day2 run on different pods; a token one issues may look slightly
# early to the other.
CLOCK_SKEW: Final = timedelta(seconds=30)


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
        """The user a valid token was issued for. Raises ``InvalidSessionError``.

        Expiry is checked against the injected clock, the same one ``issue``
        uses; PyJWT's own check would read the wall clock instead.
        """
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],
                options={
                    "require": ["sub", "exp", "iat", "role"],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
            role = Role(payload["role"])
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise InvalidSessionError(type(exc).__name__) from exc
        exp, iat = payload["exp"], payload["iat"]
        if not all(isinstance(t, int | float) and not isinstance(t, bool) for t in (exp, iat)):
            raise InvalidSessionError("non-numeric exp or iat")
        now = self._clock().timestamp()
        if exp <= now:
            raise InvalidSessionError("expired")
        if iat > now + CLOCK_SKEW.total_seconds():
            raise InvalidSessionError("issued in the future")
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
