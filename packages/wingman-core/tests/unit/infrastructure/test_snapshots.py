"""RepoSnapshots: one head check per TTL, one archive per commit, file by file as the fallback."""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from wingman_core.domain.errors import InvalidRequestError
from wingman_core.domain.git import (
    Branch,
    EntryKind,
    FileChange,
    FileContent,
    RepoArchive,
    RepoPath,
    TreeEntry,
    tree_of,
)
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.infrastructure.snapshots import RepoSnapshots

FILES = {"README.md": "# r\n", "sites/s1/values.yaml": "a: 1\n", "sites/s1/mces/m/values.yaml": ""}


class Counting(InMemoryGitLab):
    """The fake, counting calls, with an archive that can be refused."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: Counter[str] = Counter()
        self.refuse_archives = False

    async def get_branch(self, project_id: int, name: str) -> Branch:
        self.calls["get_branch"] += 1
        return await super().get_branch(project_id, name)

    async def read_archive(self, project_id: int, sha: str, *, max_bytes: int) -> RepoArchive:
        self.calls["read_archive"] += 1
        await asyncio.sleep(0)  # let concurrent readers pile up on one download
        if self.refuse_archives:
            raise InvalidRequestError("GET .../archive.tar.gz: 429 too many requests")
        return await super().read_archive(project_id, sha, max_bytes=max_bytes)

    async def read_file(self, project_id: int, path: RepoPath, ref: str) -> FileContent:
        self.calls["read_file"] += 1
        return await super().read_file(project_id, path, ref)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def gitlab() -> Counting:
    return Counting()


def snapshots(gitlab: Counting, clock: Clock, **budget: int) -> RepoSnapshots:
    return RepoSnapshots(gitlab, TtlCache(clock=clock), ttl=15, **budget)


async def change(gitlab: InMemoryGitLab, project_id: int, path: str, content: str) -> None:
    await gitlab.commit(
        project_id,
        branch="main",
        message=f"change {path}",
        changes=[FileChange.update(RepoPath(path), content, last_commit_id=None)],
    )


async def test_an_unchanged_branch_costs_one_head_check_per_ttl(
    gitlab: Counting, clock: Clock
) -> None:
    project = gitlab.create_project("g/p", FILES)
    reader = snapshots(gitlab, clock)
    files = await reader.files(project.id, "main")
    assert files is not None and files.paths == frozenset(FILES)
    assert await files.read(RepoPath("sites/s1/values.yaml")) == "a: 1\n"
    assert await files.read(RepoPath("nope.yaml")) is None
    await reader.files(project.id, "main")
    clock.now += 16
    again = await reader.files(project.id, "main")
    await asyncio.sleep(0)  # the head check runs in the background (ADR-0041)
    assert again is files
    assert gitlab.calls == Counter(get_branch=2, read_archive=1)


async def test_past_the_ttl_the_known_head_answers_while_one_check_runs(
    gitlab: Counting, clock: Clock
) -> None:
    project = gitlab.create_project("g/p", FILES)
    reader = snapshots(gitlab, clock)
    before = await reader.files(project.id, "main")
    await change(gitlab, project.id, "README.md", "# new\n")
    clock.now += 16
    stale = await asyncio.gather(*(reader.files(project.id, "main") for _ in range(5)))
    assert all(s is before for s in stale)  # no reader waited on GitLab
    await asyncio.sleep(0)
    assert gitlab.calls["get_branch"] == 2  # one check for all five
    after = await reader.files(project.id, "main")
    assert after is not None and before is not None and after.commit_id != before.commit_id


async def test_a_head_older_than_a_minute_is_checked_before_answering(
    gitlab: Counting, clock: Clock
) -> None:
    project = gitlab.create_project("g/p", FILES)
    reader = snapshots(gitlab, clock)
    await reader.files(project.id, "main")
    await change(gitlab, project.id, "README.md", "# new\n")
    clock.now += 61
    files = await reader.files(project.id, "main")
    assert files is not None and await files.read(RepoPath("README.md")) == "# new\n"


async def test_a_moved_branch_is_read_again_at_its_new_head(gitlab: Counting, clock: Clock) -> None:
    project = gitlab.create_project("g/p", FILES)
    reader = snapshots(gitlab, clock)
    before = await reader.files(project.id, "main")
    await change(gitlab, project.id, "README.md", "# new\n")
    clock.now += 16
    await reader.files(project.id, "main")  # answers the known head, checks it in the background
    await asyncio.sleep(0)
    after = await reader.files(project.id, "main")
    assert before is not None and after is not None and before.commit_id != after.commit_id
    assert await after.read(RepoPath("README.md")) == "# new\n"
    assert await before.read(RepoPath("README.md")) == "# r\n"  # a commit's files never change
    assert gitlab.calls["read_archive"] == 2


async def test_forget_checks_the_head_again_before_the_ttl(gitlab: Counting, clock: Clock) -> None:
    project = gitlab.create_project("g/p", FILES)
    reader = snapshots(gitlab, clock)
    await reader.files(project.id, "main")
    await change(gitlab, project.id, "README.md", "# mine\n")
    reader.forget(project.id)
    files = await reader.files(project.id, "main")
    assert files is not None and await files.read(RepoPath("README.md")) == "# mine\n"


async def test_concurrent_readers_share_one_download(gitlab: Counting, clock: Clock) -> None:
    project = gitlab.create_project("g/p", FILES)
    reader = snapshots(gitlab, clock)
    head = await reader.head(project.id, "main")
    assert head is not None
    results = await asyncio.gather(*(reader.at(project.id, head) for _ in range(5)))
    assert len({id(r) for r in results}) == 1
    assert gitlab.calls["read_archive"] == 1


async def test_a_refused_archive_is_read_file_by_file_at_the_same_commit(
    gitlab: Counting, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    project = gitlab.create_project("g/p", FILES)
    gitlab.refuse_archives = True
    reader = snapshots(gitlab, clock)
    files = await reader.files(project.id, "main")
    assert files is not None and files.paths == frozenset(FILES)
    await change(gitlab, project.id, "README.md", "# later\n")
    path = RepoPath("README.md")
    assert await asyncio.gather(files.read(path), files.read(path)) == ["# r\n", "# r\n"]
    assert await files.read(RepoPath("nope.yaml")) is None
    assert gitlab.calls["read_file"] == 1
    assert "file by file" in caplog.text and "429" in caplog.text


async def test_an_archive_over_the_budget_is_read_file_by_file(
    gitlab: Counting, clock: Clock
) -> None:
    project = gitlab.create_project("g/p", FILES)
    files = await snapshots(gitlab, clock, max_archive_bytes=4).files(project.id, "main")
    assert files is not None and await files.read(RepoPath("README.md")) == "# r\n"
    assert gitlab.calls["read_file"] == 1


async def test_held_archives_stay_within_the_budget(gitlab: Counting, clock: Clock) -> None:
    one = gitlab.create_project("g/one", {"a.yaml": "x" * 60})
    two = gitlab.create_project("g/two", {"b.yaml": "y" * 60})
    reader = snapshots(gitlab, clock, max_held_bytes=100)
    await reader.files(one.id, "main")
    await reader.files(two.id, "main")  # one is dropped: both would be 120 bytes
    await reader.files(two.id, "main")
    await reader.files(one.id, "main")
    assert gitlab.calls["read_archive"] == 3


async def test_a_missing_branch_has_no_files(gitlab: Counting, clock: Clock) -> None:
    project = gitlab.create_project("g/p", FILES)
    assert await snapshots(gitlab, clock).files(project.id, "no-such-branch") is None


async def test_a_file_that_is_not_utf8_is_refused_like_read_file(clock: Clock) -> None:
    class Binary(Counting):
        async def read_archive(self, project_id: int, sha: str, *, max_bytes: int) -> RepoArchive:
            return RepoArchive(sha, {"logo.png": b"\x89PNG\xff"})

    gitlab = Binary()
    project = gitlab.create_project("g/p", {"logo.png": "x"})
    files = await snapshots(gitlab, clock).files(project.id, "main")
    assert files is not None
    with pytest.raises(InvalidRequestError, match="not UTF-8"):
        await files.read(RepoPath("logo.png"))


def test_tree_of_lists_files_and_the_directories_they_imply() -> None:
    paths = frozenset(FILES)
    entry = TreeEntry
    assert tree_of(paths, RepoPath("sites"), recursive=False) == [
        entry(RepoPath("sites/s1"), EntryKind.DIRECTORY)
    ]
    assert tree_of(paths, RepoPath("sites"), recursive=True) == [
        entry(RepoPath("sites/s1"), EntryKind.DIRECTORY),
        entry(RepoPath("sites/s1/mces"), EntryKind.DIRECTORY),
        entry(RepoPath("sites/s1/mces/m"), EntryKind.DIRECTORY),
        entry(RepoPath("sites/s1/mces/m/values.yaml"), EntryKind.FILE),
        entry(RepoPath("sites/s1/values.yaml"), EntryKind.FILE),
    ]
    assert [e.path for e in tree_of(paths, RepoPath.root(), recursive=False) or []] == [
        RepoPath("README.md"),
        RepoPath("sites"),
    ]
    assert tree_of(paths, RepoPath("nope"), recursive=True) is None
    assert tree_of(frozenset(), RepoPath.root(), recursive=True) is None
