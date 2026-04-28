"""Platform JWT management.

The platform issues its own short-lived JWTs after OpenShift OAuth completes.
This decouples the platform session from the OpenShift opaque token (which
we only use once during the OAuth callback).

JWT payload:
    sub     — username
    groups  — list of OpenShift groups
    uid     — OpenShift user UID
    exp     — expiry timestamp
    iat     — issued-at timestamp
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as pyjwt

from ..exceptions import AuthError

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"


class JWTManager:
    """Create and validate platform JWT session tokens."""

    def __init__(self, secret_key: str, expiry_hours: int = 8) -> None:
        if not secret_key:
            raise ValueError("JWT_SECRET_KEY must be set")
        self._secret = secret_key
        self._expiry = timedelta(hours=expiry_hours)

    def create_token(self, username: str, groups: list[str], uid: str, role: str = "viewer") -> str:
        """Create a signed JWT for the authenticated user.

        Args:
            username: OpenShift username
            groups: User's OpenShift groups
            uid: OpenShift user UID
            role: Resolved role ("admin" or "viewer")

        Returns:
            Signed JWT string
        """
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": username,
            "groups": groups,
            "uid": uid,
            "role": role,
            "iat": now,
            "exp": now + self._expiry,
        }
        return pyjwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def validate_token(self, token: str) -> dict[str, Any]:
        """Validate and decode a JWT.

        Returns:
            Decoded payload dict.

        Raises:
            AuthError: if token is invalid, expired, or tampered with.
        """
        try:
            payload = pyjwt.decode(token, self._secret, algorithms=[ALGORITHM])
            return payload
        except pyjwt.ExpiredSignatureError as exc:
            raise AuthError("Token has expired") from exc
        except pyjwt.InvalidTokenError as exc:
            raise AuthError(f"Invalid token: {exc}") from exc
