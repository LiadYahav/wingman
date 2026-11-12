"""The catalogue and the defaults, read from the seeded in-memory GitLab."""

from __future__ import annotations

from typing import Any

import pytest

from wingman_core.domain.errors import GitUnavailableError
from wingman_core.domain.git import FileContent, RepoPath
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.domain.machine_configs import ConfigEntry
from wingman_day1.infrastructure.repositories import CachedRepository


def repo(gitlab: InMemoryGitLab, path: str, files: dict[str, str]) -> CachedRepository:
    gitlab.create_project(path, files)
    return CachedRepository(gitlab, TtlCache(), key=path, project=path, ttl=30)


class UnreadableSpecs:
    """The specs project, failing to answer."""

    async def read(self, path: RepoPath, *, ref: str | None = None) -> FileContent:
        raise GitUnavailableError("GitLab timed out")


async def test_the_overview_is_the_fixture_catalogue_and_defaults(context: Day1Context) -> None:
    overview = await context.machine_configs.overview()
    assert set(overview.catalog.static) == {
        "nic-ring-buffer",
        "worker-kubeletconfig-reserved",
        "workers-chrony-configuration",
        "kubevirt-worker-tuning",
    }
    assert set(overview.catalog.hardware) == {"generic", "cisco", "dell", "dell-data"}
    assert overview.defaults.found
    assert overview.defaults.error is None
    assert overview.defaults.defaults.configs[0] == ConfigEntry("nm-conf")
    assert overview.defaults_problems == ()


async def test_no_mc_files_folder_is_an_empty_catalogue_that_says_so(
    gitlab: InMemoryGitLab,
) -> None:
    service = MachineConfigService(
        repo(gitlab, "g/day1", {"sites/configValues.yaml": "{}\n"}),
        repo(gitlab, "g/specs", {"cluster-template.j2": "x\n"}),
    )
    overview = await service.overview()
    assert overview.catalog.static == {}
    assert overview.catalog.problems == (
        "the day1 repo has no mc-files/ folder: no config resolves",
    )
    assert not overview.defaults.found
    assert overview.defaults.defaults.configs == ()


async def test_a_broken_defaults_file_is_reported_not_treated_as_empty(
    gitlab: InMemoryGitLab,
) -> None:
    service = MachineConfigService(
        repo(gitlab, "g/day1", {"mc-files/x.bu": "x\n"}),
        repo(gitlab, "g/specs", {"nodepool-defaults.yaml": "configs: [\n"}),
    )
    reading = await service.defaults()
    assert reading.found
    assert reading.error is not None
    assert "not valid YAML" in str(reading.error)


async def test_defaults_that_do_not_resolve_are_listed(gitlab: InMemoryGitLab) -> None:
    service = MachineConfigService(
        repo(gitlab, "g/day1", {"mc-files/x.bu": "x\n"}),
        repo(gitlab, "g/specs", {"nodepool-defaults.yaml": "configs:\n  - name: x\n  - name: y\n"}),
    )
    overview = await service.overview()
    assert overview.defaults_problems == ("configs[1]: no machine config 'y' in mc-files/",)


async def test_a_failed_read_of_the_defaults_is_not_swallowed(gitlab: InMemoryGitLab) -> None:
    day1 = repo(gitlab, "g/day1", {"mc-files/x.bu": "x\n"})
    service = MachineConfigService(day1, UnreadableSpecs())  # ty: ignore[invalid-argument-type]
    with pytest.raises(GitUnavailableError):
        await service.overview()


async def test_the_catalogue_is_cached_until_the_repo_moves(
    context: Day1Context, gitlab: InMemoryGitLab, support: Any
) -> None:
    before = await context.machine_configs.catalog()
    await support.push(
        gitlab, support.DAY1, branch="main", file="mc-files/new-config.bu", content="x\n"
    )
    assert await context.machine_configs.catalog() == before
    context.repos[RepoKey.DAY1].forget_files()
    after = await context.machine_configs.catalog()
    assert "new-config" in after.static
