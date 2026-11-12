"""The fake's membership model: what access_level answers per account (ADR-0043)."""

from __future__ import annotations

import pytest

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import AccessLevel
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab


async def test_the_account_owns_the_projects_it_creates() -> None:
    gitlab = InMemoryGitLab()
    project = gitlab.create_project("sigs/team", {"a": "1"})
    assert await gitlab.access_level(project.id) is AccessLevel.OWNER


async def test_set_access_level_replaces_the_membership_and_none_removes_it() -> None:
    gitlab = InMemoryGitLab()
    project = gitlab.create_project("sigs/team", {"a": "1"}, visibility="internal")
    gitlab.set_access_level(project.id, AccessLevel.REPORTER)
    assert await gitlab.access_level(project.id) is AccessLevel.REPORTER
    gitlab.set_access_level(project.id, AccessLevel.NONE)
    assert await gitlab.access_level(project.id) is AccessLevel.NONE


async def test_a_private_project_without_access_is_not_found_as_on_gitlab() -> None:
    gitlab = InMemoryGitLab()
    private = gitlab.create_project("sigs/team", {"a": "1"})
    internal = gitlab.create_project("sigs/open", {"a": "1"}, visibility="internal")
    public = gitlab.create_project("sigs/public", {"a": "1"}, visibility="public")
    outsider = gitlab.as_account("outsider")
    with pytest.raises(NotFoundError):
        await outsider.access_level(private.id)
    assert await outsider.access_level(internal.id) is AccessLevel.NONE
    assert await outsider.access_level(public.id) is AccessLevel.NONE
    # Removing the account's own membership hides the private project from it too.
    gitlab.set_access_level(private.id, AccessLevel.NONE)
    with pytest.raises(NotFoundError):
        await gitlab.access_level(private.id)
    gitlab.add_group_member("sigs", AccessLevel.GUEST, username="outsider")
    assert await outsider.access_level(private.id) is AccessLevel.GUEST


async def test_group_membership_is_inherited_from_every_group_above() -> None:
    gitlab = InMemoryGitLab()
    project = gitlab.create_project("top/sigs/team", {"a": "1"}, visibility="internal")
    other = gitlab.create_project("elsewhere/team", {"a": "1"}, visibility="internal")
    member = gitlab.as_account("member")
    assert await member.access_level(project.id) is AccessLevel.NONE
    gitlab.add_group_member("top", AccessLevel.DEVELOPER, username="member")
    assert await member.access_level(project.id) is AccessLevel.DEVELOPER
    assert await member.access_level(other.id) is AccessLevel.NONE


async def test_the_higher_of_project_and_group_membership_counts() -> None:
    gitlab = InMemoryGitLab()
    project = gitlab.create_project("sigs/team", {"a": "1"})
    gitlab.add_group_member("sigs", AccessLevel.REPORTER, username="member")
    gitlab.set_access_level(project.id, AccessLevel.MAINTAINER, username="member")
    assert await gitlab.as_account("member").access_level(project.id) is AccessLevel.MAINTAINER


async def test_another_account_shares_the_state_but_not_the_access() -> None:
    gitlab = InMemoryGitLab()
    project = gitlab.create_project("sigs/team", {"a": "1"}, visibility="internal")
    member = gitlab.as_account("member")
    later = gitlab.create_project("sigs/later", {"b": "2"})
    assert [p.path_with_namespace for p in await member.list_group_projects("sigs")] == [
        "sigs/later",
        "sigs/team",
    ]
    assert await member.access_level(project.id) is AccessLevel.NONE
    assert await gitlab.access_level(later.id) is AccessLevel.OWNER


async def test_an_unknown_project_is_not_found() -> None:
    gitlab = InMemoryGitLab()
    with pytest.raises(NotFoundError):
        await gitlab.access_level(99)
    with pytest.raises(NotFoundError):
        gitlab.set_access_level(99, AccessLevel.REPORTER)
