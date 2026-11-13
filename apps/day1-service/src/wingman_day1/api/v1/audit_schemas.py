"""The bodies of ``/api/day1/audit``: a commit of the day1 or specs project."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from wingman_day1.application.audit import AuditCommit


class CommitRecordOut(BaseModel):
    """A commit in the audit list (the legacy ``CommitRecord`` plus ``repo``)."""

    id: str
    short_id: str
    title: str
    author_name: str
    author_email: str
    authored_date: str
    message: str
    web_url: str
    repo: Literal["day1", "specs"]

    @classmethod
    def of(cls, item: AuditCommit) -> CommitRecordOut:
        """From an audit commit."""
        commit = item.commit
        return cls(
            id=commit.id,
            short_id=commit.short_id,
            title=commit.title,
            author_name=commit.author_name,
            author_email=commit.author_email,
            authored_date=commit.authored_at.isoformat(),
            message=commit.message,
            web_url=commit.web_url,
            repo=item.repo.value,
        )
