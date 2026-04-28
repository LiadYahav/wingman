"""Authentication utilities for Wingman platform services."""

from .rbac import Role, get_user_role, is_allowed, parse_groups_env

__all__ = ["Role", "get_user_role", "is_allowed", "parse_groups_env"]
