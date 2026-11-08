"""CachedRepository: which reads are cached, for how long, and what each write clears.

Files and trees at the default branch come from one archive per commit (ADR-0035).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import pytest

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import (
    Branch,
    Commit,
    FileChange,
    FileContent,
    FileDiff,
    Project,
    RepoArchive,
    RepoPath,
    TreeEntry,
)
from wingman_core.domain.merge_request import MergeRequest, MRState, NewMergeRequest
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.fixtures import default_fixture_root, load_fixture_projects, seed_fake
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.infrastructure.repositories import CachedRepository

DAY1 = "gitops-day1/platform-config"
VALUES = RepoPath("sites/site1/mces/ocp4-prod-mce-site1-a/values.yaml")
HERZI = RepoPath("sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-herzi-site1.yaml")


class CountingGitLab(InMemoryGitLab):
    """The in-memory GitLab, counting every port call by method."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: Counter[str] = Counter()

    async def get_project(self, project: int | str) -> Project:
        self.calls["get_project"] += 1
        return await super().get_project(project)

    async def list_tree(
        self, project_id: int, path: RepoPath, ref: str, *, recursive: bool = False
    ) -> list[TreeEntry]:
        self.calls["list_tree"] += 1
        return await super().list_tree(project_id, path, ref, recursive=recursive)

    async def read_file(self, project_id: int, path: RepoPath, ref: str) -> FileContent:
        self.calls["read_file"] += 1
        return await super().read_file(project_id, path, ref)

    async def get_branch(self, project_id: int, name: str) -> Branch:
        self.calls["get_branch"] += 1
        return await super().get_branch(project_id, name)

    async def read_archive(self, project_id: int, sha: str, *, max_bytes: int) -> RepoArchive:
        self.calls["read_archive"] += 1
        return await super().read_archive(project_id, sha, max_bytes=max_bytes)

    async def list_commits(
        self, project_id: int, *, ref: str, path: RepoPath | None = None, limit: int = 50
    ) -> list[Commit]:
        self.calls["list_commits"] += 1
        return await super().list_commits(project_id, ref=ref, path=path, limit=limit)

    async def get_commit(self, project_id: int, sha: str) -> Commit:
        self.calls["get_commit"] += 1
        return await super().get_commit(project_id, sha)

    async def commit_diff(self, project_id: int, sha: str) -> list[FileDiff]:
        self.calls["commit_diff"] += 1
        return await super().commit_diff(project_id, sha)

    async def list_merge_requests(
        self,
        project_id: int,
        *,
        state: MRState | None = MRState.OPENED,
        labels: Sequence[str] = (),
        limit: int = 100,
    ) -> list[MergeRequest]:
        self.calls["list_merge_requests"] += 1
        return await super().list_merge_requests(
            project_id, state=state, labels=labels, limit=limit
        )


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def counting() -> CountingGitLab:
    gitlab = CountingGitLab()
    seed_fake(gitlab, load_fixture_projects(default_fixture_root()))
    return gitlab


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cache(clock: Clock) -> TtlCache:
    return TtlCache(clock=clock)


@pytest.fixture
def repo(counting: CountingGitLab, cache: TtlCache) -> CachedRepository:
    return CachedRepository(counting, cache, key="day1", project=DAY1, ttl=30.0)


async def _read_everything(repo: CachedRepository, sha: str) -> None:
    await repo.project()
    await repo.tree(RepoPath("sites"), recursive=True)
    await repo.tree(RepoPath("sites"))
    await repo.read(VALUES)
    await repo.history(HERZI)
    await repo.commits(limit=10)
    await repo.commit(sha)
    await repo.commit_diff(sha)
    await repo.merge_requests(state=MRState.OPENED, labels=("wingman",))


async def test_every_read_family_is_cached(
    repo: CachedRepository, counting: CountingGitLab
) -> None:
    sha = (await repo.read(HERZI)).last_commit_id
    counting.calls.clear()
    await _read_everything(repo, sha)
    first = Counter(counting.calls)
    await _read_everything(repo, sha)
    assert counting.calls == first
    assert repo.key == "day1"


async def test_after_the_ttl_only_the_head_is_checked_until_the_branch_moves(
    repo: CachedRepository, counting: CountingGitLab, clock: Clock
) -> None:
    await repo.read(VALUES)
    clock.now += 31
    await repo.read(VALUES)
    assert (counting.calls["get_branch"], counting.calls["read_archive"]) == (2, 1)
    project = await repo.project()
    await counting.commit(
        project.id,
        branch="main",
        message="m",
        changes=[FileChange.update(VALUES, "changed: true\n", last_commit_id=None)],
    )
    clock.now += 31
    assert (await repo.read(VALUES)).content == "changed: true\n"
    assert (counting.calls["read_archive"], counting.calls["read_file"]) == (2, 0)


async def test_reads_at_another_ref_are_never_cached(
    repo: CachedRepository, counting: CountingGitLab
) -> None:
    sha = (await repo.read(VALUES)).last_commit_id
    counting.calls.clear()
    await repo.read(VALUES, ref=sha)
    await repo.read(VALUES, ref=sha)
    assert counting.calls["read_file"] == 2
    await repo.read(VALUES, ref="main")
    await repo.read(VALUES, ref="main")
    assert counting.calls["read_file"] == 2, "the default branch by name is the cached read"


async def test_a_missing_file_or_directory_is_not_found_without_a_call(
    repo: CachedRepository, counting: CountingGitLab
) -> None:
    await repo.project()
    for _ in range(2):
        with pytest.raises(NotFoundError):
            await repo.read(RepoPath("sites/nope.yaml"))
        with pytest.raises(NotFoundError):
            await repo.tree(RepoPath("nope"))
    assert counting.calls["read_archive"] == 1
    assert counting.calls["read_file"] == counting.calls["list_tree"] == 0


async def test_changed_since_asks_what_gitlabs_write_guard_asks(
    repo: CachedRepository, counting: CountingGitLab
) -> None:
    project = await repo.project()
    read_at = (await repo.read(VALUES)).last_commit_id

    async def change(path: RepoPath) -> None:
        await counting.commit(
            project.id,
            branch="main",
            message=f"change {path}",
            changes=[FileChange.update(path, "x: 1\n", last_commit_id=None)],
        )

    await change(HERZI)  # the head moves; VALUES does not change
    assert not await repo.changed_since(VALUES, read_at)
    await change(VALUES)
    assert await repo.changed_since(VALUES, read_at)
    assert await repo.changed_since(VALUES, "0" * 40)  # unknown: reload


async def test_forget_files_checks_the_head_and_history_again_but_not_mrs_or_commits(
    repo: CachedRepository, counting: CountingGitLab
) -> None:
    sha = (await repo.read(HERZI)).last_commit_id
    await _read_everything(repo, sha)
    counting.calls.clear()
    repo.forget_files()
    await _read_everything(repo, sha)
    assert counting.calls == Counter({"get_branch": 1, "list_commits": 2})


async def test_forget_merge_requests_clears_only_mr_lists(
    repo: CachedRepository, counting: CountingGitLab
) -> None:
    sha = (await repo.read(HERZI)).last_commit_id
    await _read_everything(repo, sha)
    counting.calls.clear()
    repo.forget_merge_requests()
    await _read_everything(repo, sha)
    assert counting.calls == Counter({"list_merge_requests": 1})


async def test_a_new_mr_is_seen_only_after_the_lists_are_forgotten(
    repo: CachedRepository, counting: CountingGitLab
) -> None:
    project = await repo.project()
    assert await repo.merge_requests(state=MRState.OPENED) == []
    await counting.commit(
        project.id,
        branch="feature",
        start_branch="main",
        message="m",
        changes=[FileChange.create(RepoPath("x.yaml"), "a: 1\n")],
    )
    await counting.create_merge_request(project.id, NewMergeRequest("feature", "main", "t"))
    assert await repo.merge_requests(state=MRState.OPENED) == []
    repo.forget_merge_requests()
    assert len(await repo.merge_requests(state=MRState.OPENED)) == 1


async def test_two_repositories_share_one_cache_without_clearing_each_other(
    counting: CountingGitLab, cache: TtlCache
) -> None:
    day1 = CachedRepository(counting, cache, key="day1", project=DAY1, ttl=30.0)
    specs = CachedRepository(counting, cache, key="specs", project="wingman/cluster-specs", ttl=30)
    await day1.read(VALUES)
    await specs.read(RepoPath("cluster-template.j2"))
    counting.calls.clear()
    specs.forget_files()
    await day1.read(VALUES)
    await specs.read(RepoPath("cluster-template.j2"))
    assert counting.calls == Counter({"get_branch": 1})


def test_cache_keys_put_each_family_under_its_prefix() -> None:
    path = RepoPath("a/b.yaml")
    for key in (
        keys.history("day1", path, limit=5),
        keys.commits("day1", limit=5),
    ):
        assert key.startswith(keys.files_prefix("day1"))
    listed = keys.merge_requests("day1", state=None, labels=("b", "a"), limit=5)
    assert listed.startswith(keys.merge_requests_prefix("day1"))
    assert listed == keys.merge_requests("day1", state=None, labels=("a", "b"), limit=5)
    assert ":any:" in listed
    for immutable in (
        keys.commit("day1", "abc"),
        keys.commit_diff("day1", "abc"),
        keys.project("day1"),
    ):
        assert not immutable.startswith(keys.files_prefix("day1"))
        assert not immutable.startswith(keys.merge_requests_prefix("day1"))
    assert keys.day2_installed("s", "m", "c") == "day2:installed:s:m:c"
