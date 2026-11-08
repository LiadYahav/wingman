from __future__ import annotations

from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wingman_core.domain.errors import InvalidRepoPathError
from wingman_core.domain.git import ChangeKind, CommitAuthor, FileChange, RepoPath, commit_author
from wingman_core.domain.users import Role, User


@pytest.mark.parametrize("value", ["/abs", "a//b", "a/../b", "..", "./a", "a/", "a\\b", "a\x00b"])
def test_repo_path_rejects_non_normalized_paths(value: str) -> None:
    with pytest.raises(InvalidRepoPathError):
        RepoPath(value)


def test_repo_path_navigation() -> None:
    path = RepoPath("sites/site1/mces/m/values.yaml")
    assert path.name == "values.yaml"
    assert path.parent == RepoPath("sites/site1/mces/m")
    assert path.parts == ("sites", "site1", "mces", "m", "values.yaml")
    assert RepoPath("top").parent.is_root
    assert RepoPath.root().child("a", "b") == RepoPath("a/b")
    assert RepoPath("a").child("b") == RepoPath("a/b")
    assert path.is_within(RepoPath("sites/site1"))
    assert not RepoPath("sites/site10").is_within(RepoPath("sites/site1"))
    assert path.is_within(RepoPath.root())
    assert str(path) == "sites/site1/mces/m/values.yaml"


@pytest.mark.parametrize("segment", ["a/b", "..", ".", ""])
def test_repo_path_of_rejects_segments_that_would_escape(segment: str) -> None:
    with pytest.raises(InvalidRepoPathError):
        RepoPath.of("sites", segment)


@given(st.lists(st.text(min_size=1, max_size=12), min_size=1, max_size=4))
def test_repo_path_of_never_leaves_its_first_segment(segments: list[str]) -> None:
    try:
        path = RepoPath.of("sites", *segments)
    except InvalidRepoPathError:
        return
    assert path.is_within(RepoPath("sites"))
    assert path.parts[1:] == tuple(segments)


def test_file_change_constructors_set_the_kind() -> None:
    path = RepoPath("a.yaml")
    assert FileChange.create(path, "x").kind is ChangeKind.CREATE
    assert FileChange.update(path, "x", last_commit_id="c").last_commit_id == "c"
    assert FileChange.delete(path).content is None
    moved = FileChange.move(RepoPath("old.yaml"), path)
    assert moved.previous_path == RepoPath("old.yaml")


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: FileChange(ChangeKind.CREATE, RepoPath("a")), "needs content"),
        (lambda: FileChange(ChangeKind.DELETE, RepoPath("a"), content="x"), "no content"),
        (lambda: FileChange(ChangeKind.MOVE, RepoPath("a")), "previous_path"),
        (
            lambda: FileChange(
                ChangeKind.UPDATE, RepoPath("a"), content="x", previous_path=RepoPath("b")
            ),
            "previous_path",
        ),
        (lambda: FileChange(ChangeKind.DELETE, RepoPath.root()), "file path"),
    ],
)
def test_file_change_rejects_impossible_combinations(
    build: Callable[[], FileChange], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build()


@pytest.mark.parametrize(
    ("name", "email"),
    [("", "a@b"), ("Jane", " "), ("Jane\nX-Header: y", "a@b"), ("Jane", "<a@b>")],
)
def test_commit_author_rejects_empty_or_header_breaking_values(name: str, email: str) -> None:
    with pytest.raises(ValueError, match="invalid commit author"):
        CommitAuthor(name, email)


def test_the_commit_author_is_the_requesting_user() -> None:
    author = commit_author(User(username="alice", role=Role.ADMIN, full_name="Alice Admin"))
    assert (author.name, author.email) == ("Alice Admin", "alice@openshift.local")


def test_the_commit_author_falls_back_to_the_username() -> None:
    author = commit_author(User(username="bob", role=Role.ADMIN))
    assert (author.name, author.email) == ("bob", "bob@openshift.local")


def test_the_commit_author_cannot_forge_header_lines() -> None:
    sneaky = User(username="eve\nX-Evil: 1", role=Role.ADMIN, full_name="Eve <eve@evil>\r\nx")
    author = commit_author(sneaky)
    for value in (author.name, author.email):
        assert not set(value) & set("\r\n<>")
    assert author.email == "eve-X-Evil: 1@openshift.local"


def test_a_username_of_only_forbidden_characters_still_gives_an_author() -> None:
    author = commit_author(User(username="<>", role=Role.ADMIN, full_name="\n"))
    assert (author.name, author.email) == ("-", "-@openshift.local")
