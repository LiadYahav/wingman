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
    Verb,
    branch_name,
    mr_description,
    mr_title,
    parse_mr_description,
    parse_mr_title,
)

_words = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126, exclude_characters="]/"),
    min_size=1,
    max_size=30,
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
