"""An in-memory GitLab, for tests and for running Wingman without GitLab (ADR-0005)."""

from wingman_core.infrastructure.fake_gitlab.gitlab import InMemoryGitLab

__all__ = ["InMemoryGitLab"]
