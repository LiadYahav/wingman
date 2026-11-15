"""The tuning-profile catalogue, read from ``tuning/`` through the cached day1 repo (ADR-0061).

One recursive tree listing and the files' contents, all from the day1
repo's snapshot (ADR-0035), cached like every other read (ADR-0011) and
never written. A repo without ``tuning/`` is an empty catalogue that says
so (``found: false``); a failed read fails the request (ADR-0004).
"""

from __future__ import annotations

import asyncio

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import EntryKind
from wingman_day1.domain.tuning_profiles import (
    MAX_TUNING_FILES,
    TUNING_DIR,
    TuningCatalog,
    is_hidden,
)
from wingman_day1.ports import RepoReads


class TuningProfileService:
    """Read ``tuning/`` from the day1 repo."""

    def __init__(self, day1: RepoReads) -> None:
        """Read through ``day1``, the cached day1 repo."""
        self._day1 = day1

    async def catalog(self) -> TuningCatalog:
        """Every shared profile and per-cluster variant, and the files that are neither."""
        try:
            entries = await self._day1.tree(TUNING_DIR, recursive=True)
        except NotFoundError:
            return TuningCatalog(found=False)
        paths = sorted(
            e.path for e in entries if e.kind is EntryKind.FILE and not is_hidden(str(e.path))
        )
        files = await asyncio.gather(*(self._day1.read(p) for p in paths[:MAX_TUNING_FILES]))
        return TuningCatalog.from_files(
            {str(p): f.content for p, f in zip(paths, files, strict=False)}, listed=len(paths)
        )
