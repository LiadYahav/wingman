from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wingman_core.domain.mr_conventions import (
    MRMetadata,
    ParsedTitle,
    Repo,
    ResourceType,
    RolloutBranch,
    Verb,
    branch_name,
    mr_description,
    mr_title,
    parse_mr_description,
    parse_mr_title,
    parse_rollout_branch,
    rollout_branch,
)

_words = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126, exclude_characters="]/"),
    min_size=1,
    max_size=30,
)
_dns_labels = st.from_regex(r"\A[a-z0-9]([-a-z0-9]{0,30}[a-z0-9])?\Z")
_numbers = st.integers(min_value=0, max_value=9999).map(str)
_versions = st.builds(
    lambda major, minor, patch, pre: f"{major}.{minor}.{patch}{pre}",
    _numbers,
    _numbers,
    _numbers,
    st.sampled_from(["", "-rc.1", "-alpha", "-beta.2", "_1"]),
)


def test_branch_name_format_and_utc_stamp() -> None:
    at = datetime(2026, 4, 18, 16, 30, 22, tzinfo=timezone(timedelta(hours=2)))
    assert (
        branch_name(
            username="jane.doe", action="create-cluster", resource="ocp4-prod-a-site1", at=at
        )
        == "platform/jane.doe/create-cluster-ocp4-prod-a-site1-20260418T143022"
    )


@given(st.text(max_size=40), st.text(max_size=40))
def test_branch_name_is_always_a_valid_ref(username: str, resource: str) -> None:
    name = branch_name(
        username=username, action="create-cluster", resource=resource, at=datetime.now(UTC)
    )
    assert ".." not in name
    assert " " not in name
    assert not name.endswith((".", "/", ".lock"))
    assert all(part for part in name.split("/"))


@pytest.mark.parametrize(
    ("flavor", "version", "cluster", "branch"),
    [
        (
            "agent-baseline",
            "1.1.0",
            "ocp4-prod-lark-site1",
            "platform/rollout/agent-baseline/v1.1.0/ocp4-prod-lark-site1",
        ),
        (
            "gpu",
            "2026.11.1",
            "ocp4-dev-x-site-a-2",
            "platform/rollout/gpu/v2026.11.1/ocp4-dev-x-site-a-2",
        ),
        ("gpu", "1.0.0-rc.1", "c", "platform/rollout/gpu/v1.0.0-rc.1/c"),
        # Unsafe characters are rewritten as in every branch.
        ("my flavor", "1.0+build", "c..d", "platform/rollout/my-flavor/v1.0-build/c.d"),
    ],
)
def test_rollout_branch_format(flavor: str, version: str, cluster: str, branch: str) -> None:
    assert rollout_branch(flavor=flavor, version=version, cluster=cluster) == branch


def test_rollout_branch_is_the_same_for_the_same_inputs() -> None:
    # No timestamp: a second run, or a second pod, must find this branch, not make another.
    parts = {"flavor": "agent-baseline", "version": "1.1.0", "cluster": "ocp4-prod-lark-site1"}
    assert rollout_branch(**parts) == rollout_branch(**parts)
    assert rollout_branch(**parts) != rollout_branch(**{**parts, "version": "1.2.0"})
    assert rollout_branch(**parts) != rollout_branch(**{**parts, "cluster": "ocp4-prod-wren-site1"})


@given(_dns_labels, _versions, _dns_labels)
def test_rollout_branch_round_trips(flavor: str, version: str, cluster: str) -> None:
    branch = rollout_branch(flavor=flavor, version=version, cluster=cluster)
    assert parse_rollout_branch(branch) == RolloutBranch(flavor, version, cluster)
    assert ".." not in branch
    assert not branch.endswith((".", "/", ".lock"))


@given(st.text(max_size=40), st.text(max_size=20), st.text(max_size=40))
def test_any_rollout_branch_parses_and_is_a_valid_ref(
    flavor: str, version: str, cluster: str
) -> None:
    branch = rollout_branch(flavor=flavor, version=version, cluster=cluster)
    assert parse_rollout_branch(branch) is not None
    assert len(branch.split("/")) == 5
    assert all(branch.split("/"))
    assert ".." not in branch
    assert " " not in branch


@given(st.text(max_size=40), st.text(max_size=20), st.text(max_size=40))
def test_a_user_branch_is_never_a_rollout_branch(username: str, action: str, resource: str) -> None:
    name = branch_name(username=username, action=action, resource=resource, at=datetime.now(UTC))
    assert parse_rollout_branch(name) is None


def test_a_user_named_rollout_does_not_make_a_rollout_branch() -> None:
    at = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
    name = branch_name(username="rollout", action="sync-cluster", resource="v1.0.0", at=at)
    assert name.startswith("platform/rollout/")
    assert parse_rollout_branch(name) is None


@pytest.mark.parametrize(
    "branch",
    [
        "",
        "main",
        "platform/rollout/f/1.0.0/c",  # no "v"
        "platform/rollout/f/v/c",  # no version after the "v"
        "platform/rollout/f/v1.0.0",  # no cluster
        "platform/rollout/f/v1.0.0/c/extra",
        "platform/rollout/f-v1.0.0/c",  # four segments
        "platform/jane/f/v1.0.0/c",
        "other/rollout/f/v1.0.0/c",
        "platform/rollout//v1.0.0/c",
        "platform/rollout/f/v1..0/c",  # rollout_branch never writes ".."
        "platform/rollout/-f/v1.0.0/c",
        "platform/rollout/f/v1.0.0/c+d",
    ],
)
def test_other_branches_are_not_rollout_branches(branch: str) -> None:
    assert parse_rollout_branch(branch) is None


def test_title_matches_the_existing_format() -> None:
    title = mr_title(
        Repo.DAY1, Verb.CREATE, ResourceType.CLUSTER, "ocp4-prod-a-site1", "from spec agent"
    )
    assert title == "[Wingman/Day1] Create cluster ocp4-prod-a-site1 from spec agent"


def test_import_and_sync_titles_parse() -> None:
    imported = "[Wingman/Day1] Import spec agent-baseline into 2 clusters"
    assert mr_title(Repo.DAY1, Verb.IMPORT, ResourceType.SPEC, "agent-baseline", "into 2 clusters")
    assert parse_mr_title(imported) == ParsedTitle(
        Repo.DAY1, Verb.IMPORT, ResourceType.SPEC, "agent-baseline"
    )
    synced = parse_mr_title("[Wingman/Day1] Sync cluster ocp4-prod-a-site1 to spec agent v2")
    assert synced == ParsedTitle(Repo.DAY1, Verb.SYNC, ResourceType.CLUSTER, "ocp4-prod-a-site1")


def test_an_add_on_edit_titled_team_default_reads_as_one_titled_sig_values() -> None:
    # Day2 said "team default" before 3.19.1; MRs opened then are still open in GitLab.
    new = mr_title(Repo.DAY2, Verb.UPDATE, ResourceType.ADDON, "redbull/bmhgen", "Sig values")
    assert new == "[Wingman/Day2] Update addon redbull/bmhgen Sig values"
    old = "[Wingman/Day2] Update addon redbull/bmhgen team default"
    expected = ParsedTitle(Repo.DAY2, Verb.UPDATE, ResourceType.ADDON, "redbull/bmhgen")
    assert parse_mr_title(old) == parse_mr_title(new) == expected


@given(
    st.sampled_from(Repo),
    st.sampled_from(Verb),
    st.sampled_from(ResourceType),
    _words,
    st.text(max_size=30),
)
def test_title_round_trips(
    repo: Repo, verb: Verb, kind: ResourceType, name: str, extra: str
) -> None:
    parsed = parse_mr_title(mr_title(repo, verb, kind, name, extra))
    assert parsed is not None
    assert (parsed.repo, parsed.verb, parsed.resource_type, parsed.resource_name) == (
        repo,
        verb,
        kind,
        name,
    )


def test_title_rejects_names_that_would_not_parse() -> None:
    with pytest.raises(ValueError, match="one non-empty word"):
        mr_title(Repo.DAY2, Verb.INSTALL, ResourceType.ADDON, "two words")


@pytest.mark.parametrize(
    "title",
    [
        "Update README",
        "[Day2] Install addon x",
        "[Wingman/Nope] Create cluster x",
        "[Wingman/Day1] Frobnicate cluster x",
    ],
)
def test_other_titles_do_not_parse(title: str) -> None:
    assert parse_mr_title(title) is None


@given(
    _words,
    _words,
    st.sampled_from(ResourceType),
    _words,
    st.sampled_from(Repo),
    st.text(max_size=200),
)
def test_description_round_trips(
    author: str, action: str, kind: ResourceType, name: str, repo: Repo, human: str
) -> None:
    metadata = MRMetadata(
        author=author, action=action, resource_type=kind, resource_name=name, repo=repo
    )
    assert parse_mr_description(mr_description(human, metadata)) == metadata


def test_description_from_the_old_service_still_parses() -> None:
    legacy = (
        "Create cluster alpha\n\n---\nAuthor: jane\nAction: create\n"
        "Resource: cluster/alpha\nRepo: Day1\n"
    )
    parsed = parse_mr_description(legacy)
    assert parsed == MRMetadata("jane", "create", ResourceType.CLUSTER, "alpha", Repo.DAY1)


@pytest.mark.parametrize(
    "description",
    [
        "",
        "no footer",
        "x\n\n---\nAuthor: a\n",
        "x\n\n---\nAuthor: a\nAction: b\nResource: nope/x\nRepo: Day1\n",
    ],
)
def test_incomplete_descriptions_do_not_parse(description: str) -> None:
    assert parse_mr_description(description) is None
