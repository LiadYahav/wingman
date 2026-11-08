"""Cluster use cases on the seeded in-memory GitLab: create, preview, list, edit, delete."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.clusters import CreateCluster
from wingman_day1.domain.errors import (
    AlreadyInUseError,
    AmbiguousNameError,
    InvalidInputError,
    RenderError,
    ResourceNotFoundError,
    StaleError,
)
from wingman_day1.domain.paths import ClusterRef

NEW = "ocp4-prod-falcon-site1"
NEW_PATH = f"sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/{NEW}.yaml"
HERZI = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-herzi-site1")


def request(support: Any, name: str = NEW, **overrides: Any) -> CreateCluster:
    body = support.create_body(name, **overrides)
    return CreateCluster(
        name=body["name"],
        site=body["site"],
        mce=body["mce"],
        spec_name=body["spec_name"],
        spec_version=body["spec_version"],
        variables=body["variables"],
        addon_overrides=body.get("addon_overrides") or {},
    )


def variables(support: Any, **changes: Any) -> dict[str, Any]:
    values = dict(support.create_body()["variables"])
    values.update(changes)
    return {k: v for k, v in values.items() if v is not None}


async def delete_file(gitlab: InMemoryGitLab, project: str, path: str) -> None:
    pid = (await gitlab.get_project(project)).id
    current = await gitlab.read_file(pid, RepoPath(path), "main")
    await gitlab.commit(
        pid,
        branch="main",
        message=f"remove {path}",
        changes=[FileChange.delete(RepoPath(path), last_commit_id=current.last_commit_id)],
    )


# ── Create ───────────────────────────────────────────────────────────────────


async def test_create_commits_one_new_file_on_a_new_branch_and_opens_one_mr(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    before = gitlab.snapshot(pid, "main")
    result = await context.clusters.create(request(support), user=support.ALICE)
    mr = result.merge_request
    assert mr.target_branch == "main"
    branch = gitlab.snapshot(pid, mr.source_branch)
    assert set(branch) - set(before) == {NEW_PATH}
    assert gitlab.snapshot(pid, "main") == before
    commits = await gitlab.list_commits(pid, ref=mr.source_branch, limit=2)
    assert commits[0].author_name == "Alice Admin"
    assert commits[0].author_email == "alice@openshift.local"
    assert "Requested-by: alice" in commits[0].message
    assert "Author: alice" in mr.description
    assert "Resource: cluster/ocp4-prod-falcon-site1" in mr.description


async def test_preview_is_exactly_the_committed_file(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    rendered = await context.clusters.preview(request(support))
    result = await context.clusters.create(request(support), user=support.ALICE)
    pid = await support.project_id(gitlab, support.DAY1)
    committed = gitlab.snapshot(pid, result.merge_request.source_branch)[NEW_PATH]
    assert committed == rendered.content
    assert str(rendered.ref.path) == NEW_PATH


async def test_addon_overrides_given_at_create_are_kept_in_the_file_header(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    # Legacy: CreateClusterRequest.addon_overrides was accepted and ignored, so the values
    # a user chose for the spec's day2 addons were lost and "Fix" installed with {}.
    overrides = {"redbull/cluster-roles": {"a": 1, "nested": {"b": "two"}}}
    result = await context.clusters.create(
        request(support, addon_overrides=overrides), user=support.ALICE
    )
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, result.merge_request.source_branch)[NEW_PATH]
    header = [line for line in content.splitlines() if line.startswith("#")]
    assert header[:2] == ['# specName: "agent-standard"', '# specVersion: "1.0.0"']
    assert '"override_values": {"a": 1, "nested": {"b": "two"}}' in header[2]
    assert yaml.safe_load(content)["mastertag"] == "4.18.56-x86_64"


async def test_an_override_for_an_addon_the_spec_lacks_is_refused(
    context: Day1Context, support: Any
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.create(
            request(support, addon_overrides={"orca/metrics": {"x": 1}}), user=support.ALICE
        )
    assert any("orca/metrics" in p for p in caught.value.problems)


@pytest.mark.parametrize(
    ("name", "mce", "expected"),
    [
        ("ocp4-falcon", "ocp4-prod-mce-site1-a", "does not follow ocp4-<env>-<name>-site1"),
        ("ocp4-prep-falcon-site1", "ocp4-prod-mce-site1-a", "does not match MCE"),
        ("ocp4-prod-falcon-site1", "ocp4-mce-workflow-test", "cannot be checked"),
        ("Ocp4-Prod-Falcon-Site1", "ocp4-prod-mce-site1-a", "lowercase"),
        ("ocp4-prod-falcon-site2", "ocp4-prod-mce-site1-a", "does not follow"),
    ],
)
async def test_new_cluster_names_are_checked_against_the_convention_and_the_mce(
    context: Day1Context, support: Any, name: str, mce: str, expected: str
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request(support, name, mce=mce))
    assert any(expected in p for p in caught.value.problems), caught.value.problems


async def test_a_name_whose_namespace_would_exceed_a_dns_label_is_refused(
    context: Day1Context, support: Any
) -> None:
    long_name = "ocp4-prod-" + "a" * 20 + "-site1"
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request(support, long_name))
    assert any("control-plane namespace" in p for p in caught.value.problems)


@pytest.mark.parametrize(("site", "mce"), [("site9", "ocp4-prod-mce-site9-a"), ("site1", "nope")])
async def test_creating_under_a_site_or_mce_that_does_not_exist_is_not_found(
    context: Day1Context, support: Any, site: str, mce: str
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await context.clusters.preview(request(support, site=site, mce=mce))


async def test_a_name_used_under_another_mce_is_already_in_use(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    # The same stem under another MCE: cluster names are unique across the whole repo.
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file=f"sites/site2/mces/ocp4-prod-mce-site2-a/hostedClusters/{NEW}.yaml",
        content="mastertag: 4.18.56-x86_64\n",
    )
    with pytest.raises(AlreadyInUseError, match="already exists under site2"):
        await context.clusters.preview(request(support))


async def test_a_stale_spec_version_is_a_conflict(context: Day1Context, support: Any) -> None:
    with pytest.raises(StaleError, match=r"now v1\.0\.0"):
        await context.clusters.preview(request(support, spec_version="0.9.0"))


async def test_an_unknown_spec_is_not_found(context: Day1Context, support: Any) -> None:
    with pytest.raises(ResourceNotFoundError):
        await context.clusters.preview(request(support, spec_name="no-such-spec"))


async def test_a_newline_in_a_variable_cannot_inject_keys(
    context: Day1Context, support: Any
) -> None:
    body = variables(support, owner_mador="7\nvlanId: 5")
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request(support, variables=body))
    assert caught.value.problems


async def test_a_reserved_input_that_disagrees_with_the_request_is_refused(
    context: Day1Context, support: Any
) -> None:
    body = variables(support, cluster_name="ocp4-prod-other-site1")
    with pytest.raises(RenderError) as caught:
        await context.clusters.preview(request(support, variables=body))
    assert any("cluster_name" in p for p in caught.value.problems)


async def test_a_missing_release_version_is_refused(context: Day1Context, support: Any) -> None:
    body = variables(support, openshift_release_version=None)
    with pytest.raises(RenderError):
        await context.clusters.preview(request(support, variables=body))


async def test_a_missing_template_variable_is_a_render_error(
    context: Day1Context, support: Any
) -> None:
    body = variables(support, owner_mador=None)
    with pytest.raises(RenderError):
        await context.clusters.preview(request(support, variables=body))


async def test_without_a_template_in_the_specs_project_nothing_can_be_rendered(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await delete_file(gitlab, support.SPECS, "cluster-template.j2")
    with pytest.raises(RenderError, match=r"no cluster-template\.j2"):
        await context.clusters.preview(request(support))


async def test_a_template_that_renders_automation_keys_is_refused(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab,
        support.SPECS,
        branch="main",
        file="cluster-template.j2",
        content=(
            "mastertag: {{ openshift_release_version }}\nvlanId: 7\n"
            "nodepool:\n  - infraEnvName: x\n"
        ),
    )
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request(support))
    assert any("vlanId" in p for p in caught.value.problems)


# ── Reads ────────────────────────────────────────────────────────────────────


async def test_a_cluster_is_found_by_name_alone(context: Day1Context) -> None:
    assert await context.clusters.locate("ocp4-prod-herzi-site1") == HERZI


async def test_a_name_under_two_mces_needs_site_and_mce(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file="sites/site1/mces/ocp4-prep-mce-site1-a/hostedClusters/ocp4-prod-herzi-site1.yaml",
        content="mastertag: 4.16.27-x86_64\n",
    )
    with pytest.raises(AmbiguousNameError):
        await context.clusters.locate("ocp4-prod-herzi-site1")
    found = await context.clusters.locate("ocp4-prod-herzi-site1", mce="ocp4-prod-mce-site1-a")
    assert found == HERZI


async def test_an_unknown_cluster_is_not_found(context: Day1Context) -> None:
    with pytest.raises(ResourceNotFoundError):
        await context.clusters.locate("ocp4-prod-ghost-site1")
    with pytest.raises(ResourceNotFoundError):
        await context.clusters.get(ClusterRef("site1", "ocp4-prod-mce-site1-a", "ghost"))


async def test_an_unparsable_cluster_file_is_listed_with_its_problems(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    # Legacy: a file that failed to load was logged and silently dropped from the list.
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file="sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-junk-site1.yaml",
        content="mastertag: [unclosed\n",
    )
    junk = next(
        c for c in await context.clusters.clusters() if c.ref.name == "ocp4-prod-junk-site1"
    )
    assert junk.values is None
    assert junk.problems
    assert "line" in junk.problems[0]


async def test_a_file_with_a_clustername_key_names_its_hosted_cluster(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file=str(HERZI.path),
        content="clusterName: herzi-special\nmastertag: 4.16.27-x86_64\n",
    )
    cluster = await context.clusters.get(HERZI)
    assert cluster.hosted_cluster.name == "ocp4-herzi-special"
    assert cluster.hosted_cluster.namespace == "hcp-herzi-special"


async def test_history_names_the_user_who_asked_for_the_change(
    context: Day1Context, support: Any
) -> None:
    result = await context.clusters.create(request(support), user=support.ALICE)
    await context.approvals.approve(
        RepoKey.DAY1,
        result.merge_request.ref.iid,
        sha=result.merge_request.sha,
        approver=support.BOB,
    )
    ref = await context.clusters.locate(NEW)
    authors = [c.author_name for c in await context.clusters.history(ref)]
    assert "Alice Admin" in authors


async def test_web_url_points_at_the_file_on_the_default_branch(context: Day1Context) -> None:
    url = await context.clusters.web_url(HERZI)
    assert url.endswith(f"/-/blob/main/{HERZI.path}")


# ── Modify and delete ────────────────────────────────────────────────────────


async def test_an_edit_that_changes_nothing_is_refused(context: Day1Context, support: Any) -> None:
    current = await context.clusters.get(HERZI)
    with pytest.raises(InvalidInputError, match="changes nothing"):
        await context.clusters.modify(HERZI, current.content, user=support.ALICE, summary="noop")


async def test_an_edit_keeps_the_automation_owned_keys(context: Day1Context, support: Any) -> None:
    current = await context.clusters.get(HERZI)
    edited = current.content.replace('network: "10.20.44.0"', 'network: "10.20.45.0"')
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.modify(HERZI, edited, user=support.ALICE, summary="x")
    assert any("dhcp_values" in p for p in caught.value.problems)


async def test_an_edit_opens_a_modify_mr_guarded_by_the_read(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    current = await context.clusters.get(HERZI)
    edited = current.content.replace("4.16.27", "4.16.28")
    result = await context.clusters.modify(
        HERZI, edited, user=support.ALICE, summary="", last_commit_id=current.last_commit_id
    )
    mr = result.merge_request
    assert mr.title == "[Wingman/Day1] Modify cluster ocp4-prod-herzi-site1"
    assert set(mr.labels) == {"wingman", "day1", "modify"}
    assert "Modify cluster ocp4-prod-herzi-site1 via Wingman" in mr.description
    pid = await support.project_id(gitlab, support.DAY1)
    assert gitlab.snapshot(pid, mr.source_branch)[str(HERZI.path)] == edited


async def test_an_edit_from_a_stale_read_is_a_conflict(context: Day1Context, support: Any) -> None:
    current = await context.clusters.get(HERZI)
    with pytest.raises(StaleError):
        await context.clusters.modify(
            HERZI,
            current.content.replace("4.16.27", "4.16.28"),
            user=support.ALICE,
            summary="x",
            last_commit_id="0" * 40,
        )


async def test_an_edit_read_before_other_files_changed_is_not_stale(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    # Reads carry the commit they were read at (ADR-0035). A merge that touches
    # other files moves that commit on, but this cluster's file is unchanged.
    current = await context.clusters.get(HERZI)
    pid = await support.project_id(gitlab, support.DAY1)
    await gitlab.commit(
        pid,
        branch="main",
        message="another cluster's change",
        changes=[FileChange.create(RepoPath("sites/site1/notes.md"), "n\n")],
    )
    context.repos[RepoKey.DAY1].forget_files()  # as after the merge Wingman sees
    edited = current.content.replace("4.16.27", "4.16.28")
    result = await context.clusters.modify(
        HERZI, edited, user=support.ALICE, summary="", last_commit_id=current.last_commit_id
    )
    assert gitlab.snapshot(pid, result.merge_request.source_branch)[str(HERZI.path)] == edited


async def test_a_delete_from_a_stale_read_is_a_conflict(context: Day1Context, support: Any) -> None:
    with pytest.raises(StaleError):
        await context.clusters.delete(HERZI, user=support.ALICE, last_commit_id="0" * 40)


async def test_a_delete_removes_only_the_cluster_file(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    before = gitlab.snapshot(pid, "main")
    result = await context.clusters.delete(HERZI, user=support.ALICE)
    after = gitlab.snapshot(pid, result.merge_request.source_branch)
    assert set(before) - set(after) == {str(HERZI.path)}
    assert set(after) - set(before) == set()
    assert result.merge_request.title == "[Wingman/Day1] Delete cluster ocp4-prod-herzi-site1"


async def test_deleting_a_cluster_that_does_not_exist_is_not_found(
    context: Day1Context, support: Any
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await context.clusters.delete(
            ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-ghost-site1"),
            user=support.ALICE,
        )
