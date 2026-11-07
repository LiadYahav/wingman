"""Spec use cases: reading the catalog and proposing spec changes as MRs."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.domain.errors import (
    AlreadyInUseError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleError,
)
from wingman_day1.domain.specs import ClusterSpec, validate_spec


def spec(name: str = "agent-mini", version: str = "1.0.0", **body: Any) -> ClusterSpec:
    return validate_spec(
        {
            "metadata": {"name": name, "version": version, "description": "small"},
            "spec": {"day1": {"values": {"nodepools": [{"replicas": 1}]}, **body}},
        }
    )


async def test_the_catalog_lists_every_spec_with_the_shared_template(
    context: Day1Context,
) -> None:
    entries = await context.specs.entries()
    assert [e.name for e in entries] == ["agent-single", "agent-standard"]
    assert all(e.spec is not None and "nodepool:" in e.spec.spec.day1.template for e in entries)


async def test_a_broken_spec_file_is_listed_with_its_error(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    # Legacy: a spec that failed to load was logged and dropped from the list.
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/broken.yaml", content="metadata: [\n"
    )
    broken = next(e for e in await context.specs.entries() if e.name == "broken")
    assert broken.spec is None
    assert broken.error is not None


async def test_a_spec_whose_name_differs_from_its_file_is_broken(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    content = yaml.safe_dump({"metadata": {"name": "other", "version": "1"}})
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/misnamed.yaml", content=content
    )
    entry = next(e for e in await context.specs.entries() if e.name == "misnamed")
    assert entry.error is not None
    assert "does not match its file" in str(entry.error)


async def test_get_fills_in_the_shared_template(context: Day1Context) -> None:
    standard = await context.specs.get("agent-standard")
    assert standard.metadata.version == "1.0.0"
    assert standard.spec.day1.template.startswith("{#-")
    assert [str(a.key) for a in standard.spec.day2.addons] == ["redbull/cluster-roles"]


async def test_an_unknown_spec_is_not_found(context: Day1Context) -> None:
    with pytest.raises(ResourceNotFoundError):
        await context.specs.get("nope")
    with pytest.raises(ResourceNotFoundError):
        await context.specs.get("../escape")


async def test_versions_skip_comments_and_blank_lines(context: Day1Context) -> None:
    assert await context.specs.versions() == [
        "4.16.27-x86_64",
        "4.18.22-x86_64",
        "4.21.40-x86_64",
    ]


async def test_schema_hides_reserved_inputs_unless_asked(context: Day1Context) -> None:
    plain = [f.name for f in await context.specs.schema()]
    full = [f.name for f in await context.specs.schema(include_reserved=True)]
    assert "cluster_name" not in plain
    assert "openshift_release_version" not in plain
    assert "openshift_release_version" in full  # the only reserved input the template uses
    assert {"owner_merkaz", "nodepools"} <= set(plain)


async def test_create_opens_an_mr_in_the_specs_project(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    result = await context.specs.create(spec(), user=support.ALICE)
    mr = result.merge_request
    assert mr.title == "[Wingman/Specs] Create spec agent-mini"
    assert set(mr.labels) == {"wingman", "specs", "create"}
    pid = await support.project_id(gitlab, support.SPECS)
    assert mr.ref.project_id == pid
    content = gitlab.snapshot(pid, mr.source_branch)["specs/agent-mini.yaml"]
    assert "template" not in content
    assert validate_spec(yaml.safe_load(content)) == spec()


async def test_creating_a_spec_that_exists_is_already_in_use(
    context: Day1Context, support: Any
) -> None:
    with pytest.raises(AlreadyInUseError):
        await context.specs.create(spec("agent-single"), user=support.ALICE)


async def test_an_update_cannot_rename_the_spec(context: Day1Context, support: Any) -> None:
    with pytest.raises(InvalidInputError, match="renamed"):
        await context.specs.update("agent-single", spec("agent-other"), user=support.ALICE)


async def test_an_update_from_a_stale_read_is_a_conflict(
    context: Day1Context, support: Any
) -> None:
    with pytest.raises(StaleError):
        await context.specs.update(
            "agent-single", spec("agent-single"), user=support.ALICE, last_commit_id="0" * 40
        )


async def test_an_update_proposes_the_new_version(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    result = await context.specs.update(
        "agent-single", spec("agent-single", "1.1.0"), user=support.ALICE
    )
    assert result.merge_request.title == "[Wingman/Specs] Update spec agent-single to v1.1.0"
    pid = await support.project_id(gitlab, support.SPECS)
    content = gitlab.snapshot(pid, result.merge_request.source_branch)["specs/agent-single.yaml"]
    assert yaml.safe_load(content)["metadata"]["version"] == "1.1.0"


async def test_delete_proposes_removing_the_file(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    result = await context.specs.delete("agent-single", user=support.ALICE)
    pid = await support.project_id(gitlab, support.SPECS)
    assert "specs/agent-single.yaml" not in gitlab.snapshot(pid, result.merge_request.source_branch)
    assert result.merge_request.title == "[Wingman/Specs] Delete spec agent-single"


async def test_a_broken_spec_can_still_be_deleted(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/broken.yaml", content="metadata: [\n"
    )
    result = await context.specs.delete("broken", user=support.ALICE)
    assert result.merge_request.title == "[Wingman/Specs] Delete spec broken"


async def test_deleting_an_unknown_spec_is_not_found(context: Day1Context, support: Any) -> None:
    with pytest.raises(ResourceNotFoundError):
        await context.specs.delete("nope", user=support.ALICE)


async def test_history_and_content_at_a_commit(context: Day1Context) -> None:
    history = await context.specs.history("agent-single")
    assert history
    content = await context.specs.at("agent-single", history[0].id)
    assert "name: agent-single" in content
    with pytest.raises(ResourceNotFoundError):
        await context.specs.at("nope", history[0].id)
