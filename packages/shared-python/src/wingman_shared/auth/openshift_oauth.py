"""OpenShift OAuth integration.

OpenShift OAuth returns OPAQUE tokens (sha256~...), NOT JWTs.
There are no refresh tokens. Token expiry is 24h by default.

Flow:
1. Frontend redirects to OAuth authorize endpoint
2. OpenShift redirects back with ?code=...
3. Backend exchanges code for opaque token (this module)
4. Backend calls users/~ API with opaque token to get user info (this module)
5. Backend creates platform JWT and returns it to frontend
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..exceptions import AuthError

logger = logging.getLogger(__name__)

# Scope: user:info is sufficient for identity; user:full grants full API access via the token
OAUTH_SCOPE = "user:info"


class OpenShiftOAuth:
    """Handles OpenShift OAuth code exchange and user info retrieval."""

    def __init__(
        self,
        oauth_host: str,
        api_host: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        ssl_verify: bool | str = True,
    ) -> None:
        """
        Args:
            oauth_host: OAuth server hostname (e.g. "oauth-openshift.apps.mgmt.internal")
            api_host: Kubernetes API server host:port (e.g. "api.mgmt.internal:6443")
            client_id: OAuthClient metadata.name
            client_secret: OAuthClient secret
            redirect_uri: Must match OAuthClient redirectURIs exactly
            ssl_verify: True, False, or path to CA bundle file
        """
        self._oauth_base = f"https://{oauth_host}"
        self._api_base = f"https://{api_host}"
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._ssl_verify = ssl_verify

        # Resolved dynamically from .well-known endpoint (lazy)
        self._authorize_endpoint: str | None = None
        self._token_endpoint: str | None = None

    async def _resolve_endpoints(self) -> None:
        """Discover OAuth endpoints from .well-known/oauth-authorization-server."""
        if self._authorize_endpoint and self._token_endpoint:
            return
        try:
            async with httpx.AsyncClient(verify=self._ssl_verify) as client:
                resp = await client.get(f"{self._api_base}/.well-known/oauth-authorization-server")
                resp.raise_for_status()
                data = resp.json()
                self._authorize_endpoint = data["authorization_endpoint"]
                self._token_endpoint = data["token_endpoint"]
                logger.debug(
                    "Resolved OAuth endpoints: authorize=%s token=%s",
                    self._authorize_endpoint,
                    self._token_endpoint,
                )
        except Exception as exc:
            # Fall back to well-known URL pattern
            logger.warning("Could not discover OAuth endpoints, using defaults: %s", exc)
            self._authorize_endpoint = f"{self._oauth_base}/oauth/authorize"
            self._token_endpoint = f"{self._oauth_base}/oauth/token"

    async def get_authorize_url(self) -> str:
        """Build the OAuth authorize URL for the frontend redirect."""
        await self._resolve_endpoints()
        params = (
            f"?client_id={self._client_id}"
            f"&redirect_uri={self._redirect_uri}"
            f"&response_type=code"
            f"&scope={OAUTH_SCOPE}"
        )
        return f"{self._authorize_endpoint}{params}"

    async def exchange_code(self, code: str) -> str:
        """Exchange authorization code for an opaque access token.

        Args:
            code: The authorization code received from the OAuth redirect.

        Returns:
            Opaque access token (sha256~...) — NOT a JWT.

        Raises:
            AuthError: on invalid code or token endpoint error.
        """
        await self._resolve_endpoints()
        try:
            async with httpx.AsyncClient(verify=self._ssl_verify) as client:
                resp = await client.post(
                    self._token_endpoint,  # type: ignore[arg-type]
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self._redirect_uri,
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    headers={"Accept": "application/json"},
                )
                if resp.status_code != 200:
                    raise AuthError(f"Token exchange failed: {resp.status_code} {resp.text}")
                data = resp.json()
                token = data.get("access_token")
                if not token:
                    raise AuthError("No access_token in token response")
                return token
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError(f"Token exchange request failed: {exc}") from exc

    async def get_user_info(self, opaque_token: str) -> dict[str, Any]:
        """Get user info from OpenShift API using the opaque token.

        Calls GET /apis/user.openshift.io/v1/users/~ which returns
        the currently authenticated user's info.

        Args:
            opaque_token: The sha256~... token from exchange_code()

        Returns:
            Dict with: username (str), groups (list[str]), uid (str)

        Raises:
            AuthError: if token is invalid or expired.
        """
        try:
            async with httpx.AsyncClient(verify=self._ssl_verify) as client:
                resp = await client.get(
                    f"{self._api_base}/apis/user.openshift.io/v1/users/~",
                    headers={"Authorization": f"Bearer {opaque_token}"},
                )
                if resp.status_code == 401:
                    raise AuthError("OpenShift token is invalid or expired")
                if resp.status_code != 200:
                    raise AuthError(f"Failed to get user info: {resp.status_code} {resp.text}")
                data = resp.json()
                return {
                    "username": data.get("metadata", {}).get("name", ""),
                    "groups": data.get("groups") or [],
                    "uid": data.get("metadata", {}).get("uid", ""),
                    "full_name": data.get("fullName", ""),
                }
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError(f"User info request failed: {exc}") from exc
