"""GitLabHttpAdapter against recorded-shape GitLab responses (httpx.MockTransport)."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import AnyHttpUrl, SecretStr

from wingman_core.domain.errors import (
    AlreadyExistsError,
    AmbiguousWriteError,
    GitUnavailableError,
    InvalidRequestError,
    NotFoundError,
    NotMergeableError,
    PermissionDeniedError,
    RevisionConflictError,
)
from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.merge_request import MergeRequestRef, MRState, NewMergeRequest
from wingman_core.infrastructure.gitlab import GitLabHttpAdapter
from wingman_core.infrastructure.gitlab.http import build_client
from wingman_core.settings import GitLabSettings

TOKEN = "test-token-never-logged-0001"

Handler = Callable[[httpx.Request], httpx.Response]

MR = {
    "project_id": 7,
    "iid": 3,
    "title": "[Wingman/Day1] Create cluster c",
    "description": "d",
    "state": "opened",
    "source_branch": "b",
    "target_branch": "main",
    "author": {"username": "wingman-bot"},
    "labels": ["wingman", "day1"],
    "web_url": "http://gl/x/-/merge_requests/3",
    "created_at": "2026-11-07T10:00:00.000Z",
    "updated_at": "2026-11-07T10:00:01.000+02:00",
    "merged_at": None,
    "sha": "abc",
    "has_conflicts": False,
    "detailed_merge_status": "mergeable",
}
COMMIT = {
    "id": "a" * 40,
    "short_id": "aaaaaaaa",
    "title": "t",
    "message": "t\n",
    "author_name": "bot",
    "author_email": "bot@x",
    "authored_date": "2026-11-07T10:00:00Z",
    "web_url": "http://gl/c",
    "parent_ids": ["b" * 40],
}


class Recorder:
    def __init__(self, *handlers: Handler) -> None:
        self.handlers = list(handlers)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.handlers.pop(0) if len(self.handlers) > 1 else self.handlers[0]
        return handler(request)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def adapter(self) -> GitLabHttpAdapter:
        settings = GitLabSettings(url=AnyHttpUrl("http://gitlab.test"), token=SecretStr(TOKEN))
        client = build_client(settings, transport=httpx.MockTransport(self))
        return GitLabHttpAdapter(client, sleep=self.sleep, backoff_seconds=0.1)


def reply(status: int, body: object = None, headers: dict[str, str] | None = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body, headers=headers)


def fail(exc: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc("boom", request=request)

    return handler


async def test_token_is_sent_as_header_and_file_paths_are_encoded() -> None:
    content = base64.b64encode(b"a: 1\n").decode()
    rec = Recorder(reply(200, {"content": content, "last_commit_id": "c" * 40}))
    file = await rec.adapter().read_file(7, RepoPath("sites/site1/values.yaml"), "main")
    assert file.content == "a: 1\n"
    assert file.last_commit_id == "c" * 40
    [request] = rec.requests
    assert request.headers["PRIVATE-TOKEN"] == TOKEN
    assert (
        request.url.raw_path
        == b"/api/v4/projects/7/repository/files/sites%2Fsite1%2Fvalues.yaml?ref=main"
    )


async def test_project_paths_are_encoded() -> None:
    rec = Recorder(
        reply(
            200, {"id": 1, "path_with_namespace": "g/p", "default_branch": "main", "web_url": "u"}
        )
    )
    project = await rec.adapter().get_project("g/p")
    assert project.id == 1
    assert rec.requests[0].url.raw_path == b"/api/v4/projects/g%2Fp"


async def test_non_utf8_file_is_rejected() -> None:
    rec = Recorder(
        reply(200, {"content": base64.b64encode(b"\xff\xfe").decode(), "last_commit_id": "c"})
    )
    with pytest.raises(InvalidRequestError, match="not UTF-8"):
        await rec.adapter().read_file(7, RepoPath("bin"), "main")


async def test_pagination_follows_next_page_until_limit() -> None:
    page = [COMMIT] * 100
    rec = Recorder(
        reply(200, page, {"x-next-page": "2"}),
        reply(200, page, {"x-next-page": "3"}),
        reply(200, page, {"x-next-page": ""}),
    )
    commits = await rec.adapter().list_commits(7, ref="main", limit=150)
    assert len(commits) == 150
    assert [r.url.params["page"] for r in rec.requests] == ["1", "2"]


async def test_list_tree_sorts_and_reports_a_missing_directory() -> None:
    entries = [
        {"path": "b/file.yaml", "type": "blob"},
        {"path": "b/a", "type": "tree"},
        {"path": "b/sub", "type": "commit"},
    ]
    rec = Recorder(reply(200, entries), reply(200, []))
    adapter = rec.adapter()
    assert [str(e.path) for e in await adapter.list_tree(7, RepoPath("b"), "main")] == [
        "b/a",
        "b/file.yaml",
    ]
    with pytest.raises(NotFoundError):
        await adapter.list_tree(7, RepoPath("missing"), "main")


async def test_reads_retry_transient_failures_with_backoff_and_retry_after() -> None:
    rec = Recorder(
        reply(503),
        reply(429, {"message": "slow down"}, {"retry-after": "3"}),
        reply(200, {"id": 1, "path_with_namespace": "g/p", "web_url": "u"}),
    )
    project = await rec.adapter().get_project(1)
    assert project.default_branch == "main"
    assert rec.sleeps == [0.1, 3.0]


async def test_reads_give_up_as_unavailable() -> None:
    rec = Recorder(fail(httpx.ConnectError))
    with pytest.raises(GitUnavailableError):
        await rec.adapter().get_project(1)
    assert len(rec.requests) == 3
    rec = Recorder(reply(502))
    with pytest.raises(GitUnavailableError):
        await rec.adapter().get_project(1)


@pytest.mark.parametrize(
    ("status", "message", "error"),
    [
        (404, "404 File Not Found", NotFoundError),
        (401, "401 Unauthorized", PermissionDeniedError),
        (403, "403 Forbidden", PermissionDeniedError),
        (400, "A file with this name already exists", AlreadyExistsError),
        (400, "A file with this name doesn't exist", NotFoundError),
        (400, "You can only create or edit files when you are on a branch", NotFoundError),
        (
            400,
            "You are attempting to update a file that has changed since you started editing it.",
            RevisionConflictError,
        ),
        (400, {"branch": ["is invalid"]}, InvalidRequestError),
        (
            409,
            ["Another open merge request already exists for this source branch: !1"],
            AlreadyExistsError,
        ),
        (422, "Unprocessable", InvalidRequestError),
        (500, "500 Internal Server Error", AmbiguousWriteError),
    ],
)
async def test_write_errors_map_to_domain_errors(
    status: int, message: object, error: type[Exception]
) -> None:
    rec = Recorder(reply(status, {"message": message}))
    with pytest.raises(error) as raised:
        await rec.adapter().commit(
            7, branch="main", message="m", changes=[FileChange.create(RepoPath("a"), "x")]
        )
    assert TOKEN not in str(raised.value)
    assert len(rec.requests) == 1


async def test_writes_are_never_retried() -> None:
    rec = Recorder(fail(httpx.ReadTimeout))
    with pytest.raises(AmbiguousWriteError, match="re-read"):
        await rec.adapter().create_branch(7, "b", "main")
    assert len(rec.requests) == 1
    rec = Recorder(fail(httpx.ConnectError))
    with pytest.raises(GitUnavailableError):
        await rec.adapter().create_branch(7, "b", "main")
    assert len(rec.requests) == 1


async def test_commit_sends_the_golden_body() -> None:
    rec = Recorder(reply(201, COMMIT))
    await rec.adapter().commit(
        7,
        branch="feature",
        start_branch="main",
        message="Create cluster",
        changes=[
            FileChange.create(RepoPath("a.yaml"), "a: 1\n"),
            FileChange.update(RepoPath("b.yaml"), "b: 2\n", last_commit_id="f" * 40),
            FileChange.delete(RepoPath("c.yaml")),
            FileChange.move(RepoPath("d.yaml"), RepoPath("e.yaml")),
        ],
    )
    assert json.loads(rec.requests[0].content) == {
        "branch": "feature",
        "start_branch": "main",
        "commit_message": "Create cluster",
        "actions": [
            {"action": "create", "file_path": "a.yaml", "content": "a: 1\n", "encoding": "text"},
            {
                "action": "update",
                "file_path": "b.yaml",
                "content": "b: 2\n",
                "encoding": "text",
                "last_commit_id": "f" * 40,
            },
            {"action": "delete", "file_path": "c.yaml"},
            {"action": "move", "file_path": "e.yaml", "previous_path": "d.yaml"},
        ],
    }


async def test_empty_commit_is_rejected_without_a_request() -> None:
    rec = Recorder(reply(201, COMMIT))
    with pytest.raises(InvalidRequestError):
        await rec.adapter().commit(7, branch="main", message="m", changes=[])
    assert rec.requests == []


async def test_merge_request_parsing_and_creation_body() -> None:
    rec = Recorder(reply(201, MR))
    mr = await rec.adapter().create_merge_request(
        7, NewMergeRequest("b", "main", "t", "d", labels=("wingman", "day1"))
    )
    assert mr.ref == MergeRequestRef(7, 3)
    assert mr.state is MRState.OPENED
    assert mr.labels == ("day1", "wingman")
    assert mr.updated_at.utcoffset() is not None
    assert json.loads(rec.requests[0].content)["labels"] == "wingman,day1"


async def test_merge_waits_for_the_mergeability_check() -> None:
    checking = {**MR, "detailed_merge_status": "checking"}
    merged = {**MR, "state": "merged", "merged_at": "2026-11-07T10:01:00Z"}
    rec = Recorder(reply(200, checking), reply(200, checking), reply(200, MR), reply(200, merged))
    result = await rec.adapter().merge_merge_request(MergeRequestRef(7, 3), sha="abc")
    assert result.state is MRState.MERGED
    assert [r.method for r in rec.requests] == ["GET", "GET", "GET", "PUT"]
    assert json.loads(rec.requests[-1].content) == {"sha": "abc"}
    assert rec.sleeps == [0.1, 0.2]


@pytest.mark.parametrize(
    ("status", "error"),
    [(405, NotMergeableError), (406, NotMergeableError), (409, RevisionConflictError)],
)
async def test_merge_refusals(status: int, error: type[Exception]) -> None:
    rec = Recorder(reply(200, MR), reply(status, {"message": "refused"}))
    with pytest.raises(error):
        await rec.adapter().merge_merge_request(MergeRequestRef(7, 3))


async def test_closing_a_non_open_mr_is_not_mergeable() -> None:
    rec = Recorder(reply(200, {**MR, "state": "merged"}))
    with pytest.raises(NotMergeableError):
        await rec.adapter().close_merge_request(MergeRequestRef(7, 3))
    assert len(rec.requests) == 1


async def test_list_merge_requests_parameters() -> None:
    rec = Recorder(reply(200, [MR]))
    adapter = rec.adapter()
    await adapter.list_merge_requests(7, state=None, labels=("wingman", "day2"), limit=5)
    params = rec.requests[0].url.params
    assert (params["state"], params["labels"], params["order_by"]) == (
        "all",
        "wingman,day2",
        "created_at",
    )


async def test_error_text_survives_a_non_json_body() -> None:
    rec = Recorder(lambda _r: httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(AmbiguousWriteError, match="bad gateway"):
        await rec.adapter().approve_merge_request(MergeRequestRef(7, 3))


async def test_open_mr_diff_compares_branches_and_a_merged_one_uses_the_stored_diff() -> None:
    diff = {
        "old_path": "a.yaml",
        "new_path": "a.yaml",
        "new_file": False,
        "deleted_file": False,
        "renamed_file": False,
        "diff": "@@ -1 +1 @@\n-a\n+b\n",
    }
    rec = Recorder(
        reply(200, MR),
        reply(200, {"diffs": [diff]}),
        reply(200, {**MR, "state": "merged"}),
        reply(200, [diff]),
    )
    adapter = rec.adapter()
    ref = MergeRequestRef(7, 3)
    assert [str(d.new_path) for d in await adapter.merge_request_diff(ref)] == ["a.yaml"]
    assert [str(d.new_path) for d in await adapter.merge_request_diff(ref)] == ["a.yaml"]
    compare = rec.requests[1]
    assert compare.url.path == "/api/v4/projects/7/repository/compare"
    assert (compare.url.params["from"], compare.url.params["to"]) == ("main", "b")
    assert rec.requests[3].url.path == "/api/v4/projects/7/merge_requests/3/diffs"
