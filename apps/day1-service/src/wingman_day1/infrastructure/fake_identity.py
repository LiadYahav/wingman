"""FakeIdentityProvider: an IdentityProvider over a fixed table of codes, for tests."""

from __future__ import annotations

from collections.abc import Mapping

from wingman_day1.domain.auth import Identity
from wingman_day1.domain.errors import IdentityError


class FakeIdentityProvider:
    """Each known authorization code logs in one identity; any other code is refused."""

    def __init__(
        self,
        users: Mapping[str, Identity],
        *,
        authorize_url: str = "https://oauth.example.invalid/oauth/authorize?client_id=wingman",
    ) -> None:
        """``users`` maps an authorization code to who it logs in."""
        self._users = dict(users)
        self._authorize_url = authorize_url

    async def authorize_url(self) -> str:
        """See IdentityProvider.authorize_url."""
        return self._authorize_url

    async def identify(self, code: str) -> Identity:
        """See IdentityProvider.identify."""
        identity = self._users.get(code)
        if identity is None:
            raise IdentityError("token exchange: OpenShift refused the credentials (401)")
        return identity
