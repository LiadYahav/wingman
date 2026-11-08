"""The changes day1 asks for: a cluster created, modified or deleted; a spec likewise.

They say *what* should change, not how. Today a :class:`ClusterChange`
becomes one commit on a new branch plus a merge request (Wingman owns
day1); when the team's ``create-cluster`` workflow exists, the same change
can start that workflow instead (ADR-0017).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from wingman_core.domain.merge_request import MergeRequest
from wingman_core.domain.users import User
from wingman_day1.domain.paths import ClusterRef


class ClusterAction(StrEnum):
    """What happens to a cluster file; the values are the MR label and footer action."""

    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class SpecAction(StrEnum):
    """What happens to a spec file; the values are the MR label and footer action."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class ClusterChange:
    """One cluster file to create, replace or remove, on behalf of a user.

    ``last_commit_id`` is the commit the caller read the file at; a modify or
    delete fails with a revision conflict if the file moved since (ADR-0006).
    """

    action: ClusterAction
    cluster: ClusterRef
    requested_by: User
    summary: str
    """The human part of the MR description."""
    content: str | None = None
    last_commit_id: str | None = None
    spec_name: str | None = None
    spec_version: str | None = None

    def __post_init__(self) -> None:
        """Reject combinations that cannot be applied."""
        if (self.action is ClusterAction.DELETE) != (self.content is None):
            raise ValueError("a delete carries no content; a create or modify needs content")
        if self.action is ClusterAction.CREATE and self.last_commit_id is not None:
            raise ValueError("a create has no previous revision")
        if self.action is not ClusterAction.CREATE and not self.last_commit_id:
            raise ValueError(f"a {self.action} needs the last_commit_id it was read at")


@dataclass(frozen=True, slots=True)
class SpecChange:
    """One spec file to create, replace or remove, on behalf of a user."""

    action: SpecAction
    name: str
    version: str
    requested_by: User
    summary: str
    content: str | None = None
    last_commit_id: str | None = None

    def __post_init__(self) -> None:
        """Reject combinations that cannot be applied."""
        if (self.action is SpecAction.DELETE) != (self.content is None):
            raise ValueError("a delete carries no content; a create or update needs content")
        if self.action is not SpecAction.CREATE and not self.last_commit_id:
            raise ValueError(f"a {self.action} needs the last_commit_id it was read at")


@dataclass(frozen=True, slots=True)
class ProvisionResult:
    """What a change produced. Today always a merge request awaiting approval."""

    merge_request: MergeRequest
