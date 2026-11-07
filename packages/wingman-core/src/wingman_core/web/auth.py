"""Authentication dependencies for route handlers.

    @router.get("/api/day1/clusters")
    async def list_clusters(user: CurrentUser) -> ...

    @router.post("/api/day1/clusters")
    async def create_cluster(user: AdminUser) -> ...

The token is read from ``Authorization: Bearer <token>``; the web app sends
it on every request. ``SessionTokens`` must be on ``app.state.session_tokens``
(``create_base_app`` puts it there).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from wingman_core.domain.users import User
from wingman_core.infrastructure.session_tokens import InvalidSessionError, SessionTokens
from wingman_core.web.errors import Forbidden, Unauthorized


def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("Log in to continue.")
    return token.strip()


async def current_user(request: Request) -> User:
    """The logged-in user; 401 if the token is missing or invalid."""
    tokens: SessionTokens = request.app.state.session_tokens
    try:
        return tokens.verify(_bearer(request))
    except InvalidSessionError as exc:
        raise Unauthorized("Your session is invalid or has expired. Log in again.") from exc


async def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    """The logged-in user if they are an admin; 403 for a viewer."""
    if not user.is_admin:
        raise Forbidden("This needs the admin role.", details={"role": str(user.role)})
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(admin_user)]
