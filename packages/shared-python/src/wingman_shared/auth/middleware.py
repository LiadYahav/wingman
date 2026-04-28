"""FastAPI authentication dependency for Wingman services.

Usage in route handlers:
    from wingman_shared.auth.middleware import get_current_user
    from wingman_shared.models import UserInfo

    @router.get("/api/day1/clusters")
    async def list_clusters(user: Annotated[UserInfo, Depends(get_current_user)]):
        ...
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from ..exceptions import AuthError
from ..models import UserInfo

logger = logging.getLogger(__name__)

# tokenUrl is informational only (not a real password flow) — documents where
# the token comes from for OpenAPI/Swagger UI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/callback")


def make_auth_dependency(jwt_manager: object) -> object:
    """Factory that creates a get_current_user dependency bound to a JWTManager.

    Called once during service startup, not per-request.

    Args:
        jwt_manager: A JWTManager instance

    Returns:
        An async FastAPI dependency function
    """

    async def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)],
    ) -> UserInfo:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt_manager.validate_token(token)  # type: ignore[union-attr]
            username: str = payload.get("sub", "")
            groups: list[str] = payload.get("groups", [])
            uid: str = payload.get("uid", "")
            if not username:
                raise credentials_exception
            return UserInfo(username=username, groups=groups, uid=uid)
        except AuthError as exc:
            logger.debug("Auth failed: %s", exc)
            raise credentials_exception from exc

    return get_current_user
