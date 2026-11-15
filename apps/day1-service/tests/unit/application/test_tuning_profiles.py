"""The tuning catalogue, read from ``tuning/`` through the cached day1 repo (ADR-0061)."""

from __future__ import annotations

import pytest

from wingman_core.domain.errors import GitUnavailableError
from wingman_core.domain.git import FileContent, RepoPath, TreeEntry
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.tuning_profiles import TuningProfileService
from wingman_day1.infrastructure.repositories import CachedRepository
from wingman_day1.ports import RepoReads


def repo(gitlab: InMemoryGitLab, files: dict[str, str]) -> CachedRepository:
    gitlab.create_project("g/day1", files)
    return CachedRepository(gitlab, TtlCache(), key="g/day1", project="g/day1", ttl=30)


class UnreadableFiles:
    """A day1 repo that lists ``tuning/`` and then fails to read a file."""

    def __init__(self, inner: RepoReads) -> None:
        self._inner = inner

    async def tree(self, path: RepoPath, *, recursive: bool = False) -> list[TreeEntry]:
        return await self._inner.tree(path, recursive=recursive)

    async def read(self, path: RepoPath, *, ref: str | None = None) -> FileContent:
        raise GitUnavailableError("GitLab timed out")


async def test_the_service_reads_the_fixture_catalogue(context: Day1Context) -> None:
    found = await context.machine_configs.tuning()
    assert found.found
    assert sorted(found.shared) == [
        "performance-pinned",
        "tuned-network-latency",
        "tuned-pinned-irq",
        "tuned-sysctl-baseline",
    ]
    assert list(found.variants) == ["prod-lark-site1"]


async def test_no_tuning_folder_is_an_empty_catalogue_that_says_so(gitlab: InMemoryGitLab) -> None:
    found = await TuningProfileService(repo(gitlab, {"sites/configValues.yaml": "{}\n"})).catalog()
    assert (found.found, found.shared, found.problems) == (False, {}, ())


async def test_documentation_is_not_read(gitlab: InMemoryGitLab) -> None:
    day1 = repo(gitlab, {"tuning/README.md": "# notes\n", "sites/configValues.yaml": "{}\n"})
    found = await TuningProfileService(UnreadableFiles(day1)).catalog()  # ty: ignore[invalid-argument-type]
    assert (found.found, found.shared, found.problems) == (True, {}, ())


async def test_a_failed_read_fails_the_catalogue(gitlab: InMemoryGitLab) -> None:
    day1 = repo(gitlab, {"tuning/tuned-a.yaml": "a: 1\n"})
    with pytest.raises(GitUnavailableError):
        await TuningProfileService(UnreadableFiles(day1)).catalog()  # ty: ignore[invalid-argument-type]
