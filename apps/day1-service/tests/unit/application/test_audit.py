"""Audit: commits and MRs across both projects, each tagged with its repository."""

from __future__ import annotations

from typing import Any

import pytest

from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.clusters import CreateCluster
from wingman_day1.domain.errors import ResourceNotFoundError
from wingman_day1.domain.specs import validate_spec


async def make_changes(context: Day1Context, support: Any) -> None:
    body = support.create_body()
    cluster = await context.clusters.create(
        CreateCluster(
            name=body["name"],
            site=body["site"],
            mce=body["mce"],
            spec_name=body["spec_name"],
            spec_version=body["spec_version"],
            variables=body["variables"],
        ),
        user=support.ALICE,
    )
    await context.approvals.approve(
        RepoKey.DAY1,
        cluster.merge_request.ref.iid,
        sha=cluster.merge_request.sha,
        approver=support.BOB,
    )
    spec = validate_spec({"metadata": {"name": "agent-mini", "version": "1"}})
    await context.specs.create(spec, user=support.ALICE)


async def test_merge_requests_carry_the_repository_they_belong_to(
    context: Day1Context, support: Any
) -> None:
    # Legacy: every audit MR came back tagged "day1", so a specs MR was looked up
    # in the day1 project.
    await make_changes(context, support)
    items = await context.audit.merge_requests(per_page=10, page=1)
    assert [(i.repo, i.change.merge_request.title.split("]")[0]) for i in items] == [
        (RepoKey.SPECS, "[Wingman/Specs"),
        (RepoKey.DAY1, "[Wingman/Day1"),
    ]
    assert items[1].change.requested_by == "alice"


async def test_commits_are_merged_newest_first_and_paginated(
    context: Day1Context, support: Any
) -> None:
    await make_changes(context, support)
    everything = await context.audit.commits(per_page=50, page=1)
    assert {c.repo for c in everything} == {RepoKey.DAY1, RepoKey.SPECS}
    times = [c.commit.authored_at for c in everything]
    assert times == sorted(times, reverse=True)
    first = await context.audit.commits(per_page=1, page=1)
    second = await context.audit.commits(per_page=1, page=2)
    assert [c.commit.id for c in first + second] == [c.commit.id for c in everything[:2]]
    authors = {c.commit.author_name for c in everything}
    assert "Alice Admin" in authors


async def test_a_commit_diff_is_found_whatever_repository_is_named(
    context: Day1Context, support: Any
) -> None:
    await make_changes(context, support)
    specs_commit = next(
        c for c in await context.audit.commits(per_page=50, page=1) if c.repo is RepoKey.SPECS
    )
    # The web app tags every day1-service commit "day1"; the specs commit is still found.
    diffs = await context.audit.commit_diff(RepoKey.DAY1, specs_commit.commit.id)
    assert diffs


async def test_an_unknown_commit_is_not_found(context: Day1Context) -> None:
    with pytest.raises(ResourceNotFoundError):
        await context.audit.commit_diff(RepoKey.DAY1, "deadbeefdeadbeef")
