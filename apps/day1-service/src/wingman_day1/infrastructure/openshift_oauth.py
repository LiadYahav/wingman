"""OpenShiftOAuth: login through the management cluster's OAuth server, over httpx.

The flow (OpenShift issues opaque ``sha256~`` tokens, not JWTs):

1. The login page redirects to :meth:`OpenShiftOAuth.authorize_url`.
2. OpenShift redirects back with ``?code=``; the page posts it to day1.
3. :meth:`OpenShiftOAuth.identify` exchanges the code for an opaque token
   and reads ``GET /apis/user.openshift.io/v1/users/~`` with it. The token is
   used once and dropped; Wingman then issues its own session token.

Endpoints are discovered from ``/.well-known/oauth-authorization-server`` on
the API server, with ``https://<oauth-host>/oauth/{authorize,token}`` as the
fallback. No error message ever carries the client secret, the code or the
opaque token.
"""

from __future__ import annotations

import ssl
import time
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.auth import Identity
from wingman_day1.domain.errors import IdentityError, IdentityUnavailableError
from wingman_day1.infrastructure.observed import OAuthOperation, Observer, Timer

OAUTH_SCOPE: Final = "user:info"
_DISCOVERY_PATH: Final = "/.well-known/oauth-authorization-server"
_USER_PATH: Final = "/apis/user.openshift.io/v1/users/~"

JSON = Any
"""A decoded JSON value; narrowed where it is read."""


@dataclass(frozen=True, slots=True)
class _Endpoints:
    authorize: str
    token: str


def _base(host: str) -> str:
    """``https://<host>``; a scheme or trailing slash in the setting is tolerated."""
    bare = host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    return f"https://{bare}" if bare else ""


class OpenShiftOAuth:
    """An ``IdentityProvider`` for one OpenShift cluster and one OAuthClient."""

    def __init__(
        self,
        *,
        oauth_host: str,
        api_host: str,
        client_id: str,
        client_secret: SecretStr,
        redirect_uri: str,
        verify: bool | str = True,
        timeout_seconds: float = 10.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Log in against ``api_host`` (and ``oauth_host`` when discovery fails).

        ``verify`` is ``True``/``False`` or a CA bundle path; ``transport``
        replaces the network in tests.
        """
        self._oauth_base = _base(oauth_host)
        self._api_base = _base(api_host)
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._endpoints: _Endpoints | None = None
        self._observer = Observer(Dependency.OPENSHIFT_OAUTH, metrics, timer=timer)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            verify=verify
            if isinstance(verify, bool)
            else ssl.create_default_context(cafile=verify),
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def authorize_url(self) -> str:
        """See IdentityProvider.authorize_url."""
        endpoints = await self._resolve()
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": OAUTH_SCOPE,
            }
        )
        separator = "&" if "?" in endpoints.authorize else "?"
        return f"{endpoints.authorize}{separator}{query}"

    async def identify(self, code: str) -> Identity:
        """See IdentityProvider.identify."""
        if not code.strip():
            raise IdentityError("the login callback carried no authorization code")
        endpoints = await self._resolve()
        token = await self._observer.call(
            OAuthOperation.EXCHANGE_CODE, self._exchange(endpoints.token, code)
        )
        return await self._observer.call(OAuthOperation.GET_USER, self._user(token))

    # ── Steps ───────────────────────────────────────────────────────────────

    async def _resolve(self) -> _Endpoints:
        """Discovered endpoints (cached once found), else the OAuth host's defaults."""
        if self._endpoints is not None:
            return self._endpoints
        try:
            self._endpoints = await self._observer.call(OAuthOperation.DISCOVER, self._discover())
        except IdentityError:
            if not self._oauth_base:
                raise
            # Not cached: the next login tries discovery again.
            return _Endpoints(
                f"{self._oauth_base}/oauth/authorize", f"{self._oauth_base}/oauth/token"
            )
        return self._endpoints

    async def _discover(self) -> _Endpoints:
        if not self._api_base:
            raise IdentityError("OAuth endpoint discovery needs OPENSHIFT_API_HOST")
        raw = await self._send("discovery", "GET", f"{self._api_base}{_DISCOVERY_PATH}")
        authorize = raw.get("authorization_endpoint") if isinstance(raw, dict) else None
        token = raw.get("token_endpoint") if isinstance(raw, dict) else None
        if not (isinstance(authorize, str) and authorize and isinstance(token, str) and token):
            raise IdentityError("OAuth discovery document has no authorization/token endpoint")
        return _Endpoints(authorize, token)

    async def _exchange(self, token_endpoint: str, code: str) -> str:
        raw = await self._send(
            "token exchange",
            "POST",
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
            },
        )
        token = raw.get("access_token") if isinstance(raw, dict) else None
        if not isinstance(token, str) or not token:
            raise IdentityError("token exchange: the response has no access_token")
        return token

    async def _user(self, token: str) -> Identity:
        if not self._api_base:
            raise IdentityError("reading the user needs OPENSHIFT_API_HOST")
        raw = await self._send(
            "user lookup",
            "GET",
            f"{self._api_base}{_USER_PATH}",
            headers={"Authorization": f"Bearer {token}"},
        )
        user = raw if isinstance(raw, dict) else {}
        metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}
        username = metadata.get("name") if isinstance(metadata, dict) else None
        if not isinstance(username, str) or not username.strip():
            raise IdentityError("user lookup: OpenShift returned no username")
        groups = user.get("groups") or []
        if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
            raise IdentityError("user lookup: groups is not a list of names")
        uid = metadata.get("uid") if isinstance(metadata, dict) else None
        full_name = user.get("fullName")
        return Identity(
            username=username,
            groups=tuple(groups),
            uid=uid if isinstance(uid, str) else "",
            full_name=full_name if isinstance(full_name, str) else "",
        )

    async def _send(
        self,
        step: str,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> JSON:
        """One request; every failure is an ``IdentityError`` naming the step and status only."""
        try:
            response = await self._client.request(method, url, data=data, headers=headers)
        except httpx.TransportError as exc:
            raise IdentityUnavailableError(
                f"{step}: OpenShift unreachable ({type(exc).__name__})"
            ) from exc
        if response.status_code == 401:
            raise IdentityError(f"{step}: OpenShift refused the credentials (401)")
        if response.status_code >= 500:
            raise IdentityUnavailableError(f"{step}: OpenShift answered {response.status_code}")
        if not response.is_success:
            raise IdentityError(f"{step}: OpenShift answered {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise IdentityError(f"{step}: the response is not JSON") from exc
