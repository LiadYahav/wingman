"""The bodies of ``/api/day2`` approvals: approve, edit, the MR and its diff, the audit."""

from __future__ import annotations

from pydantic import BaseModel, Field

from wingman_core.domain.git import Commit
from wingman_core.web.schemas import FileDiffOut
from wingman_day2.api.v1.schemas import MRDetailOut, _Input

# ── Requests ────────────────────────────────────────────────────────────────


class ApproveBody(_Input):
    """Approve and merge the commit that was reviewed."""

    sha: str = Field(min_length=7, description="The MR head the approver reviewed (MRDetail.sha).")


class EditedFile(_Input):
    """New content for a file the MR changes."""

    path: str
    content: str
    last_commit_id: str | None = None


class EditMergeRequestBody(_Input):
    """Push edits onto an MR's branch; ``sha`` is the head the editor reviewed (409 if it moved)."""

    files: list[EditedFile] = Field(min_length=1)
    message: str = ""
    sha: str | None = Field(default=None, min_length=7, max_length=64)


# ── Responses ───────────────────────────────────────────────────────────────


class ApprovalDetailOut(BaseModel):
    """An MR and its diff (the legacy ``{mr, diffs}`` shape)."""

    mr: MRDetailOut
    diffs: list[FileDiffOut]


class CommitRecordOut(BaseModel):
    """A commit (legacy audit shape plus ``team``)."""

    id: str
    short_id: str
    title: str
    author_name: str
    author_email: str
    authored_date: str
    message: str
    web_url: str
    team: str
    repo: str = "day2"

    @classmethod
    def of(cls, team: str, commit: Commit) -> CommitRecordOut:
        """From the core commit."""
        return cls(
            id=commit.id,
            short_id=commit.short_id,
            title=commit.title,
            author_name=commit.author_name,
            author_email=commit.author_email,
            authored_date=commit.authored_at.isoformat(),
            message=commit.message,
            web_url=commit.web_url,
            team=team,
        )
