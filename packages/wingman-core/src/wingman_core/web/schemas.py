"""Response models both services answer with the same shape."""

from __future__ import annotations

from pydantic import BaseModel

from wingman_core.domain.git import FileDiff


class FileDiffOut(BaseModel):
    """One file of a diff (an MR's, or a commit's): the web renders both services' alike."""

    old_path: str
    new_path: str
    diff: str
    new_file: bool
    renamed_file: bool
    deleted_file: bool

    @classmethod
    def of(cls, diff: FileDiff) -> FileDiffOut:
        """From the core diff."""
        return cls(
            old_path=str(diff.old_path),
            new_path=str(diff.new_path),
            diff=diff.diff,
            new_file=diff.new_file,
            renamed_file=diff.renamed_file,
            deleted_file=diff.deleted_file,
        )
